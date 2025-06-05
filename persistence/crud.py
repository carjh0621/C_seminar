from sqlalchemy.orm import Session
from persistence import models # Assuming models.py contains Task and TaskStatus
from persistence.models import TaskStatus # Explicit import for clarity
from datetime import datetime

# Placeholder for crud.py
print("CRUD module initialized")

def create_task(db: Session, task_data: dict) -> models.Task:
    # Ensure 'created_dt' is set, default to now if not provided
    if 'created_dt' not in task_data:
        task_data['created_dt'] = datetime.utcnow()

    # Handle status string to enum conversion
    if 'status' in task_data and isinstance(task_data['status'], str):
        task_data['status'] = TaskStatus[task_data['status'].upper()]
    elif 'status' not in task_data: # Default status
        task_data['status'] = TaskStatus.TODO

    # Ensure countdown_int is present, even if it's a default or None
    if 'countdown_int' not in task_data:
        task_data['countdown_int'] = 0 # Or some other sensible default

    db_task = models.Task(**task_data)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task

def get_task(db: Session, task_id: int) -> models.Task | None:
    return db.query(models.Task).filter(models.Task.id == task_id).first()

def get_tasks(db: Session, skip: int = 0, limit: int = 100) -> list[models.Task]:
    return db.query(models.Task).offset(skip).limit(limit).all()

def update_task(db: Session, task_id: int, update_data: dict) -> models.Task | None:
    db_task = get_task(db, task_id)
    if db_task:
        for key, value in update_data.items():
            if key == 'status' and isinstance(value, str):
                value = TaskStatus[value.upper()]
            setattr(db_task, key, value)
        db.commit()
        db.refresh(db_task)
    return db_task

def delete_task(db: Session, task_id: int) -> models.Task | None:
    db_task = get_task(db, task_id)
    if db_task:
        db.delete(db_task)
        db.commit()
    return db_task

if __name__ == '__main__':
    # This block is for basic, direct testing of CRUD functions.
    # It requires database.py and models.py to be correctly set up.
    from persistence.database import SessionLocal, create_db_tables
    # from persistence.models import Base # Not strictly needed here if tables created via create_db_tables

    print("Running basic CRUD operations test...")
    create_db_tables()

    db_session_main = SessionLocal()

    # Example Usage for Task CRUD
    new_task_data = {
        "source": "test_main", "title": "Main Test Task", "body": "Body for main test.",
        "due_dt": datetime.utcnow() + timedelta(days=1), "status": "TODO", "countdown_int": 1
    }
    # ... (rest of Task CRUD testing as before) ...

    print("\n--- Conceptual SourceToken CRUD calls (no DB interaction) ---")
    mock_user_id = "user123"
    mock_platform = "gmail"
    mock_token_data = {
        'access_token': 'new_access_token_example',
        'refresh_token': 'new_refresh_token_example',
        'expires_dt': datetime.utcnow() + timedelta(hours=1)
    }

    # ... (rest of Task CRUD testing as before) ...

    # print("\n--- Conceptual SourceToken CRUD calls (no DB interaction) ---")
    # mock_user_id = "user123"
    # mock_platform = "gmail"
    # mock_token_data = {
    #     'access_token': 'new_access_token_example',
    #     'refresh_token': 'new_refresh_token_example',
    #     'expires_dt': datetime.utcnow() + timedelta(hours=1)
    # }
    # # Test get_token (conceptual)
    # print(f"Calling get_token for user '{mock_user_id}', platform '{mock_platform}'")
    # token = get_token(db_session_main, mock_user_id, mock_platform)
    # if token:
    #     print(f"get_token (conceptual) returned: {token.access_token}")
    # else:
    #     print("get_token (conceptual) returned None.")
    # # Test save_token (conceptual)
    # print(f"Calling save_token for user '{mock_user_id}', platform '{mock_platform}'")
    # saved_token = save_token(db_session_main, mock_user_id, mock_platform, mock_token_data)
    # if saved_token:
    #     print(f"save_token (conceptual) returned mock token with access_token: {saved_token.access_token}")
    # # Test delete_token (conceptual)
    # print(f"Calling delete_token for user '{mock_user_id}', platform '{mock_platform}'")
    # deleted = delete_token(db_session_main, mock_user_id, mock_platform)
    # print(f"delete_token (conceptual) returned: {deleted}")
    print("Conceptual test in __main__ for SourceToken CRUD is commented out to prevent errors if model isn't updated yet.")
    db_session_main.close()


# --- SourceToken CRUD Operations (Implementation) ---

