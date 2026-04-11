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
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    hash = Column(String, nullable=False)
    streak = Column(Integer, default=0, nullable=False)
    last_login_date = Column(Date, nullable=True)

    subjects = relationship(
        "Subject",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    target = relationship(
        "Target",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    uid = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sname = Column(String, nullable=False)
    difficulty = Column(Integer, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="subjects")
    topics = relationship(
        "Topic",
        back_populates="subject",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True)
    sid = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    tname = Column(String, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    planned_date = Column(Date, nullable=True)
    planned_hours = Column(Float, nullable=True)

    subject = relationship("Subject", back_populates="topics")

class Target(Base):
    __tablename__ = "target"
    id = Column(Integer, primary_key=True)
    uid = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    examdate = Column(Date, nullable=False)
    hours_commit = Column(Float, nullable=False)

    user = relationship("User", back_populates="target")

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