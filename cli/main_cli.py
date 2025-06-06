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
from typing import Dict, List # For type hints in sync command
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

@app.command(name="sync", help="Synchronize changes from an Obsidian Markdown agenda file (dry-run).")
def sync_obsidian_changes(
    filepath: Annotated[str, typer.Argument(help="Path to the Obsidian Markdown agenda file.")],
    dry_run: Annotated[bool, typer.Option(help="Only show what changes would be made, do not write to DB.")] = True
):
    """
    Parses an Obsidian Markdown agenda file, matches tasks to the database,
    and shows potential changes (currently, only status updates from MD to DB).
    """
    console.print(f"[bold cyan]Starting Obsidian Sync for file: {filepath}[/bold cyan]")
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        console.print(f"[bold red]Error: File not found or is not a file: {filepath}[/bold red]")
        raise typer.Exit(code=1)

    if dry_run:
        console.print("[yellow]Running in DRY-RUN mode. No changes will be made to the database.[/yellow]")

    parsed_md_tasks = parse_markdown_agenda_file(filepath)
    if not parsed_md_tasks:
        console.print("[yellow]No tasks found in the Markdown file or file could not be parsed.[/yellow]")
        return

    console.print(f"Found {len(parsed_md_tasks)} tasks in Markdown file.")

    db_gen = get_db_session()
    db = next(db_gen)

    potential_updates: List[Dict[str, Any]] = []
    tasks_not_found_in_db_count = 0
    tasks_found_but_no_change = 0

    try:
        # Efficiently fetch relevant DB tasks by grouping MD tasks by date first
        md_tasks_grouped_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for md_task in parsed_md_tasks:
            date_str = md_task.get("date_str")
            if date_str:
                md_tasks_grouped_by_date.setdefault(date_str, []).append(md_task)

        for date_str, md_task_list_on_date in md_tasks_grouped_by_date.items():
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                console.print(f"[yellow]Warning: Invalid date string '{date_str}' from MD parser. Skipping tasks for this date.[/yellow]")
                continue

            # Fetch DB tasks for this specific date once
            # This assumes crud.get_tasks can be modified or a new function like crud.get_tasks_on_date exists
            # For now, using a conceptual filter on all tasks (inefficient for large DBs)
            # console.print(f"[dim]Fetching DB tasks for date: {date_str}...[/dim]")
            all_db_tasks_on_date = [
                t for t in crud.get_tasks(db, limit=10000) # TODO: Optimize DB query
                if t.due_dt and t.due_dt.date() == date_obj
            ]
            # console.print(f"[dim]Found {len(all_db_tasks_on_date)} DB tasks for {date_str}.[/dim]")


            for md_task in md_task_list_on_date:
                matched_db_task = find_matching_task_in_db(md_task, all_db_tasks_on_date)

                if matched_db_task:
                    md_status_str = md_task.get("status_md")
                    md_status_enum = get_status_from_md_marker(md_status_str) if md_status_str else None

                    if md_status_enum and matched_db_task.status != md_status_enum:
                        potential_updates.append({
                            "task_id": matched_db_task.id,
                            "db_title": matched_db_task.title,
                            "change_type": "status",
                            "from_db": matched_db_task.status.name if matched_db_task.status else "N/A",
                            "to_md": md_status_enum.name
                        })
                    else:
                        tasks_found_but_no_change +=1
                        # console.print(f"[dim]MD Task '{md_task.get('title_md')}' matched DB Task ID {matched_db_task.id}. No status change needed.[/dim]")

                    # Conceptual: Add more comparisons here (title, due_dt, tags) if needed for Phase 2
                else:
                    tasks_not_found_in_db_count +=1
                    # console.print(f"[dim]MD Task '{md_task.get('title_md')}' on {date_str} - No unique DB match found.[/dim]")

        console.print(f"Processed {len(parsed_md_tasks)} MD tasks. {len(potential_updates)} potential status changes.")
        if tasks_not_found_in_db_count > 0:
            console.print(f"[yellow]{tasks_not_found_in_db_count} MD tasks could not be matched to DB tasks.[/yellow]")
        if tasks_found_but_no_change > 0:
            console.print(f"[dim]{tasks_found_but_no_change} MD tasks matched DB tasks with no status difference.[/dim]")


        if not potential_updates:
            if tasks_not_found_in_db_count == 0 : # Only print this if there were also no unmatched tasks
                 console.print("[green]No differences found between Markdown file and database tasks (for status).[/green]")
        else:
            console.print(f"\n[bold yellow]Detected {len(potential_updates)} potential status updates (Dry Run):[/bold yellow]")
            table = Table(title="Potential Task Status Updates (Dry Run)")
            table.add_column("DB ID", style="dim", justify="right")
            table.add_column("Task Title (DB)")
            table.add_column("Change Field")
            table.add_column("From (DB Value)")
            table.add_column("To (MD Value)")

            for update in potential_updates:
                table.add_row(
                    str(update["task_id"]),
                    update["db_title"],
                    update["change_type"],
                    update["from_db"],
                    update["to_md"]
                )
            console.print(table)

            if not dry_run:
                console.print("\n[INFO] Actual database updates for 'sync' command not yet implemented.", style="yellow")
                # TODO: Implement actual DB updates in Phase 2
                # if typer.confirm("Proceed with these status updates to the database?"):
                #    for update_item in potential_updates:
                #        if update_item['change_type'] == 'status':
                #            new_status_enum = TaskStatus[update_item['to_md']]
                #            crud.update_task(db, update_item['task_id'], {"status": new_status_enum})
                #    console.print("[green]Database updated with status changes.[/green]")
                # else:
                #    console.print("Database update cancelled by user.")

    except Exception as e:
        console.print(f"[bold red]An error occurred during sync process: {e}[/bold red]")
        # import traceback; traceback.print_exc(); # For debugging full trace
    finally:
        next(db_gen, None) # Ensure session is closed
