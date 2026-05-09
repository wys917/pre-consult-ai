import io
import os
import uuid

from dotenv import load_dotenv

from backend.app import create_app
from backend.app.domain.doctor_schedules import DOCTOR_SCHEDULES

load_dotenv()

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True, threaded=True)
