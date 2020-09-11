# -*- coding: utf-8 -*-
import argparse
import logging
import os

import awsgi
from flask import Flask
from paste.translogger import TransLogger
from waitress import serve

from api import api_bp
from web import web_bp

app = Flask(__name__, template_folder='src', static_folder='dist')
app.secret_key = os.environ["FLASK_SECRET_KEY"]
app.register_blueprint(api_bp, url_prefix="/api")
app.register_blueprint(web_bp)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info("Event: {}".format(event))
    return awsgi.response(app, event, context, base64_content_types={
        "image/png",
        "image/x-icon",
        # Inside the Lambda container Flask uses an alternative content type for "favicon.ico"
        "image/vnd.microsoft.icon",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Enable debug messages.')
    args = parser.parse_args()

    port = int(os.environ.get('PORT', 8080))

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        app.debug = True
    serve(TransLogger(app), host='localhost', port=port)
