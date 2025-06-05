# Telegram Bot Setup for Notifications

To enable notifications from the Agenda Manager via Telegram, you need to create a Telegram Bot and obtain its API token, as well as your personal Chat ID (or the ID of a group where you want notifications).

## 1. Create a Telegram Bot with BotFather

1.  **Open Telegram** and search for "BotFather" (it's a verified bot with a blue checkmark).
2.  Start a chat with BotFather by sending the `/start` command.
3.  Create a new bot by sending the `/newbot` command.
4.  Follow the instructions:
    *   Choose a **name** for your bot (e.g., "My Agenda Notifier").
    *   Choose a **username** for your bot. It must end in "bot" (e.g., `MyAgendaNotifierBot` or `my_agenda_notifier_bot`).
5.  BotFather will then provide you with an **API Token**. This token is a long string of characters and numbers. **Copy this token immediately and save it securely.** This is your `TELEGRAM_BOT_TOKEN`.

## 2. Obtain Your Telegram Chat ID

Your Chat ID is a unique identifier for your personal chat with the bot (or a group chat). The bot needs this ID to know where to send messages.

*   **For Personal Notifications (to yourself)**:
    1.  After creating your bot, find it in Telegram search using its username (e.g., `@MyAgendaNotifierBot`).
    2.  Send any message to your bot (e.g., `/start` or "hello"). This "activates" the chat.
    3.  There are several ways to get your Chat ID:
        *   **Using another bot**: Search for a bot like "@userinfobot", "@JsonDumpBot", or "@getidsbot". Start a chat with one of these bots, send any message (or follow its instructions), and it will reply with your user information, including your Chat ID.
        *   **Using a simple Python script (if you have `python-telegram-bot` installed locally)**:
            You can run a small Python script to get updates for your bot. The first update after you message it will contain your Chat ID.
            ```python
            import telegram # pip install python-telegram-bot

            # Replace with your actual bot token
            BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

            try:
                bot = telegram.Bot(token=BOT_TOKEN)
                updates = bot.get_updates(timeout=10) # Add a timeout
                if updates:
                    chat_id = updates[0].message.chat_id
                    print(f"Your Chat ID is: {chat_id}")
                    # You can also see other user info:
                    # print(f"User info: {updates[0].message.from_user}")
                else:
                    print("No updates found. Ensure you have sent a message to your bot first.")
            except Exception as e:
                print(f"An error occurred: {e}")
                print("Ensure your BOT_TOKEN is correct and you have an internet connection.")
            ```
        *   **Via browser (less straightforward for user IDs)**: You can use the Telegram Bot API URL in your browser: `https://api.telegram.org/botYOUR_TOKEN/getUpdates` (replace `YOUR_TOKEN` with your bot's token). After sending a message to your bot, refresh this page. Look for `message.chat.id` in the JSON output.

*   **For Group Notifications**:
    1.  Add your bot to the desired Telegram group.
    2.  Send a message to the bot within the group (e.g., `/start@your_bot_username` or any message if the bot has privacy mode off).
    3.  Use one of the methods above (like "@userinfobot" added to the group, or checking the `getUpdates` JSON output from the browser method). The group's Chat ID is typically a negative number.

## 3. Configure the Application

Provide the `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to the Agenda Manager application:

*   **(Recommended) Environment Variables**:
    *   Set the following environment variables in your system or shell configuration file (e.g., `.bashrc`, `.zshrc`, `.env` file if your application loads it):
        ```bash
        export TELEGRAM_BOT_TOKEN="your_copied_bot_token"
        export TELEGRAM_CHAT_ID="your_chat_id"
        ```
    *   The application (`config.py`) is set up to read these environment variables.

*   **(Development Only) Directly in `config.py`**:
    *   Open the `config.py` file in the project.
    *   Find the lines:
        ```python
        TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
        TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID_HERE")
        ```
    *   Replace `"YOUR_TELEGRAM_BOT_TOKEN_HERE"` with your bot token, and `"YOUR_TELEGRAM_CHAT_ID_HERE"` with your Chat ID.
    *   **Warning**: Avoid committing your actual token and chat ID to version control if you use this method. The use of `os.getenv` with placeholders is safer for version control.

Once configured, the application will be able to send notifications to your specified Telegram chat.
