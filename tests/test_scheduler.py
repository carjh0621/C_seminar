import unittest
from unittest.mock import patch, MagicMock, call
import sys
import datetime # For comparing datetime strings in logs if needed

# Attempt to import the module to be tested
# This structure assumes tests are run from the project root, e.g., using
# `python -m unittest discover -s tests`
# Or that the PYTHONPATH is configured for the 'scheduler' module to be found.
try:
    from scheduler import jobs as scheduler_jobs
except ModuleNotFoundError:
    print("ERROR in tests/test_scheduler.py: Could not import 'scheduler.jobs'.")
    print("Ensure tests are run from the project root or PYTHONPATH is correctly set.")
    # Define a dummy scheduler_jobs so the test file can be parsed by the runner,
    # even if the actual tests might fail due to import issues later.
    class scheduler_jobs:
        _using_dummy_pipeline = True # Simulate that the import failed in jobs.py
        def scheduled_job():
            print("DUMMY scheduler_jobs.scheduled_job() called because of import failure.")
        def run_gmail_ingestion_pipeline(app_user_id="default_user"):
            print(f"DUMMY run_gmail_ingestion_pipeline for {app_user_id} in test dummy.")


class TestSchedulerJobs(unittest.TestCase):

    @patch('scheduler.jobs.run_gmail_ingestion_pipeline')
    def test_scheduled_job_calls_pipeline(self, mock_run_pipeline):
        """
        Tests that scheduled_job() calls run_gmail_ingestion_pipeline correctly.
        """
        # print("TestSchedulerJobs: Testing scheduled_job call to pipeline...")
        scheduler_jobs.scheduled_job()

        mock_run_pipeline.assert_called_once()

        args, kwargs = mock_run_pipeline.call_args
        self.assertEqual(kwargs.get('app_user_id'), "default_gmail_user")

    @patch('scheduler.jobs.run_gmail_ingestion_pipeline')
    @patch('builtins.print')
    def test_scheduled_job_logging_and_error_handling(self, mock_print, mock_run_pipeline):
        """
        Tests logging messages and error handling within scheduled_job.
        """
        # Scenario 1: Successful run
        # print("TestSchedulerJobs: Testing scheduled_job success logging...")
        # Ensure _using_dummy_pipeline is False for this part of the test if the real import succeeded
        original_dummy_flag_state = getattr(scheduler_jobs, '_using_dummy_pipeline', False)
        if hasattr(scheduler_jobs, '_using_dummy_pipeline'):
            scheduler_jobs._using_dummy_pipeline = False

        scheduler_jobs.scheduled_job()

        print_args_list = [c[0][0] for c in mock_print.call_args_list if c[0]] # Get first arg of each print call

        self.assertTrue(any("Scheduler job started" in s for s in print_args_list), "Start message not found in print output.")
        # Check for the actual pipeline finish message
        self.assertTrue(any("Scheduler job (actual pipeline) finished." in s for s in print_args_list), "Actual finish message not found.")

        mock_print.reset_mock()
        mock_run_pipeline.reset_mock() # Reset for next scenario

        # Scenario 2: Pipeline raises an exception
        # print("TestSchedulerJobs: Testing scheduled_job error logging...")
        mock_run_pipeline.side_effect = Exception("Test pipeline error from mock")
        scheduler_jobs.scheduled_job()

        print_args_list_error = [c[0][0] for c in mock_print.call_args_list if c[0]]
        self.assertTrue(any("Scheduler job started" in s for s in print_args_list_error), "Start message not found in error scenario.")
        self.assertTrue(any("Error during scheduled job execution: Test pipeline error from mock" in s for s in print_args_list_error), "Error message not found.")

        # Restore original dummy flag state if it was changed
        if hasattr(scheduler_jobs, '_using_dummy_pipeline'):
            scheduler_jobs._using_dummy_pipeline = original_dummy_flag_state


    @patch('builtins.print')
    def test_scheduled_job_with_dummy_pipeline_if_import_failed(self, mock_print):
        """
        Tests the behavior when the initial import of the main pipeline failed in jobs.py
        and the dummy pipeline is used.
        """
        # This test relies on the _using_dummy_pipeline flag being correctly set by jobs.py
        # if the import of 'main.run_gmail_ingestion_pipeline' failed when jobs.py was loaded.

        # We need to ensure we are testing the scenario where the dummy IS used.
        # If the actual import of 'main' succeeded when 'scheduler.jobs' was first imported by the test runner,
        # then _using_dummy_pipeline would be False.
        # This test is therefore more of an integration check of how jobs.py handles its own import error.

        if not (hasattr(scheduler_jobs, '_using_dummy_pipeline') and scheduler_jobs._using_dummy_pipeline):
            self.skipTest("Skipping dummy pipeline test: Real pipeline was imported successfully by scheduler.jobs, or flag not present.")
            return

        # print("TestSchedulerJobs: Testing scheduled_job with dummy pipeline scenario...")
        # Temporarily ensure the run_gmail_ingestion_pipeline is the dummy from jobs.py for this test's scope
        # This is a bit of a complex setup because the dummy is defined conditionally at module load.
        # The most reliable check is that _using_dummy_pipeline is True.

        scheduler_jobs.scheduled_job()

        print_args_list_dummy = [c[0][0] for c in mock_print.call_args_list if c[0]]

        # Check for the DUMMY message from the dummy function itself
        self.assertTrue(any("DUMMY: run_gmail_ingestion_pipeline called" in s for s in print_args_list_dummy),
                        "Dummy pipeline's own message not found.")
        # Check for the specific log from scheduled_job when using the dummy
        self.assertTrue(any("Scheduler job (dummy pipeline) attempted." in s for s in print_args_list_dummy),
                        "Scheduled_job's log for dummy attempt not found.")


if __name__ == '__main__':
    # This allows running this test file directly, e.g., `python tests/test_scheduler.py`
    # However, for imports to work correctly (like `from scheduler import jobs`),
    # it's often better to run from the project root:
    # `python -m unittest tests.test_scheduler`
    # Or using `discover`: `python -m unittest discover -s tests`

    # If running directly and 'scheduler' is not in path, one might add project root:
    # script_dir = os.path.dirname(__file__)
    # project_root = os.path.abspath(os.path.join(script_dir, '..'))
    # if project_root not in sys.path:
    #    sys.path.insert(0, project_root)
    # print(f"Adjusted sys.path for direct run: {sys.path}")

    unittest.main()
