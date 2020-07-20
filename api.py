from flask import Blueprint, session

from common import (
    SariConfig,
    aws_regions_load_descriptions,
    get_boto3_session,
    aws_get_enabled_db_instances, rds_get_db_connection_parameters,
)

api_bp = Blueprint('api_bp', __name__)


@api_bp.route("/databases")
def list_databases():
    """
    List all RDS instances enabled for the current user, grouped by region.
    """
    aws_credentials = session["aws_credentials"]
    sari_config = SariConfig.from_json(session["sari_config"])
    login = session["login"]

    boto3_session = get_boto3_session(aws_credentials, sari_config.primary_aws_region)
    instances_per_region = aws_get_enabled_db_instances(boto3_session, sari_config, login)

    # Supplement instances information with region description
    descriptions = aws_regions_load_descriptions()
    return {name: dict(
        location=descriptions.get(name, name),
        instances=instances
    ) for name, instances in instances_per_region.items()}


@api_bp.route("/db_config/<region>/<db_identifier>/<db_name>")
def get_db_configuration(region, db_identifier, db_name):
    """
    Generates all parameters required to access a given RDS instance.
    """
    aws_credentials = session["aws_credentials"]
    sari_config = SariConfig.from_json(session["sari_config"])
    login = session["login"]

    boto3_session = get_boto3_session(aws_credentials, region)
    db, password = rds_get_db_connection_parameters(boto3_session, db_identifier, login)
    return {
        # The key names MUST match the IDs of the form INPUT tag
        "bh_hostname": sari_config.bh_hostname,
        "bh_username": sari_config.bh_username,
        "rds_hostname": db.Endpoint.Address,
        "rds_port": db.Endpoint.Port,
        "rds_username": login,
        "rds_password": password,
        "db_name": db_name,
    }

