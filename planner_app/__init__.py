import os
from flask import Flask
from flask_session import Session as FlaskSession

# This is the directory WHERE THIS FILE LIVES (planner_app/)
APP_DIR = os.path.dirname(__file__)
# This is the project root (where app.py lives)
ROOT_DIR = os.path.dirname(APP_DIR)

app = Flask(
    __name__,
    # Look inside planner_app/templates and planner_app/static
    template_folder=os.path.join(APP_DIR, "templates"),
    static_folder=os.path.join(APP_DIR, "static")
)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(ROOT_DIR, "flask_session_data")

os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
FlaskSession(app)

from . import routes  # noqa: E402, F401