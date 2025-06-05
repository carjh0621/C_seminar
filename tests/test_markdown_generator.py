import unittest
from datetime import datetime, date, timedelta, time as dt_time
import os
import tempfile
import jinja2 # For TemplateNotFound error

from markdown_generator.writer import ObsidianWriter
from persistence.models import TaskStatus # Assuming TaskStatus enum is here

# Helper MockTask class for tests
class MockTask:
    def __init__(self, id, title, due_dt_val, status_val, task_type="personal", body=""):
        self.id = id
        self.title = title
        # due_dt_val can be a datetime object, a string to be parsed, or None
        if isinstance(due_dt_val, str):
            self.due_dt = datetime.fromisoformat(due_dt_val) if due_dt_val else None
        elif isinstance(due_dt_val, datetime):
            self.due_dt = due_dt_val
        elif due_dt_val is None:
            self.due_dt = None
        else:
            raise ValueError(f"Unsupported type for due_dt_val: {type(due_dt_val)}")

        self.status = status_val # This should be the enum member, e.g., TaskStatus.TODO
        self.type = task_type
        self.body = body
        # Add other attributes if your template uses them extensively, otherwise keep minimal
        self.source = "mock_source"
        self.created_dt = datetime.now()


class TestObsidianWriter(unittest.TestCase):

    def setUp(self):
        # Determine templates path relative to this test file's location for robustness
        # Assuming this test file is in 'tests/' and writer.py is in 'markdown_generator/'
        # and templates are in 'markdown_generator/templates/'
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir) # Up one level from 'tests/' to project root
        templates_dir = os.path.join(project_root, "markdown_generator", "templates")

        if not os.path.isdir(templates_dir):
            # Fallback if structure is different, e.g. if tests are run from inside markdown_generator
            alt_templates_dir = os.path.join(os.path.dirname(os.path.abspath(markdown_generator.writer.__file__)), "templates")
            if os.path.isdir(alt_templates_dir):
                templates_dir = alt_templates_dir
            # else: could print a warning, but writer's init also has checks

        self.writer = ObsidianWriter(templates_path=templates_dir)
        self.today = date(2024, 3, 10) # Fixed date for consistent D-day calcs in tests

        # Create a temporary directory for test output files
        self.test_dir_context = tempfile.TemporaryDirectory()
        self.test_dir = self.test_dir_context.name # Get the path to the temp directory
        self.temp_output_file = os.path.join(self.test_dir, "test_agenda.md")


    def tearDown(self):
        # Clean up the temporary directory and its contents
        self.test_dir_context.cleanup()

    def test_group_tasks_by_date(self):
        tasks = [
            MockTask(1, "Task 1", datetime(2024, 3, 10, 10, 0), TaskStatus.TODO),
            MockTask(2, "Task 2", datetime(2024, 3, 11, 12, 0), TaskStatus.TODO),
            MockTask(3, "Task 3", datetime(2024, 3, 10, 8, 0), TaskStatus.DONE), # Same day, earlier
            MockTask(4, "Task No Due Date", None, TaskStatus.TODO),
        ]
        grouped = self.writer.group_tasks_by_date(tasks)

        self.assertIn(date(2024, 3, 10), grouped)
        self.assertIn(date(2024, 3, 11), grouped)
        self.assertEqual(len(grouped[date(2024, 3, 10)]), 2)
        self.assertEqual(grouped[date(2024, 3, 10)][0].title, "Task 3") # Sorted by time
        self.assertEqual(grouped[date(2024, 3, 10)][1].title, "Task 1")
        self.assertEqual(len(grouped[date(2024, 3, 11)]), 1)
        self.assertEqual(grouped[date(2024, 3, 11)][0].title, "Task 2")

        # Check that tasks with no due dates are not in any group's list
        for task_list in grouped.values():
            for task_item in task_list:
                self.assertIsNotNone(task_item.due_dt)

        # Test chronological order of dates in the returned dict
        self.assertEqual(list(grouped.keys()), [date(2024, 3, 10), date(2024, 3, 11)])


    def test_render_agenda_output_content(self):
        tasks = [
            MockTask(1, "Meeting A", datetime(2024, 3, 10, 10, 0), TaskStatus.TODO, "meeting"),
            MockTask(2, "Homework B", datetime(2024, 3, 11, 15, 0), TaskStatus.DONE, "assignment"),
            MockTask(3, "All-day task", datetime(2024, 3, 10, 0, 0), TaskStatus.TODO, "general"), # All-day
        ]
        try:
            self.writer.render_agenda(tasks, self.temp_output_file, today=self.today)
        except jinja2.TemplateNotFound:
            self.fail(f"Template agenda.md.j2 not found. Searched in: {self.writer.env.loader.searchpath}")

        with open(self.temp_output_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 2024-03-10 is a Sunday
        self.assertIn("## 2024-03-10 (일)", content)
        self.assertIn("- [ ] All-day task (D-Day) #general", content) # No time for 00:00 task
        self.assertIn("- [ ] 10:00 Meeting A (D-Day) #meeting", content)

        # 2024-03-11 is a Monday
        self.assertIn("## 2024-03-11 (월)", content)
        self.assertIn("- ~~[x] 15:00 Homework B~~ (D-1 남음) #assignment", content)

    def test_render_empty_tasks(self):
        try:
            self.writer.render_agenda([], self.temp_output_file, today=self.today)
        except jinja2.TemplateNotFound:
            self.fail(f"Template agenda.md.j2 not found. Searched in: {self.writer.env.loader.searchpath}")

        with open(self.temp_output_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        # Based on current template, it should be empty if tasks_by_date is empty
        self.assertEqual(content, "")

    def test_task_sorting_in_output(self):
        tasks = [
            MockTask(1, "Late Task", datetime(2024, 3, 10, 14, 0), TaskStatus.TODO),
            MockTask(2, "Early Task", datetime(2024, 3, 10, 9, 0), TaskStatus.TODO),
            MockTask(3, "Middle Task", datetime(2024, 3, 10, 11, 0), TaskStatus.DONE),
        ]
        try:
            self.writer.render_agenda(tasks, self.temp_output_file, today=self.today)
        except jinja2.TemplateNotFound:
            self.fail(f"Template agenda.md.j2 not found. Searched in: {self.writer.env.loader.searchpath}")

        with open(self.temp_output_file, "r", encoding="utf-8") as f:
            content = f.read()

        early_pos = content.find("Early Task")
        middle_pos = content.find("Middle Task")
        late_pos = content.find("Late Task")

        self.assertTrue(all(p != -1 for p in [early_pos, middle_pos, late_pos]), "Not all tasks found in output")
        self.assertLess(early_pos, middle_pos, "Early task not before Middle task")
        self.assertLess(middle_pos, late_pos, "Middle task not before Late task")

        self.assertIn("- [ ] 09:00 Early Task", content)
        self.assertIn("- ~~[x] 11:00 Middle Task~~", content) # Assuming DONE status for Middle Task
        self.assertIn("- [ ] 14:00 Late Task", content)


    def test_d_day_calculation_rendering(self):
        tasks = [
            MockTask(1, "D-Day Task", datetime(2024, 3, 10, 10, 0), TaskStatus.TODO),
            MockTask(2, "Future Task D-3", datetime(2024, 3, 13, 10, 0), TaskStatus.TODO),
            MockTask(3, "Past Task D+2", datetime(2024, 3, 8, 10, 0), TaskStatus.DONE),
            MockTask(4, "Cancelled Task D-5", datetime(2024, 3, 15, 10, 0), TaskStatus.CANCELLED),
        ]
        try:
            self.writer.render_agenda(tasks, self.temp_output_file, today=self.today)
        except jinja2.TemplateNotFound:
            self.fail(f"Template agenda.md.j2 not found. Searched in: {self.writer.env.loader.searchpath}")

        with open(self.temp_output_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("D-Day Task (D-Day)", content)
        self.assertIn("Future Task D-3 (D-3 남음)", content)
        self.assertIn("Past Task D+2 (D+2 지남)", content)
        self.assertIn("Cancelled Task D-5 (D-5 남음) #personal (Cancelled)", content) # Assuming default type 'personal'

if __name__ == '__main__':
    unittest.main()
