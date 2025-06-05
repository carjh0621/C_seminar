import enum
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class TaskStatus(enum.Enum):
    TODO = "TODO"
    DONE = "DONE"
    CANCELLED = "CANCELLED"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String)
    title = Column(String)
    body = Column(String)
    due_dt = Column(DateTime, nullable=True)
    created_dt = Column(DateTime)
    status = Column(Enum(TaskStatus))
    countdown_int = Column(Integer)
    last_seen_dt = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<Task(id={self.id}, title='{self.title}', status='{self.status}')>"

class SourceToken(Base):
    __tablename__ = "source_tokens"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expires_dt = Column(DateTime, nullable=True)
    user_id = Column(Integer) # Assuming simple user ID for now

    def __repr__(self):
        return f"<SourceToken(id={self.id}, platform='{self.platform}', user_id={self.user_id})>"

class FileCursor(Base):
    __tablename__ = "file_cursors"

    id = Column(Integer, primary_key=True, index=True)
    obsidian_file = Column(String, nullable=False, unique=True)
    line_no_end = Column(Integer, nullable=False)
    last_rotated_dt = Column(DateTime, nullable=False)

    def __repr__(self):
        return f"<FileCursor(id={self.id}, obsidian_file='{self.obsidian_file}', line_no_end={self.line_no_end})>"

# Placeholder for database models
print("Database models module initialized with Task, SourceToken, and FileCursor models.")
