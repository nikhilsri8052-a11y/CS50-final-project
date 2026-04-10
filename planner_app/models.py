import os
from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String, create_engine, event, text
from sqlalchemy.orm import Session as OrmSession, declarative_base, relationship

# 1. SMART DATABASE SELECTION
# On Render, DATABASE_URL will be set in the Environment settings.
# Locally, it will default to your SQLite file.
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    # Render provides postgres:// but SQLAlchemy 1.4+ requires postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
    DATABASE_FILE = os.path.join(ROOT_DIR, "database.db")
    DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True)

# 2. SQLITE-ONLY CONFIG
# Foreign keys are default in Postgres, but need to be enabled for SQLite.
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

# ... (User, Subject, Topic, Target classes remain exactly the same) ...

# 3. MIGRATION LOGIC
Base.metadata.create_all(engine)

def _ensure_topic_columns():
    # We only need this manual PRAGMA check for SQLite. 
    # Postgres users usually use Alembic, but we'll keep this safe for now.
    if "sqlite" in DATABASE_URL:
        with engine.begin() as conn:
            result = conn.execute(text("PRAGMA table_info(topics)"))
            existing_columns = {row[1] for row in result}
            if "planned_date" not in existing_columns:
                conn.execute(text("ALTER TABLE topics ADD COLUMN planned_date DATE"))
            if "planned_hours" not in existing_columns:
                conn.execute(text("ALTER TABLE topics ADD COLUMN planned_hours FLOAT"))

_ensure_topic_columns()
Session = OrmSession