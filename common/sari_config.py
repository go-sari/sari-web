import json

import boto3.session

SARI_ROLE_NAME = "SARI"


class SariConfig:
    def __init__(self, bh_hostname, bh_username, pulumi_backend_url, pulumi_stack_name, primary_aws_region):
        self.bh_hostname = bh_hostname
        self.bh_username = bh_username
        self.pulumi_backend_url = pulumi_backend_url
        self.pulumi_stack_name = pulumi_stack_name
        self.primary_aws_region = primary_aws_region

    def to_json(self):
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, json_str):
        return SariConfig(**json.loads(json_str))

    @classmethod
    def from_aws(cls, boto3_session: boto3.session.Session):
        """
        Retrieve the SARI configuration stored as tags of to the IAM Role.
        """
        iam = boto3_session.client("iam")
        # list_role_tags() reference:
        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/iam.html#IAM.Client.list_role_tags
        response = iam.list_role_tags(RoleName=SARI_ROLE_NAME)
        prefix = "sari:"
        settings = dict(
            [(tag["Key"][len(prefix):], tag["Value"]) for tag in response["Tags"]
             if tag["Key"].startswith(prefix)]
        )
        return SariConfig(**settings)
