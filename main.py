from datetime import datetime, timedelta, time as dt_time, date # Ensure all are imported
import sys
import time
import typer

# APScheduler Imports
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Project module imports
from ingestion.agents import GmailAgent, KakaoAgent # Added KakaoAgent
from preprocessing.normalizer import normalize as normalize_text
from extract_nlp.classifiers import TaskClassifier, resolve_date
from extract_nlp.utils import generate_task_fingerprint
from openai import OpenAIError

from persistence.database import SessionLocal, create_db_tables
from persistence import crud as persistence_crud
from persistence.models import TaskStatus # Import TaskStatus enum

from scheduler.jobs import scheduled_job
from cli.main_cli import app as cli_app

# --- New Imports for KakaoTalk Pipeline ---
from playwright.sync_api import sync_playwright, Playwright, PlaywrightError # For managing Playwright lifecycle
from typing import Optional # For KakaoAgent type hint in pipeline function
# --- End New KakaoTalk Imports ---


def run_gmail_ingestion_pipeline(app_user_id: str = "default_user"):
    """
    Runs the full ingestion pipeline for Gmail.
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
    task_classifier = None
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
        print("This could be due to an invalid API key or network issues with OpenAI.")
        return
    except Exception as e:
        print(f"Unexpected error initializing TaskClassifier: {e}")
        return

    print("Fetching emails for the current day...")
    today_date = date.today()
    yesterday_date = today_date - timedelta(days=1)
    since_date_str_for_gmail = yesterday_date.strftime("%Y/%m/%d")
    print(f"Fetching all emails received after {since_date_str_for_gmail} (i.e., from {today_date.isoformat()} onwards) up to a limit of 500.")
    fetched_emails = gmail_agent.fetch_messages(since_date_str=since_date_str_for_gmail, max_results=500)

    if not fetched_emails:
        print("No new emails found for today. Pipeline run complete.")
        return
    print(f"Fetched {len(fetched_emails)} emails from today.")

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

        task_title_from_llm = None
        classification_result = task_classifier.classify_task(normalized_content, source_id=task_source_id)

        if not classification_result:
            print(f"No task classified or error during classification for email ID {email_data['id']}.")
            continue

        task_title_from_llm = classification_result['title']
        print(f"Task classified: Type='{classification_result['type']}', Title='{task_title_from_llm}'")

        due_datetime = None
        due_date_str_from_classifier = classification_result.get('due')
        if due_date_str_from_classifier:
            due_datetime = date_resolver_func(due_date_str_from_classifier)
            if due_datetime: print(f"Due date resolved to: {due_datetime.isoformat()}")
            else: print(f"Could not resolve due date string: '{due_date_str_from_classifier}'")

        task_fingerprint = None
        if task_title_from_llm:
            try:
                task_fingerprint = generate_task_fingerprint(task_title_from_llm, due_datetime)
                print(f"Generated fingerprint: {task_fingerprint}")
            except ValueError as ve:
                print(f"Skipping fingerprint generation due to error: {ve}")
            except Exception as e:
                print(f"Unexpected error generating fingerprint for title '{task_title_from_llm}': {e}")
        else:
            print("No title from LLM, cannot generate fingerprint.")

        task_data_for_db = {
            "source": task_source_id, "title": task_title_from_llm,
            "body": classification_result.get('body', normalized_content[:1000]),
            "due_dt": due_datetime, "created_dt": datetime.utcnow(),
            "status": TaskStatus.TODO,
            "fingerprint": task_fingerprint,
            "tags": None,
            "type": classification_result.get('type', 'gmail_task') # Add type from classifier
        }

        if task_fingerprint:
            print(f"Checking for existing task with fingerprint: {task_fingerprint}...")
            existing_task_by_fp = persistence_crud.get_task_by_fingerprint(db, task_fingerprint)
            if existing_task_by_fp:
                print(f"Duplicate task found by fingerprint (ID: {existing_task_by_fp.id}, Title: '{existing_task_by_fp.title}'). Skipping creation.")
                continue
            else:
                print("No duplicate task found with this fingerprint.")
        else:
            print("No fingerprint generated for this task, cannot perform deduplication check based on it.")

        newly_created_task_obj = None
        try:
            print(f"Saving task '{task_data_for_db['title']}' to database (fingerprint: {task_fingerprint})...")
            newly_created_task_obj = persistence_crud.create_task(db, task_data_for_db)
            print(f"Task created successfully with ID: {newly_created_task_obj.id}, Fingerprint: {newly_created_task_obj.fingerprint}")
            tasks_created_count += 1
        except Exception as e:
            db.rollback()
            print(f"Error saving task (Source ID: {task_source_id}) to database: {e}")
            continue

        if newly_created_task_obj and newly_created_task_obj.due_dt and \
           newly_created_task_obj.due_dt.time() != dt_time(0, 0, 0):

            print(f"Performing conflict check for task ID {newly_created_task_obj.id} (Due: {newly_created_task_obj.due_dt})...")
            task_date_for_conflict_check = newly_created_task_obj.due_dt.date()

            potential_conflicts = persistence_crud.get_tasks_on_same_day_with_time(
                db, task_date_for_conflict_check, exclude_task_id=newly_created_task_obj.id
            )

            conflict_window = timedelta(hours=1)

            for existing_task_conflict in potential_conflicts:
                if existing_task_conflict.due_dt:
                    time_diff = abs(newly_created_task_obj.due_dt - existing_task_conflict.due_dt)
                    if time_diff < conflict_window:
                        print(f"Conflict detected between Task ID {newly_created_task_obj.id} (Due: {newly_created_task_obj.due_dt}) "
                              f"and Task ID {existing_task_conflict.id} (Due: {existing_task_conflict.due_dt}).")

                        updated_new_task_after_tagging = persistence_crud.update_task_tags(db, newly_created_task_obj.id, "#conflict")
                        if updated_new_task_after_tagging:
                            newly_created_task_obj = updated_new_task_after_tagging
                        else:
                            print(f"Warning: Failed to update tags for new task {newly_created_task_obj.id}")

                        persistence_crud.update_task_tags(db, existing_task_conflict.id, "#conflict")
    try:
        if 'db' in locals() and db.is_active:
            db.close()
            print("Database session closed.")
    except Exception as e:
        print(f"Error closing database session: {e}")
    print(f"\nGmail ingestion pipeline finished for this run. {tasks_created_count} tasks created.")


def run_kakaotalk_ingestion_pipeline(
    app_user_id: str = "default_kakaotalk_user",
    target_chat_name: Optional[str] = None
):
    print(f"\n--- Starting KakaoTalk Ingestion Pipeline for user: {app_user_id} ---")
    try:
        from config import KAKAOTALK_CHAT_NAME_TO_MONITOR, KAKAOTALK_USER_DATA_DIR
    except ImportError:
        print("Error: Could not import KakaoTalk configurations from config.py.")
        return

    effective_target_chat_name = target_chat_name or KAKAOTALK_CHAT_NAME_TO_MONITOR

    if not effective_target_chat_name or effective_target_chat_name == "My Notes Chat":
        print(f"Warning: KAKAOTALK_CHAT_NAME_TO_MONITOR is not configured or is set to default ('{effective_target_chat_name}').")
        if not typer.confirm("Proceed with this chat name, or do you want to skip KakaoTalk pipeline? (Skip recommended if not configured)", default=False):
            print("KakaoTalk pipeline skipped by user due to chat name configuration.")
            return
        if not effective_target_chat_name:
             print("Error: Target chat name is empty. Cannot proceed.")
             return

    print(f"Target KakaoTalk chat room: '{effective_target_chat_name}'")
    kakao_agent_instance: Optional[KakaoAgent] = None
    tasks_created_count = 0

    try:
        with sync_playwright() as p_instance:
            print("Initializing KakaoAgent with Playwright...")
            kakao_agent_instance = KakaoAgent(
                playwright_instance=p_instance,
                user_data_dir=KAKAOTALK_USER_DATA_DIR
            )

            if not kakao_agent_instance.login():
                print("KakaoTalk login/setup failed by agent. Pipeline cannot continue.")
                return

            if not kakao_agent_instance.select_chat(effective_target_chat_name):
                print(f"Failed to select KakaoTalk chat: '{effective_target_chat_name}'. Pipeline cannot continue.")
                return

            fetched_messages = kakao_agent_instance.read_messages(num_messages_to_capture=20)

            if not fetched_messages:
                print("No new messages fetched from KakaoTalk. Pipeline run complete for KakaoTalk.")
                return

            print(f"Fetched {len(fetched_messages)} messages from KakaoTalk chat '{effective_target_chat_name}'.")

            normalizer_func = normalize_text
            task_classifier_instance = None
            try:
                task_classifier_instance = TaskClassifier()
            except ValueError as e_tc_val:
                print(f"Error initializing TaskClassifier for KakaoTalk pipeline: {e_tc_val}. Skipping task processing.")
                return
            except OpenAIError as e_tc_openai:
                print(f"OpenAI API Error during TaskClassifier init for KakaoTalk: {e_tc_openai}. Skipping.")
                return
            except Exception as e_tc_other:
                print(f"Unexpected error initializing TaskClassifier for KakaoTalk: {e_tc_other}. Skipping.")
                return

            date_resolver_func = resolve_date
            db_session = SessionLocal()

            try:
                for i, msg_data in enumerate(fetched_messages):
                    print(f"\nProcessing KakaoTalk message {i+1}/{len(fetched_messages)}: ID {msg_data.get('id', 'N/A')}")
                    content_to_process = msg_data.get("text", "")
                    if not content_to_process.strip():
                        print("Message text is empty. Skipping NLP for this message.")
                        continue
                    normalized_content = normalizer_func(content_to_process, content_type="text/plain")
                    task_source_id = f"kakaotalk_{effective_target_chat_name}_{msg_data.get('id', f'msgidx{i}')}"
                    task_title_from_llm = None
                    classification_result = task_classifier_instance.classify_task(normalized_content, source_id=task_source_id)
                    if not classification_result:
                        print("No task classified from this KakaoTalk message.")
                        continue
                    task_title_from_llm = classification_result['title']
                    print(f"Task classified: Type='{classification_result['type']}', Title='{task_title_from_llm}'")
                    due_datetime = None
                    if classification_result.get('due'):
                        due_datetime = date_resolver_func(classification_result['due'])
                        if due_datetime: print(f"Due date resolved to: {due_datetime.isoformat()}")
                        else: print(f"Could not resolve due date string: '{classification_result['due']}'")
                    task_fingerprint = None
                    if task_title_from_llm:
                        try:
                            task_fingerprint = generate_task_fingerprint(task_title_from_llm, due_datetime)
                        except ValueError as ve_fp: print(f"Could not generate fingerprint: {ve_fp}")
                        except Exception as e_fp: print(f"Error generating fingerprint: {e_fp}")
                    if task_fingerprint:
                        existing_task = persistence_crud.get_task_by_fingerprint(db_session, task_fingerprint)
                        if existing_task:
                            print(f"Duplicate task found (ID: {existing_task.id}) by fingerprint. Skipping.")
                            continue
                    task_data_for_db = {
                        "source": task_source_id, "title": task_title_from_llm,
                        "body": classification_result.get('body', normalized_content[:1000]),
                        "due_dt": due_datetime, "created_dt": datetime.utcnow(),
                        "status": TaskStatus.TODO, "fingerprint": task_fingerprint, "tags": None,
                        "type": classification_result.get('type', 'kakaotalk_task')
                    }
                    newly_created_task_obj = None
                    try:
                        newly_created_task_obj = persistence_crud.create_task(db_session, task_data_for_db)
                        print(f"Task created from KakaoTalk: ID {newly_created_task_obj.id}, FP: {newly_created_task_obj.fingerprint}")
                        tasks_created_count += 1
                    except Exception as e_save:
                        db_session.rollback()
                        print(f"Error saving task from KakaoTalk: {e_save}")
                        continue
                    if newly_created_task_obj and newly_created_task_obj.due_dt and \
                       newly_created_task_obj.due_dt.time() != dt_time(0,0,0):
                        task_date_cdt = newly_created_task_obj.due_dt.date()
                        potential_conflicts_cdt = persistence_crud.get_tasks_on_same_day_with_time(
                            db_session, task_date_cdt, exclude_task_id=newly_created_task_obj.id
                        )
                        conflict_window_cdt = timedelta(hours=1)
                        for existing_task_cdt in potential_conflicts_cdt:
                            if existing_task_cdt.due_dt:
                                time_diff_cdt = abs(newly_created_task_obj.due_dt - existing_task_cdt.due_dt)
                                if time_diff_cdt < conflict_window_cdt:
                                    print(f"Conflict detected (KakaoTalk): Task {newly_created_task_obj.id} and Task {existing_task_cdt.id}.")
                                    updated_task_cdt = persistence_crud.update_task_tags(db_session, newly_created_task_obj.id, "#conflict")
                                    if updated_task_cdt: newly_created_task_obj = updated_task_cdt
                                    persistence_crud.update_task_tags(db_session, existing_task_cdt.id, "#conflict")
            finally:
                if 'db_session' in locals() and db_session.is_active:
                    db_session.close()
                    print("KakaoTalk pipeline DB session closed.")
            print(f"\nKakaoTalk ingestion pipeline finished. {tasks_created_count} tasks created.")
    except PlaywrightError as e_pw:
        print(f"A Playwright error occurred during KakaoTalk pipeline: {e_pw}")
    except ImportError as e_imp:
        print(f"ImportError during KakaoTalk pipeline (check config for KAKAOTALK_* values): {e_imp}")
    except Exception as e_main:
        print(f"An unexpected error occurred during KakaoTalk pipeline: {e_main}")
        import traceback
        traceback.print_exc()
    finally:
        if kakao_agent_instance:
            print("Closing KakaoAgent resources...")
            kakao_agent_instance.close()

# Main application entry point
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'cli':
        print("Starting Agenda Manager CLI...")
        cli_app()
    elif len(sys.argv) > 1 and sys.argv[1].lower() == 'kakaotalk_once':
        print("Running KakaoTalk ingestion pipeline once...")
        try:
            create_db_tables()
            print("Database tables checked/created for KakaoTalk run.")
        except Exception as e_db_init:
            print(f"DB init error before KakaoTalk run: {e_db_init}");
            sys.exit(1)
        run_kakaotalk_ingestion_pipeline()
    else:
        print("Starting Agenda Manager Scheduler...")
        print("Ensuring database tables are created for scheduler...")
        try:
            create_db_tables()
            print("Database tables checked/created successfully.")
        except Exception as e:
            print(f"CRITICAL: Error creating database tables: {e}. Scheduler cannot start. Exiting.")
            sys.exit(1)

        print("Initializing scheduler...")
        scheduler = None
        try:
            scheduler = BlockingScheduler(timezone='Asia/Seoul')
            scheduler.add_job(
                scheduled_job,
                trigger=CronTrigger(hour=22, minute=0, timezone='Asia/Seoul'),
                id='daily_gmail_ingestion_job',
                name='Daily Gmail Ingestion at 22:00 KST',
                replace_existing=True
            )
            # TODO: Add KakaoTalk job to scheduler if desired for automated runs
            # scheduler.add_job(
            #    run_kakaotalk_ingestion_pipeline,
            #    trigger=CronTrigger(hour=22, minute=5, timezone='Asia/Seoul'),
            #    id='daily_kakaotalk_ingestion_job',
            #    name='Daily KakaoTalk Ingestion at 22:05 KST',
            #    replace_existing=True,
            #    args=["default_kakaotalk_user"]
            # )
            print("Scheduler initialized. Starting jobs...")
            scheduler.print_jobs()
            print("Press Ctrl+C to exit scheduler.")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            print("Scheduler shutdown requested...")
        except Exception as e:
            print(f"A critical error occurred with the scheduler: {e}")
        finally:
            if scheduler and scheduler.running:
                print("Attempting to shut down scheduler...")
                scheduler.shutdown()
                print("Scheduler shutdown complete.")
            print("Application exited.")
