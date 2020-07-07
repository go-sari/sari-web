# -*- coding: utf-8 -*-
import json
import logging
import os
import pkgutil
import re
import uuid
from typing import Dict, List, Optional, Tuple

import boto3
import botocore
from flask import Flask, render_template, request, session, url_for
from prodict import Prodict
from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT, entity
from saml2.client import Saml2Client
from saml2.config import Config as Saml2Config
from saml2.response import AuthnResponse, StatusResponse

# AWS Region used when the primary region is still unknown.
DEFAULT_AWS_REGION = "us-east-1"

# SARI Configuration parameters
SARI_PARAM_BH_HOSTNAME = "BH_HOSTNAME"
SARI_PARAM_BH_USERNAME = "BH_USERNAME"
SARI_PARAM_PULUMI_BACKEND_URL = "PULUMI_BACKEND_URL"
SARI_PARAM_PULUMI_STACK_NAME = "PULUMI_STACK_NAME"
SARI_PARAM_PRIMARY_AWS_REGION = "PRIMARY_AWS_REGION"

app = Flask(__name__)
app.config['APPLICATION_ROOT'] = os.environ.get('FLASK_APPLICATION_ROOT', '/')
app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))
logging.basicConfig(level=logging.DEBUG)

_aws_regions_descriptions = {}


@app.route("/saml/idp/<idp_name>", methods=['POST'])
def idp_initiated(idp_name):
    saml_client = saml_client_for(idp_name)
    saml_assertion = request.form['SAMLResponse']
    hack_disable_response_verify()
    authn_response = saml_client.parse_authn_request_response(
        saml_assertion,
        entity.BINDING_HTTP_POST)
    user_info = authn_response.get_subject()
    session["login"] = user_info.text

    aws_roles = saml_enum_aws_roles(authn_response)
    accounts = saml_enum_account_aliases(authn_response)

    if not aws_roles:
        raise ValueError("Invalid assertion: no roles defined")
    if len(aws_roles) == 1:
        account_id = next(iter(aws_roles))
    elif 'account_id' in request.form:
        account_id = request.form['account_id']
    else:
        return render_template('select_account.html', accounts=accounts, saml_assertion=saml_assertion,
                               session_timeout=authn_response.not_on_or_after)

    role_arn, principal_arn = aws_roles[account_id]

    client = boto3.client(
        'sts',
        aws_access_key_id='',
        aws_secret_access_key='',
        aws_session_token=''
    )

    response = client.assume_role_with_saml(
        RoleArn=role_arn,
        PrincipalArn=principal_arn,
        SAMLAssertion=saml_assertion,
        DurationSeconds=3600,
    )
    aws_credentials = response["Credentials"]
    session["aws_credentials"] = aws_credentials
    session["sari_config"] = get_sari_config(aws_credentials)

    account = dict(alias=accounts[account_id], id=account_id)
    return render_template('db_config.html', session=session, aws_account=account,
                           session_timeout=int(aws_credentials['Expiration'].timestamp()))


@app.route("/logout", methods=["POST"])
def logout():
    return do_farewell(header1="You are logged out!")


@app.route("/farewell", methods=["POST"])
def farewell():
    header1 = request.form["header1"]
    header2 = request.form.get("header2", "")
    emoji = request.form.get("emoji")
    return do_farewell(header1=header1, header2=header2, emoji=emoji)


# noinspection PyUnusedLocal
@app.errorhandler(404)
def error_not_found(error):
    return do_farewell(header1="Oops!", header2="The requested page was not found", emoji="sad")


@app.route("/api/databases")
def list_databases():
    """
    List all RDS instances enabled for the current user, grouped by region.
    """
    descriptions = load_regions_descriptions()
    return {name: dict(
        location=descriptions.get(name, name),
        instances=instances
    ) for name, instances in load_db_instances().items()}


