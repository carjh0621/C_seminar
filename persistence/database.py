from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from persistence.models import Base # Needed for create_db_tables
import config

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} # Specific to SQLite
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency provider for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_db_tables():
    """Creates all database tables based on SQLAlchemy models."""
    Base.metadata.create_all(bind=engine)
    print("Database tables created (if they didn't exist).")

if __name__ == "__main__":
    # For basic testing of this script
    print(f"Database engine configured for URL: {config.DATABASE_URL}")
    create_db_tables()
    print("Persistence database module initialized with session management and tables checked/created.")
