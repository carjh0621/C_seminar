# cli/main_cli.py
import typer
from typing_extensions import Annotated
from rich.console import Console
from rich.table import Table
from datetime import datetime, date, time as dt_time # Ensure date and time are imported

# --- Backend Logic Imports ---
from persistence.database import SessionLocal, create_db_tables
from persistence import crud
from extract_nlp.utils import generate_task_fingerprint
from extract_nlp.classifiers import resolve_date # For parsing date strings from CLI
from persistence.models import TaskStatus, Task # For status enum and type hints
import os # For path operations

# --- New imports for Obsidian Sync ---
from obsidian_sync.parser import parse_markdown_agenda_file
from obsidian_sync.matcher import find_matching_task_in_db
from typing import Dict, List, Any # For type hints in sync command
from extract_nlp.utils import normalize_title_for_fingerprint # Added for title comparison
# --- End new imports ---
# --- End Backend Logic Imports ---

console = Console()
app = typer.Typer(
    name="agenda-cli",
    help="Agenda Manager CLI - Manage your tasks from the command line.",
    no_args_is_help=True # Show help if no command is given
)

# --- Helper function to get DB session ---
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Helper function to format a single task for display ---
def format_task_details(task: Task) -> str:
    if not task:
        return "[red]Task not found.[/red]"

    status_emoji = {
        TaskStatus.TODO: "⏳",
        TaskStatus.DONE: "✅",
        TaskStatus.CANCELLED: "❌"
    }

    details = f"[bold cyan]Task ID: {task.id}[/bold cyan]\n"
    details += f"  Title    : {task.title}\n"
    details += f"  Status   : {(status_emoji.get(task.status, '') + ' ' + task.status.name) if task.status else 'N/A'}\n"
    details += f"  Due Date : {task.due_dt.strftime('%Y-%m-%d %H:%M') if task.due_dt else 'Not set'}\n"
    details += f"  Type     : {task.type if task.type else 'N/A'}\n"
    details += f"  Body     : {task.body if task.body else 'N/A'}\n"
    details += f"  Tags     : {task.tags if task.tags else 'None'}\n"
    details += f"  Source   : {task.source if task.source else 'N/A'}\n"
    details += f"  Fingerprt: {task.fingerprint if task.fingerprint else 'N/A'}\n"
    details += f"  Created  : {task.created_dt.strftime('%Y-%m-%d %H:%M') if task.created_dt else 'N/A'}\n"
    if task.last_modified_dt and task.last_modified_dt != task.created_dt : # Show if modified
        details += f"  Modified : {task.last_modified_dt.strftime('%Y-%m-%d %H:%M')}\n"
    return details

# --- CLI Commands Implementation ---

@app.command(name="add", help="Add a new task to the agenda.")
def add_task_cmd(
    title: Annotated[str, typer.Argument(help="The title of the task.")],
    due_date_str: Annotated[str, typer.Option("--due", "-d", help="Due date (e.g., 'tomorrow 3pm', '2024-12-31').")] = None,
    body: Annotated[str, typer.Option("--body", "-b", help="Detailed description for the task.")] = None,
    task_type: Annotated[str, typer.Option("--type", "-tt", help="Type of task (e.g., personal, work).")] = "personal"
):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        due_datetime = None
        if due_date_str:
            due_datetime = resolve_date(due_date_str)
            if not due_datetime:
                console.print(f"[bold red]Error: Could not parse due date string: '{due_date_str}'[/bold red]")
                raise typer.Exit(code=1)

        fingerprint = generate_task_fingerprint(title, due_datetime)

        existing_task = crud.get_task_by_fingerprint(db, fingerprint)
        if existing_task:
            console.print(f"[yellow]Warning: A similar task already exists (ID: {existing_task.id}, Title: '{existing_task.title}').[/yellow]")
            if not typer.confirm("Do you want to add this task anyway?", default=False):
                console.print("Task addition cancelled.")
                raise typer.Exit()

        task_data = {
            "title": title, "due_dt": due_datetime, "body": body,
            "type": task_type, "status": TaskStatus.TODO,
            "fingerprint": fingerprint, "source": "cli",
            "tags": None # Tags can be added via update
        }
        created_task = crud.create_task(db, task_data)
        console.print(f"[green]Task added successfully![/green]")
        console.print(format_task_details(created_task))
    except typer.Exit: # Re-raise Typer Exit exceptions
        raise
    except Exception as e:
        console.print(f"[bold red]Error adding task: {e}[/bold red]")
        raise typer.Exit(code=1)
    finally:
        next(db_gen, None)

