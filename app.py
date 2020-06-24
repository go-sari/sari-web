# -*- coding: utf-8 -*-
import json
import logging
import os
import re
import uuid
from typing import Dict, List, Optional, Tuple

import boto3
from flask import Flask, render_template, request, session, url_for
from flask_bootstrap import Bootstrap
from prodict import Prodict
from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT, entity
from saml2.client import Saml2Client
from saml2.config import Config as Saml2Config
from saml2.response import AuthnResponse, StatusResponse

# AWS Region used when the primary region is still unknown.
DEFAULT_AWS_REGION = "us-east-1"

# SARI Configuration parameters
SARI_PARAM_PULUMI_BACKEND_URL = "PULUMI_BACKEND_URL"
SARI_PARAM_PULUMI_STACK_NAME = "PULUMI_STACK_NAME"
SARI_PARAM_PRIMARY_AWS_REGION = "PRIMARY_AWS_REGION"

app = Flask(__name__)
app.config['sso_url'] = os.environ['SSO_URL']
Bootstrap(app)
app.secret_key = str(uuid.uuid4())
logging.basicConfig(level=logging.DEBUG)


@app.route("/saml/idp/<idp_name>", methods=['POST'])
def idp_initiated(idp_name):
    saml_client = saml_client_for(idp_name)
    saml_assertion = request.form['SAMLResponse']
    authn_response = saml_client.parse_authn_request_response(
        saml_assertion,
        entity.BINDING_HTTP_POST)
    user_info = authn_response.get_subject()
    session["login"] = user_info.text

    aws_roles = saml_enum_aws_roles(authn_response)
    # TODO: support multiple roles. Redirect to page allowing user to pick which Role he/she wants to use
    role_arn, principal_arn = aws_roles[0]

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

    return render_template('db_config.html', session=session)


# noinspection PyUnusedLocal
@app.errorhandler(404)
def error_not_found(error):
    return render_template('not_found.html')


@app.route("/v1/databases")
def list_databases():
    """
    List all RDS instances enabled for the current user, grouped by region.
    """
    return load_db_instances()


@app.route("/v1/db_config/<region>/<db_identifier>")
def get_db_configuration(region, db_identifier):
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
    return {
        # The key names MUST match the IDs of the form INPUT tag
        "rds_hostname": db.Endpoint.Address,
        "rds_port": db.Endpoint.Port,
        "rds_username": login,
        "rds_password": token,
        "db_name": db.DBName,
    }


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
    urn_pattern = re.compile(f"urn:pulumi:{pulumi_stack_name}::sari::mysql:index/user:User::"
                             f"(?:(?P<region>[a-z0-9-]+)/)?(?P<db_id>[a-z0-9-]+)/{login}")
    for res in json.loads(contents)["checkpoint"]["latest"]["resources"]:
        urn = res["urn"]
        match = urn_pattern.match(urn)
        if match:
            region = match.group("region") or default_region
            db_id = match.group("db_id")
            databases.setdefault(region, []).append(db_id)
    return databases


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


def saml_enum_aws_roles(auth_response: AuthnResponse) -> List[Tuple[str, str]]:
    # See
    # https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_saml_assertions.html#saml_role-attribute
    return [pair.split(",") for pair in auth_response.get_identity()["https://aws.amazon.com/SAML/Attributes/Role"]]


def force_attribute_value(cls, attr_name, value):
    def new_getattribute(this, name):
        if name == attr_name:
            return value
        else:
            return object.__getattribute__(this, name)

    cls.__getattribute__ = new_getattribute


if __name__ == "__main__":
    force_attribute_value(StatusResponse, "do_not_verify", True)
    port = int(os.environ.get('PORT', 8080))
    if port == 8080:
        app.debug = True
    app.run(host='localhost', port=port)
