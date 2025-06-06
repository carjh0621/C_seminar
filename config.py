import os
from dotenv import load_dotenv # For loading .env file

# Load environment variables from .env file if it exists
# This allows overriding default configurations or setting sensitive keys locally.
load_dotenv()

# --- General Configurations ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agenda.db")


# --- OpenAI API Key Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_API_KEY_HERE")


# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID_HERE")


# --- KakaoTalk Agent Configuration (New) ---
# Name of the KakaoTalk chat room to monitor for messages.
# Example: your "Chat with myself" or a specific group chat name.
KAKAOTALK_CHAT_NAME_TO_MONITOR = os.getenv("KAKAOTALK_CHAT_NAME_TO_MONITOR", "My Notes Chat") # Default example

# Optional: Path to a Playwright user data directory for persistent browser sessions for KakaoTalk.
# If set, KakaoAgent will try to use it.
# If None or empty string, a temporary context will be used by Playwright.
# Example path: "./kakaotalk_playwright_user_data" (ensure this is in .gitignore if used)
KAKAOTALK_USER_DATA_DIR = os.getenv("KAKAOTALK_USER_DATA_DIR", None)


# --- Feedback on Configurations (Helper Function) ---
def print_config_feedback():
    """Prints feedback on the current configuration status, highlighting placeholders."""
    console_lines = ["--- Configuration Feedback ---"]

    # Database
    if DATABASE_URL == "sqlite:///./agenda.db":
        console_lines.append("INFO: Using default SQLite database (agenda.db).")
    else:
        console_lines.append(f"INFO: DATABASE_URL is set to: {DATABASE_URL}")

    # OpenAI
    if OPENAI_API_KEY == "YOUR_API_KEY_HERE" or not OPENAI_API_KEY:
        console_lines.append("WARNING: OpenAI API Key is using the placeholder or is not set. LLM features will not work.")
        console_lines.append("         Refer to docs/llm_setup.md to configure it (e.g., via OPENAI_API_KEY env var).")
    else:
        console_lines.append("INFO: OpenAI API Key is SET.")

    # Telegram
    telegram_token_is_placeholder = TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or not TELEGRAM_BOT_TOKEN
    telegram_chat_id_is_placeholder = TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID_HERE" or not TELEGRAM_CHAT_ID

    if telegram_token_is_placeholder or telegram_chat_id_is_placeholder:
        warning_msg = "WARNING: Telegram configurations are using placeholders or are not set."
        if telegram_token_is_placeholder: warning_msg += " Token is missing/placeholder."
        if telegram_chat_id_is_placeholder: warning_msg += " Chat ID is missing/placeholder."
        warning_msg += " Notifications may not work."
        console_lines.append(warning_msg)
        console_lines.append("         Refer to docs/telegram_setup.md.")
    else:
        console_lines.append("INFO: Telegram Bot Token and Chat ID are SET.")

    # KakaoTalk
    if KAKAOTALK_CHAT_NAME_TO_MONITOR == "My Notes Chat": # Default example value
        console_lines.append("INFO: KAKAOTALK_CHAT_NAME_TO_MONITOR is set to the default 'My Notes Chat'.")
        console_lines.append("      Update this in config.py or via environment variable if monitoring a different chat.")
    else:
        console_lines.append(f"INFO: KAKAOTALK_CHAT_NAME_TO_MONITOR is set to: '{KAKAOTALK_CHAT_NAME_TO_MONITOR}'.")

    if KAKAOTALK_USER_DATA_DIR is None or KAKAOTALK_USER_DATA_DIR == "": # Check for None or empty string explicitly
        console_lines.append("INFO: KAKAOTALK_USER_DATA_DIR is not set. Playwright will use a temporary browser context for KakaoAgent.")
    else:
         console_lines.append(f"INFO: KAKAOTALK_USER_DATA_DIR is set to '{KAKAOTALK_USER_DATA_DIR}'. Ensure this path is valid/writable.")

    console_lines.append("----------------------------")

    # This function now just returns the lines. The caller (e.g., main.py) can decide to print them.
    # This makes config.py more declarative and import-friendly without side effects like printing.
    return "\n".join(console_lines)

# To get feedback when the application starts, the main application entry point (e.g., main.py)
# can import and call print_config_feedback().
# Example (in main.py):
# import config
# print(config.print_config_feedback())

# The existing print statements are removed to make this module purely declarative on import.
# The print_config_feedback function should be called explicitly from an application entry point.
