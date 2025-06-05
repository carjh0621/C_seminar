# scheduler/jobs.py
import datetime
import sys

# --- Import Pipeline Function ---
_using_dummy_pipeline = False # Flag to indicate if dummy pipeline is used
try:
    from main import run_gmail_ingestion_pipeline
except ImportError as e:
    print(f"Error importing 'run_gmail_ingestion_pipeline' from main: {e}")
    print("Using DUMMY pipeline function for scheduler.jobs.")
    _using_dummy_pipeline = True
    def run_gmail_ingestion_pipeline(app_user_id="default_user"): # Dummy
        print(f"DUMMY: run_gmail_ingestion_pipeline called for {app_user_id}")
        if app_user_id == "simulate_pipeline_failure": # Specific user ID to test failure path
            raise Exception("Simulated DUMMY pipeline failure")
        print("DUMMY: Pipeline finished successfully.")
        return True # Simulate success
# --- End Pipeline Import ---

# --- Import Notifier ---
_notifier_available = False # Flag to indicate if real notifier is available
try:
    from notifier.bots import TelegramNotifier
    _notifier_available = True
    print("Successfully imported TelegramNotifier.")
except ImportError as e:
    print(f"Error importing 'TelegramNotifier' from notifier.bots: {e}")
    print("Telegram notifications will be disabled for this scheduler run (using DUMMY Notifier).")
    class TelegramNotifier: # Dummy Notifier if import fails
        def __init__(self, *args, **kwargs):
            print("DUMMY TelegramNotifier initialized because real one failed to import or is misconfigured.")
        def send_message(self, message_text: str) -> bool:
            print(f"DUMMY TelegramNotifier: Would send message: '{message_text[:100]}...'. Returning True as placeholder.")
            return True # Simulate success for testing flow
# --- End Notifier Import ---


def scheduled_job(simulate_failure_for_user: str = None):
    """
    The job function that will be executed by the scheduler.
    Calls the main Gmail ingestion pipeline and sends a notification.
    Args:
        simulate_failure_for_user: If set to a user_id, and dummy pipeline is active,
                                   will simulate a failure for that user.
    """
    current_time_start_obj = datetime.datetime.now()
    current_time_start_str = current_time_start_obj.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time_start_str}] Scheduler job started: Running Gmail ingestion pipeline...")

    pipeline_success = False
    pipeline_error_message = None
    job_end_time_str = current_time_start_str # Initialize with start time

    try:
        # Define the user for whom the pipeline should run.
        target_user_id = simulate_failure_for_user if simulate_failure_for_user and _using_dummy_pipeline else "default_gmail_user"

        run_gmail_ingestion_pipeline(app_user_id=target_user_id)
        pipeline_success = True
        job_end_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if _using_dummy_pipeline:
            print(f"[{job_end_time_str}] Scheduler job finished (using DUMMY Gmail pipeline).")
        else:
            print(f"[{job_end_time_str}] Scheduler job finished successfully (Gmail pipeline).")

    except Exception as e:
        pipeline_success = False
        pipeline_error_message = str(e)
        job_end_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{job_end_time_str}] Error during scheduled job (Gmail pipeline execution): {e}")

    # --- Send Notification ---
    if _notifier_available:
        print("Attempting to send notification via Telegram...")
        try:
            # Notifier will use token/chat_id from config.py or environment variables
            notifier = TelegramNotifier()

            timestamp_for_notif = job_end_time_str.split(" ")[1] # Extract HH:MM:SS

            if pipeline_success:
                if _using_dummy_pipeline:
                    message = f"✅ Agenda Manager (Dummy Pipeline) finished successfully at {timestamp_for_notif} KST."
                else:
                    message = f"✅ Agenda Manager pipeline finished successfully at {timestamp_for_notif} KST."
            else:
                error_summary = (pipeline_error_message[:75] + '...') if pipeline_error_message and len(pipeline_error_message) > 75 else pipeline_error_message
                if _using_dummy_pipeline:
                    message = f"⚠️ Agenda Manager (Dummy Pipeline) encountered an error at {timestamp_for_notif} KST: {error_summary or 'Unknown error'}"
                else:
                    message = f"⚠️ Agenda Manager pipeline failed at {timestamp_for_notif} KST. Error: {error_summary or 'Unknown error'}"

            # Escape MarkdownV2 special characters for the message to be sent
            # For simplicity, this example does not include a full MarkdownV2 escaper.
            # Characters like '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
            # need to be escaped with a preceding '\' if they are part of the literal text.
            # Example: "Error: Something went wrong." -> "Error: Something went wrong\\."
            # For now, we send it as is, assuming simple error messages or that the library handles some cases.
            # A proper escaper function should be used for arbitrary text.

            notif_success = notifier.send_message(message) # Assumes message is MarkdownV2 compatible
            if notif_success:
                print("Notification sent successfully via Telegram.")
            else:
                print("Failed to send Telegram notification (see notifier logs for details).")
        except ValueError as ve:
             print(f"Failed to initialize TelegramNotifier (configuration error): {ve}. Notification not sent.")
        except Exception as e:
            print(f"An unexpected error occurred while attempting to send Telegram notification: {e}")
    else:
        print("Telegram notification system not available (import failed or disabled). Skipping notification.")


if __name__ == '__main__':
    print("Directly testing scheduled_job() with notification logic...")

    # Test success path
    print("\n--- Testing SUCCESS notification path ---")
    # To ensure it doesn't use the failure simulation of dummy:
    if hasattr(scheduler_jobs, '_using_dummy_pipeline') and scheduler_jobs._using_dummy_pipeline:
         print("(Note: Using dummy pipeline for this test run as real one failed to import in jobs.py)")
    scheduled_job()

    # Test failure path (if dummy pipeline is active and can simulate failure)
    if hasattr(scheduler_jobs, '_using_dummy_pipeline') and scheduler_jobs._using_dummy_pipeline:
        print("\n--- Testing FAILURE notification path (using dummy pipeline) ---")
        scheduled_job(simulate_failure_for_user="simulate_pipeline_failure")
    else:
        print("\nSkipping FAILURE notification path test as it relies on configurable dummy pipeline failure.")

    print("\nDirect test of scheduled_job() complete.")
