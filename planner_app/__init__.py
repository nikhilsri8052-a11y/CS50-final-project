import os
from flask import Flask
from flask_session import Session as FlaskSession

# 1. Get the absolute path to the 'planner_app' folder
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Get the absolute path to the PROJECT ROOT (where app.py lives)
ROOT_DIR = os.path.dirname(CURRENT_DIR)

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_folder=os.path.join(ROOT_DIR, "static")
)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

# Store session data in the root project folder
app.config["SESSION_FILE_DIR"] = os.path.join(ROOT_DIR, "flask_session_data")

os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
FlaskSession(app)

from . import routes