import os
import subprocess
from datetime import datetime, date, timedelta, timezone

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

from . import app, ROOT_DIR
from .models import Session, Subject, Target, Topic, User, engine


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


def get_streak(uid):
    with Session(engine) as db:
        user = db.get(User, uid)
        return user.streak if user and user.streak is not None else 0


def get_user_today():
    """Return the user's local date using browser-reported timezone offset when available."""
    offset_minutes = session.get("timezone_offset", session.get("tz_offset_minutes", 0))

    if isinstance(offset_minutes, (int, float, str)):
        try:
            minutes = int(offset_minutes)
            if -840 <= minutes <= 840:
                return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).date()
        except (TypeError, ValueError):
            pass

    return datetime.now(timezone.utc).date()


@app.route("/api/client-timezone", methods=["POST"])
def set_client_timezone():
    payload = request.get_json(silent=True) or request.form
    offset = payload.get("offset") if payload is not None else None

    try:
        offset = int(offset)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid timezone offset"}), 400

    if offset < -840 or offset > 840:
        return jsonify({"ok": False, "error": "Timezone offset out of range"}), 400

    session["timezone_offset"] = offset
    session["tz_offset_minutes"] = offset
    return '', 204


def _ensure_planner_executable(path):
    if os.name != "nt" and os.path.exists(path) and not os.access(path, os.X_OK):
        try:
            os.chmod(path, os.stat(path).st_mode | 0o111)
        except OSError:
            pass


def clear_user_plan(uid, db):
    # Bulk ORM deletes bypass SQLAlchemy cascade, and SQLite's ON DELETE CASCADE
    # only fires when PRAGMA foreign_keys=ON is active for that connection.
    # To be safe across all DB backends, delete in explicit dependency order:
    # Topics → Subjects → Target.

    # 1. Delete all topics belonging to this user's subjects
    subject_ids = [
        sid for (sid,) in db.query(Subject.id).filter_by(uid=uid).all()
    ]
    if subject_ids:
        db.query(Topic).filter(Topic.sid.in_(subject_ids)).delete(
            synchronize_session=False
        )

    # 2. Delete all subjects
    db.query(Subject).filter_by(uid=uid).delete(synchronize_session=False)

    # 3. Delete target
    db.query(Target).filter_by(uid=uid).delete(synchronize_session=False)


def reset_topic_plans(uid, db):
    # Query.update() cannot be combined with .join() in SQLAlchemy legacy API.
    # Fetch IDs first, then update by ID.
    incomplete_ids = [
        tid for (tid,) in
        db.query(Topic.id)
        .join(Subject)
        .filter(Subject.uid == uid, Topic.completed.is_(False))
        .all()
    ]
    if incomplete_ids:
        db.query(Topic).filter(Topic.id.in_(incomplete_ids)).update(
            {Topic.planned_date: None, Topic.planned_hours: None},
            synchronize_session=False
        )
