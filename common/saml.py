from typing import Dict, Tuple
from urllib.parse import urlparse, urlunparse

from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
from saml2.client import Saml2Client
from saml2.config import Config as Saml2Config
from saml2.response import AuthnResponse, StatusResponse

from .aws import get_aws_account_from_arn

_drv_patched = False


def saml_client_for(endpoint):
    """
    Given the endpoint URL, return a configuration.
    The configuration is a hash for use by saml2.config.Config
    """

    parts = urlparse(endpoint)
    # noinspection PyProtectedMember
    http_acs_url = urlunparse(parts._replace(scheme="http"))
    # noinspection PyProtectedMember
    https_acs_url = urlunparse(parts._replace(scheme="https"))

    settings = {
        'entityid': 'urn:amazon:webservices',
        'service': {
            'sp': {
                'endpoints': {
                    'assertion_consumer_service': [
                        (http_acs_url, BINDING_HTTP_REDIRECT),
                        (http_acs_url, BINDING_HTTP_POST),
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


def saml_enum_aws_roles(auth_response: AuthnResponse) -> Dict[str, Tuple[str, str]]:
    """
    Return the Role/Principal pairs defined stored as a pair of attributes in the SAML assertion.

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


def saml_disable_response_verify():
    def new_getattribute(this, name):
        if name == 'do_not_verify':
            return True
        else:
            return object.__getattribute__(this, name)

    global _drv_patched
    if not _drv_patched:
        StatusResponse.__getattribute__ = new_getattribute
        _drv_patched = True
