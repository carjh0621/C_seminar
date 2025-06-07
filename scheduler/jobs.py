# scheduler/jobs.py
import datetime
import sys
import logging
import re # For Markdown escaping

# --- Logger for this module ---
logger = logging.getLogger(f"agenda_manager.{__name__}")


# --- Import Pipeline Functions (with fallbacks) ---
_using_dummy_gmail_pipeline = False
try:
    from main import run_gmail_ingestion_pipeline
    logger.info("Successfully imported 'run_gmail_ingestion_pipeline' from main.")
except ImportError as e:
    logger.error(f"Failed to import 'run_gmail_ingestion_pipeline' from main: {e}. Using DUMMY.")
    _using_dummy_gmail_pipeline = True
    def run_gmail_ingestion_pipeline(app_user_id="default_user"):
        logger.info(f"DUMMY: run_gmail_ingestion_pipeline called for {app_user_id}")
        if app_user_id == "fail_gmail":
            logger.warning("DUMMY: Simulating Gmail pipeline failure as requested.")
            raise Exception("Simulated Gmail pipeline failure")
        logger.info("DUMMY: Gmail pipeline finished successfully.")
        return {"success": True, "source": "Gmail (Dummy)", "tasks_created": 0, "processed_items": 0, "error": None}

_using_dummy_kakaotalk_pipeline = False
try:
    from main import run_kakaotalk_ingestion_pipeline
    logger.info("Successfully imported 'run_kakaotalk_ingestion_pipeline' from main.")
except ImportError as e:
    logger.error(f"Failed to import 'run_kakaotalk_ingestion_pipeline' from main: {e}. Using DUMMY.")
    _using_dummy_kakaotalk_pipeline = True
    def run_kakaotalk_ingestion_pipeline(app_user_id="default_user", target_chat_name=None):
        logger.info(f"DUMMY: run_kakaotalk_ingestion_pipeline for user '{app_user_id}', chat '{target_chat_name}'.")
        if app_user_id == "fail_kakaotalk":
            logger.warning("DUMMY: Simulating KakaoTalk pipeline failure as requested.")
            raise Exception("Simulated KakaoTalk pipeline failure")
        logger.info("DUMMY: KakaoTalk pipeline finished successfully.")
        return {"success": True, "source": "KakaoTalk (Dummy)", "tasks_created": 0, "processed_items": 0, "error": None}
# --- End Pipeline Imports ---


# --- Import Notifier (with fallback) ---
_notifier_available = False
try:
    from notifier.bots import TelegramNotifier
    _notifier_available = True
    logger.info("Successfully imported TelegramNotifier for scheduler jobs.")
except ImportError as e:
    logger.warning(f"Failed to import 'TelegramNotifier': {e}. Notifications will be disabled in scheduler jobs.")
    class TelegramNotifier:
        def __init__(self, *args, **kwargs): logger.info("DUMMY TelegramNotifier: Initialized for scheduler jobs.")
        def send_message(self, message_text: str) -> bool:
            logger.info(f"DUMMY TelegramNotifier: Would send '{message_text}'. Returning True.")
            return True
# --- End Notifier Import ---

def escape_markdown_v2(text: str) -> str:
    """Escapes text for Telegram MarkdownV2.
    Order matters for some escape sequences.
    """
    if not isinstance(text, str): # Ensure text is a string
        text = str(text)
    # Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # Note: '.' and '!' only need escaping if they are the last char of a sentence for some clients,
    # or could be part of other markdown syntax. For simplicity, escape them generally.
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # Use re.escape to handle special characters in the pattern itself, then replace.
    # This loop ensures that already escaped characters are not double-escaped if this func is called multiple times.
    # However, for a single pass, direct replacement is fine.
    # For robust escaping, iterate and replace each char:
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_pipeline_result_for_notification(result: dict) -> str:
    """Formats a single pipeline result for the notification message.
       Returns a MarkdownV2 formatted string line.
    """
    status_emoji = "✅" if result.get("success") else "⚠️"
    source_name = escape_markdown_v2(result.get("source", "Unknown Source"))

    # TODO: Update when pipelines return actual 'tasks_created' and 'processed_items'
    # tasks_info = f", Tasks: {result.get('tasks_created', 'N/A')}" if result.get("success") else ""
    # processed_info = f", Items: {result.get('processed_items', 'N/A')}"
    # For now, simpler message:
    tasks_info = "" # No tasks_created info yet from pipelines
    processed_info = "" # No processed_items info yet

    details = f"{status_emoji} *{source_name}*: {'Succeeded' if result.get('success') else 'Failed'}"

    if not result.get("success") and result.get("error"):
        error_msg_short = escape_markdown_v2(
            (str(result["error"])[:70] + '...') if len(str(result["error"])) > 70 else str(result["error"])
        )
        details += f" \\(Error: _{error_msg_short}_\\)" # Escape parentheses for MD
    # elif result.get("success"):
    #     details += f"{escape_markdown_v2(processed_info)}{escape_markdown_v2(tasks_info)}"
    return details


