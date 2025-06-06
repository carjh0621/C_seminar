import unittest
from unittest.mock import patch, MagicMock, ANY, call
from typer.testing import CliRunner
from rich.console import Console
from datetime import datetime, timedelta

try:
    from cli.main_cli import app as cli_app
    from persistence.models import Task, TaskStatus
    # Assuming datetime is used directly, not just for type hints in models
except ModuleNotFoundError as e:
    print(f"CRITICAL in tests/test_cli.py: Could not import CLI app or models for testing: {e}")
    print("Ensure tests are run from project root or PYTHONPATH is correctly set.")
    import typer
    cli_app = typer.Typer()
    class Task:
        def __init__(self, **kwargs): setattr(self, 'id', kwargs.get('id', None)) # Basic mock
    class TaskStatus:
        TODO=MagicMock(name="TODO"); DONE=MagicMock(name="DONE"); CANCELLED=MagicMock(name="CANCELLED")
        def __getitem__(self, item): return getattr(self, item.upper()) # For TaskStatus[str.upper()]
    # datetime and timedelta are standard library, should be fine.


runner = CliRunner()

class TestCliCommands(unittest.TestCase):

    def setUp(self):
        # This setup assumes that the dummy Task/TaskStatus might be used if imports fail.
        # In a correctly configured environment, the actual models will be imported.
        self.dummy_task = Task(id=1) # Example, if needed for type checks with dummy
        self.dummy_status = TaskStatus.TODO

    # Patching at the location where 'crud' and other utils are imported BY 'cli.main_cli'
    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.resolve_date')
    @patch('cli.main_cli.generate_task_fingerprint')
    @patch('cli.main_cli.SessionLocal')
    def test_add_task_success(self, MockSessionLocal, mock_generate_fp, mock_resolve_date, mock_crud):
        mock_db_session = MagicMock()
        # Simulate the generator behavior of get_db_session by having SessionLocal return a mock
        # that can be iterated once to yield the db_session.
        # However, cli.main_cli directly calls SessionLocal() then next() on the generator.
        # So, we need get_db_session to be a generator that yields mock_db_session.
        # Easier: the cli.main_cli.get_db_session uses SessionLocal.
        # Patching SessionLocal means when cli.main_cli.get_db_session calls SessionLocal(), it gets our mock_db_session.
        MockSessionLocal.return_value = mock_db_session # SessionLocal() returns the mock session directly

        mock_resolve_date.return_value = datetime(2024, 1, 1, 14, 0)
        mock_generate_fp.return_value = "fp_test_add_cli"
        mock_crud.get_task_by_fingerprint.return_value = None

        mock_created_task_obj = Task(id=1) # Using actual Task or dummy if import failed
        mock_created_task_obj.title = "New CLI Task from Test"
        mock_created_task_obj.due_dt = datetime(2024, 1, 1, 14, 0)
        mock_created_task_obj.status = TaskStatus.TODO
        mock_created_task_obj.type = "work_cli"
        mock_created_task_obj.body = "Details from CLI test"
        mock_created_task_obj.tags = None
        mock_created_task_obj.fingerprint = "fp_test_add_cli"
        mock_created_task_obj.created_dt = datetime.utcnow()
        mock_created_task_obj.last_modified_dt = datetime.utcnow() # For format_task_details
        mock_crud.create_task.return_value = mock_created_task_obj

        result = runner.invoke(cli_app, [
            "add", "New CLI Task from Test",
            "--due", "tomorrow 2pm",
            "--body", "Details from CLI test",
            "--type", "work_cli"
        ])

        self.assertEqual(result.exit_code, 0, f"CLI add command failed: {result.stdout}")
        self.assertIn("Task added successfully!", result.stdout)
        self.assertIn("Title    : New CLI Task from Test", result.stdout)
        mock_resolve_date.assert_called_once_with("tomorrow 2pm")
        mock_generate_fp.assert_called_once_with("New CLI Task from Test", datetime(2024, 1, 1, 14, 0))
        mock_crud.get_task_by_fingerprint.assert_called_once_with(mock_db_session, "fp_test_add_cli")
        mock_crud.create_task.assert_called_once()

        args_create, kwargs_create = mock_crud.create_task.call_args
        self.assertEqual(args_create[0], mock_db_session) # Check db session
        self.assertEqual(kwargs_create['task_data']['title'], "New CLI Task from Test")
        self.assertEqual(kwargs_create['task_data']['fingerprint'], "fp_test_add_cli")
        self.assertEqual(kwargs_create['task_data']['type'], "work_cli")

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.resolve_date')
    @patch('cli.main_cli.generate_task_fingerprint')
    @patch('cli.main_cli.SessionLocal')
    @patch('typer.confirm')
    def test_add_task_duplicate_confirmed(self, mock_confirm, MockSessionLocal, mock_generate_fp, mock_resolve_date, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session
        mock_resolve_date.return_value = datetime(2024, 1, 1)
        mock_generate_fp.return_value = "fp_duplicate_cli"

        mock_existing_task_obj = Task(id=99); mock_existing_task_obj.title="Existing Task"
        mock_crud.get_task_by_fingerprint.return_value = mock_existing_task_obj
        mock_confirm.return_value = True

        mock_newly_created_task_obj = Task(id=100); mock_newly_created_task_obj.title="New Task Despite Warning CLI";
        mock_newly_created_task_obj.fingerprint="fp_duplicate_cli"; mock_newly_created_task_obj.status=TaskStatus.TODO
        mock_newly_created_task_obj.created_dt = datetime.utcnow(); mock_newly_created_task_obj.last_modified_dt = datetime.utcnow()
        mock_crud.create_task.return_value = mock_newly_created_task_obj

        result = runner.invoke(cli_app, ["add", "New Task Despite Warning CLI", "--due", "2024-01-01"])

        self.assertEqual(result.exit_code, 0, f"CLI add (duplicate confirmed) failed: {result.stdout}")
        self.assertIn("Warning: A similar task already exists", result.stdout)
        mock_confirm.assert_called_once()
        self.assertIn("Task added successfully!", result.stdout)
        mock_crud.create_task.assert_called_once()

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    def test_list_tasks_success_displays_table(self, MockSessionLocal, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session

        task1_obj = Task(id=1); task1_obj.title="Task One CLI"; task1_obj.due_dt=datetime(2024,1,1,10,0); task1_obj.status=TaskStatus.TODO; task1_obj.type="work"; task1_obj.tags=None
        task2_obj = Task(id=2); task2_obj.title="Task Two CLI"; task2_obj.due_dt=datetime(2024,1,2,12,0); task2_obj.status=TaskStatus.DONE; task2_obj.type="personal"; task2_obj.tags="#urgent_cli"
        mock_crud.get_tasks.return_value = [task1_obj, task2_obj]

        result = runner.invoke(cli_app, ["list"])

        self.assertEqual(result.exit_code, 0, f"CLI list command failed: {result.stdout}")
        self.assertIn("Task One CLI", result.stdout)
        self.assertIn("Task Two CLI", result.stdout)
        self.assertIn("10:00", result.stdout)
        self.assertIn("DONE", result.stdout)
        self.assertIn("#urgent_cli", result.stdout)
        mock_crud.get_tasks.assert_called_once_with(mock_db_session, skip=0, limit=1000)

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    def test_show_task_success(self, MockSessionLocal, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session

        mock_task_obj = Task(id=1); mock_task_obj.title="Detailed Task CLI"; mock_task_obj.status=TaskStatus.TODO;
        mock_task_obj.due_dt=datetime(2024,1,5,11,0); mock_task_obj.body="Full body CLI";
        mock_task_obj.created_dt=datetime.utcnow(); mock_task_obj.last_modified_dt = datetime.utcnow()
        mock_crud.get_task.return_value = mock_task_obj

        result = runner.invoke(cli_app, ["show", "1"])

        self.assertEqual(result.exit_code, 0, f"CLI show command failed: {result.stdout}")
        self.assertIn("Task ID: 1", result.stdout)
        self.assertIn("Title    : Detailed Task CLI", result.stdout)
        self.assertIn("Status   : ⏳ TODO", result.stdout)
        mock_crud.get_task.assert_called_once_with(mock_db_session, 1)

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    def test_show_task_not_found(self, MockSessionLocal, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session
        mock_crud.get_task.return_value = None

        result = runner.invoke(cli_app, ["show", "999"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Error: Task with ID 999 not found.", result.stdout)

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.resolve_date')
    @patch('cli.main_cli.generate_task_fingerprint')
    @patch('cli.main_cli.SessionLocal')
    def test_update_task_success(self, MockSessionLocal, mock_generate_fp, mock_resolve_date, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session

        mock_existing_task_obj = Task(id=5); mock_existing_task_obj.title="Old Title CLI";
        mock_existing_task_obj.due_dt=datetime(2023,12,1); mock_existing_task_obj.fingerprint = "old_fp_cli"
        mock_crud.get_task.return_value = mock_existing_task_obj # For initial fetch
        mock_crud.get_task_by_fingerprint.return_value = None # No collision with new fingerprint

        mock_resolve_date.return_value = datetime(2024, 2, 1, 10, 0)
        mock_generate_fp.return_value = "new_fp_after_update_cli"

        mock_updated_task_return_obj = Task(id=5); mock_updated_task_return_obj.title="New Updated Title CLI";
        mock_updated_task_return_obj.due_dt=datetime(2024,2,1,10,0); mock_updated_task_return_obj.status=TaskStatus.TODO;
        mock_updated_task_return_obj.fingerprint="new_fp_after_update_cli";
        mock_updated_task_return_obj.created_dt=datetime.utcnow(); mock_updated_task_return_obj.last_modified_dt = datetime.utcnow()
        mock_crud.update_task.return_value = mock_updated_task_return_obj

        result = runner.invoke(cli_app, ["update", "5", "--title", "New Updated Title CLI", "--due", "2024-02-01 10:00", "--status", "TODO"])

        self.assertEqual(result.exit_code, 0, f"CLI update command failed: {result.stdout}")
        self.assertIn("Task updated successfully!", result.stdout)
        self.assertIn("Title    : New Updated Title CLI", result.stdout)
        mock_crud.get_task.assert_called_once_with(mock_db_session, 5)
        mock_resolve_date.assert_called_once_with("2024-02-01 10:00")
        mock_generate_fp.assert_called_once_with("New Updated Title CLI", datetime(2024,2,1,10,0))
        mock_crud.update_task.assert_called_once()
        args_update, kwargs_update = mock_crud.update_task.call_args
        self.assertEqual(args_update[1], 5)
        self.assertEqual(kwargs_update['update_data']['title'], "New Updated Title CLI")
        self.assertEqual(kwargs_update['update_data']['fingerprint'], "new_fp_after_update_cli")

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    def test_complete_task_success(self, MockSessionLocal, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session

        mock_updated_task_obj = Task(id=7); mock_updated_task_obj.title="Task to complete CLI"; mock_updated_task_obj.status=TaskStatus.DONE;
        mock_updated_task_obj.created_dt=datetime.utcnow(); mock_updated_task_obj.last_modified_dt = datetime.utcnow()
        mock_crud.update_task.return_value = mock_updated_task_obj

        result = runner.invoke(cli_app, ["done", "7"])

        self.assertEqual(result.exit_code, 0, f"CLI done command failed: {result.stdout}")
        self.assertIn("Task ID 7 status changed to DONE successfully!", result.stdout)
        mock_crud.update_task.assert_called_once_with(mock_db_session, 7, {"status": TaskStatus.DONE})

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    @patch('typer.confirm')
    def test_delete_task_confirmed(self, mock_confirm, MockSessionLocal, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session
        mock_confirm.return_value = True

        mock_task_to_delete_obj = Task(id=3); mock_task_to_delete_obj.title="Delete Me CLI";
        mock_task_to_delete_obj.created_dt=datetime.utcnow(); mock_task_to_delete_obj.last_modified_dt = datetime.utcnow(); mock_task_to_delete_obj.status=TaskStatus.TODO
        mock_crud.get_task.return_value = mock_task_to_delete_obj
        mock_crud.delete_task.return_value = True

        result = runner.invoke(cli_app, ["delete", "3"])

        self.assertEqual(result.exit_code, 0, f"CLI delete command failed: {result.stdout}")
        self.assertIn("Task ID 3 deleted successfully.", result.stdout)
        mock_crud.get_task.assert_called_once_with(mock_db_session, 3)
        mock_confirm.assert_called_once()
        mock_crud.delete_task.assert_called_once_with(mock_db_session, 3)

    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    @patch('typer.confirm')
    def test_delete_task_cancelled_by_user(self, mock_confirm, MockSessionLocal, mock_crud):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session
        mock_confirm.return_value = False

        mock_task_to_delete_obj = Task(id=4); mock_task_to_delete_obj.title="Don't Delete Me CLI";
        mock_task_to_delete_obj.created_dt=datetime.utcnow(); mock_task_to_delete_obj.last_modified_dt = datetime.utcnow(); mock_task_to_delete_obj.status=TaskStatus.TODO
        mock_crud.get_task.return_value = mock_task_to_delete_obj

        result = runner.invoke(cli_app, ["delete", "4"])

        self.assertEqual(result.exit_code, 0) # Typer.Exit() without code is 0
        self.assertIn("Deletion cancelled.", result.stdout)
        mock_crud.delete_task.assert_not_called()

    @patch('cli.main_cli.create_db_tables')
    def test_initdb_command(self, mock_create_tables):
        result = runner.invoke(cli_app, ["initdb"])
        self.assertEqual(result.exit_code, 0, f"CLI initdb command failed: {result.stdout}")
        self.assertIn("Database tables checked/created successfully.", result.stdout)
        mock_create_tables.assert_called_once()

if __name__ == '__main__':
    unittest.main()
