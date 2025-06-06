# Agenda Manager Project

This project is an Agenda Manager that ingests data from various sources (initially Gmail), processes it, and generates tasks and agenda views.

## Features (Planned/Implemented)

*   Data Ingestion (Gmail)
*   Text Normalization
*   Task Classification (Using LLM - OpenAI)
*   Date Resolution
*   Task Persistence (SQLite Database)
*   Markdown Agenda Generation
*   Scheduled Pipeline Runs (Daily)
*   Telegram notifications for pipeline status (success/failure)
*   KakaoTalk Ingestion (Experimental - Phase 1: Basic Setup Complete)

## Project Structure

*   `ingestion/`: Agents for data collection (e.g., `GmailAgent`).
*   `preprocessing/`: Text normalization utilities.
*   `extract_nlp/`: NLP tasks like classification and date resolution.
*   `persistence/`: Database models, CRUD operations, and session management.
*   `markdown_generator/`: Logic for creating markdown agenda files.
*   `scheduler/`: Job definitions and scheduler setup.
*   `tests/`: Unit and integration tests.
*   `docs/`: Documentation files.
*   `main.py`: Main application entry point, pipeline orchestration, and scheduler control.
*   `config.py`: Configuration settings (database URL, API keys).
*   `requirements.txt`: Project dependencies.

## Setup

1.  **Clone the repository.**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure Gmail API**: Follow the instructions in `docs/gmail_setup.md` to obtain `credentials.json` and place it in the project root.
4.  **Configure OpenAI API Key**: Follow the instructions in `docs/llm_setup.md` to set up your OpenAI API key (preferably as an environment variable `OPENAI_API_KEY`).
5.  **Configure Telegram Bot for Notifications**: Follow the instructions in `docs/telegram_setup.md` to set up your Telegram bot token and chat ID.
6.  **(Experimental)** Configure KakaoTalk Agent: See `docs/kakaotalk_setup.md`. This includes running `playwright install` for browser automation capabilities.
7.  **Database**: The SQLite database (`agenda.db`) and its tables will be created automatically when you first run `main.py` (if running the scheduler) or via the CLI `initdb` command.

## Running the Application

The primary way to run the application is to start its built-in scheduler. The scheduler will automatically trigger the data ingestion and processing pipeline at configured intervals.

### Prerequisites

Before running, ensure you have completed the setup steps outlined above, particularly:
*   Obtaining `credentials.json` as per `docs/gmail_setup.md`.
*   Configuring your OpenAI API key as per `docs/llm_setup.md`.
*   Installing all required dependencies from `requirements.txt`.

### Starting the Scheduler

To start the scheduler, run the main script from the project's root directory:

```bash
python main.py
```
(or `python3 main.py` depending on your Python installation and PATH setup)

