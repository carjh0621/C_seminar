import unittest
from unittest.mock import patch, MagicMock, call
import sys
import logging
import datetime # For datetime objects in test and mock returns

# Attempt to import the module to be tested
try:
    from scheduler import jobs as scheduler_jobs
    # This import is primarily to allow patching within scheduler_jobs namespace
except ModuleNotFoundError:
    print("ERROR in tests/test_scheduler.py: Could not import 'scheduler.jobs'.")
    print("Ensure tests are run from project root or PYTHONPATH is correctly set.")
    # Define a comprehensive dummy scheduler_jobs for parsing and basic structure test
    class scheduler_jobs: # type: ignore
        _using_dummy_gmail_pipeline = True
        _using_dummy_kakaotalk_pipeline = True
        _notifier_available = True # Assume available for dummy tests

        # Need a logger instance for the dummy module if its functions use module-level logger
        logger = logging.getLogger(f"agenda_manager.dummy_scheduler_jobs")
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

        @staticmethod
        def scheduled_job():
            scheduler_jobs.logger.info("DUMMY scheduler_jobs.scheduled_job() called.")
            # Simulate calling dummy pipelines
            gmail_res = scheduler_jobs.run_gmail_ingestion_pipeline()
            kakaotalk_res = scheduler_jobs.run_kakaotalk_ingestion_pipeline()
            # Simulate notification attempt with dummy notifier
            if scheduler_jobs._notifier_available:
                notifier = scheduler_jobs.TelegramNotifier()
                notifier.send_message(f"Dummy summary: Gmail: {gmail_res['success']}, Kakao: {kakaotalk_res['success']}")
            scheduler_jobs.logger.info("DUMMY scheduler_jobs.scheduled_job() finished.")


        @staticmethod
        def run_gmail_ingestion_pipeline(app_user_id="default_user"):
            scheduler_jobs.logger.info(f"DUMMY: run_gmail_ingestion_pipeline for {app_user_id}")
            return {"success": True, "source": "Gmail (Dummy)", "tasks_created": 0, "error": None, "items_processed":0}

        @staticmethod
        def run_kakaotalk_ingestion_pipeline(app_user_id="default_user", target_chat_name=None):
            scheduler_jobs.logger.info(f"DUMMY: run_kakaotalk_ingestion_pipeline for {app_user_id}")
            return {"success": True, "source": "KakaoTalk (Dummy)", "tasks_created": 0, "error": None, "items_processed":0}

        class TelegramNotifier: # Dummy Notifier nested for simplicity if jobs.py imports it there
            def __init__(self, *args, **kwargs):
                scheduler_jobs.logger.info("DUMMY TelegramNotifier initialized.")
            def send_message(self, msg_text:str):
                scheduler_jobs.logger.info(f"DUMMY TelegramNotifier would send: {msg_text}")
                return True

        # escape_markdown_v2 and format_pipeline_result_for_notification would also be here if used by dummy scheduled_job
        @staticmethod
        def escape_markdown_v2(text:str) -> str: return text # Dummy
        @staticmethod
        def format_pipeline_result_for_notification(result:dict) -> str: # Dummy
             return f"{result['source']}: {'Success' if result['success'] else 'Failed'}"


