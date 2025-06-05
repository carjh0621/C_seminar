from datetime import datetime
import sys
import time # For keeping the main thread alive if using BackgroundScheduler (not used here yet)

# --- APScheduler Imports ---
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
# For explicit pytz usage if 'Asia/Seoul' string causes issues:
# import pytz
# --- End APScheduler Imports ---

from ingestion.agents import GmailAgent
from preprocessing.normalizer import normalize as normalize_text # Alias to avoid name clash
from extract_nlp.classifiers import TaskClassifier, resolve_date
from openai import OpenAIError

from persistence.database import SessionLocal, create_db_tables # For DB session and initial table creation
from persistence import crud as persistence_crud # For create_task
from persistence.models import TaskStatus # For setting task status

# --- Import the job to be scheduled ---
from scheduler.jobs import scheduled_job
# --- End job import ---


def run_gmail_ingestion_pipeline(app_user_id: str = "default_user"):
    """
    Runs the full ingestion pipeline for Gmail.
    (Implementation remains as defined in previous steps)
    """
    print(f"Starting Gmail ingestion pipeline for user: {app_user_id}...")

    print("Initializing GmailAgent...")
    gmail_agent = GmailAgent(credentials_file='credentials.json')

    print(f"Authenticating Gmail for user: {app_user_id}...")
    try:
        gmail_service = gmail_agent.authenticate_gmail(app_user_id=app_user_id)
        if not gmail_service:
            print(f"Gmail authentication failed for user {app_user_id}. Pipeline cannot continue.")
            return
        print("Gmail authentication successful.")
    except Exception as e:
        print(f"An critical error occurred during Gmail authentication: {e}")
        return

    normalizer_func = normalize_text
    date_resolver_func = resolve_date
    try:
        print("Initializing TaskClassifier...")
        task_classifier = TaskClassifier()
        print("TaskClassifier initialized successfully.")
    except ValueError as e:
        print(f"Error initializing TaskClassifier: {e}")
        print("Please ensure your OpenAI API key is correctly configured as per docs/llm_setup.md.")
        return
    except OpenAIError as e:
        print(f"OpenAI API Error during TaskClassifier initialization: {e}")
        return
    except Exception as e:
        print(f"Unexpected error initializing TaskClassifier: {e}")
        return

    print("Fetching emails...")
    fetched_emails = gmail_agent.fetch_messages(max_results=10)

    if not fetched_emails:
        print("No new emails fetched. Pipeline run complete for this cycle.")
        return
    print(f"Fetched {len(fetched_emails)} emails.")

    db = SessionLocal()
    tasks_created_count = 0
    for i, email_data in enumerate(fetched_emails):
        print(f"\nProcessing email {i+1}/{len(fetched_emails)}: ID {email_data['id']}, Subject: '{email_data['headers'].get('subject', 'N/A')[:60]}...'")
        content_to_process = ""
        content_type_for_normalizer = "text/plain"
        if email_data.get('body_plain', "").strip():
            content_to_process = email_data['body_plain']
        elif email_data.get('body_html', "").strip():
            content_to_process = email_data['body_html']
            content_type_for_normalizer = "text/html"
        elif email_data.get('snippet', "").strip():
            content_to_process = email_data['snippet']
            print("Using email snippet as body was empty.")
        else:
            print("Email body and snippet are empty. Skipping NLP for this email.")
            continue
        if not content_to_process.strip():
             print("Content to process is empty or whitespace after selection. Skipping NLP.")
             continue
        normalized_content = normalizer_func(content_to_process, content_type=content_type_for_normalizer)
        task_source_id = f"gmail_{email_data['id']}"
        classification_result = task_classifier.classify_task(normalized_content, source_id=task_source_id)
        if not classification_result:
            print(f"No task classified or error during classification for email ID {email_data['id']}.")
            continue
        print(f"Task classified: Type='{classification_result['type']}', Title='{classification_result['title']}'")
        due_datetime = None
        due_date_str_from_classifier = classification_result.get('due')
        if due_date_str_from_classifier:
            due_datetime = date_resolver_func(due_date_str_from_classifier)
            if due_datetime: print(f"Due date resolved to: {due_datetime.isoformat()}")
            else: print(f"Could not resolve due date string: '{due_date_str_from_classifier}'")
        task_data_for_db = {
            "source": task_source_id, "title": classification_result['title'],
            "body": classification_result.get('body', normalized_content[:1000]),
            "due_dt": due_datetime, "created_dt": datetime.utcnow(),
            "status": TaskStatus.TODO,
        }
        try:
            print(f"Saving task '{task_data_for_db['title']}' to database...")
            created_task = persistence_crud.create_task(db, task_data_for_db)
            print(f"Task created successfully with ID: {created_task.id}")
            tasks_created_count += 1
        except Exception as e:
            db.rollback()
            print(f"Error saving task (Source ID: {task_source_id}) to database: {e}")
    try:
        db.close()
        print("Database session closed.")
    except Exception as e:
        print(f"Error closing database session: {e}")
    print(f"\nGmail ingestion pipeline finished for this run. {tasks_created_count} tasks created.")


if __name__ == '__main__':
    print("Running Agenda Manager application...")

    print("Ensuring database tables are created...")
    try:
        create_db_tables()
        print("Database tables checked/created successfully.")
    except Exception as e:
        print(f"CRITICAL: Error creating database tables: {e}. Exiting.")
        sys.exit(1)

    # --- Initialize and Start Scheduler ---
    print("Initializing scheduler...")
    # Using BlockingScheduler as this main.py is intended to be the scheduler process.
    # For timezone, ensure your system has 'Asia/Seoul' or install pytz and use pytz.timezone('Asia/Seoul')
    try:
        scheduler = BlockingScheduler(timezone='Asia/Seoul')
    except Exception as e:
        print(f"Error initializing scheduler (timezone might be an issue): {e}")
        print("If 'UnknownTimeZoneError', try installing 'pytz' (`pip install pytz`) and uncommenting pytz import.")
        sys.exit(1)


    # Schedule the job from scheduler.jobs
    # This runs daily at 22:00 (10 PM) KST.
    try:
        scheduler.add_job(
            scheduled_job,
            trigger=CronTrigger(hour=22, minute=0, timezone='Asia/Seoul'),
            id='daily_gmail_ingestion_job',
            name='Daily Gmail Ingestion at 22:00 KST',
            replace_existing=True
        )

        # For testing purposes, you can add a job that runs more frequently, e.g., every X minutes or seconds.
        # scheduler.add_job(scheduled_job, 'interval', minutes=1, id='test_interval_job_1min')
        # print("Added test job to run every 1 minute for testing.")

    except Exception as e:
        print(f"Error adding job to scheduler: {e}")
        sys.exit(1)

    print("Scheduler initialized. Starting jobs...")
    print("Scheduled jobs:")
    try:
        scheduler.print_jobs()
    except Exception as e:
        print(f"Could not print jobs: {e}") # Might fail if job store is misconfigured, though unlikely for default

    print("Press Ctrl+C to exit.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler shutdown requested...")
    except Exception as e:
        print(f"An critical error occurred with the scheduler: {e}")
    finally:
        # Ensure scheduler is shut down cleanly in most cases
        if scheduler.running:
            try:
                print("Attempting to shut down scheduler...")
                scheduler.shutdown()
                print("Scheduler shutdown complete.")
            except Exception as se:
                print(f"Error during scheduler shutdown: {se}")
        else:
            print("Scheduler was not running or already shut down.")
