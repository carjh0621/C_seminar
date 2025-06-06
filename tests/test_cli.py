import unittest
from unittest.mock import patch, MagicMock, ANY, call
from typer.testing import CliRunner
from rich.console import Console
from datetime import datetime, timedelta

try:
    from cli.main_cli import app as cli_app, get_status_from_md_marker # Import helper
    from persistence.models import Task, TaskStatus
    from datetime import datetime, date, time as dt_time # Added date and dt_time
    from telegram import constants as telegram_constants # For ParseMode, though not directly used in these CLI tests
    from typing import Any # For dummy Task
except ModuleNotFoundError as e:
    print(f"CRITICAL in tests/test_cli.py: Could not import CLI app or models for testing: {e}")
    print("Ensure tests are run from project root or PYTHONPATH is correctly set.")
    # Define dummy app and models if import fails so the test file itself is valid Python
    import typer
    cli_app = typer.Typer()
    class Task: # type: ignore
        def __init__(self, **kwargs):
            self.id = kwargs.get('id')
            self.title = kwargs.get('title')
            self.due_dt = kwargs.get('due_dt')
            self.status = kwargs.get('status')
            self.type = kwargs.get('type')
            self.body = kwargs.get('body')
            self.tags = kwargs.get('tags')
            self.fingerprint = kwargs.get('fingerprint')
            self.created_dt = kwargs.get('created_dt')
            self.last_modified_dt = kwargs.get('last_modified_dt')
    class TaskStatus: # type: ignore
        TODO=MagicMock(name="TODO"); DONE=MagicMock(name="DONE"); CANCELLED=MagicMock(name="CANCELLED")
        @classmethod
        def __getitem__(cls, item): return getattr(cls, item.upper())
    class datetime: # type: ignore
        @staticmethod
        def utcnow(): return MagicMock(spec=datetime)
        @staticmethod
        def strptime(s, f): return MagicMock(spec=datetime)
        def date(self): return MagicMock(spec=date)
        def time(self): return MagicMock(spec=dt_time)
        def isoformat(self): return "dummy_iso_string"
    class date: pass # type: ignore
    class dt_time: # type: ignore
        def __init__(self, h=0, m=0, s=0): pass
    class timedelta: # type: ignore
        def __init__(self, hours=0):pass
    class telegram_constants: # type: ignore
        class ParseMode: MARKDOWN_V2 = "MarkdownV2"
    def get_status_from_md_marker(status_md: str): # type: ignore
        if status_md == "[x]": return TaskStatus.DONE
        if status_md == "[ ]": return TaskStatus.TODO
        if status_md == "[c]": return TaskStatus.CANCELLED
        return None


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


