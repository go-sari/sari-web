import json
import re
from typing import Dict, List

import boto3.session

from .sari_config import SariConfig
from .aws import s3_bucket_name_from_url, s3_read_text


def aws_get_enabled_db_instances(boto3_session: boto3.session.Session,
                                 sari_config: SariConfig,
                                 login: str) -> Dict[str, List[str]]:
    pulumi_state = load_pulumi_state(boto3_session, sari_config)
    return filter_allowed_instances(pulumi_state, sari_config.primary_aws_region, login, sari_config.pulumi_stack_name)


def aws_list_managed_db_instances(boto3_session: boto3.session.Session,
                                  sari_config: SariConfig) -> Dict[str, List[str]]:
    pulumi_state = load_pulumi_state(boto3_session, sari_config)
    return filter_managed_instances(pulumi_state)


def load_pulumi_state(boto3_session: boto3.session.Session, sari_config: SariConfig):
    pulumi_backend_bucket = s3_bucket_name_from_url(sari_config.pulumi_backend_url)
    stack_file = f".pulumi/stacks/{sari_config.pulumi_stack_name}.json"
    s3 = boto3_session.resource("s3")
    return json.loads(s3_read_text(s3, pulumi_backend_bucket, stack_file))


def filter_allowed_instances(pulumi_state, default_region, login, pulumi_stack_name) -> Dict[str, List[str]]:
    """
    Select all MySQL User resources for the given user.

    :param pulumi_state: The Pulumi Stack state.
    :param default_region: The default AWS region.
    :param login: The user login (email).
    :param pulumi_stack_name: The name of the Pulumi stack.

    :return: A dictionary that associates the AWS regions found to a list with their corresponding RDS instances
    identifiers.
    """
    databases = dict()
    # urn:pulumi:<STACK_NAME>::sari::mysql:index/grant:Grant::(<REGION>/)?<DB_ID>(.<DB_NAME>)?/<LOGIN>
    grant_pattern = re.compile(f"urn:pulumi:{pulumi_stack_name}::sari::mysql:index/grant:Grant::"
                               "(?:(?P<region>[a-z0-9-]+)/)?"
                               "(?P<db_id>[a-z0-9-]+)"
                               r"(\.(?P<db_name>[a-z0-9_-]+))?"
                               f"/{login}")
    for res in pulumi_state["checkpoint"]["latest"]["resources"]:
        urn = res["urn"]
        if match := grant_pattern.match(urn):
            region = match.group("region") or default_region
            db_id = match.group("db_id")
            db_name = res["inputs"]["database"]
            databases.setdefault(region, {}).setdefault(db_id, []).append(db_name)
    return databases


def filter_managed_instances(pulumi_state) -> Dict[str, List[str]]:
    databases = dict()
    # Endpoint example:
    # blackwells.c36k3kl10p4v.eu-west-1.rds.amazonaws.com:3306
    endpoint_pattern = re.compile(r"(?P<name>[a-z0-9-]+)"
                                  r"\.[a-z0-9-]+"
                                  r"\.(?P<region>[a-z0-9-]+)"
                                  r"\.rds\.amazonaws\.com:[0-9]+")
    for res in pulumi_state["checkpoint"]["latest"]["resources"]:
        if res["type"] == "pulumi:providers:mysql":
            if match := endpoint_pattern.match(res["inputs"]["endpoint"]):
                name = match.group("name")
                region = match.group("region")
                databases.setdefault(region, []).append(name)
    return databases