def scheduled_job():
    """
    The job function executed by the scheduler.
    Runs all configured ingestion pipelines and sends a summary notification.
    """
    current_time_start_obj = datetime.datetime.now()
    kst_display_tz_name = "KST" # For display purposes
    current_time_start_str = current_time_start_obj.strftime(f"%Y-%m-%d %H:%M:%S {kst_display_tz_name}")
    logger.info(f"Scheduler job started at {current_time_start_str}: Running all ingestion pipelines...")

    pipeline_results = []

    # --- Run Gmail Pipeline ---
    gmail_user_id = "default_gmail_user"
    logger.info(f"Starting Gmail pipeline for user: {gmail_user_id}...")
    try:
        # Actual pipeline functions in main.py currently do not return structured results.
        # This will be assumed success if no exception, and counts will be "N/A".
        # The dummy functions do return a dict, so we handle that.
        gmail_result_data = run_gmail_ingestion_pipeline(app_user_id=gmail_user_id)
        if isinstance(gmail_result_data, dict) and "success" in gmail_result_data:
             pipeline_results.append(gmail_result_data)
        else: # Real pipeline (no return value yet) or unexpected return
             pipeline_results.append({"success": True, "source": "Gmail", "tasks_created": "N/A", "processed_items": "N/A", "error": None})
        logger.info("Gmail pipeline finished successfully.")
    except Exception as e:
        logger.error(f"Error during Gmail pipeline execution: {e}", exc_info=True)
        pipeline_results.append({"success": False, "source": "Gmail", "tasks_created": 0, "processed_items": 0, "error": str(e)})

    # --- Run KakaoTalk Pipeline ---
    kakaotalk_user_id = "default_kakaotalk_user"
    logger.info(f"Starting KakaoTalk pipeline (experimental) for user: {kakaotalk_user_id}...")
    try:
        kakaotalk_result_data = run_kakaotalk_ingestion_pipeline(app_user_id=kakaotalk_user_id)
        if isinstance(kakaotalk_result_data, dict) and "success" in kakaotalk_result_data:
            pipeline_results.append(kakaotalk_result_data)
        else:
            pipeline_results.append({"success": True, "source": "KakaoTalk (Experimental)", "tasks_created": "N/A", "processed_items": "N/A", "error": None})
        logger.info("KakaoTalk pipeline finished successfully (experimental).")
    except Exception as e:
        logger.error(f"Error during KakaoTalk pipeline execution: {e}", exc_info=True)
        pipeline_results.append({"success": False, "source": "KakaoTalk (Experimental)", "tasks_created": 0, "processed_items": 0, "error": str(e)})

    # --- Consolidate Results and Send Notification ---
    current_time_end_obj = datetime.datetime.now()
    current_time_end_str = current_time_end_obj.strftime(f"%Y-%m-%d %H:%M:%S {kst_display_tz_name}")
    logger.info(f"All ingestion pipelines complete at {current_time_end_str}.")

    if _notifier_available:
        logger.info("Preparing consolidated notification...")

        num_successful = sum(1 for r in pipeline_results if r.get("success"))
        num_failed = len(pipeline_results) - num_successful

        overall_status_emoji = "✅" if num_failed == 0 else ("🔶" if num_successful > 0 else "❌")
        overall_status_text = "All pipelines ran successfully\\." # Escaped period
        if num_failed > 0 and num_successful > 0:
            overall_status_text = f"{num_successful} succeeded, {num_failed} failed\\."
        elif num_failed > 0 and num_successful == 0:
            overall_status_text = "All pipelines failed\\."

        escaped_start_time = escape_markdown_v2(current_time_start_str)
        escaped_end_time = escape_markdown_v2(current_time_end_str)

        message_lines = [
            f"{overall_status_emoji} *Agenda Manager Run Summary*",
            f"  🕒 Started: {escaped_start_time}",
            f"  🏁 Finished: {escaped_end_time}",
            f"  📊 Status: {overall_status_text}", # Already escaped
            "" # Newline
        ]

        if pipeline_results:
            message_lines.append("*Pipeline Details:*")
            for result in pipeline_results:
                message_lines.append(f"  {format_pipeline_result_for_notification(result)}")
        else:
            message_lines.append("No pipelines were configured to run or results are unavailable\\.")

        final_message = "\n".join(message_lines)

        try:
            notifier = TelegramNotifier()
            notif_success = notifier.send_message(final_message)
            if notif_success:
                logger.info("Consolidated notification sent successfully via Telegram.")
            else:
                logger.warning("Failed to send consolidated Telegram notification (see notifier logs).")
        except ValueError as ve:
             logger.error(f"Failed to initialize TelegramNotifier for consolidated message: {ve}", exc_info=True)
        except Exception as e_notif:
            logger.error(f"Unexpected error sending consolidated Telegram notification: {e_notif}", exc_info=True)
    else:
        logger.warning("Telegram notification system not available. Skipping consolidated notification.")


if __name__ == '__main__':
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO,
                            format='%(asctime)s - [%(name)s] %(levelname)s - %(message)s', # Added logger name to format
                            handlers=[logging.StreamHandler(sys.stdout)])

    logger.info("Directly testing scheduled_job()...")
    scheduled_job()
    logger.info("\nDirect test of scheduled_job() complete.")
