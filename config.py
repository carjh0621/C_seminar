import os

# Configuration settings

# --- Database Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agenda.db")

# --- OpenAI API Key Configuration ---
# For production, prefer environment variables for sensitive keys.
# Example: OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# If using environment variable, ensure it's set in your deployment environment.
# The placeholder "YOUR_API_KEY_HERE" should be replaced if hardcoding (not recommended for production).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_API_KEY_HERE")


# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID_HERE") # Can be a user ID or group ID


# --- Initialization Feedback ---
# This print statement is for local development feedback.
# It's good practice to use a more formal logging setup in production.
print("Configuration loaded:")
print(f"  DATABASE_URL: {DATABASE_URL}")
print(f"  OpenAI API Key: {'SET (from env or hardcoded)' if OPENAI_API_KEY and OPENAI_API_KEY != 'YOUR_API_KEY_HERE' else 'NOT SET (using placeholder or missing)'}")
print(f"  Telegram Bot Token: {'SET (from env or hardcoded)' if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != 'YOUR_TELEGRAM_BOT_TOKEN_HERE' else 'NOT SET (using placeholder or missing)'}")
print(f"  Telegram Chat ID: {'SET (from env or hardcoded)' if TELEGRAM_CHAT_ID and TELEGRAM_CHAT_ID != 'YOUR_TELEGRAM_CHAT_ID_HERE' else 'NOT SET (using placeholder or missing)'}")

# A check to ensure critical configurations are not using placeholder values if needed:
# if OPENAI_API_KEY == "YOUR_API_KEY_HERE":
#     print("Warning: OpenAI API Key is using a placeholder value.")
# if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
#     print("Warning: Telegram Bot Token is using a placeholder value.")
# if TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID_HERE":
#     print("Warning: Telegram Chat ID is using a placeholder value.")