class TestCliSyncCommands(unittest.TestCase):

    def test_get_status_from_md_marker(self):
        # This test now uses the get_status_from_md_marker imported (or dummied) at the top
        self.assertEqual(get_status_from_md_marker("[ ]"), TaskStatus.TODO)
        self.assertEqual(get_status_from_md_marker("[x]"), TaskStatus.DONE)
        self.assertEqual(get_status_from_md_marker("[X]"), TaskStatus.DONE)
        self.assertEqual(get_status_from_md_marker("[c]"), TaskStatus.CANCELLED)
        self.assertEqual(get_status_from_md_marker("[C]"), TaskStatus.CANCELLED)
        self.assertIsNone(get_status_from_md_marker("[-]"))
        self.assertIsNone(get_status_from_md_marker(""))
        self.assertIsNone(get_status_from_md_marker("[?]"))

    @patch('cli.main_cli.os.path.exists')
    @patch('cli.main_cli.os.path.isfile')
    @patch('cli.main_cli.parse_markdown_agenda_file')
    @patch('cli.main_cli.find_matching_task_in_db')
    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    def test_sync_obsidian_dry_run_status_change(
        self, MockSessionLocal, mock_crud_cli, mock_find_match, mock_parse_md, mock_is_file, mock_path_exists
    ):
        mock_path_exists.return_value = True
        mock_is_file.return_value = True

        mock_db_session = MagicMock()
        MockSessionLocal.return_value = mock_db_session

        md_tasks = [
            {"date_str": "2024-01-01", "status_md": "[x]", "time_str": "10:00", "title_md": "MD Task 1 Title", "tags_md": ["#test"]},
            {"date_str": "2024-01-01", "status_md": "[ ]", "time_str": "11:00", "title_md": "MD Task 2 Title", "tags_md": []},
        ]
        mock_parse_md.return_value = md_tasks

        db_task1 = Task(id=1); db_task1.title="MD Task 1 Title"; db_task1.status=TaskStatus.TODO; db_task1.due_dt=datetime(2024,1,1,10,0)
        db_task2 = Task(id=2); db_task2.title="MD Task 2 Title"; db_task2.status=TaskStatus.TODO; db_task2.due_dt=datetime(2024,1,1,11,0)

        mock_crud_cli.get_tasks.return_value = [db_task1, db_task2]

        def find_match_side_effect(parsed_md_task, db_tasks_on_date_list):
            self.assertEqual(len(db_tasks_on_date_list), 2)
            if parsed_md_task["title_md"] == "MD Task 1 Title": return db_task1
            if parsed_md_task["title_md"] == "MD Task 2 Title": return db_task2
            return None
        mock_find_match.side_effect = find_match_side_effect

        result = runner.invoke(cli_app, ["sync", "dummy_path.md", "--dry-run"])

        self.assertEqual(result.exit_code, 0, f"CLI sync command failed: {result.stdout}")
        mock_parse_md.assert_called_once_with("dummy_path.md")

        mock_crud_cli.get_tasks.assert_called_once()
        self.assertEqual(mock_find_match.call_count, 2)

        self.assertIn("Detected 1 potential status updates", result.stdout)
        self.assertIn("MD Task 1 Title", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn(TaskStatus.TODO.name, result.stdout)
        self.assertIn(TaskStatus.DONE.name, result.stdout)

        mock_crud_cli.update_task.assert_not_called()
        mock_crud_cli.update_task_tags.assert_not_called()

    @patch('cli.main_cli.os.path.exists', return_value=True)
    @patch('cli.main_cli.os.path.isfile', return_value=True)
    @patch('cli.main_cli.parse_markdown_agenda_file')
    @patch('cli.main_cli.find_matching_task_in_db')
    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    def test_sync_obsidian_dry_run_no_changes(self, MockSessionLocal, mock_crud_cli, mock_find_match_in_cli, mock_parse_md):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session

        md_tasks = [{"date_str": "2024-01-01", "status_md": "[ ]", "title_md": "MD Task No Change", "tags_md": []}]
        mock_parse_md.return_value = md_tasks

        db_task_no_change = Task(id=3); db_task_no_change.title="MD Task No Change";
        db_task_no_change.status=TaskStatus.TODO; db_task_no_change.due_dt=datetime(2024,1,1,0,0)
        mock_crud_cli.get_tasks.return_value = [db_task_no_change]

        mock_find_match_in_cli.return_value = db_task_no_change

        result = runner.invoke(cli_app, ["sync", "path.md"])

        self.assertEqual(result.exit_code, 0, f"CLI sync (no changes) failed: {result.stdout}")
        self.assertIn("No differences found", result.stdout)
        self.assertNotIn("Detected 0 potential status updates", result.stdout)
        mock_find_match_in_cli.assert_called_once()

    @patch('cli.main_cli.os.path.exists')
    @patch('cli.main_cli.os.path.isfile')
    def test_sync_obsidian_file_not_found(self, mock_is_file, mock_path_exists):
        mock_path_exists.return_value = False
        mock_is_file.return_value = False

        result = runner.invoke(cli_app, ["sync", "nonexistent.md"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Error: File not found", result.stdout)

    # Placeholder for testing --no-dry-run when implemented
    # @patch('cli.main_cli.os.path.exists', return_value=True)
    # @patch('cli.main_cli.os.path.isfile', return_value=True)
    # @patch('cli.main_cli.parse_markdown_agenda_file')
    # @patch('cli.main_cli.find_matching_task_in_db')
    # @patch('cli.main_cli.crud')
    # @patch('cli.main_cli.SessionLocal')
    # @patch('typer.confirm', return_value=True)
    # def test_sync_obsidian_actual_run_status_update(
    #     self, mock_typer_confirm, MockSessionLocal, mock_crud_cli,
    #     mock_find_match, mock_parse_md
    # ):
    #     pass

    @patch('cli.main_cli.os.path.exists', return_value=True)
    @patch('cli.main_cli.os.path.isfile', return_value=True)
    @patch('cli.main_cli.parse_markdown_agenda_file')
    @patch('cli.main_cli.find_matching_task_in_db')
    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    @patch('typer.confirm')
    def test_sync_obsidian_live_run_applies_status_changes_on_confirm(
        self, mock_typer_confirm, MockSessionLocal, mock_crud_cli,
        mock_find_match, mock_parse_md, mock_is_file, mock_path_exists # Patches are in reverse order of decorators
    ):
        mock_typer_confirm.return_value = True
        mock_db_session = MagicMock()
        MockSessionLocal.return_value = mock_db_session

        md_tasks = [
            {"date_str": "2024-01-01", "status_md": "[x]", "time_str": "10:00", "title_md": "MD Task 1 (Done in MD)", "tags_md": []},
            {"date_str": "2024-01-01", "status_md": "[c]", "time_str": "11:00", "title_md": "MD Task 2 (Cancelled in MD)", "tags_md": []},
        ]
        mock_parse_md.return_value = md_tasks

        # DB tasks with different initial statuses
        db_task1 = Task(id=1, title="MD Task 1 (Done in MD)", status=TaskStatus.TODO, due_dt=datetime(2024,1,1,10,0), created_dt=datetime(2023,1,1), last_modified_dt=datetime(2023,1,1))
        db_task2 = Task(id=2, title="MD Task 2 (Cancelled in MD)", status=TaskStatus.TODO, due_dt=datetime(2024,1,1,11,0), created_dt=datetime(2023,1,1), last_modified_dt=datetime(2023,1,1))

        # Mock for the DB task fetching logic
        if hasattr(mock_crud_cli, 'get_tasks_on_date'): # Check if the intended optimized crud exists
            mock_crud_cli.get_tasks_on_date.return_value = [db_task1, db_task2]
        else: # Fallback for current sync logic that uses get_tasks and filters
            mock_crud_cli.get_tasks.return_value = [db_task1, db_task2]


        def find_match_side_effect(parsed_md_task, db_tasks_on_date):
            if parsed_md_task["title_md"] == "MD Task 1 (Done in MD)": return db_task1
            if parsed_md_task["title_md"] == "MD Task 2 (Cancelled in MD)": return db_task2
            return None
        mock_find_match.side_effect = find_match_side_effect

        # Mock the return of update_task to simulate successful update
        def mock_update_task_effect(db, task_id, update_data):
            # Return a dictionary or a mock Task object that looks like an updated task
            # This helps format_task_details if it were called, though not strictly necessary for this test's asserts
            updated_status = update_data["status"]
            if task_id == 1:
                return Task(id=1, title="MD Task 1 (Done in MD)", status=updated_status, due_dt=db_task1.due_dt, created_dt=db_task1.created_dt, last_modified_dt=datetime.utcnow())
            if task_id == 2:
                return Task(id=2, title="MD Task 2 (Cancelled in MD)", status=updated_status, due_dt=db_task2.due_dt, created_dt=db_task2.created_dt, last_modified_dt=datetime.utcnow())
            return None # Should not happen if task_id is correct
        mock_crud_cli.update_task.side_effect = mock_update_task_effect


        result = runner.invoke(cli_app, ["sync", "dummy_path.md", "--no-dry-run"])

        self.assertEqual(result.exit_code, 0, msg=f"CLI exited with errors: {result.stdout}")
        mock_typer_confirm.assert_called_once()

        self.assertEqual(mock_crud_cli.update_task.call_count, 2)
        expected_calls = [
            call(mock_db_session, task_id=1, update_data={"status": TaskStatus.DONE}),
            call(mock_db_session, task_id=2, update_data={"status": TaskStatus.CANCELLED})
        ]
        mock_crud_cli.update_task.assert_has_calls(expected_calls, any_order=True)

        self.assertIn("Successfully applied: 2 updates.", result.stdout)
        self.assertIn("Database update process complete.", result.stdout)


    @patch('cli.main_cli.os.path.exists', return_value=True)
    @patch('cli.main_cli.os.path.isfile', return_value=True)
    @patch('cli.main_cli.parse_markdown_agenda_file')
    @patch('cli.main_cli.find_matching_task_in_db')
    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    @patch('typer.confirm')
    def test_sync_obsidian_live_run_user_cancels_update(
        self, mock_typer_confirm, MockSessionLocal, mock_crud_cli,
        mock_find_match, mock_parse_md, mock_is_file, mock_path_exists # Patches in reverse order
    ):
        mock_typer_confirm.return_value = False # User cancels (says 'no')
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session

        md_tasks = [{"date_str": "2024-01-01", "status_md": "[x]", "title_md": "MD Task 1", "tags_md": []}]
        mock_parse_md.return_value = md_tasks

        db_task1 = Task(id=1, title="MD Task 1", status=TaskStatus.TODO, due_dt=datetime(2024,1,1,10,0))
        if hasattr(mock_crud_cli, 'get_tasks_on_date'):
            mock_crud_cli.get_tasks_on_date.return_value = [db_task1]
        else:
            mock_crud_cli.get_tasks.return_value = [db_task1]
        mock_find_match.return_value = db_task1

        result = runner.invoke(cli_app, ["sync", "dummy_path.md", "--no-dry-run"])

        self.assertEqual(result.exit_code, 1) # typer.confirm with abort=True exits with 1 if user says no
        self.assertIn("Operation cancelled by user.", result.stdout)
        mock_typer_confirm.assert_called_once()
        mock_crud_cli.update_task.assert_not_called()

    @patch('cli.main_cli.os.path.exists', return_value=True)
    @patch('cli.main_cli.os.path.isfile', return_value=True)
    @patch('cli.main_cli.parse_markdown_agenda_file')
    @patch('cli.main_cli.find_matching_task_in_db')
    @patch('cli.main_cli.crud')
    @patch('cli.main_cli.SessionLocal')
    @patch('typer.confirm', return_value=True)
    def test_sync_obsidian_live_run_update_fails_for_one_task(
        self, mock_typer_confirm, MockSessionLocal, mock_crud_cli,
        mock_find_match, mock_parse_md, mock_is_file, mock_path_exists # Patches in reverse order
    ):
        mock_db_session = MagicMock(); MockSessionLocal.return_value = mock_db_session
        md_tasks = [
            {"date_str": "2024-01-01", "status_md": "[x]", "title_md": "Task Success", "tags_md": []},
            {"date_str": "2024-01-01", "status_md": "[c]", "title_md": "Task Fail Update", "tags_md": []},
        ]
        mock_parse_md.return_value = md_tasks

        db_task_ok = Task(id=1, title="Task Success", status=TaskStatus.TODO, due_dt=datetime(2024,1,1,10,0))
        db_task_fail = Task(id=2, title="Task Fail Update", status=TaskStatus.TODO, due_dt=datetime(2024,1,1,11,0))
        if hasattr(mock_crud_cli, 'get_tasks_on_date'):
            mock_crud_cli.get_tasks_on_date.return_value = [db_task_ok, db_task_fail]
        else:
            mock_crud_cli.get_tasks.return_value = [db_task_ok, db_task_fail]

        def find_match_side_effect(parsed_md_task, db_tasks_on_date):
            if parsed_md_task["title_md"] == "Task Success": return db_task_ok
            if parsed_md_task["title_md"] == "Task Fail Update": return db_task_fail
            return None
        mock_find_match.side_effect = find_match_side_effect

        def update_task_side_effect(db, task_id, update_data):
            if task_id == 1:
                return Task(id=1, title="Task Success", status=update_data["status"])
            if task_id == 2:
                return None # Simulate failure to update task 2
            return None
        mock_crud_cli.update_task.side_effect = update_task_side_effect

        result = runner.invoke(cli_app, ["sync", "dummy_path.md", "--no-dry-run"])

        self.assertEqual(result.exit_code, 0, f"CLI sync (one fail) failed: {result.stdout}")
        self.assertIn("Successfully applied: 1 updates.", result.stdout)
        self.assertIn("Failed to apply: 1 updates.", result.stdout)
        self.assertIn("Failed to update Task ID 2 - task not found by update_task", result.stdout)
        self.assertEqual(mock_crud_cli.update_task.call_count, 2)
