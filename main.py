from datetime import datetime, timedelta, time as dt_time, date
import sys
import time
import typer
from typing import Dict, Any, Optional # Ensure Dict, Any, Optional are imported

# APScheduler Imports
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Project module imports
from ingestion.agents import GmailAgent, KakaoAgent
from preprocessing.normalizer import normalize as normalize_text
from extract_nlp.classifiers import TaskClassifier, resolve_date
from extract_nlp.utils import generate_task_fingerprint
from openai import OpenAIError

from persistence.database import SessionLocal, create_db_tables
from persistence import crud as persistence_crud
from persistence.models import TaskStatus

from scheduler.jobs import scheduled_job
from cli.main_cli import app as cli_app

from playwright.sync_api import sync_playwright, Playwright, PlaywrightError


def run_gmail_ingestion_pipeline(app_user_id: str = "default_user") -> Dict[str, Any]:
    result_summary = {
        "success": False, "source": "Gmail",
        "items_processed": 0, "tasks_created": 0, "error": None
    }
    print(f"Starting Gmail ingestion pipeline for user: {app_user_id}...")

    gmail_agent = GmailAgent(credentials_file='credentials.json')
    gmail_service = None
    try:
        gmail_service = gmail_agent.authenticate_gmail(app_user_id=app_user_id)
        if not gmail_service:
            error_msg = f"Gmail authentication failed for user {app_user_id}."
            print(error_msg); result_summary["error"] = error_msg
            return result_summary
        print("Gmail authentication successful.")
    except Exception as e:
        error_msg = f"Critical error during Gmail authentication: {e}"
        print(error_msg); result_summary["error"] = error_msg
        return result_summary

    task_classifier = None
    try:
        print("Initializing TaskClassifier...")
        task_classifier = TaskClassifier()
        print("TaskClassifier initialized successfully.")
    except Exception as e:
        error_msg = f"Error initializing TaskClassifier for Gmail pipeline: {e}"
        print(error_msg); result_summary["error"] = error_msg
        return result_summary

    today_date = date.today()
    yesterday_date = today_date - timedelta(days=1)
    since_date_str_for_gmail = yesterday_date.strftime("%Y/%m/%d")

    print(f"Fetching Gmail emails after: {since_date_str_for_gmail}")
    fetched_emails = gmail_agent.fetch_messages(since_date_str=since_date_str_for_gmail, max_results=500)
    result_summary["items_processed"] = len(fetched_emails)

    if not fetched_emails:
        print("No new emails found for today (Gmail).")
        result_summary["success"] = True
        return result_summary
    print(f"Fetched {len(fetched_emails)} emails from Gmail.")

    db = SessionLocal()
    normalizer_func = normalize_text
    date_resolver_func = resolve_date

    try:
        for i, email_data in enumerate(fetched_emails):
            print(f"\nProcessing Gmail email {i+1}/{len(fetched_emails)}: ID {email_data['id']}, Subject: '{email_data['headers'].get('subject', 'N/A')[:60]}...'")
            content_to_process = ""
            content_type_for_normalizer = "text/plain"
            if email_data.get('body_plain', "").strip():
                content_to_process = email_data['body_plain']
            elif email_data.get('body_html', "").strip():
                content_to_process = email_data['body_html']
                content_type_for_normalizer = "text/html"
            elif email_data.get('snippet', "").strip():
                content_to_process = email_data['snippet']
            else:
                print("Email body/snippet empty. Skipping."); continue
            if not content_to_process.strip():
                 print("Content empty after selection. Skipping."); continue

            normalized_content = normalizer_func(content_to_process, content_type=content_type_for_normalizer)
            task_source_id = f"gmail_{email_data['id']}"
            task_title_from_llm = None
            classification_result = task_classifier.classify_task(normalized_content, source_id=task_source_id)
            if not classification_result:
                print(f"No task classified for email ID {email_data['id']}."); continue
            task_title_from_llm = classification_result['title']

            due_datetime = None
            if classification_result.get('due'):
                due_datetime = date_resolver_func(classification_result['due'])

            task_fingerprint = None
            if task_title_from_llm:
                try: task_fingerprint = generate_task_fingerprint(task_title_from_llm, due_datetime)
                except ValueError as ve: print(f"FP Gen Error: {ve}")
                except Exception as e_fp: print(f"Unexpected FP Gen Error: {e_fp}")

            if task_fingerprint:
                existing_task = persistence_crud.get_task_by_fingerprint(db, task_fingerprint)
                if existing_task:
                    print(f"Duplicate task (ID: {existing_task.id}) by FP. Skipping."); continue

            task_data_for_db = {
                "source": task_source_id, "title": task_title_from_llm,
                "body": classification_result.get('body', normalized_content[:1000]),
                "due_dt": due_datetime, "created_dt": datetime.utcnow(),
                "status": TaskStatus.TODO, "fingerprint": task_fingerprint, "tags": None,
                "type": classification_result.get('type', 'gmail_task')
            }
            newly_created_task_obj = None
            try:
                newly_created_task_obj = persistence_crud.create_task(db, task_data_for_db)
                result_summary["tasks_created"] += 1
            except Exception as e_save:
                db.rollback(); print(f"Error saving task: {e_save}"); continue

            if newly_created_task_obj and newly_created_task_obj.due_dt and \
               newly_created_task_obj.due_dt.time() != dt_time(0,0,0):
                task_date_cdt = newly_created_task_obj.due_dt.date()
                potential_conflicts_cdt = persistence_crud.get_tasks_on_same_day_with_time(
                    db, task_date_cdt, exclude_task_id=newly_created_task_obj.id)
                conflict_window_cdt = timedelta(hours=1)
                for existing_task_cdt in potential_conflicts_cdt:
                    if existing_task_cdt.due_dt:
                        if abs(newly_created_task_obj.due_dt - existing_task_cdt.due_dt) < conflict_window_cdt:
                            updated_task_cdt = persistence_crud.update_task_tags(db, newly_created_task_obj.id, "#conflict")
                            if updated_task_cdt: newly_created_task_obj = updated_task_cdt
                            persistence_crud.update_task_tags(db, existing_task_cdt.id, "#conflict")
        result_summary["success"] = True
    except Exception as e_pipeline:
        error_msg = f"Error during Gmail email processing loop: {e_pipeline}"
        print(error_msg); result_summary["error"] = error_msg
    finally:
        if 'db' in locals() and db.is_active:
            db.close()
            print("Gmail pipeline DB session closed.")

    print(f"Gmail ingestion pipeline finished. Tasks created: {result_summary['tasks_created']}")
    return result_summary