This will:
1.  Perform initial database setup (create tables if they don't exist).
2.  Initialize and start the scheduler.
3.  The scheduler is configured by default to run the **Gmail ingestion pipeline daily at 22:00 KST (Korean Standard Time)**.

The application will then run in the foreground, printing log messages from the scheduler and the pipeline jobs to the console.

### Stopping the Scheduler

To stop the scheduler, press `Ctrl+C` in the terminal where it's running. The application should perform a graceful shutdown.

## Using the Command Line Interface (CLI)

The Agenda Manager includes a Command Line Interface (CLI) for interacting with your tasks directly without using the scheduler, or for manual task management.

To see all available CLI commands and their options, run:
```bash
python main.py cli --help
```

To run a specific command, for example, to list tasks:
```bash
python main.py cli list
```

### Common CLI Commands:

**1. Initialize Database (`initdb`)**
   Ensures database tables are created. This is useful for first-time setup if you are primarily using the CLI or before the first scheduler run.
   ```bash
   python main.py cli initdb
   ```

**2. Add a New Task (`add`)**
   Adds a new task to your agenda.
   ```bash
   # Add a task with title and due date
   python main.py cli add "Dentist Appointment" --due "tomorrow 3pm" --type "personal"

   # Add a task with more details
   python main.py cli add "Prepare Q3 Report" --due "next friday" --body "Finalize slides and gather all data." --type "work"
   ```
   *   `TITLE`: The title of the task (required argument).
   *   `--due` / `-d`: Due date (e.g., "tomorrow", "2024-12-25 17:00").
   *   `--body` / `-b`: Optional detailed description.
   *   `--type` / `-tt`: Task type (default: "personal").

**3. List Tasks (`list`)**
   Displays tasks from your agenda.
   ```bash
   # List all tasks (default limit 20, sorted by due_dt ascending)
   python main.py cli list

   # List only TODO tasks
   python main.py cli list --status todo

   # List tasks due before a certain date, sorted by title descending
   python main.py cli list --before "2024-06-01" --sort title --desc

   # List up to 5 tasks
   python main.py cli list --limit 5
   ```
   *   `--status` / `-s`: Filter by status (todo, done, cancelled).
   *   `--before` / `--after`: Filter by due date range (YYYY-MM-DD).
   *   `--limit` / `-n`: Number of tasks to show.
   *   `--sort`: Field to sort by (id, due_dt, title, status). Default for `due_dt` is ascending, for `id` is descending.
   *   `--asc` / `--desc`: Specify sorting order.

**4. Show Task Details (`show`)**
   Displays all information for a specific task.
   ```bash
   python main.py cli show <TASK_ID>
   # Example: python main.py cli show 123
   ```
   *   `<TASK_ID>`: The numerical ID of the task.

**5. Update a Task (`update`)**
   Modifies an existing task.
   ```bash
   # Update title and status of task with ID 42
   python main.py cli update 42 --title "Updated Q3 Report Title" --status done

   # Clear the due date for task with ID 43
   python main.py cli update 43 --due "none"

   # Update tags for task with ID 44
   python main.py cli update 44 --tags "important,#projectZ,review"

   # Clear all tags for task with ID 45
   python main.py cli update 45 --tags "CLEAR"
   ```
   *   `<TASK_ID>`: The numerical ID of the task to update.
   *   Provide options for fields to change (e.g., `--title` or `-T`, `--due` or `-d`, `--status` or `-s`, `--tags`).

**6. Manage Task Status**
   Quickly change a task's status. Replace `<TASK_ID>` with the actual task ID.
   *   **Mark as Done (`done`)**:
     ```bash
     python main.py cli done <TASK_ID>
     ```
   *   **Mark as Cancelled (`cancel`)**:
     ```bash
     python main.py cli cancel <TASK_ID>
     ```
   *   **Reopen Task / Mark as TODO (`todo`)**:
     ```bash
     python main.py cli todo <TASK_ID>
     ```

**7. Delete a Task (`delete`)**
   Removes a task from the agenda. You will be asked for confirmation.
   ```bash
   python main.py cli delete <TASK_ID>
   ```

**8. Synchronize with Obsidian Markdown File (`sync`)**
   Parses an Obsidian Markdown agenda file, matches tasks to the database, and synchronizes detected changes from Markdown to the database.
   This command can sync changes to **task status, title, and due date**.

   ```bash
   # Perform a dry-run (default) to see all potential changes (status, title, due date)
   python main.py cli sync path/to/your/agenda.md

   # Perform a live sync (applies all detected changes to DB after confirmation)
   python main.py cli sync path/to/your/agenda.md --no-dry-run
   ```
   *   `filepath`: (Required argument) Path to your Markdown agenda file.
   *   `--dry-run`: (Default: True) Show potential changes without modifying the database. Use `--no-dry-run` to enable applying changes.
   *   **How it works**:
        *   The command parses tasks from your Markdown file (including their status `[ ]`, `[x]`, `[c]`, title, and time).
        *   It attempts to match these tasks with existing tasks in the database based on a normalized version of the title and the task's time (or lack thereof for all-day tasks) on a given date.
        *   **For matched tasks, it detects differences in:**
            *   **Status**: e.g., if `[ ] Task A` in Markdown corresponds to a "DONE" Task A in the database.
            *   **Title**: If the text of the task in Markdown (after normalization) differs from the normalized title in the database.
            *   **Due Date/Time**: If the time specified in Markdown (e.g., `10:30 Task B`) or the date of the section for an all-day task differs from the `due_dt` in the database. The parser attempts to re-interpret the due date from the Markdown line.
        *   If you run a live sync (`--no-dry-run`):
            *   You will be shown a summary of all proposed changes (status, title, due date) and asked for confirmation before any modifications are made to the database.
            *   If confirmed, the database tasks will be updated with the values from the Markdown file.
            *   **Fingerprint Handling**: If a change to a task's title or due date results in a new "fingerprint" (a unique identifier based on normalized title and due date), the system checks if this new fingerprint would collide with a *different existing* task. If a collision is detected, the update for that specific task will be skipped to prevent creating data that looks like a duplicate of another existing entry.

---

## Future Enhancements (Conceptual)
*   Full KakaoTalk message reading and task creation.
*   Support for more data sources (e.g., other messengers, calendar APIs).
*   Web interface / API for user interaction.
*   More sophisticated de-duplication and conflict resolution.
*   Notification system.
*   Advanced security for sensitive data.
*   Comprehensive observability (logging, metrics, tracing).
