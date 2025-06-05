import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

# Attempt to import necessary modules from the project
# This structure assumes tests are run from the project root.
try:
    from notifier.bots import TelegramNotifier
    from telegram.error import TelegramError
    from telegram import constants as telegram_constants
except ModuleNotFoundError as e:
    print(f"ERROR in tests/test_notifier.py: Could not import project modules: {e}")
    print("Ensure tests are run from the project root or PYTHONPATH includes the project root.")
    # Define dummy classes if import fails, so the test file itself is valid Python
    # and can be parsed by the test runner, even if tests might fail due to missing modules.
    class TelegramNotifier:
        def __init__(self, bot_token=None, chat_id=None):
            print(f"DUMMY TelegramNotifier initialized with token: {bot_token}, chat_id: {chat_id}")
            self.bot_token = bot_token
            self.chat_id = chat_id
            if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE": raise ValueError("Bot token missing")
            if not chat_id or chat_id == "YOUR_TELEGRAM_CHAT_ID_HERE": raise ValueError("Chat ID missing")
        async def _send_message_async(self, message_text: str) -> bool:
            print(f"DUMMY Notifier Async Send: {message_text}"); return True
        def send_message(self, message_text: str) -> bool:
            print(f"DUMMY Notifier Sync Send: {message_text}"); return True

    class TelegramError(Exception):
        def __init__(self, message): self.message = message # Simplified TelegramError

    class telegram_constants:
        class ParseMode: MARKDOWN_V2 = "MarkdownV2"


# Mock config values to simulate different states of config.py
MOCK_CONFIG_VALID = MagicMock()
MOCK_CONFIG_VALID.TELEGRAM_BOT_TOKEN = "test_token_123_valid"
MOCK_CONFIG_VALID.TELEGRAM_CHAT_ID = "123456789_valid"

MOCK_CONFIG_NO_TOKEN = MagicMock()
MOCK_CONFIG_NO_TOKEN.TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE" # Placeholder
MOCK_CONFIG_NO_TOKEN.TELEGRAM_CHAT_ID = "123456789_no_token_test"

MOCK_CONFIG_NO_CHAT_ID = MagicMock()
MOCK_CONFIG_NO_CHAT_ID.TELEGRAM_BOT_TOKEN = "test_token_123_no_chat_id_test"
MOCK_CONFIG_NO_CHAT_ID.TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID_HERE" # Placeholder

MOCK_CONFIG_EMPTY_STRINGS = MagicMock() # Test case for empty strings vs placeholders
MOCK_CONFIG_EMPTY_STRINGS.TELEGRAM_BOT_TOKEN = ""
MOCK_CONFIG_EMPTY_STRINGS.TELEGRAM_CHAT_ID = ""


