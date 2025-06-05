import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLAlchemyEnum, ForeignKey, UniqueConstraint
# For server-side defaults/onupdate with func.now(), it would be needed.
# SQLAlchemy handles Python-side defaults like datetime.utcnow automatically.
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class TaskStatus(enum.Enum):
    TODO = "TODO"
    DONE = "DONE"
    CANCELLED = "CANCELLED"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String, index=True) # e.g., 'gmail_messageId123', 'manual_entry', 'obsidian_note_uuid'
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    due_dt = Column(DateTime, nullable=True, index=True) # Added index for due_dt
    created_dt = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(SQLAlchemyEnum(TaskStatus), default=TaskStatus.TODO, nullable=False)

    # Fields for D-day calculation (as per original spec, though calculation is external)
    # countdown_int can be populated by a separate process or when tasks are queried.
    countdown_int = Column(Integer, nullable=True)
    last_seen_dt = Column(DateTime, nullable=True) # For external systems, when was this item last seen/synced

    # --- New fields for deduplication and conflict management ---
    # Fingerprint for identifying potentially duplicate tasks.
    # Unique constraint ensures no two tasks (that have a fingerprint) can be identical.
    # Nullable because not all tasks might have a fingerprint (e.g. manually added, or if generation fails).
    fingerprint = Column(String, index=True, unique=True, nullable=True)

    # Comma-separated string for tags like '#conflict', '#projectX', '#urgent'
    tags = Column(String, nullable=True)
    # --- End new fields ---

    def __repr__(self):
        return (f"<Task(id={self.id}, title='{self.title}', "
                f"due_dt='{self.due_dt.isoformat() if self.due_dt else None}', "
                f"status='{self.status.name if self.status else None}', "
                f"fingerprint='{self.fingerprint}')>")


class SourceToken(Base):
    __tablename__ = "source_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    platform = Column(String, index=True, nullable=False)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expires_dt = Column(DateTime, nullable=True)
    scopes = Column(String, nullable=True)
    token_uri = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    client_secret = Column(String, nullable=True) # HIGHLY SENSITIVE - consider encryption or alternative storage

    created_dt = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_modified_dt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Enforce that a user can only have one token per platform.
    __table_args__ = (UniqueConstraint('user_id', 'platform', name='uq_user_platform_token'),)

    def __repr__(self):
        return (f"<SourceToken(id={self.id}, user_id='{self.user_id}', "
                f"platform='{self.platform}', expires_dt='{self.expires_dt.isoformat() if self.expires_dt else None}')>")

class FileCursor(Base):
    __tablename__ = "file_cursors"

    id = Column(Integer, primary_key=True, index=True)
    obsidian_file = Column(String, nullable=False, unique=True)
    line_no_end = Column(Integer, nullable=False)
    last_rotated_dt = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return (f"<FileCursor(id={self.id}, obsidian_file='{self.obsidian_file}', "
                f"line_no_end={self.line_no_end})>")

# Informational print statement (optional, can be removed)
# print("Persistence models (Task, SourceToken, FileCursor) defined with SQLAlchemy Base.")
