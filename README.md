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
5.  **Database**: The SQLite database (`agenda.db`) and its tables will be created automatically when you first run `main.py`.

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

## Future Enhancements (Conceptual)
*   Support for more data sources (e.g., KakaoTalk, calendar).
*   Web interface / API for user interaction.
*   More sophisticated de-duplication and conflict resolution.
*   Notification system.
*   Advanced security for sensitive data.
*   Comprehensive observability (logging, metrics, tracing).
