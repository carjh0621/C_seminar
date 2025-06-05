import jinja2
from datetime import date, datetime, time as dt_time # Import time separately to avoid clash in template
from collections import defaultdict
from persistence import models # For Task and TaskStatus enum
import os
from datetime import timedelta # For example usage

# Placeholder for writer.py - update or remove
# print("Markdown Generator Writer initialized")

class ObsidianWriter:
    def __init__(self, templates_path="markdown_generator/templates"):
        """
        Initializes the ObsidianWriter with a Jinja2 environment.

        Args:
            templates_path: Path to the directory containing Jinja2 templates.
        """
        # Try to construct path relative to this file's directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_templates_path = os.path.join(base_dir, 'templates')

        if os.path.isdir(templates_path): # Check provided path first
            pass
        elif os.path.isdir(project_templates_path): # Fallback to path relative to this file
            templates_path = project_templates_path
        else:
            # If still not found, this will likely cause an error when get_template is called
            print(f"Warning: Templates path '{templates_path}' or '{project_templates_path}' not found. Check path.")
            # Defaulting to current directory, which might fail if template isn't there.
            templates_path = '.'


        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_path),
            autoescape=jinja2.select_autoescape(['html', 'xml', 'md']), # md is for completeness, not a standard autoescaped type
            trim_blocks=True,
            lstrip_blocks=True
        )
        # Make TaskStatus enum and other utilities available in templates
        self.env.globals['TaskStatus'] = models.TaskStatus
        self.env.globals['datetime'] = datetime
        self.env.globals['time'] = dt_time # Make datetime.time available as 'time' in Jinja

    def group_tasks_by_date(self, tasks: list[models.Task]) -> dict[date, list[models.Task]]:
        """
        Groups a list of tasks by their due date (ignoring time).
        Tasks without a due_dt are ignored. Tasks are sorted by due_dt within each group.
        The groups (dates) are sorted chronologically.

        Args:
            tasks: A list of Task objects.

        Returns:
            A dictionary where keys are date objects and values are lists of tasks for that date.
        """
        grouped = defaultdict(list)
        for task in tasks:
            if task.due_dt: # Only include tasks with a due date
                grouped[task.due_dt.date()].append(task)

        # Sort tasks within each day by their full due_dt
        for task_date in grouped:
            grouped[task_date].sort(key=lambda t: t.due_dt)

        # Return a dict sorted by date keys
        return dict(sorted(grouped.items()))

    def render_agenda(self, tasks: list[models.Task], output_filename: str, today: date = None):
        """
        Renders a list of tasks to a markdown agenda file using agenda.md.j2.

        Args:
            tasks: A list of Task objects to render.
            output_filename: The name of the markdown file to create/overwrite.
            today: The reference date for D-Day calculations. Defaults to date.today().
        """
        if today is None:
            today = date.today()

        tasks_by_date = self.group_tasks_by_date(tasks)

        try:
            template = self.env.get_template("agenda.md.j2")
        except jinja2.TemplateNotFound:
            print(f"Error: Template 'agenda.md.j2' not found in loader paths: {self.env.loader.searchpath}")
            return

        # The template 'agenda.md.j2' expects 'TaskStatus' and 'time' in its context,
        # which are already provided as globals in self.env.globals.
        rendered_content = template.render(
            tasks_by_date=tasks_by_date,
            today=today
            # TaskStatus, time, datetime are available via Jinja globals
        )

        try:
            # Ensure output directory exists if filename includes path
            output_dir = os.path.dirname(output_filename)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(rendered_content)
            print(f"Agenda rendered to {output_filename}")
        except IOError as e:
            print(f"Error writing to file {output_filename}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during rendering or writing: {e}")


    def placeholder_for_file_splitting(self):
        """
        Acknowledges the file splitting requirement.
        Actual implementation deferred.
        - File naming: Agenda-YYYY-MM.md, Agenda-YYYY-MM-Part-2.md
        - Line limit: ~1000 lines
        """
        print("Placeholder: File splitting logic (e.g., by month, by line count) is not yet implemented.")