class TestTelegramNotifier(unittest.TestCase):

    @patch('notifier.bots.config', MOCK_CONFIG_VALID)
    @patch('notifier.bots.telegram.Bot') # Mock the telegram.Bot class used in notifier.bots
    def test_init_success(self, MockTelegramBot):
        """Test successful initialization of TelegramNotifier."""
        mock_bot_instance = MagicMock()
        MockTelegramBot.return_value = mock_bot_instance

        notifier = TelegramNotifier() # Uses MOCK_CONFIG_VALID due to patch

        MockTelegramBot.assert_called_once_with(token="test_token_123_valid")
        self.assertEqual(notifier.bot_token, "test_token_123_valid")
        self.assertEqual(notifier.chat_id, "123456789_valid")
        self.assertEqual(notifier.bot, mock_bot_instance)

    @patch('notifier.bots.config', MOCK_CONFIG_NO_TOKEN)
    def test_init_fail_no_token(self):
        """Test initialization failure if bot token is the placeholder."""
        with self.assertRaisesRegex(ValueError, "Telegram Bot Token not configured"):
            TelegramNotifier()

    @patch('notifier.bots.config', MOCK_CONFIG_EMPTY_STRINGS) # Test with empty string token
    def test_init_fail_empty_token(self):
        """Test initialization failure if bot token is an empty string."""
        with self.assertRaisesRegex(ValueError, "Telegram Bot Token not configured"):
            TelegramNotifier()

    @patch('notifier.bots.config', MOCK_CONFIG_NO_CHAT_ID)
    def test_init_fail_no_chat_id(self):
        """Test initialization failure if chat ID is the placeholder."""
        with self.assertRaisesRegex(ValueError, "Telegram Chat ID not configured"):
            TelegramNotifier()

    @patch('notifier.bots.config', MOCK_CONFIG_VALID)
    @patch('notifier.bots.telegram.Bot')
    def test_send_message_success(self, MockTelegramBot):
        """Test successful message sending."""
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_message = AsyncMock() # Mock the async send_message method
        MockTelegramBot.return_value = mock_bot_instance

        notifier = TelegramNotifier()
        message_text = "Test message for success"

        result = notifier.send_message(message_text)

        self.assertTrue(result, "send_message should return True on success.")
        mock_bot_instance.send_message.assert_called_once_with(
            chat_id="123456789_valid",
            text=message_text,
            parse_mode=telegram_constants.ParseMode.MARKDOWN_V2
        )

    @patch('notifier.bots.config', MOCK_CONFIG_VALID)
    @patch('notifier.bots.telegram.Bot')
    def test_send_message_telegram_api_error(self, MockTelegramBot):
        """Test message sending failure due to a Telegram API error."""
        mock_bot_instance = MagicMock()
        # Simulate a TelegramError being raised by the API call
        mock_bot_instance.send_message = AsyncMock(side_effect=TelegramError("Simulated API error from Telegram"))
        MockTelegramBot.return_value = mock_bot_instance

        notifier = TelegramNotifier()
        result = notifier.send_message("Test message for Telegram API error")

        self.assertFalse(result, "send_message should return False on TelegramError.")
        mock_bot_instance.send_message.assert_called_once()

    @patch('notifier.bots.config', MOCK_CONFIG_VALID)
    @patch('notifier.bots.telegram.Bot')
    @patch('notifier.bots.asyncio.run') # Mock asyncio.run itself
    def test_send_message_asyncio_runtime_error(self, mock_asyncio_run, MockTelegramBot):
        """Test message sending failure due to asyncio.run raising a RuntimeError."""
        mock_bot_instance = MagicMock()
        MockTelegramBot.return_value = mock_bot_instance

        # Simulate asyncio.run raising a RuntimeError (e.g., nested event loops)
        mock_asyncio_run.side_effect = RuntimeError("Simulated asyncio.run error (e.g., nested loop)")

        notifier = TelegramNotifier()
        result = notifier.send_message("Test message for asyncio.run RuntimeError")

        self.assertFalse(result, "send_message should return False on asyncio.run RuntimeError.")
        mock_asyncio_run.assert_called_once() # Check that our wrapper attempted to call asyncio.run

    @patch('notifier.bots.config', MOCK_CONFIG_VALID)
    @patch('notifier.bots.telegram.Bot')
    def test_send_message_unexpected_error_in_async_helper(self, MockTelegramBot):
        """Test message sending failure due to an unexpected error within _send_message_async."""
        mock_bot_instance = MagicMock()
        # Simulate an error other than TelegramError within the _send_message_async's try block
        mock_bot_instance.send_message = AsyncMock(side_effect=Exception("Unexpected internal error in async helper"))
        MockTelegramBot.return_value = mock_bot_instance

        notifier = TelegramNotifier()
        result = notifier.send_message("Test message for unexpected internal error")

        self.assertFalse(result, "send_message should return False on unexpected internal error.")
        mock_bot_instance.send_message.assert_called_once()

if __name__ == '__main__':
    # This allows running this test file directly like `python tests/test_notifier.py`
    # For imports to work correctly, ensure project root is in PYTHONPATH or run as module:
    # `python -m unittest tests.test_notifier`
    unittest.main()
