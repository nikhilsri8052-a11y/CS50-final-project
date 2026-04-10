import os
import subprocess
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from flask import url_for
from datetime import datetime, date

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

db = SQL("sqlite:///database.db")
db.execute("PRAGMA foreign_keys = ON")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/")
def intro():
    if 'user_id' not in session:
        return render_template("intro_page.html")
    return redirect("/home")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not username or not password or not confirm:
            flash("Invalid Username or password", "danger")
            return redirect("/register")
        if password != confirm:
            flash("Password and Confirm password don't match", "danger")
            return redirect("/register")
        hash = generate_password_hash(password)
        try:
            db.execute("INSERT INTO users (username, hash) VALUES(?,?)", username, hash)
            flash("Registration successful!", "success")
            return redirect("/login")
        except:
            flash("Username already taken", "danger")
            return redirect("/register")
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        session.clear()
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Invalid username or password", "danger")
            return redirect("/login")
        try:
            row = db.execute("SELECT id, username, hash FROM users WHERE username=(?)", username)
        except:
            flash("Invalid username or password", "danger")
            return redirect("/login")
        if len(row) != 1 or not check_password_hash(row[0]["hash"], password):
            flash("Invalid username or password", "danger")
            return redirect("/login")
        session["user_id"] = row[0]["id"]

        # Streak logic
        current_data = db.execute("SELECT streak, last_login_date FROM users WHERE id = ?", row[0]["id"])
        streak = current_data[0]["streak"]
        last_login_str = current_data[0]["last_login_date"]
        today = date.today()

        if last_login_str:
            last_login_date = datetime.strptime(last_login_str, "%Y-%m-%d").date()
            delta = (today - last_login_date).days
            if delta == 1:
                streak += 1
            elif delta > 1:
                streak = 1
        else:
            streak = 1

        db.execute("UPDATE users SET streak = ?, last_login_date = ? WHERE id = ?", streak, str(today), row[0]["id"])
        return redirect("/home")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect("/")

@app.route("/home")
@login_required
def home():
    uid = session['user_id']

    rows = db.execute("SELECT streak FROM users WHERE id = ?", uid)
    streak = rows[0]["streak"] if rows else 0

    target = db.execute("SELECT * FROM target WHERE uid = ?", uid)
    if not target:
        return redirect("/setup")

    exam_date_str = target[0]["examdate"]
    exam_date = datetime.strptime(exam_date_str, "%Y-%m-%d").date()

    todo_data = db.execute("""
        SELECT topics.id, topics.tname, subjects.difficulty
        FROM topics
        JOIN subjects ON topics.sid = subjects.id
        WHERE subjects.uid = ? AND topics.completed = 0
    """, uid)

    if not todo_data:
        return render_template("home.html", tasks=[], plan=[], streak=streak,
                               target_date=exam_date_str, all_done=True)

    days_left = (exam_date - date.today()).days
    if days_left <= 0:
        days_left = 1

    input_str = "|".join([f"{t['tname']},{t['difficulty']}" for t in todo_data])

    # 6. Call C planner — binary is in engine/ subfolder
    plan_names = []
    try:
        result = subprocess.run(
            ['./engine/planner', str(days_left), str(target[0]["hours_commit"]), input_str],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            plan_names = [name.strip() for name in result.stdout.strip().split(',')]
    except Exception as e:
        flash(f"Planner engine error: {e}", "warning")

    # 7. FIX: Filter todo_data to only today's planned topics (matched by name)
    plan_set = set(plan_names)
    todays_tasks = [t for t in todo_data if t['tname'] in plan_set]

    # Fallback: if C returned nothing usable, show first topic
    if not todays_tasks and todo_data:
        todays_tasks = [todo_data[0]]

    return render_template("home.html", tasks=todays_tasks, streak=streak,
                           target_date=exam_date_str, all_done=False)

@app.route("/complete", methods=["POST"])
@login_required
def complete():
    topic_id = request.form.get("topic_id")
    if not topic_id:
        return redirect("/home")
    # Security: only mark current user's topics
    db.execute("""
        UPDATE topics SET completed = 1
        WHERE id = ? AND sid IN (
            SELECT id FROM subjects WHERE uid = ?
        )
    """, topic_id, session["user_id"])
    return redirect("/home")

@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    if request.method == "POST":
        uid = session['user_id']
        exam_date = request.form.get('exam_date')
        daily_hours = request.form.get('hours')

        if not exam_date or not daily_hours:
            flash("Please provide exam date and daily commitment hours", "danger")
            return redirect("/setup")

        # Validate exam date is in the future
        try:
            exam_dt = datetime.strptime(exam_date, "%Y-%m-%d").date()
            if exam_dt <= date.today():
                flash("Exam date must be in the future", "danger")
                return redirect("/setup")
        except ValueError:
            flash("Invalid exam date format", "danger")
            return redirect("/setup")

        try:
            db.execute("DELETE FROM target WHERE uid = ?", uid)
            db.execute("DELETE FROM subjects WHERE uid = ?", uid)
        except Exception:
            flash("Error clearing previous plan data", "danger")
            return redirect("/setup")

        try:
            db.execute("INSERT INTO target (uid, examdate, hours_commit) VALUES(?,?,?)", uid, exam_date, daily_hours)
        except Exception:
            flash("Error saving target goals", "danger")
            return redirect("/setup")

        subjects_added = 0
        i = 0
        while True:
            sname = request.form.get(f'subjects[{i}][name]')
            if sname is None:
                break

            if not sname.strip():
                i += 1
                continue

            difficulty = request.form.get(f"subjects[{i}][difficulty]", 5)

            try:
                sid = db.execute("INSERT INTO subjects (uid, sname, difficulty) VALUES (?,?,?)",
                                 uid, sname.strip(), difficulty)
                topics = request.form.getlist(f"subjects[{i}][topics][]")
                topics_added = 0
                for topic in topics:
                    if topic and topic.strip():
                        db.execute("INSERT INTO topics (sid, tname) VALUES (?,?)", sid, topic.strip())
                        topics_added += 1

                if topics_added > 0:
                    subjects_added += 1

            except Exception as e:
                flash(f"Error processing subject: {sname}", "danger")
                return redirect("/setup")

            i += 1

        if subjects_added == 0:
            flash("Please add at least one subject with topics", "warning")
            return redirect("/setup")

        flash("Study plan saved! Here's today's schedule.", "success")
        return redirect("/home")

    rows = db.execute("SELECT streak FROM users WHERE id = ?", session['user_id'])
    streak = rows[0]["streak"] if rows else 0
    return render_template("setup.html", streak=streak)

if __name__ == "__main__":
    app.run()
