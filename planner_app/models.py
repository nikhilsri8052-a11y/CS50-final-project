import os
from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String, create_engine, event, inspect, text
from sqlalchemy.orm import Session as OrmSession, declarative_base, relationship

# 1. DATABASE SELECTION
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    # Use the root directory for the local SQLite file
    DATABASE_FILE = os.path.join(ROOT_DIR, "database.db")
    DATABASE_URL = f"sqlite:///{DATABASE_FILE}"

Base = declarative_base()
engine = create_engine(DATABASE_URL, future=True)

# Ensure compatibility with older local SQLite databases.
if DATABASE_URL.startswith("sqlite"):
    db_path = os.path.join(ROOT_DIR, "database.db")
    if os.path.exists(db_path):
        inspector = inspect(engine)
        if inspector.has_table("users"):
            column_names = [col["name"] for col in inspector.get_columns("users")]
            if "last_login_date" not in column_names:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN last_login_date DATE"))

# 2. CLASSES
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    hash = Column(String, nullable=False)
    streak = Column(Integer, default=0)
    last_login_date = Column(Date)
    target = relationship("Target", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    uid = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sname = Column(String, nullable=False)
    difficulty = Column(Integer, default=5)
    topics = relationship("Topic", back_populates="subject", cascade="all, delete-orphan")

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
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

Base.metadata.create_all(engine)

def Session(bind):
    return OrmSession(bind)