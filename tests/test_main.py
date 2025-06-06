import unittest
from unittest.mock import patch, MagicMock, ANY
from datetime import date, timedelta, datetime as dt # dt for datetime objects

# Modules to be tested or mocked
try:
    from main import run_gmail_ingestion_pipeline
    # If main.py imports other project modules directly at top level,
    # those might need mocking too if they have side effects on import or are slow.
except ModuleNotFoundError:
    print("CRITICAL: Could not import 'main.run_gmail_ingestion_pipeline' for testing in test_main.py.")
    # Define a dummy function if import fails for test runner parsing
    def run_gmail_ingestion_pipeline(app_user_id="default_user"):
        print(f"DUMMY run_gmail_ingestion_pipeline called for {app_user_id} due to import error in test_main.py")
        pass

class TestMainPipelineGmailFetching(unittest.TestCase):

    # Patching order is bottom-up for decorators.
    # Patches should target where the object is *looked up*, which is in 'main' module's namespace.
    @patch('main.date') # Mock datetime.date for controlling date.today()
    @patch('main.GmailAgent') # Mock the GmailAgent class imported in main.py
    @patch('main.TaskClassifier') # Mock TaskClassifier imported in main.py
    @patch('main.persistence_crud') # Mock persistence_crud module imported in main.py
    @patch('main.SessionLocal') # Mock SessionLocal imported in main.py
    # create_db_tables is not called by run_gmail_ingestion_pipeline directly,
    # so not strictly needed here unless testing __main__ block of main.py
    # @patch('main.create_db_tables')
    def test_run_gmail_pipeline_fetches_todays_emails(
        self, mock_session_local, mock_crud_main, MockTaskClassifier,
        MockGmailAgent, mock_date_main
    ):
        # 1. Setup Mocks

        # Mock datetime.date.today() to return a fixed date
        fixed_today = date(2024, 3, 15)
        mock_date_main.today.return_value = fixed_today
        # If main.py uses `from datetime import date` and then `date.today()` this works.
        # If it uses `datetime.date.today()`, then `main.datetime.date.today` needs mocking.
        # Assuming `from datetime import date` is used in main.py based on provided code.

        # Prepare mock instances for Agent and its methods
        mock_agent_instance = MagicMock()
        MockGmailAgent.return_value = mock_agent_instance

        mock_auth_service = MagicMock()
        mock_agent_instance.authenticate_gmail.return_value = mock_auth_service

        # Simulate fetch_messages returning a list with one dummy email
        mock_agent_instance.fetch_messages.return_value = [
            {'id': 'email1', 'headers': {'subject': 'Test Email Today'}, 'body_plain': 'Test content for today'}
        ]

        # Mock TaskClassifier instance and its method
        mock_classifier_instance = MagicMock()
        MockTaskClassifier.return_value = mock_classifier_instance
        mock_classifier_instance.classify_task.return_value = {
            "type": "test", "title": "Test Task from Email Today", "due": None, "body": "Test content today",
            "source_id": "gmail_email1", "confidence": 0.9
        }

        # Mock CRUD operations used after fetching
        mock_crud_main.create_task.return_value = MagicMock(id=1, fingerprint="fp_test_main")
        mock_crud_main.get_task_by_fingerprint.return_value = None
        # Mock for conflict detection part
        mock_crud_main.get_tasks_on_same_day_with_time.return_value = []
        mock_crud_main.update_task_tags.return_value = MagicMock()


        # Mock SessionLocal to return a mock session
        mock_db_session_instance = MagicMock()
        mock_session_local.return_value = mock_db_session_instance

        # 2. Call the pipeline function
        run_gmail_ingestion_pipeline(app_user_id="test_user_today")

        # 3. Assertions

        MockGmailAgent.assert_called_once_with(credentials_file='credentials.json')
        mock_agent_instance.authenticate_gmail.assert_called_once_with(app_user_id="test_user_today")

        # Calculate expected since_date_str based on mocked 'today'
        expected_yesterday = fixed_today - timedelta(days=1)
        expected_since_str = expected_yesterday.strftime("%Y/%m/%d")

        mock_agent_instance.fetch_messages.assert_called_once_with(
            since_date_str=expected_since_str,
            max_results=500
        )

        # Verify TaskClassifier was called because emails were "fetched"
        MockTaskClassifier.assert_called_once()
        mock_classifier_instance.classify_task.assert_called()

        # Verify DB session handling and task creation attempt
        mock_session_local.assert_called_once() # Check that a session was initiated
        mock_crud_main.create_task.assert_called()
        mock_db_session_instance.close.assert_called_once() # Check session was closed


if __name__ == '__main__':
    unittest.main()
```
