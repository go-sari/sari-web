import json
import pkgutil
from typing import Any, Dict, Tuple

import boto3
import botocore
from prodict import Prodict

# AWS Region used when the primary region is still unknown.
DEFAULT_AWS_REGION = "us-east-1"

S3_SCHEME = "s3://"

_aws_regions_descriptions = {}


def get_aws_account_from_arn(arn):
    # Reference:
    # https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html#arns-syntax
    return arn.split(":")[4]


def sts_assume_role_with_saml(role_arn: str, principal_arn: str, saml_assertion: str) -> Dict[str, Any]:
    sts = boto3.client(
        'sts',
        aws_access_key_id='',
        aws_secret_access_key='',
        aws_session_token=''
    )

    response = sts.assume_role_with_saml(
        RoleArn=role_arn,
        PrincipalArn=principal_arn,
        SAMLAssertion=saml_assertion,
        DurationSeconds=3600,
    )
    return response["Credentials"]


def get_boto3_session(aws_credentials: Dict[str, str],
                      region_name: str = DEFAULT_AWS_REGION) -> boto3.session.Session:
    return boto3.session.Session(
        aws_access_key_id=aws_credentials["AccessKeyId"],
        aws_secret_access_key=aws_credentials["SecretAccessKey"],
        aws_session_token=aws_credentials["SessionToken"],
        region_name=region_name
    )


def aws_regions_load_descriptions() -> Dict[str, str]:
    global _aws_regions_descriptions
    if not _aws_regions_descriptions:
        data = pkgutil.get_data(botocore.__name__, "data/endpoints.json")
        json.loads(data.decode())
        regions = json.loads(data.decode())["partitions"][0]["regions"]
        _aws_regions_descriptions = {name: region["description"] for name, region in regions.items()}
    return _aws_regions_descriptions


def s3_bucket_name_from_url(url: str) -> str:
    if not url.startswith(S3_SCHEME):
        raise ValueError(f"URL should start with {S3_SCHEME}")
    return url[len(S3_SCHEME):]


def s3_read_text(s3: Any, bucket: str, key: str) -> str:
    """
    Reads the contents of a S3 bucket/key.
    """
    obj = s3.Object(bucket_name=bucket, key=key)
    return obj.get()["Body"].read()


def rds_get_db_connection_parameters(boto3_session: boto3.session.Session, db_identifier, username) \
        -> Tuple[Prodict, str]:
    rds = boto3_session.client("rds")
    # Retrieve the basic parameters
    db_instances = rds.describe_db_instances(DBInstanceIdentifier=db_identifier)['DBInstances']
    db = Prodict.from_dict(db_instances[0])
    # Generate the ephemeral password
    password = rds.generate_db_auth_token(DBHostname=db.Endpoint.Address,
                                          Port=db.Endpoint.Port,
                                          DBUsername=username)
    return db, password