class TestSchedulerJobs(unittest.TestCase):

    @patch('scheduler.jobs.TelegramNotifier')
    @patch('scheduler.jobs.run_kakaotalk_ingestion_pipeline')
    @patch('scheduler.jobs.run_gmail_ingestion_pipeline')
    @patch('scheduler.jobs.logger')
    def test_scheduled_job_all_pipelines_succeed(
        self, mock_logger, mock_run_gmail, mock_run_kakaotalk, MockTelegramNotifier
    ):
        mock_notifier_instance = MagicMock()
        MockTelegramNotifier.return_value = mock_notifier_instance

        mock_run_gmail.return_value = {
            "success": True, "source": "Gmail",
            "tasks_created": 2, "items_processed": 10, "error": None
        }
        mock_run_kakaotalk.return_value = {
            "success": True, "source": "KakaoTalk (Experimental)",
            "tasks_created": 1, "items_processed": 5, "error": None
        }

        scheduler_jobs.scheduled_job()

        mock_run_gmail.assert_called_once_with(app_user_id="default_gmail_user")
        mock_run_kakaotalk.assert_called_once_with(app_user_id="default_kakaotalk_user")

        MockTelegramNotifier.assert_called_once()
        mock_notifier_instance.send_message.assert_called_once()

        sent_message = mock_notifier_instance.send_message.call_args[0][0]

        self.assertIn("✅ *Agenda Manager Run Summary*", sent_message)
        self.assertIn("Status: All pipelines ran successfully\\.", sent_message)
        self.assertIn("✅ \\*Gmail\\*: Succeeded", sent_message)
        self.assertIn("✅ \\*KakaoTalk \\(Experimental\\)\\*: Succeeded", sent_message)


    @patch('scheduler.jobs.TelegramNotifier')
    @patch('scheduler.jobs.run_kakaotalk_ingestion_pipeline')
    @patch('scheduler.jobs.run_gmail_ingestion_pipeline')
    @patch('scheduler.jobs.logger')
    def test_scheduled_job_one_pipeline_fails(
        self, mock_logger, mock_run_gmail, mock_run_kakaotalk, MockTelegramNotifier
    ):
        mock_notifier_instance = MagicMock()
        MockTelegramNotifier.return_value = mock_notifier_instance

        mock_run_gmail.return_value = {
            "success": True, "source": "Gmail",
            "tasks_created": 1, "items_processed": 5, "error": None
        }
        mock_run_kakaotalk.return_value = {
            "success": False, "source": "KakaoTalk (Experimental)",
            "tasks_created": 0, "items_processed": 2, "error": "Simulated KT Connection Error"
        }

        scheduler_jobs.scheduled_job()

        mock_notifier_instance.send_message.assert_called_once()
        sent_message = mock_notifier_instance.send_message.call_args[0][0]

        self.assertIn("🔶 *Agenda Manager Run Summary*", sent_message)
        self.assertIn("Status: 1 succeeded, 1 failed\\.", sent_message)
        self.assertIn("✅ \\*Gmail\\*: Succeeded", sent_message)
        self.assertIn("⚠️ \\*KakaoTalk \\(Experimental\\)\\*: Failed \\(Error: _Simulated KT Connection Error_\\)", sent_message)

    @patch('scheduler.jobs.TelegramNotifier')
    @patch('scheduler.jobs.run_kakaotalk_ingestion_pipeline')
    @patch('scheduler.jobs.run_gmail_ingestion_pipeline')
    @patch('scheduler.jobs.logger')
    def test_scheduled_job_all_pipelines_fail(
        self, mock_logger, mock_run_gmail, mock_run_kakaotalk, MockTelegramNotifier
    ):
        mock_notifier_instance = MagicMock()
        MockTelegramNotifier.return_value = mock_notifier_instance

        mock_run_gmail.return_value = {
            "success": False, "source": "Gmail",
            "tasks_created": 0, "items_processed": 0, "error": "Gmail Auth Error"
        }
        mock_run_kakaotalk.return_value = {
            "success": False, "source": "KakaoTalk (Experimental)",
            "tasks_created": 0, "items_processed": 0, "error": "KT Generic Error"
        }

        scheduler_jobs.scheduled_job()

        mock_notifier_instance.send_message.assert_called_once()
        sent_message = mock_notifier_instance.send_message.call_args[0][0]

        self.assertIn("❌ *Agenda Manager Run Summary*", sent_message)
        self.assertIn("Status: All pipelines failed\\.", sent_message)
        self.assertIn("⚠️ \\*Gmail\\*: Failed \\(Error: _Gmail Auth Error_\\)", sent_message)
        self.assertIn("⚠️ \\*KakaoTalk \\(Experimental\\)\\*: Failed \\(Error: _KT Generic Error_\\)", sent_message)

    @patch('scheduler.jobs._notifier_available', False)
    @patch('scheduler.jobs.run_kakaotalk_ingestion_pipeline')
    @patch('scheduler.jobs.run_gmail_ingestion_pipeline')
    @patch('scheduler.jobs.logger')
    def test_scheduled_job_notifier_not_available(
        self, mock_logger, mock_run_gmail, mock_run_kakaotalk
    ):
        mock_run_gmail.return_value = {"success": True, "source": "Gmail", "tasks_created": 0, "error": None, "items_processed":0}
        mock_run_kakaotalk.return_value = {"success": True, "source": "KakaoTalk", "tasks_created": 0, "error": None, "items_processed":0}

        # Patch TelegramNotifier within the scope of this test, even if _notifier_available is False,
        # to ensure it's not called if the flag is correctly handled.
        with patch('scheduler.jobs.TelegramNotifier', MagicMock()) as MockedNotifierClassInTest:
            scheduler_jobs.scheduled_job()
            MockedNotifierClassInTest.assert_not_called()

        # Verify logger warning about notifier unavailability
        # This requires checking the calls made to the mocked logger instance
        log_messages = [call_arg[0][0] for call_arg in mock_logger.warning.call_args_list]
        self.assertTrue(any("Notification system not available. Skipping consolidated notification." in msg for msg in log_messages))


if __name__ == '__main__':
    # This allows running this test file directly, e.g., `python tests/test_scheduler.py`
    # For imports to work correctly, ensure project root is in PYTHONPATH or run as module.
    unittest.main()
