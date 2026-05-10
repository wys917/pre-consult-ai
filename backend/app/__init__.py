from flask import Flask

from backend.app.api.routes import bp as routes_bp
from backend.app.services.session_helpers import (
    build_assistant_reply,
    extract_patient_inputs,
    normalize_session_id,
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["NORMALIZE_SESSION_ID"] = normalize_session_id
    app.config["EXTRACT_PATIENT_INPUTS"] = extract_patient_inputs
    app.config["BUILD_ASSISTANT_REPLY"] = build_assistant_reply
    app.register_blueprint(routes_bp)
    return app
