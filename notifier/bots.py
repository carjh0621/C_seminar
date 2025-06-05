# notifier/bots.py
import telegram # From python-telegram-bot, e.g., version 20.x or higher
from telegram.error import TelegramError
from telegram import constants # For ParseMode
import asyncio

# --- Import configuration ---
# This assumes config.py is in the project root and project root is in PYTHONPATH
# or the application is run from the project root.
try:
    import config
except ModuleNotFoundError:
    print("ERROR in notifier/bots.py: Could not import 'config'.")
    print("Ensure 'config.py' exists in the project root and PYTHONPATH is set correctly.")
    # Define dummy config attributes if import fails, so the rest of the file can be parsed
    # by the subtask runner, though TelegramNotifier will likely fail at runtime.
    class config: # type: ignore
        TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
        TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID_HERE"
# --- End import for configuration ---

class TelegramNotifier:
    def __init__(self, bot_token: str = None, chat_id: str = None):
        """
        Initializes the TelegramNotifier.

        Args:
            bot_token: The Telegram Bot Token. If None, loads from config.
            chat_id: The Telegram Chat ID to send messages to. If None, loads from config.
        """
        self.bot_token = bot_token or getattr(config, 'TELEGRAM_BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
        self.chat_id = chat_id or getattr(config, 'TELEGRAM_CHAT_ID', 'YOUR_TELEGRAM_CHAT_ID_HERE')

        if self.bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or not self.bot_token:
            raise ValueError("Telegram Bot Token not configured. Please set TELEGRAM_BOT_TOKEN in config.py or as an environment variable.")
        if self.chat_id == "YOUR_TELEGRAM_CHAT_ID_HERE" or not self.chat_id:
            raise ValueError("Telegram Chat ID not configured. Please set TELEGRAM_CHAT_ID in config.py or as an environment variable.")

        try:
            self.bot = telegram.Bot(token=self.bot_token)
            # To get bot's username, an async call is needed: asyncio.run(self.bot.get_me()).username
            # For simplicity in __init__, we'll just confirm bot object creation.
            print(f"TelegramNotifier initialized for chat_id: {self.chat_id}. Bot object created.")

            # Basic check for chat_id format (numeric or @channelname)
            if not self.chat_id.startswith('@'):
                try:
                    int(self.chat_id)
                except ValueError:
                    print(f"Warning: Telegram Chat ID '{self.chat_id}' is not numeric and does not start with '@'. It might be invalid if it's not a public channel name that the bot can resolve.")
        except Exception as e:
            # This might happen if token is syntactically wrong or other unexpected issues.
            raise ValueError(f"Failed to initialize Telegram Bot with the provided token: {e}")


    async def _send_message_async(self, message_text: str) -> bool:
        """Asynchronous helper to send message."""
        try:
            # Using MARKDOWN_V2 for more formatting options. Ensure your messages are V2 compatible.
            # Telegram's MarkdownV2 requires escaping for certain characters: _ * [ ] ( ) ~ ` > # + - = | { } . !
            # For simplicity, if complex messages are sent, ensure they are pre-escaped or use HTML parse mode.
            await self.bot.send_message(chat_id=self.chat_id, text=message_text, parse_mode=constants.ParseMode.MARKDOWN_V2)
            print(f"Message sent successfully to chat_id {self.chat_id}: '{message_text[:50].replace(chr(10), ' ')}...'")
            return True
        except TelegramError as e:
            print(f"Telegram API error sending message to chat_id {self.chat_id}: {e.message}")
            # Example: e.message might be "Chat not found" or "Bot was blocked by the user"
            return False
        except Exception as e:
            print(f"Unexpected error sending Telegram message: {e}")
            return False

    def send_message(self, message_text: str) -> bool:
        """
        Sends a message to the configured Telegram chat_id.
        This is a synchronous wrapper for the async send method.

        Args:
            message_text: The text of the message to send. Supports MarkdownV2.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        try:
            # Check if an event loop is already running.
            # asyncio.get_event_loop() can error if no loop and not main thread.
            # asyncio.get_running_loop() errors if no loop is running.
            # asyncio.get_event_loop_policy().get_event_loop() is safer to get/create a loop.
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_running():
                 print("Warning: Attempting to run async Telegram send from a running event loop.")
                 # If inside a running loop, create a task. This won't block.
                 # For a truly synchronous call from an async context, one would need more complex solutions
                 # like running the new loop in a separate thread, or using something like nest_asyncio.
                 # This simple check just logs a warning; asyncio.run() will still likely fail.
                 # For a simple script/scheduled job, asyncio.run() is usually fine.
            return asyncio.run(self._send_message_async(message_text))
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                print(f"RuntimeError with asyncio.run: {e}. This often happens if called from an existing asyncio event loop (e.g., in a Jupyter notebook or some web frameworks).")
                print("Consider using `await notifier._send_message_async(...)` if calling from async code.")
                print("For synchronous calls from a context with a running loop, `nest_asyncio` might be needed, or run the notifier in a separate thread/process.")
                return False
            else:
                # Re-raise other RuntimeErrors not related to nested loops
                print(f"Unhandled RuntimeError in send_message: {e}")
                return False
        except Exception as e:
            print(f"General error in send_message wrapper: {e}")
            return False


if __name__ == '__main__':
    print("Testing TelegramNotifier...")
    # This test requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to be set
    # in config.py or as environment variables.

    notifier_instance = None
    try:
        # Initialize notifier. This will use values from config.py or environment variables.
        notifier_instance = TelegramNotifier()

        # Test sending a simple message
        # MarkdownV2 requires escaping of special characters like '.', '!', '-'
        # For example: 'Hello from Agenda Manager\! This is a *test notification*\.'
        test_message_1 = "Hello from Agenda Manager\\! This is a *test notification* from `notifier/bots.py`\\."
        print(f"Attempting to send test message 1: '{test_message_1}'")
        success1 = notifier_instance.send_message(test_message_1)

        if success1:
            print("Test message 1 sent successfully (check your Telegram chat).")
        else:
            print("Failed to send test message 1. Check token, chat_id, network, and bot permissions.")

        # Test sending a message with more MarkdownV2 characters
        test_message_2 = "Another test: _All systems nominal_\\.\nSee [Google](https://google.com) for info\\."
        # Note: URLs in MarkdownV2 don't need escaping of . within the URL itself.
        print(f"\nAttempting to send test message 2: '{test_message_2}'")
        success2 = notifier_instance.send_message(test_message_2)
        if success2:
            print("Test message 2 sent successfully.")
        else:
            print("Failed to send test message 2.")

    except ValueError as ve: # Catches initialization errors (e.g., missing config)
        print(f"ERROR: Could not initialize TelegramNotifier: {ve}")
        print("Please ensure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are correctly set up.")
        print("Refer to `docs/telegram_setup.md` for instructions.")
    except Exception as e: # Catches other unexpected errors during the test
        print(f"An unexpected error occurred during Notifier test: {e}")

    if notifier_instance is None: # If initialization failed
        print("\nReminder: To run this test effectively and send actual messages,")
        print("ensure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correctly set up.")
        print("Refer to `docs/telegram_setup.md`.")