@app.command(name="list", help="List tasks from the agenda.")
def list_tasks_cmd(
    status_filter_str: Annotated[str, typer.Option("--status", "-s", help="Filter by status (todo, done, cancelled). Case insensitive.")] = None,
    due_before_str: Annotated[str, typer.Option("--before", help="Filter tasks due before this date (YYYY-MM-DD).")] = None,
    due_after_str: Annotated[str, typer.Option("--after", help="Filter tasks due after this date (YYYY-MM-DD).")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum number of tasks to display.")] = 20,
    sort_by: Annotated[str, typer.Option("--sort", help="Sort by field (id, due_dt, title, status). Default: due_dt.")] = "due_dt",
    ascending: Annotated[bool, typer.Option(help="Sort order. Default: --asc for due_dt, title; --desc for id.")] = None # Default based on sort_by
):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        status_enum = None
        if status_filter_str:
            try:
                status_enum = TaskStatus[status_filter_str.upper()]
            except KeyError:
                console.print(f"[bold red]Error: Invalid status filter '{status_filter_str}'. Valid are: todo, done, cancelled.[/bold red]")
                raise typer.Exit(code=1)

        due_before = resolve_date(due_before_str, custom_settings={'STRICT_PARSING': True, 'REQUIRE_PARTS': ['year', 'month', 'day']}) if due_before_str else None
        due_after = resolve_date(due_after_str, custom_settings={'STRICT_PARSING': True, 'REQUIRE_PARTS': ['year', 'month', 'day']}) if due_after_str else None

        # For now, use a simplified get_tasks and filter in Python.
        # TODO: Enhance crud.get_tasks to accept more filters for DB-level filtering.
        all_tasks = crud.get_tasks(db, skip=0, limit=1000) # A high limit for now

        tasks_to_display = []
        for task in all_tasks:
            if status_enum and task.status != status_enum: continue
            if due_before and task.due_dt and task.due_dt >= due_before: continue
            if due_after and task.due_dt and task.due_dt <= due_after: continue
            tasks_to_display.append(task)

        # Determine default sort order if not specified by user
        if ascending is None:
            if sort_by == "id": ascending = False # Default sort id descending (newest first)
            else: ascending = True # Default sort others ascending

        # Client-side sorting
        reverse_sort = not ascending
        if sort_by == "due_dt":
            tasks_to_display.sort(key=lambda t: t.due_dt or datetime.min, reverse=reverse_sort)
        elif sort_by == "title":
            tasks_to_display.sort(key=lambda t: t.title.lower(), reverse=reverse_sort)
        elif sort_by == "status":
             tasks_to_display.sort(key=lambda t: (t.status.name if t.status else "").lower(), reverse=reverse_sort)
        elif sort_by == "id":
            tasks_to_display.sort(key=lambda t: t.id, reverse=reverse_sort)

        tasks_to_display = tasks_to_display[:limit]

        if not tasks_to_display:
            console.print("[yellow]No tasks found matching your criteria.[/yellow]")
            return

        table = Table(title="Tasks")
        table.add_column("ID", style="dim", width=5, justify="right")
        table.add_column("Title", style="bold", min_width=20, overflow="fold")
        table.add_column("Due Date", width=16)
        table.add_column("Status", width=12)
        table.add_column("Type", width=10, overflow="fold")
        table.add_column("Tags", min_width=10, overflow="fold")

        status_emoji = {"TODO": "⏳", "DONE": "✅", "CANCELLED": "❌"}
        for task in tasks_to_display:
            due_str = task.due_dt.strftime("%Y-%m-%d %H:%M") if task.due_dt else "N/A"
            status_str = f"{status_emoji.get(task.status.name, '')} {task.status.name}" if task.status else "N/A"
            table.add_row(str(task.id), task.title, due_str, status_str, task.type or "", task.tags or "")
        console.print(table)
    finally:
        next(db_gen, None)

@app.command(name="show", help="Show details of a specific task.")
def show_task_cmd(task_id: Annotated[int, typer.Argument(help="The ID of the task to display.")]):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        task = crud.get_task(db, task_id)
        if task:
            console.print(format_task_details(task))
        else:
            console.print(f"[bold red]Error: Task with ID {task_id} not found.[/bold red]")
            raise typer.Exit(code=1)
    finally:
        next(db_gen, None)

@app.command(name="update", help="Update an existing task.")
def update_task_cmd(
    task_id: Annotated[int, typer.Argument(help="The ID of the task to update.")],
    title: Annotated[str, typer.Option("--title", "-T", help="New title for the task.")] = None,
    due_date_str: Annotated[str, typer.Option("--due", "-d", help="New due date (e.g., 'tomorrow', '2024-12-31 5pm', or 'none' to clear).")] = None,
    body: Annotated[str, typer.Option("--body", "-b", help="New body/description for the task.")] = None,
    status_filter_str: Annotated[str, typer.Option("--status", "-s", help="New status (todo, done, cancelled). Case insensitive.")] = None, # Renamed for clarity
    task_type: Annotated[str, typer.Option("--type", "-tt", help="New type for the task.")] = None,
    tags: Annotated[str, typer.Option("--tags", help="New comma-separated tags. Use 'CLEAR' to remove all tags.")] = None
):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        task_to_update = crud.get_task(db, task_id)
        if not task_to_update:
            console.print(f"[bold red]Error: Task with ID {task_id} not found.[/bold red]")
            raise typer.Exit(code=1)

        update_data = {}
        if title is not None: update_data["title"] = title
        if body is not None: update_data["body"] = body
        if task_type is not None: update_data["type"] = task_type

        new_due_dt_is_set = False
        if due_date_str is not None:
            new_due_dt_is_set = True
            if due_date_str.lower() == "none" or due_date_str.lower() == "clear":
                update_data["due_dt"] = None
            else:
                resolved_due_dt = resolve_date(due_date_str)
                if not resolved_due_dt:
                    console.print(f"[bold red]Error: Invalid due date string '{due_date_str}'[/bold red]")
                    raise typer.Exit(code=1)
                update_data["due_dt"] = resolved_due_dt

        if status_filter_str is not None:
            try:
                update_data["status"] = TaskStatus[status_filter_str.upper()]
            except KeyError:
                console.print(f"[bold red]Error: Invalid status '{status_filter_str}'. Valid: todo, done, cancelled.[/bold red]")
                raise typer.Exit(code=1)

        if tags is not None:
            update_data["tags"] = None if tags.upper() == "CLEAR" else tags

        if not update_data:
            console.print("[yellow]No update information provided.[/yellow]")
            return

        # Fingerprint regeneration if title or due_dt changed
        regen_fp_title = update_data.get("title", task_to_update.title)
        regen_fp_due_dt = update_data.get("due_dt", task_to_update.due_dt) if new_due_dt_is_set else task_to_update.due_dt

        if "title" in update_data or new_due_dt_is_set:
            new_fingerprint = generate_task_fingerprint(regen_fp_title, regen_fp_due_dt)
            if new_fingerprint != task_to_update.fingerprint:
                existing_with_new_fp = crud.get_task_by_fingerprint(db, new_fingerprint)
                if existing_with_new_fp and existing_with_new_fp.id != task_id:
                    console.print(f"[bold red]Error: Update would create a duplicate fingerprint with Task ID {existing_with_new_fp.id}. Operation aborted.[/bold red]")
                    raise typer.Exit(code=1)
                update_data["fingerprint"] = new_fingerprint

        updated_task = crud.update_task(db, task_id, update_data)
        if updated_task:
            console.print("[green]Task updated successfully![/green]")
            console.print(format_task_details(updated_task))
        else:
            console.print(f"[bold red]Error: Task with ID {task_id} update failed (possibly not found after initial check).[/bold red]")
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error updating task: {e}[/bold red]")
        raise typer.Exit(code=1)
    finally:
        next(db_gen, None)

def _change_task_status(db_session, task_id: int, new_status: TaskStatus):
    # Fingerprint should not change when only status changes.
    updated_task = crud.update_task(db_session, task_id, {"status": new_status})
    if updated_task:
        console.print(f"[green]Task ID {task_id} status changed to {new_status.name} successfully![/green]")
        console.print(format_task_details(updated_task))
    else:
        console.print(f"[bold red]Error: Task with ID {task_id} not found or update failed.[/bold red]")
        raise typer.Exit(code=1)

@app.command(name="done", help="Mark a task as DONE.")
def complete_task_cmd(task_id: Annotated[int, typer.Argument(help="ID of the task.")]):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        _change_task_status(db, task_id, TaskStatus.DONE)
    finally:
        next(db_gen, None)

@app.command(name="cancel", help="Mark a task as CANCELLED.")
def cancel_task_cmd(task_id: Annotated[int, typer.Argument(help="ID of the task.")]):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        _change_task_status(db, task_id, TaskStatus.CANCELLED)
    finally:
        next(db_gen, None)

@app.command(name="todo", help="Mark a task as TODO (reopen).")
def reopen_task_cmd(task_id: Annotated[int, typer.Argument(help="ID of the task.")]):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        _change_task_status(db, task_id, TaskStatus.TODO)
    finally:
        next(db_gen, None)

@app.command(name="delete", help="Delete a task permanently.")
def delete_task_cli_cmd(task_id: Annotated[int, typer.Argument(help="ID of the task to delete.")]):
    db_gen = get_db_session()
    db = next(db_gen)
    try:
        task_to_delete = crud.get_task(db, task_id)
        if not task_to_delete:
            console.print(f"[bold red]Error: Task with ID {task_id} not found.[/bold red]")
            raise typer.Exit(code=1)

        console.print("[yellow]You are about to delete the following task:[/yellow]")
        console.print(format_task_details(task_to_delete))
        if not typer.confirm("Are you sure you want to delete this task?", default=False):
            console.print("Deletion cancelled.")
            raise typer.Exit()

        deleted = crud.delete_task(db, task_id)
        if deleted:
            console.print(f"[green]Task ID {task_id} deleted successfully.[/green]")
        else:
            console.print(f"[bold red]Error: Task with ID {task_id} not found for deletion (should have been caught earlier).[/bold red]")
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Error deleting task: {e}[/bold red]")
        raise typer.Exit(code=1)
    finally:
        next(db_gen, None)

@app.command(name="initdb", help="Initialize the database (create tables). For dev/setup.")
def init_db_command():
    """Utility to create database tables if they don't exist."""
    try:
        console.print("Initializing database and creating tables if they don't exist...")
        create_db_tables()
        console.print("[green]Database tables checked/created successfully.[/green]")
    except Exception as e:
        console.print(f"[bold red]Error initializing database: {e}[/bold red]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()

# --- Helper for sync command ---
def get_status_from_md_marker(status_md: str) -> TaskStatus | None:
    """Converts Markdown status marker to TaskStatus enum."""
    if status_md == "[x]" or status_md == "[X]":
        return TaskStatus.DONE
    elif status_md == "[ ]":
        return TaskStatus.TODO
    elif status_md == "[c]" or status_md == "[C]": # Assuming [c] is for cancelled
        return TaskStatus.CANCELLED
    # Add other markers if necessary, e.g., [-] for irrelevant, [>] for delegated
    console.print(f"[dim]Unknown MD status marker: '{status_md}'[/dim]")
    return None

@app.command(name="sync", help="Synchronize task status changes from an Obsidian Markdown agenda file to the database.")
def sync_obsidian_changes(
    filepath: Annotated[str, typer.Argument(help="Path to the Obsidian Markdown agenda file.")],
    dry_run: Annotated[bool, typer.Option(help="Show what changes would be made, without writing to DB.")] = True
):
    """
    Parses an Obsidian Markdown agenda file, matches tasks to the database,
    and applies status changes from Markdown to the database if not in dry-run mode.
    Currently focuses on syncing task status (TODO, DONE, CANCELLED).
    """
    console.print(f"[bold cyan]Starting Obsidian Sync for file: {filepath}[/bold cyan]")
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        console.print(f"[bold red]Error: File not found or is not a file: {filepath}[/bold red]")
        raise typer.Exit(code=1)

    if dry_run:
        console.print("[yellow]Running in DRY-RUN mode. No changes will be made to the database.[/yellow]")
    else:
        console.print("[bold yellow]WARNING: Running in LIVE mode. Database changes WILL be applied.[/bold yellow]")


    parsed_md_tasks = parse_markdown_agenda_file(filepath)
    if not parsed_md_tasks:
        console.print("[yellow]No tasks found in the Markdown file or file could not be parsed.[/yellow]")
        return

    console.print(f"Found {len(parsed_md_tasks)} tasks in Markdown file.")

    db_gen = get_db_session()
    db = next(db_gen)

    # Stores dicts: {"task_id": ..., "db_title": ..., "change_type": "status",
    #                "from_db_enum": TaskStatus, "to_md_enum": TaskStatus}
    potential_updates: List[Dict[str, Any]] = []

    md_tasks_processed = 0
    matched_tasks_count = 0
    no_overall_change_count = 0 # Tasks matched but no status, title, or due_dt diff

    try:
        md_dates_str = sorted(list(set(md_task['date_str'] for md_task in parsed_md_tasks if md_task['date_str'])))
        db_tasks_by_date_map: Dict[str, List[Task]] = {}
        for date_str_to_fetch in md_dates_str:
            try:
                date_obj = datetime.strptime(date_str_to_fetch, "%Y-%m-%d").date()
                if hasattr(crud, 'get_tasks_on_date'):
                    all_db_tasks_for_day = crud.get_tasks_on_date(db, target_date=date_obj) # type: ignore
                else:
                    if not hasattr(crud, '_warned_get_tasks_on_date'):
                        console.print(f"[yellow]Developer Note: crud.get_tasks_on_date not found, using inefficient fallback.[/yellow]")
                        crud._warned_get_tasks_on_date = True # type: ignore
                    all_db_tasks = crud.get_tasks(db, limit=10000)
                    all_db_tasks_for_day = [t for t in all_db_tasks if t.due_dt and t.due_dt.date() == date_obj]
                db_tasks_by_date_map[date_str_to_fetch] = all_db_tasks_for_day
            except ValueError:
                console.print(f"[yellow]Warning: Invalid date string '{date_str_to_fetch}' from MD. Skipping.[/yellow]")
                db_tasks_by_date_map[date_str_to_fetch] = []

        for md_task in parsed_md_tasks:
            md_tasks_processed += 1
            md_date_str = md_task.get("date_str")
            if not md_date_str: continue

            db_tasks_on_this_date = db_tasks_by_date_map.get(md_date_str, [])
            matched_db_task = find_matching_task_in_db(md_task, db_tasks_on_this_date)

            if matched_db_task:
                matched_tasks_count += 1
                task_changed_details: List[Dict[str,Any]] = [] # Store specific changes for this task

                # --- 1. Compare Status ---
                md_status_str = md_task.get("status_md")
                md_status_enum = get_status_from_md_marker(md_status_str) if md_status_str else None
                if md_status_enum and matched_db_task.status != md_status_enum:
                    task_changed_details.append({
                        "change_type": "status",
                        "from_db": matched_db_task.status.name if matched_db_task.status else "N/A",
                        "to_md": md_status_enum.name,
                        "to_md_enum_or_dt": md_status_enum
                    })

                # --- 2. Compare Title ---
                md_title = str(md_task.get("title_md", ""))
                normalized_md_title = normalize_title_for_fingerprint(md_title)
                normalized_db_title = normalize_title_for_fingerprint(matched_db_task.title)
                if normalized_md_title != normalized_db_title:
                    task_changed_details.append({
                        "change_type": "title",
                        "from_db": matched_db_task.title,
                        "to_md": md_title,
                        "to_md_enum_or_dt": md_title
                    })

                # --- 3. Compare Due Date ---
                md_due_datetime: Optional[datetime] = None
                # Simplified due date resolution from MD: use date_str + time_str if available, else just date_str
                if md_task.get("time_str"):
                    md_due_datetime = resolve_date(f"{md_task['date_str']} {md_task['time_str']}")
                elif md_task['date_str']:
                    md_due_datetime = resolve_date(md_task['date_str'])

                db_due_dt = matched_db_task.due_dt
                due_dates_differ = False
                if md_due_datetime is None and db_due_dt is not None:
                    due_dates_differ = True
                elif md_due_datetime is not None and db_due_dt is None:
                    due_dates_differ = True
                elif md_due_datetime and db_due_dt:
                    if md_due_datetime.date() != db_due_dt.date():
                        due_dates_differ = True
                    else:
                        md_time = md_due_datetime.time()
                        db_time = db_due_dt.time()
                        is_md_all_day = (md_time == dt_time(0,0,0))
                        is_db_all_day = (db_time == dt_time(0,0,0))
                        if is_md_all_day != is_db_all_day:
                            due_dates_differ = True
                        elif not is_md_all_day and md_time != db_time:
                            due_dates_differ = True

                if due_dates_differ:
                    task_changed_details.append({
                        "change_type": "due_dt",
                        "from_db": db_due_dt.isoformat() if db_due_dt else "None",
                        "to_md": md_due_datetime.isoformat() if md_due_datetime else "None",
                        "to_md_enum_or_dt": md_due_datetime
                    })

                if task_changed_details:
                    for change_detail in task_changed_details:
                        potential_updates.append({
                            "task_id": matched_db_task.id,
                            "db_title": matched_db_task.title, # Original DB title for context
                            **change_detail # Add change_type, from_db, to_md, to_md_enum_or_dt
                        })
                else:
                    no_overall_change_count +=1

        # --- Reporting and Applying Changes ---
        if not potential_updates:
            console.print("[green]No differences (status, title, or due date) found between Markdown file and database tasks.[/green]")
        else:
            title_suffix = "(Dry Run)" if dry_run else "(Live Run - Pending Confirmation)"
            console.print(f"\n[bold yellow]Detected {len(potential_updates)} potential updates {title_suffix}:[/bold yellow]")
            table = Table(title=f"Potential Task Updates {title_suffix}")
            table.add_column("DB ID", style="dim", justify="right")
            table.add_column("Task Title (DB)")
            table.add_column("Change Field")
            table.add_column("From (DB Status)")
            table.add_column("To (MD Status)")

            for update_info in potential_updates:
                table.add_row(
                    str(update_info["task_id"]),
                    update_info["db_title"],
                    update_info["change_type"],
                    update_info["from_db_enum"].name if update_info["from_db_enum"] else "N/A",
                    update_info["to_md_enum"].name if update_info["to_md_enum"] else "N/A"
                )
            console.print(table)

            if not dry_run:
                console.print("\n[bold]Applying detected updates to the database...[/bold]")
                # Corrected confirmation message to reflect total field changes vs task count
                unique_task_ids_to_update = len(set(pu['task_id'] for pu in potential_updates))
                if typer.confirm(f"Proceed with {len(potential_updates)} potential field changes across {unique_task_ids_to_update} tasks?", abort=True):
                    applied_changes_count = 0 # Counts individual field changes successfully applied
                    tasks_updated_successfully_count = 0 # Counts tasks that had at least one successful change
                    tasks_failed_to_update_count = 0   # Counts tasks where all proposed changes failed or task vanished

                    # Group changes by task_id to make one update call per task
                    changes_by_task_id: Dict[int, Dict[str, Any]] = {}
                    for update_info in potential_updates:
                        task_id = update_info["task_id"]
                        if task_id not in changes_by_task_id:
                            changes_by_task_id[task_id] = {
                                "update_payload": {},
                                "original_task_title": update_info["db_title"] # For logging
                            }

                        change_type = update_info["change_type"]
                        new_value = update_info["to_md_enum_or_dt"]

                        if change_type == "status":
                            changes_by_task_id[task_id]["update_payload"]["status"] = new_value
                        elif change_type == "title":
                            changes_by_task_id[task_id]["update_payload"]["title"] = new_value
                        elif change_type == "due_dt":
                            changes_by_task_id[task_id]["update_payload"]["due_dt"] = new_value

                    processed_task_ids_for_summary = set()

                    for task_id, task_changes_info in changes_by_task_id.items():
                        update_payload = task_changes_info["update_payload"]
                        original_task_title_for_log = task_changes_info["original_task_title"]

                        task_update_succeeded_for_any_field = False

                        # Fingerprint regeneration if title or due_dt changed
                        if "title" in update_payload or "due_dt" in update_payload:
                            db_task_to_update = crud.get_task(db, task_id)
                            if not db_task_to_update:
                                console.print(f"  [red]Error: Task ID {task_id} (Title: '{original_task_title_for_log}') not found in DB before update. Skipping.[/red]")
                                if task_id not in processed_task_ids_for_summary : tasks_failed_to_update_count +=1
                                processed_task_ids_for_summary.add(task_id)
                                continue

                            new_title_for_fp = update_payload.get("title", db_task_to_update.title)
                            new_due_dt_for_fp = update_payload.get("due_dt")
                            if "due_dt" not in update_payload:
                                new_due_dt_for_fp = db_task_to_update.due_dt

                            try:
                                new_fingerprint = generate_task_fingerprint(new_title_for_fp, new_due_dt_for_fp)
                                if new_fingerprint != db_task_to_update.fingerprint:
                                    existing_task_with_new_fp = crud.get_task_by_fingerprint(db, new_fingerprint)
                                    if existing_task_with_new_fp and existing_task_with_new_fp.id != task_id:
                                        console.print(f"  [red]Error for Task ID {task_id} (Title: '{original_task_title_for_log}'): "
                                                      f"Update would create a fingerprint collision with Task ID {existing_task_with_new_fp.id}. Update for this task aborted.[/red]")
                                        if task_id not in processed_task_ids_for_summary : tasks_failed_to_update_count +=1
                                        processed_task_ids_for_summary.add(task_id)
                                        continue
                                update_payload["fingerprint"] = new_fingerprint
                            except ValueError as ve_fp:
                                 console.print(f"  [red]Error generating fingerprint for Task ID {task_id} (Title: '{new_title_for_fp}'): {ve_fp}. Update for this task aborted.[/red]")
                                 if task_id not in processed_task_ids_for_summary : tasks_failed_to_update_count +=1
                                 processed_task_ids_for_summary.add(task_id)
                                 continue

                        # Apply the update
                        if not update_payload: # Should not happen if potential_updates had items for this task_id
                            if task_id not in processed_task_ids_for_summary : tasks_failed_to_update_count +=1 # Or just log as no-op
                            processed_task_ids_for_summary.add(task_id)
                            continue

                        try:
                            # Log what's being sent for update (excluding enums that are not str-friendly directly)
                            loggable_payload = {k: (v.name if hasattr(v, 'name') else v) for k, v in update_payload.items()}
                            console.print(f"  Updating Task ID {task_id} (Original Title: '{original_task_title_for_log}') with: {loggable_payload}")
                            updated_task_obj = crud.update_task(db, task_id, update_payload)
                            if updated_task_obj:
                                console.print(f"    [green]Successfully updated Task ID {task_id}.[/green]")
                                applied_changes_count += len(update_payload) # Count fields changed
                                if task_id not in processed_task_ids_for_summary : tasks_updated_successfully_count +=1
                                task_update_succeeded_for_any_field = True
                            else: # crud.update_task returned None
                                console.print(f"    [red]Failed to update Task ID {task_id} - crud.update_task returned None (task possibly deleted during sync?).[/red]")
                                if task_id not in processed_task_ids_for_summary : tasks_failed_to_update_count +=1
                        except Exception as e_update:
                            console.print(f"    [red]Error applying update for Task ID {task_id}: {e_update}[/red]")
                            if task_id not in processed_task_ids_for_summary : tasks_failed_to_update_count +=1

                        processed_task_ids_for_summary.add(task_id)


                    console.print(f"\n[bold green]Database update process complete.[/bold]")
                    console.print(f"  Updates applied for: {tasks_updated_successfully_count} tasks.")
                    # Total individual field changes applied might be more interesting than tasks_updated_successfully_count
                    # For now, tasks_updated_successfully_count means tasks for which at least one field was attempted to be updated and succeeded.
                    # The initial applied_changes_count would be len(potential_updates) if all went well.
                    # Let's refine summary based on successful `crud.update_task` calls rather than fields.
                    console.print(f"  Total tasks with at least one successful change: {tasks_updated_successfully_count}")
                    if tasks_failed_to_update_count > 0: # This counts tasks where all changes failed or task vanished
                        console.print(f"  [bold red]Failed to apply any changes for: {tasks_failed_to_update_count} tasks.[/bold red]")

        console.print(f"\nSync Summary: MD Tasks Processed: {md_tasks_processed}, DB Tasks Matched: {matched_tasks_count}, Potential Updates (field changes): {len(potential_updates)}, Matched with No Change: {no_overall_change_count}")

    except typer.Abort:
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
    except Exception as e:
        console.print(f"[bold red]An error occurred during sync process: {e}[/bold red]")
        # import traceback; traceback.print_exc(); # For debugging
    finally:
        next(db_gen, None)