@app.route("/api/db_config/<region>/<db_identifier>/<db_name>")
def get_db_configuration(region, db_identifier, db_name):
    """
    Generates all parameters required to access a given RDS instance.
    """
    rds = get_boto3_session(region_name=region).client("rds")
    # Retrieve the basic parameters
    db_instances = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)['DBInstances']
    db = Prodict.from_dict(db_instances[0])
    # Generate the ephemeral password
    login = session["login"]
    token = rds.generate_db_auth_token(DBHostname=db.Endpoint.Address, Port=db.Endpoint.Port, DBUsername=login)
    config = session["sari_config"]
    return {
        # The key names MUST match the IDs of the form INPUT tag
        "bh_hostname": config[SARI_PARAM_BH_HOSTNAME],
        "bh_username": config[SARI_PARAM_BH_USERNAME],
        "rds_hostname": db.Endpoint.Address,
        "rds_port": db.Endpoint.Port,
        "rds_username": login,
        "rds_password": token,
        "db_name": db_name,
    }


def do_farewell(header1, header2=None, emoji=None):
    session["aws_credentials"] = {}
    session["sari_config"] = {}

    return render_template('farewell.html',
                           header1=header1,
                           header2=(header2 or ""),
                           emoji_url=url_for('static', filename=f'assets/{emoji or "see-ya"}.png'))


def saml_client_for(idp_name=None):
    """
    Given the name of an IdP, return a configuration.
    The configuration is a hash for use by saml2.config.Config
    """

    acs_url = url_for(
        "idp_initiated",
        idp_name=idp_name,
        _external=True)
    https_acs_url = url_for(
        "idp_initiated",
        idp_name=idp_name,
        _external=True,
        _scheme='https')

    settings = {
        'entityid': 'urn:amazon:webservices',
        'service': {
            'sp': {
                'endpoints': {
                    'assertion_consumer_service': [
                        (acs_url, BINDING_HTTP_REDIRECT),
                        (acs_url, BINDING_HTTP_POST),
                        (https_acs_url, BINDING_HTTP_REDIRECT),
                        (https_acs_url, BINDING_HTTP_POST)
                    ],
                },
                # Don't verify that the incoming requests originate from us via
                # the built-in cache for authn request ids in pysaml2
                'allow_unsolicited': True,
                # Don't sign authn requests, since signed requests only make
                # sense in a situation where you control both the SP and IdP
                'authn_requests_signed': False,
                'logout_requests_signed': True,
                'want_assertions_signed': True,
                'want_response_signed': False,
            },
        },
        # Although SAML response verification is disabled, pysaml2 still looks up for xmlsec1 binary.
        # See discussion at https://github.com/Miserlou/Zappa/issues/1374
        "xmlsec_binary": "/bin/echo",
    }
    config = Saml2Config()
    config.load(settings)
    config.allow_unknown_attributes = True
    return Saml2Client(config=config)


def get_sari_config(aws_credentials):
    """
    Retrieve the SARI configuration stored as tags of to the IAM Role.
    """
    client = get_boto3_session(aws_credentials).client("iam")
    # list_role_tags() reference:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/iam.html#IAM.Client.list_role_tags
    response = client.list_role_tags(RoleName="SARI")
    sari_config = {}
    for tag in response["Tags"]:
        key: str = tag["Key"]
        value = tag["Value"]
        if key.startswith("sari:"):
            key = key[5:].upper()
            sari_config[key] = value
    return sari_config


def load_db_instances() -> Dict[str, List[str]]:
    sari_config = session["sari_config"]

    pulumi_backend_bucket = s3_bucket_name_from_url(sari_config[SARI_PARAM_PULUMI_BACKEND_URL])
    pulumi_stack_name = sari_config[SARI_PARAM_PULUMI_STACK_NAME]
    primary_region = sari_config[SARI_PARAM_PRIMARY_AWS_REGION]

    login = session["login"]
    stack_file = f".pulumi/stacks/{pulumi_stack_name}.json"
    contents = s3_read_text(get_boto3_session(), pulumi_backend_bucket, stack_file)
    return filter_allowed_instances(contents, primary_region, login, pulumi_stack_name)


