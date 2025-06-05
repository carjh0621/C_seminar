import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLAlchemyEnum, ForeignKey
# Removed func from import as it's not used directly in this version of model default/onupdate
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
    source = Column(String, index=True) # e.g., 'gmail', 'manual', 'obsidian_note'
    title = Column(String, nullable=False)
    body = Column(String, nullable=True)
    due_dt = Column(DateTime, nullable=True)
    created_dt = Column(DateTime, default=datetime.utcnow)
    status = Column(SQLAlchemyEnum(TaskStatus), default=TaskStatus.TODO, nullable=False)
    countdown_int = Column(Integer, nullable=True) # Stores pre-calculated D-Day if needed, or null
    last_seen_dt = Column(DateTime, nullable=True) # For external systems, when was this item last seen

    def __repr__(self):
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status.value if self.status else None}')>"

class SourceToken(Base):
    __tablename__ = "source_tokens"

    id = Column(Integer, primary_key=True, index=True)
    # Application-specific user identifier (e.g., "default_user", or a UUID)
    # This allows for potential multi-user or multi-profile setups in the future.
    user_id = Column(String, index=True, nullable=False)

    platform = Column(String, index=True, nullable=False) # e.g., 'gmail', 'kakaotalk', 'google_calendar'
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expires_dt = Column(DateTime, nullable=True) # Expiry datetime of the access_token (UTC)

    # New fields for richer token storage, especially for Google OAuth Credentials object
    scopes = Column(String, nullable=True)  # Space-separated list of scopes
    token_uri = Column(String, nullable=True) # Token endpoint URI
    client_id = Column(String, nullable=True) # Client ID used to obtain the token
    # Storing client_secret in the database is generally discouraged due to its sensitivity.
    # If stored, it MUST be encrypted. Often, it's better to load client_secret from a config file
    # when reconstructing the Credentials object, rather than storing it with each token.
    client_secret = Column(String, nullable=True) # OAuth client secret (HIGHLY SENSITIVE)

    created_dt = Column(DateTime, default=datetime.utcnow)
    # For last_modified_dt with onupdate=datetime.utcnow, SQLAlchemy handles this by
    # setting the value when the ORM object is flushed, if it's marked as modified.
    # For databases that support onupdate in DDL (like MySQL), you could use func.now() from sqlalchemy.sql
    last_modified_dt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # To enforce that a user can only have one token per platform:
    # from sqlalchemy.schema import UniqueConstraint
    # __table_args__ = (UniqueConstraint('user_id', 'platform', name='uq_user_platform_token'),)
    # This is typically managed via database migrations (e.g., with Alembic) in larger projects.
    # The application logic in crud.save_token (get then update/create) also handles this.

    def __repr__(self):
        return f"<SourceToken(id={self.id}, user_id='{self.user_id}', platform='{self.platform}', expires_dt='{self.expires_dt}')>"

class FileCursor(Base):
    __tablename__ = "file_cursors"

    id = Column(Integer, primary_key=True, index=True)
    obsidian_file = Column(String, nullable=False, unique=True) # File path or unique file ID
    line_no_end = Column(Integer, nullable=False) # Last processed line number
    last_rotated_dt = Column(DateTime, nullable=False, default=datetime.utcnow) # When this file was last processed or rotated

    def __repr__(self):
        return f"<FileCursor(id={self.id}, obsidian_file='{self.obsidian_file}', line_no_end={self.line_no_end})>"

# Informational print statement (optional)
# print("Persistence models (Task, SourceToken, FileCursor) defined with SQLAlchemy Base.")
