import io
import os
import uuid
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from flask import Flask

from backend.app.api.routes import bp as routes_bp
from backend.app.domain.doctor_schedules import DOCTOR_SCHEDULES
from backend.app.services.session_helpers import (
    build_assistant_reply,
    extract_patient_inputs,
    normalize_session_id,
)

load_dotenv()

app = Flask(__name__)


app.config["NORMALIZE_SESSION_ID"] = normalize_session_id
app.config["EXTRACT_PATIENT_INPUTS"] = extract_patient_inputs
app.config["BUILD_ASSISTANT_REPLY"] = build_assistant_reply
app.register_blueprint(routes_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, threaded=True)
