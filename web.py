from flask import Blueprint, session, render_template, url_for, request
from saml2 import entity

from common import (
    SariConfig,
    get_boto3_session,
    saml_client_for,
    saml_disable_response_verify,
    saml_enum_account_aliases,
    saml_enum_aws_roles,
    sts_assume_role_with_saml,
)

web_bp = Blueprint('web_bp', __name__)


@web_bp.route("/saml/idp/<idp_name>", methods=['POST'])
def idp_initiated(idp_name):
    acs_url = url_for("web_bp.idp_initiated", idp_name=idp_name, _external=True)
    saml_client = saml_client_for(acs_url)
    saml_assertion = request.form['SAMLResponse']
    saml_disable_response_verify()
    authn_response = saml_client.parse_authn_request_response(saml_assertion, entity.BINDING_HTTP_POST)
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
        return render_template('select_account/page.html', accounts=accounts, saml_assertion=saml_assertion,
                               session_timeout=authn_response.not_on_or_after)

    role_arn, principal_arn = aws_roles[account_id]
    aws_credentials = sts_assume_role_with_saml(role_arn, principal_arn, saml_assertion)

    session["aws_credentials"] = aws_credentials
    session["sari_config"] = SariConfig.from_aws(get_boto3_session(aws_credentials)).to_json()

    account = dict(alias=accounts[account_id], id=account_id)
    return render_template('db_config/page.html', session=session, aws_account=account,
                           session_timeout=int(aws_credentials['Expiration'].timestamp()))


@web_bp.route("/logout", methods=["POST"])
def logout():
    return do_farewell(header1="You are logged out!")


# noinspection PyUnusedLocal
@web_bp.errorhandler(404)
def error_not_found(error):
    return do_farewell(header1="Oops!", header2="The requested page was not found", emoji="sad")


def do_farewell(header1, header2=None, emoji=None):
    session["aws_credentials"] = {}
    session["sari_config"] = {}

    return render_template('farewell.html',
                           header1=header1,
                           header2=(header2 or ""),
                           emoji_url=url_for('static', filename=f'images/{emoji or "see-ya"}.png'))