def get_token(db: Session, user_identifier: str, platform: str) -> models.SourceToken | None:
    """
    Retrieves a token for a given user_identifier and platform.
    'user_identifier' is the application-specific ID for the user.
    """
    # Assuming SourceToken.user_id is compatible with user_identifier type (e.g. String)
    # If SourceToken.user_id is Integer, user_identifier might need conversion or careful handling.
    return db.query(models.SourceToken).filter(
        models.SourceToken.user_id == user_identifier,
        models.SourceToken.platform == platform
    ).first()

def save_token(db: Session, user_identifier: str, platform: str, token_info: dict) -> models.SourceToken:
    """
    Saves or updates a token for a given user_identifier and platform.
    'token_info' should contain:
        - access_token (str)
        - expires_dt (datetime)
        - refresh_token (str, optional)
        - scopes (list[str] or str, optional)
        - token_uri (str, optional)
        - client_id (str, optional)
        - client_secret (str, optional, consider security implications)
    """
    existing_token = get_token(db, user_identifier, platform)

    scopes_str = None
    if 'scopes' in token_info and token_info['scopes'] is not None:
        if isinstance(token_info['scopes'], list):
            scopes_str = " ".join(token_info['scopes'])
        elif isinstance(token_info['scopes'], str):
            scopes_str = token_info['scopes']
        # Else, if scopes is not list/str or is None, scopes_str remains None

    if existing_token:
        # Update existing token
        existing_token.access_token = token_info['access_token']
        existing_token.expires_dt = token_info['expires_dt'] # Must be datetime object

        if 'refresh_token' in token_info: # Only update if provided
            existing_token.refresh_token = token_info['refresh_token']
        if scopes_str is not None: # Only update if scopes were processed
            existing_token.scopes = scopes_str
        if 'token_uri' in token_info:
            existing_token.token_uri = token_info['token_uri']
        if 'client_id' in token_info:
            existing_token.client_id = token_info['client_id']
        if 'client_secret' in token_info:
            existing_token.client_secret = token_info['client_secret']

        # Assuming last_modified_dt field exists on the model
        if hasattr(existing_token, 'last_modified_dt'):
            existing_token.last_modified_dt = datetime.utcnow()
        db_token_to_refresh = existing_token
    else:
        # Create new token
        # Ensure user_identifier matches the type of SourceToken.user_id
        # If SourceToken.user_id is Integer, this might need adjustment or pre-validation.
        create_data = {
            'user_id': user_identifier,
            'platform': platform,
            'access_token': token_info['access_token'],
            'refresh_token': token_info.get('refresh_token'),
            'expires_dt': token_info['expires_dt'],
            'scopes': scopes_str,
            'token_uri': token_info.get('token_uri'),
            'client_id': token_info.get('client_id'),
            'client_secret': token_info.get('client_secret'),
        }
        # Add timestamps if model supports them
        if hasattr(models.SourceToken, 'created_dt'):
            create_data['created_dt'] = datetime.utcnow()
        if hasattr(models.SourceToken, 'last_modified_dt'):
            create_data['last_modified_dt'] = datetime.utcnow()

        db_token_to_refresh = models.SourceToken(**create_data)
        db.add(db_token_to_refresh)

    try:
        db.commit()
        db.refresh(db_token_to_refresh)
    except Exception as e:
        db.rollback()
        # Consider logging the error instead of just printing
        print(f"Error saving/updating token to DB for user '{user_identifier}', platform '{platform}': {e}")
        raise # Re-raise the exception so the caller can handle it
    return db_token_to_refresh

def delete_token(db: Session, user_identifier: str, platform: str) -> bool:
    """
    Deletes a token for a given user_identifier and platform.
    Returns True if a token was deleted, False otherwise.
    """
    token_to_delete = get_token(db, user_identifier, platform)
    if token_to_delete:
        db.delete(token_to_delete)
        try:
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"Error deleting token from DB for user '{user_identifier}', platform '{platform}': {e}")
            raise # Re-raise
    return False

# Note on SourceToken model fields:
# The save_token function assumes that the SourceToken model can accept fields like:
# - scopes (String)
# - token_uri (String)
# - client_id (String)
# - client_secret (String, nullable, ensure encryption if used for sensitive secrets)
# - created_dt (DateTime, with default)
# - last_modified_dt (DateTime, with default and onupdate)
# If these fields are not on the SourceToken model, attempts to set them will
# cause errors at runtime. The model should be updated accordingly.
# The user_id field in SourceToken is assumed to be of a type compatible with user_identifier.
# If user_id is strictly an Integer, user_identifier might need to be an int or castable to int.