def run_kakaotalk_ingestion_pipeline(
    app_user_id: str = "default_kakaotalk_user",
    target_chat_name: Optional[str] = None
) -> Dict[str, Any]:
    result_summary = {
        "success": False, "source": "KakaoTalk (Experimental)",
        "items_processed": 0, "tasks_created": 0, "error": None
    }
    print(f"\n--- Starting KakaoTalk Ingestion Pipeline for user: {app_user_id} ---")

    try:
        from config import KAKAOTALK_CHAT_NAME_TO_MONITOR, KAKAOTALK_USER_DATA_DIR
    except ImportError:
        result_summary["error"] = "KakaoTalk config import failed (KAKAOTALK_CHAT_NAME_TO_MONITOR or KAKAOTALK_USER_DATA_DIR missing from config.py)."
        print(f"Error: {result_summary['error']}")
        return result_summary

    effective_target_chat_name = target_chat_name or KAKAOTALK_CHAT_NAME_TO_MONITOR
    if not effective_target_chat_name or effective_target_chat_name == "My Notes Chat": # Default placeholder check
        print(f"Warning: KAKAOTALK_CHAT_NAME_TO_MONITOR is not configured or is set to default ('{effective_target_chat_name}').")
        # In a non-interactive pipeline, we might not use typer.confirm.
        # Decide to proceed or not based on a stricter check or allow placeholder for testing.
        # For now, let's assume if it's the placeholder, it's an error for an automated run.
        if effective_target_chat_name == "My Notes Chat" or not effective_target_chat_name:
             result_summary["error"] = f"Target KakaoTalk chat name is not properly configured (current: '{effective_target_chat_name}')."
             print(f"Error: {result_summary['error']}")
             return result_summary # Stop if not configured for a specific chat
    print(f"Target KakaoTalk chat room: '{effective_target_chat_name}'")

    kakao_agent_instance: Optional[KakaoAgent] = None
    try:
        with sync_playwright() as p_instance:
            kakao_agent_instance = KakaoAgent(playwright_instance=p_instance, user_data_dir=KAKAOTALK_USER_DATA_DIR)
            if not kakao_agent_instance.login():
                result_summary["error"] = "KakaoTalk login/setup failed by agent."
                print(result_summary["error"]); return result_summary # kakao_agent.close() is in finally
            if not kakao_agent_instance.select_chat(effective_target_chat_name):
                result_summary["error"] = f"Failed to select KakaoTalk chat: '{effective_target_chat_name}'."
                print(result_summary["error"]); return result_summary

            fetched_messages = kakao_agent_instance.read_messages(num_messages_to_capture=20) # Dummy messages for now
            result_summary["items_processed"] = len(fetched_messages)
            if not fetched_messages:
                print("No new messages fetched from KakaoTalk."); result_summary["success"] = True; return result_summary
            print(f"Fetched {len(fetched_messages)} messages from KakaoTalk.")

            task_classifier_instance = None
            try:
                task_classifier_instance = TaskClassifier()
                print("TaskClassifier initialized for KakaoTalk pipeline.")
            except Exception as e_tc:
                result_summary["error"] = f"TaskClassifier init failed for KakaoTalk: {e_tc}"
                print(result_summary["error"]); return result_summary

            db_session = SessionLocal()
            normalizer_func = normalize_text
            date_resolver_func = resolve_date
            try:
                for i, msg_data in enumerate(fetched_messages):
                    print(f"\nProcessing KakaoTalk message {i+1}/{len(fetched_messages)}: ID {msg_data.get('id', 'N/A')}")
                    content_to_process = msg_data.get("text", "")
                    if not content_to_process.strip(): print("Message text empty. Skipping."); continue

                    normalized_content = normalizer_func(content_to_process, content_type="text/plain")
                    task_source_id = f"kakaotalk_{effective_target_chat_name}_{msg_data.get('id', f'msgidx{i}')}"
                    task_title_from_llm = None
                    classification_result = task_classifier_instance.classify_task(normalized_content, source_id=task_source_id)
                    if not classification_result: print(f"No task classified for Kakao msg ID {msg_data.get('id', 'N/A')}."); continue
                    task_title_from_llm = classification_result['title']

                    due_datetime = resolve_date(classification_result.get('due')) if classification_result.get('due') else None

                    task_fingerprint = None
                    if task_title_from_llm:
                        try: task_fingerprint = generate_task_fingerprint(task_title_from_llm, due_datetime)
                        except Exception: pass

                    if task_fingerprint and persistence_crud.get_task_by_fingerprint(db_session, task_fingerprint):
                        print(f"Duplicate Kakao task by FP. Skipping."); continue

                    task_data = {
                        "source": task_source_id, "title": task_title_from_llm,
                        "body": classification_result.get('body', normalized_content[:1000]),
                        "due_dt": due_datetime, "created_dt": datetime.utcnow(),
                        "status": TaskStatus.TODO, "fingerprint": task_fingerprint, "tags": None,
                        "type": classification_result.get('type', 'kakaotalk_task')
                    }
                    newly_created_task_obj = None
                    try:
                        newly_created_task_obj = persistence_crud.create_task(db_session, task_data)
                        result_summary["tasks_created"] += 1
                    except Exception as e_save:
                        db_session.rollback(); print(f"Error saving Kakao task: {e_save}"); continue

                    if newly_created_task_obj and newly_created_task_obj.due_dt and \
                       newly_created_task_obj.due_dt.time() != dt_time(0,0,0):
                        # Simplified conflict detection call for brevity in this example
                        persistence_crud.update_task_tags(db_session, newly_created_task_obj.id, "#conflict_check_needed_kakao")
                result_summary["success"] = True
            finally:
                if 'db_session' in locals() and db_session.is_active:
                    db_session.close()
                    print("KakaoTalk pipeline DB session closed.")
    except PlaywrightError as e_pw:
        result_summary["error"] = f"Playwright error in KakaoTalk pipeline: {e_pw}"
        print(result_summary["error"])
    except ImportError as e_imp:
        result_summary["error"] = f"ImportError in KakaoTalk pipeline (check config): {e_imp}"
        print(result_summary["error"])
    except Exception as e_main:
        result_summary["error"] = f"Unexpected error in KakaoTalk pipeline: {e_main}"
        print(result_summary["error"])
        import traceback; traceback.print_exc()
    finally:
        if kakao_agent_instance:
            print("Closing KakaoAgent resources...")
            kakao_agent_instance.close()

    print(f"KakaoTalk ingestion pipeline finished. Tasks created: {result_summary['tasks_created']}. Error: {result_summary['error']}")
    return result_summary

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
                id='daily_full_ingestion_job', # Renamed for clarity
                name='Daily Full Ingestion Run (Gmail, KakaoTalk) at 22:00 KST', # Updated name
                replace_existing=True
            )
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
