import os
from flask import Flask
from flask_session import Session as FlaskSession

# This is where the code is running from
CURRENT_DIR = os.path.dirname(__file__)
# This is the root folder where app.py lives
ROOT_DIR = os.path.dirname(CURRENT_DIR)

app = Flask(
    __name__,
    # Tell Flask templates are inside planner_app/templates
    template_folder=os.path.join(CURRENT_DIR, "templates"),
    # Tell Flask static files are inside planner_app/static
    static_folder=os.path.join(CURRENT_DIR, "static")
)

app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(ROOT_DIR, "flask_session_data")

os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
FlaskSession(app)

from . import routes