def _plan_topics_with_python(todo_rows, days_left, hours):
    """Fallback planner when native engine is unavailable."""
    if not todo_rows:
        return [], {}

    days_left = max(1, int(days_left))
    hours = max(0.5, float(hours))

    sorted_rows = sorted(todo_rows, key=lambda row: row[1], reverse=True)
    topics_per_day = max(1, (len(sorted_rows) + days_left - 1) // days_left)
    todays_rows = sorted_rows[:topics_per_day]

    total_difficulty = sum(max(1, int(difficulty)) for _, difficulty in todays_rows) or 1

    plan_ids = []
    task_hours = {}
    for topic, difficulty in todays_rows:
        plan_ids.append(topic.id)
        topic_hours = (max(1, int(difficulty)) / total_difficulty) * hours
        task_hours[topic.id] = round(max(0.5, topic_hours), 1)

    return plan_ids, task_hours


@app.route("/start_fresh")
@login_required
def start_fresh():
    uid = session["user_id"]
    with Session(engine) as db:
        clear_user_plan(uid, db)
        db.commit()

    flash("Your current plan has been cleared. Create a new setup plan.", "info")
    return redirect("/setup?fresh=1")


@app.route("/")
def intro():
    if "user_id" in session:
        return redirect("/home")
    with Session(engine) as db:
        recent_logins = (
            db.query(User.username, User.streak, User.last_login_date)
            .filter(User.last_login_date.isnot(None))
            .order_by(User.last_login_date.desc(), User.id.desc())
            .limit(10)
            .all()
        )

    return render_template("intro_page.html", recent_logins=recent_logins)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password or not confirm:
            flash("All fields are required.", "danger")
            return redirect("/register")
        if password != confirm:
            flash("Passwords do not match.", "danger")
            return redirect("/register")

        hash_ = generate_password_hash(password)
        with Session(engine) as db:
            user = User(username=username, hash=hash_)
            db.add(user)
            try:
                db.commit()
                flash("Account created! Please sign in.", "success")
                return redirect("/login")
            except IntegrityError:
                db.rollback()
                flash("Username already taken.", "danger")
                return redirect("/register")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        timezone_offset = session.get("timezone_offset", session.get("tz_offset_minutes"))
        session.clear()
        if timezone_offset is not None:
            session["timezone_offset"] = timezone_offset
            session["tz_offset_minutes"] = timezone_offset

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Please enter your username and password.", "danger")
            return redirect("/login")

        with Session(engine) as db:
            user = db.query(User).filter_by(username=username).first()
            if not user or not check_password_hash(user.hash, password):
                flash("Invalid username or password.", "danger")
                return redirect("/login")

            session["user_id"] = user.id
            uid = user.id

            streak = user.streak if user.streak is not None else 0
            last_login = user.last_login_date

            # Use the date from the user's own browser — eliminates server
            # timezone issues on hosted platforms like Render.
            client_date_str = request.form.get("client_date", "").strip()
            try:
                today = datetime.strptime(client_date_str, "%Y-%m-%d").date()
            except ValueError:
                today = get_user_today()  # fallback

            if last_login:
                delta = (today - last_login).days
                if delta == 1:
                    streak += 1
                elif delta > 1:
                    streak = 1
            else:
                streak = 1

            user.streak = streak
            user.last_login_date = today
            db.commit()

        return redirect("/home")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You've been signed out.", "success")
    return redirect("/")


@app.route("/home")
@login_required
def home():
    uid = session["user_id"]
    streak = get_streak(uid)

    with Session(engine) as db:
        target = db.query(Target).filter_by(uid=uid).first()
        today = get_user_today()
        if not target:
            return redirect("/setup")

        exam_date = target.examdate
        if exam_date < today:
            clear_user_plan(uid, db)
            db.commit()
            flash("Your exam date has passed. Starting a new plan.", "info")
            return redirect("/setup?fresh=1")

        hours = target.hours_commit
        exam_date_str = exam_date.isoformat()
        days_left = max(1, (exam_date - today).days)

        total_topics = (
            db.query(Topic)
            .join(Subject)
            .filter(Subject.uid == uid)
            .count()
        )
        
        subject_topic_counts = dict(
            db.query(Topic.sid, func.count(Topic.id))
            .join(Subject)
            .filter(Subject.uid == uid)
            .group_by(Topic.sid)
            .all()
        )

        todays_planned_topics = (
            db.query(Topic)
            .join(Subject)
            .filter(Subject.uid == uid, Topic.planned_date == today)
            .all()
        )

        done_count = 0
        done_pct = 0

        if todays_planned_topics:
            todays_tasks = []
            for t in todays_planned_topics:
                if t.completed:
                    continue
                todays_tasks.append({
                    "id": t.id,
                    "tname": t.tname,
                    "difficulty": t.subject.difficulty,
                    "hours": round(t.planned_hours, 1) if t.planned_hours is not None else 0.5,
                })
            if not todays_tasks:
                return render_template(
                    "home.html",
                    tasks=[], all_done=True,
                    streak=streak, target_date=exam_date_str,
                    days_left=days_left, hours=hours,
                    total_topics=total_topics,
                    done_count=0, done_pct=0,
                )
        else:
            todo_rows = (
                db.query(Topic, Subject.difficulty)
                .join(Subject)
                .filter(Subject.uid == uid, Topic.completed.is_(False))
                .order_by(Topic.id)
                .all()
            )

            if not todo_rows:
                return render_template(
                    "home.html",
                    tasks=[], all_done=True,
                    streak=streak, target_date=exam_date_str,
                    days_left=days_left, hours=hours,
                    total_topics=total_topics,
                    done_count=0, done_pct=100,
                )

            input_str = "|".join([f"{t.id},{d}" for t, d in todo_rows])
            plan_ids = []
            task_hours = {}
            planner_bin = os.path.join(
                ROOT_DIR,
                "engine",
                "planner.exe" if os.name == "nt" else "planner"
            )
            if not os.path.exists(planner_bin) and os.name == "nt":
                planner_bin = os.path.join(ROOT_DIR, "engine", "planner")

            _ensure_planner_executable(planner_bin)

            if os.path.exists(planner_bin):
                try:
                    result = subprocess.run(
                        [planner_bin, str(days_left), str(hours), input_str],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        parts = result.stdout.strip().split(",")
                        for p in parts:
                            p = p.strip()
                            if ":" in p:
                                tid_str, thours_str = p.split(":", 1)
                                try:
                                    tid = int(tid_str)
                                    thours = float(thours_str)
                                    plan_ids.append(tid)
                                    task_hours[tid] = round(thours, 1)
                                except ValueError:
                                    continue
                except Exception:
                    pass  # fall through to Python planner below

            # Python fallback — always runs if binary produced nothing
            if not plan_ids:
                plan_ids, task_hours = _plan_topics_with_python(todo_rows, days_left, hours)

            if not plan_ids and todo_rows:
                plan_ids = [todo_rows[0][0].id]
                task_hours[plan_ids[0]] = round(hours, 1)

            planned_topics = db.query(Topic).filter(Topic.id.in_(plan_ids)).all()
            for pt in planned_topics:
                pt.planned_date = today
                pt.planned_hours = task_hours.get(pt.id, pt.planned_hours or 0.5)
            db.commit()

            todays_tasks = []
            for t, d in todo_rows:
                if t.id in plan_ids:
                    todays_tasks.append({
                        "id": t.id,
                        "tname": t.tname,
                        "difficulty": d,
                        "hours": task_hours.get(t.id, round(t.planned_hours or 0.5, 1)),
                    })

        todays_total = len(todays_tasks)
        todays_done = (
            db.query(Topic)
            .join(Subject)
            .filter(
                Subject.uid == uid,
                Topic.planned_date == today,
                Topic.completed.is_(True)
            )
            .count()
        )

        done_count = todays_done
        done_pct = round(todays_done / todays_total * 100) if todays_total else 0

        return render_template(
            "home.html",
            tasks=todays_tasks, all_done=False,
            streak=streak, target_date=exam_date_str,
            days_left=days_left, hours=hours,
            total_topics=total_topics,
            done_count=done_count, done_pct=done_pct
        )


@app.route("/complete", methods=["POST"])
@login_required
def complete():
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    topic_id = request.form.get("topic_id")

    if not topic_id:
        if is_ajax:
            return jsonify({"ok": False, "error": "Missing topic_id"}), 400
        return redirect("/home")

    try:
        topic_id = int(topic_id)
    except ValueError:
        if is_ajax:
            return jsonify({"ok": False, "error": "Invalid topic_id"}), 400
        return redirect("/home")

    with Session(engine) as db:
        topic = (
            db.query(Topic)
            .join(Subject)
            .filter(Topic.id == topic_id, Subject.uid == session["user_id"])
            .first()
        )
        if not topic:
            if is_ajax:
                return jsonify({"ok": False, "error": "Topic not found"}), 404
            return redirect("/home")

        topic.completed = True
        db.commit()

    if is_ajax:
        return jsonify({"ok": True, "topic_id": topic_id})
    return redirect("/home")


@app.route("/setup", methods=["GET", "POST"])
@login_required
def setup():
    uid = session["user_id"]

    if request.method == "POST":
        exam_date = request.form.get("exam_date", "").strip()
        daily_hours = request.form.get("hours", "").strip()

        if not exam_date or not daily_hours:
            flash("Please provide your exam date and daily hours.", "danger")
            return redirect("/setup")

        try:
            exam_dt = datetime.strptime(exam_date, "%Y-%m-%d").date()
            if exam_dt <= get_user_today():
                flash("Exam date must be in the future.", "danger")
                return redirect("/setup")
        except ValueError:
            flash("Invalid date format.", "danger")
            return redirect("/setup")

        with Session(engine) as db:
            db.query(Target).filter_by(uid=uid).delete(synchronize_session=False)
            db.query(Subject).filter_by(uid=uid).delete(synchronize_session=False)
            db.commit()

            target = Target(uid=uid, examdate=exam_dt, hours_commit=float(daily_hours))
            db.add(target)
            try:
                db.commit()
            except Exception:
                db.rollback()
                flash("Error saving target.", "danger")
                return redirect("/setup")

            subjects_added = _insert_subjects(uid, request.form, db)
            if subjects_added == 0:
                flash("Please add at least one subject with topics.", "warning")
                return redirect("/setup")

            db.commit()

        flash("Study plan created! Here's today's schedule.", "success")
        return redirect("/home")

    with Session(engine) as db:
        existing = db.query(Target).filter_by(uid=uid).first()
    fresh = request.args.get("fresh")
    if existing and not fresh:
        flash("You already have a plan. Use Manage Plan to add more subjects.", "info")
        return redirect("/manage")

    return render_template("setup.html", streak=get_streak(uid))


@app.route("/manage")
@login_required
def manage():
    uid = session["user_id"]

    with Session(engine) as db:
        target = db.query(Target).filter_by(uid=uid).first()
        if not target:
            return redirect("/setup")

        today = get_user_today()
        if target.examdate < today:
            clear_user_plan(uid, db)
            db.commit()
            flash("Your exam date has passed. Starting a new plan.", "info")
            return redirect("/setup?fresh=1")

        raw_subjects = (
            db.query(Subject)
            .filter_by(uid=uid)
            .order_by(Subject.id)
            .all()
        )

        subjects = []
        for s in raw_subjects:
            topics = [
                {"tname": topic.tname, "completed": topic.completed}
                for topic in s.topics
            ]
            total = len(topics)
            done = sum(1 for t in topics if t["completed"])
            subjects.append({
                "sname": s.sname,
                "difficulty": s.difficulty,
                "topics": topics,
                "total": total,
                "done": done,
            })

    return render_template(
        "manage.html",
        subjects=subjects,
        streak=get_streak(uid),
    )


@app.route("/add_subjects", methods=["POST"])
@login_required
def add_subjects():
    uid = session["user_id"]
    today = get_user_today()

    # ── Step 1: validate target exists ───────────────────────────────────────
    with Session(engine) as db:
        target = db.query(Target).filter_by(uid=uid).first()
        if not target:
            flash("No existing plan found. Please set one up first.", "warning")
            return redirect("/setup")
        hours      = target.hours_commit
        exam_date  = target.examdate
        days_left  = max(1, (exam_date - today).days)

    # ── Step 2: insert new subjects + topics in their own clean session ───────
    added = 0
    try:
        with Session(engine) as db:
            added = _insert_subjects(uid, request.form, db)
            db.commit()
    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Error saving subjects: {exc}", "danger")
        return redirect("/manage")

    if added == 0:
        flash("Please add at least one subject with topics.", "warning")
        return redirect("/manage")

    # ── Step 3: clear planned_date for all incomplete topics (reset schedule) ─
    # SQLAlchemy's legacy Query.update() cannot be combined with .join(), so we
    # fetch the IDs first via the join, then update by ID with no join needed.
    try:
        with Session(engine) as db:
            incomplete_ids = [
                tid for (tid,) in
                db.query(Topic.id)
                .join(Subject)
                .filter(Subject.uid == uid, Topic.completed.is_(False))
                .all()
            ]
            if incomplete_ids:
                db.query(Topic).filter(Topic.id.in_(incomplete_ids)).update(
                    {Topic.planned_date: None, Topic.planned_hours: None},
                    synchronize_session=False
                )
            db.commit()
    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Error resetting schedule: {exc}", "danger")
        return redirect("/manage")

    # ── Step 4: run planner and assign today's topics ─────────────────────────
    try:
        with Session(engine) as db:
            todo_rows = (
                db.query(Topic, Subject.difficulty)
                .join(Subject)
                .filter(Subject.uid == uid, Topic.completed.is_(False))
                .order_by(Topic.id)
                .all()
            )

            if todo_rows:
                plan_ids   = []
                task_hours = {}
                input_str  = "|".join([f"{t.id},{d}" for t, d in todo_rows])

                planner_bin = os.path.join(
                    ROOT_DIR, "engine",
                    "planner.exe" if os.name == "nt" else "planner"
                )
                if not os.path.exists(planner_bin) and os.name == "nt":
                    planner_bin = os.path.join(ROOT_DIR, "engine", "planner")
                _ensure_planner_executable(planner_bin)

                if os.path.exists(planner_bin):
                    try:
                        result = subprocess.run(
                            [planner_bin, str(days_left), str(hours), input_str],
                            capture_output=True, text=True, timeout=5
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            for p in result.stdout.strip().split(","):
                                p = p.strip()
                                if ":" in p:
                                    tid_str, thours_str = p.split(":", 1)
                                    try:
                                        tid = int(tid_str)
                                        plan_ids.append(tid)
                                        task_hours[tid] = round(float(thours_str), 1)
                                    except ValueError:
                                        continue
                    except Exception:
                        pass  # fall through to Python planner

                if not plan_ids:
                    plan_ids, task_hours = _plan_topics_with_python(todo_rows, days_left, hours)

                if not plan_ids:
                    plan_ids   = [todo_rows[0][0].id]
                    task_hours = {plan_ids[0]: round(hours, 1)}

                planned = db.query(Topic).filter(Topic.id.in_(plan_ids)).all()
                for pt in planned:
                    pt.planned_date  = today
                    pt.planned_hours = task_hours.get(pt.id, 0.5)
                db.commit()
    except Exception as exc:
        import traceback; traceback.print_exc()
        flash(f"Error building schedule: {exc}", "danger")
        return redirect("/manage")

    flash(f"Added {added} subject(s) and rebuilt your plan!", "success")
    return redirect("/home")


def _insert_subjects(uid, form, db):
    """Parse subjects[N][name] / subjects[N][topics][] from form data.

    Scans form keys subjects[0]..subjects[N] with gap tolerance so that
    removing a subject card in the UI (which leaves a hole in the counter)
    doesn't stop parsing early.

    NOTE: caller is responsible for db.commit(). This function only adds
    objects to the session — no flush or rollback is performed here so the
    caller's transaction stays clean.
    """
    subjects_added = 0
    MAX_GAP = 5
    consecutive_missing = 0
    i = 0

    while consecutive_missing < MAX_GAP:
        sname = form.get(f"subjects[{i}][name]")
        if sname is None:
            consecutive_missing += 1
            i += 1
            continue

        consecutive_missing = 0
        sname = sname.strip()
        if not sname:
            i += 1
            continue

        difficulty = form.get(f"subjects[{i}][difficulty]", 5)
        try:
            difficulty = int(difficulty)
        except (TypeError, ValueError):
            difficulty = 5
        difficulty = max(1, min(10, difficulty))

        subject = Subject(uid=uid, sname=sname, difficulty=difficulty)
        topics_added = 0
        for raw_topic in form.getlist(f"subjects[{i}][topics][]"):
            t = (raw_topic or "").strip()
            if t:
                subject.topics.append(Topic(tname=t, completed=False))
                topics_added += 1

        if topics_added > 0:
            db.add(subject)
            subjects_added += 1

        i += 1

    return subjects_added