if __name__ == '__main__':
    print("Testing ObsidianWriter...")

    # Mock Task objects for testing (mimicking SQLAlchemy model attributes)
    class MockTask:
        def __init__(self, id, title, due_dt_str, status_val, task_type="personal", body=""):
            self.id = id
            self.title = title
            # For due_dt, ensure it's a datetime object or None
            if due_dt_str:
                try:
                    self.due_dt = datetime.fromisoformat(due_dt_str)
                except ValueError: # Handle cases like "YYYY-MM-DD" if time is not there
                    self.due_dt = datetime.strptime(due_dt_str, '%Y-%m-%d')
            else:
                self.due_dt = None

            self.status = models.TaskStatus[status_val.upper()] # e.g., models.TaskStatus.TODO
            self.type = task_type # This corresponds to task_type_tag in template
            self.body = body
            # Other attributes expected by some parts of system, not directly by template
            self.source = "mock_source"
            self.created_dt = datetime.now()
            self.countdown_int = 0
            self.last_seen_dt = datetime.now()


    # Sample tasks for demonstration
    today_date = date.today()
    sample_tasks_data = [
        MockTask(1, "Team Meeting for Project X", (today_date + timedelta(days=0)).strftime('%Y-%m-%dT10:00:00'), "TODO", "meeting"),
        MockTask(2, "Submit AI Ethics Report", (today_date + timedelta(days=3)).strftime('%Y-%m-%dT23:59:00'), "TODO", "assignment"),
        MockTask(3, "Dentist Appointment", (today_date - timedelta(days=2)).strftime('%Y-%m-%dT14:30:00'), "DONE", "personal"),
        MockTask(4, "Project Alpha Final Review", today_date.isoformat(), "TODO", "project"), # All day task D-Day
        MockTask(5, "Cancelled: Weekly Sync", (today_date + timedelta(days=5)).strftime('%Y-%m-%dT09:00:00'), "CANCELLED", "meeting"),
        MockTask(6, "Plan Q3 Roadmap", (today_date + timedelta(days=10)).strftime('%Y-%m-%dT11:00:00'), "TODO", "planning"),
        MockTask(7, "Follow up with Client Y", (today_date + timedelta(days=10)).strftime('%Y-%m-%dT15:00:00'), "TODO", "client"), # Same day, different time
        MockTask(8, "Research new tools (no due date)", None, "TODO", "research"), # Will be ignored by group_tasks_by_date
        MockTask(9, "Old task from last month", (today_date - timedelta(days=30)).strftime('%Y-%m-%dT12:00:00'), "DONE", "archive"),
        MockTask(10, "Task for tomorrow midnight", (today_date + timedelta(days=1)).strftime('%Y-%m-%d'), "TODO", "general") # All day
    ]

    # Ensure the 'markdown_generator/templates' directory and 'agenda.md.j2' exist
    # The __init__ tries to find it, but for this test, let's be explicit about where it might be relative to /app
    # Assuming script is run from /app or tests/
    # For testing, let's assume the script is in /app/markdown_generator/writer.py
    # and templates are in /app/markdown_generator/templates/

    # The ObsidianWriter __init__ tries to find templates relative to its own file path.
    writer = ObsidianWriter()

    output_file = "test_agenda_output.md" # Will be created in the current working directory
    writer.render_agenda(sample_tasks_data, output_file, today=today_date)
    # To test with a different "today"
    # writer.render_agenda(sample_tasks_data, "test_agenda_output_future_today.md", today=today_date + timedelta(days=5))

    print(f"Example agenda written to {output_file}. Please review its content.")
    print("Note: If you see a Jinja2 TemplateNotFound error, check the templates_path in ObsidianWriter.")

    writer.placeholder_for_file_splitting()