def filter_allowed_instances(contents, default_region, login, pulumi_stack_name) -> Dict[str, List[str]]:
    """
    Select all MySQL User resources for the given user.

    :param contents: The JSON contents of the Pulumi Stack file.
    :param default_region: The default AWS region.
    :param login: The user login (email).
    :param pulumi_stack_name: The name of the Pulumi stack.

    :return: A dictionary that associates the AWS regions found to a list with their corresponding RDS instances
    identifiers.
    """
    databases = {}
    # urn:pulumi:<STACK_NAME>::sari::mysql:index/grant:Grant::(<REGION>/)?<DB_ID>/(.<DB_NAME>)?/<LOGIN>
    grant_pattern = re.compile(f"urn:pulumi:{pulumi_stack_name}::sari::mysql:index/grant:Grant::"
                               "(?:(?P<region>[a-z0-9-]+)/)?"
                               "(?P<db_id>[a-z0-9-]+)"
                               r"(\.(?P<db_name>[a-z0-9_-]+))?"
                               f"/{login}")
    for res in json.loads(contents)["checkpoint"]["latest"]["resources"]:
        urn = res["urn"]
        if match := grant_pattern.match(urn):
            region = match.group("region") or default_region
            db_id = match.group("db_id")
            db_name = res["inputs"]["database"]
            databases.setdefault(region, {}).setdefault(db_id, []).append(db_name)
    return databases


def get_aws_account_from_arn(arn):
    # Reference:
    # https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html#arns-syntax
    return arn.split(":")[4]


def get_boto3_session(aws_credentials: Optional[Dict[str, str]] = None,
                      region_name: str = None) -> boto3.session.Session:
    if not aws_credentials:
        aws_credentials = session["aws_credentials"]
    if not region_name:
        region_name = session.get("sari_config", {}).get(SARI_PARAM_PRIMARY_AWS_REGION, DEFAULT_AWS_REGION)
    return boto3.session.Session(
        aws_access_key_id=aws_credentials["AccessKeyId"],
        aws_secret_access_key=aws_credentials["SecretAccessKey"],
        aws_session_token=aws_credentials["SessionToken"],
        region_name=region_name
    )


def s3_bucket_name_from_url(url: str) -> str:
    scheme = "s3://"
    if not url.startswith(scheme):
        raise ValueError(f"Backend URL should start with {scheme}")
    return url[len(scheme):]


def s3_read_text(boto3_session: boto3.session.Session, bucket: str, key: str) -> str:
    """
    Reads the contents of a S3 bucket/key.
    """
    s3 = boto3_session.resource("s3")
    obj = s3.Object(bucket_name=bucket, key=key)
    return obj.get()["Body"].read()


def saml_enum_aws_roles(auth_response: AuthnResponse) -> Dict[str, Tuple[str, str]]:
    """
    Return the Role/Principal pairs defined as an attribute of the SAML assertion.

    :return: a dictionary that maps an AWS account to a pair RoleARN/PrincipalARN.
    """

    def group_by_account(role_arn, provider_arn) -> Tuple[str, Tuple[str, str]]:
        acc1 = get_aws_account_from_arn(role_arn)
        acc2 = get_aws_account_from_arn(provider_arn)
        if acc1 != acc2:
            raise ValueError(f"Account mismatch: ${acc1} != ${acc2}")
        return acc1, (role_arn, provider_arn)

    # See
    # https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_saml_assertions.html#saml_role-attribute
    return dict([group_by_account(*pair.split(","))
                 for pair in auth_response.get_identity()["https://aws.amazon.com/SAML/Attributes/Role"]])


def saml_enum_account_aliases(auth_response: AuthnResponse) -> Dict[str, str]:
    """
    Return the mapping between AWS Account IDs and their aliases.
    """
    return dict(pair.split(",")
                for pair in auth_response.get_identity()["https://github.com/eliezio/sari/AccountAlias"])


_patched = False


def hack_disable_response_verify():
    def new_getattribute(this, name):
        if name == 'do_not_verify':
            return True
        else:
            return object.__getattribute__(this, name)

    global _patched
    if not _patched:
        StatusResponse.__getattribute__ = new_getattribute
        _patched = True


def load_regions_descriptions() -> Dict[str, str]:
    global _aws_regions_descriptions
    if not _aws_regions_descriptions:
        data = pkgutil.get_data(botocore.__name__, "data/endpoints.json")
        json.loads(data.decode())
        regions = json.loads(data.decode())["partitions"][0]["regions"]
        _aws_regions_descriptions = {name: region["description"] for name, region in regions.items()}
    return _aws_regions_descriptions


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    if port == 8080:
        app.debug = True
    app.run(host='localhost', port=port)
