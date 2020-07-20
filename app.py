# -*- coding: utf-8 -*-
import argparse
import logging
import os
import uuid

from flask import Flask
from paste.translogger import TransLogger
from waitress import serve

from api import api_bp
from web import web_bp

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true', help='Enable debug messages.')
    args = parser.parse_args()

    port = int(os.environ.get('PORT', 8080))

    app = Flask(__name__, template_folder='src', static_folder='dist')
    app.config['APPLICATION_ROOT'] = os.environ.get('FLASK_APPLICATION_ROOT', '/')
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", str(uuid.uuid4()))
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(web_bp)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        app.debug = True
    else:
        logging.basicConfig(level=logging.INFO)
    serve(TransLogger(app), host='localhost', port=port)
