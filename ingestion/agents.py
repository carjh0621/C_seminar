import os.path
import json # For loading client_secrets from credentials_file
from google.auth.transport.requests import Request as GoogleAuthRequest # Renamed to avoid conflict
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta # Keep for fetch_messages and potentially token expiry logic

# --- Integration with persistence layer ---
from persistence.database import SessionLocal # To get a DB session
from persistence import crud as persistence_crud # To call get_token, save_token
# --- End integration ---

import base64 # For decoding message body in _parse_email_parts

class GmailAgent:
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    def __init__(self, config=None, credentials_file='credentials.json'): # token_file removed from __init__
        self.config = config
        self.credentials_file = credentials_file
        self.service = None
        # print("GmailAgent initialized")

    def authenticate_gmail(self, app_user_id="default_user"): # app_user_id for DB operations
        creds = None
        db = SessionLocal() # Get a DB session

        try:
            print(f"Attempting to load token for user '{app_user_id}', platform 'gmail' from DB.")
            db_token_record = persistence_crud.get_token(db, user_identifier=app_user_id, platform='gmail')

            if db_token_record and db_token_record.access_token:
                print(f"Token found in DB for '{app_user_id}', platform 'gmail'. Reconstructing credentials.")

                client_id_from_db = db_token_record.client_id
                client_secret_from_db = db_token_record.client_secret # Might be None or sensitive
                token_uri_from_db = db_token_record.token_uri

                client_id_for_refresh = client_id_from_db
                client_secret_for_refresh = client_secret_from_db
                token_uri_for_refresh = token_uri_from_db or 'https://oauth2.googleapis.com/token'

                if not client_id_for_refresh or not client_secret_for_refresh:
                    if os.path.exists(self.credentials_file):
                        try:
                            with open(self.credentials_file, 'r') as f:
                                client_config_json = json.load(f)
                            if 'installed' in client_config_json: config_key = 'installed'
                            elif 'web' in client_config_json: config_key = 'web'
                            else: config_key = None

                            if config_key:
                                client_id_for_refresh = client_config_json[config_key].get('client_id', client_id_for_refresh)
                                client_secret_for_refresh = client_config_json[config_key].get('client_secret', client_secret_for_refresh)
                                token_uri_for_refresh = client_config_json[config_key].get('token_uri', token_uri_for_refresh)
                        except Exception as e:
                            print(f"Error reading client_id/secret from {self.credentials_file}: {e}")
                    else:
                        print(f"Warning: {self.credentials_file} not found, cannot load client_id/secret for potential refresh if not in DB.")

                if not client_id_for_refresh or not client_secret_for_refresh:
                    print("Client ID or Client Secret could not be determined for refresh. Refresh may fail if token is expired.")

                creds = Credentials(
                    token=db_token_record.access_token,
                    refresh_token=db_token_record.refresh_token,
                    token_uri=token_uri_for_refresh,
                    client_id=client_id_for_refresh,
                    client_secret=client_secret_for_refresh,
                    scopes=db_token_record.scopes.split(' ') if db_token_record.scopes else self.SCOPES,
                    expiry=db_token_record.expires_dt
                )
                print(f"Credentials reconstructed from DB for user '{app_user_id}'. Valid: {creds.valid}, Expired: {creds.expired}")
            else:
                print(f"No token found in DB for '{app_user_id}', platform 'gmail'.")
        except Exception as e:
            print(f"Error loading token from DB or reconstructing credentials: {e}")
            creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print(f"Refreshing expired Gmail token for user '{app_user_id}'...")
                    if not creds.client_id or not creds.client_secret:
                         print("Warning: Client ID or Secret missing from reconstructed creds. Refresh might fail.")
                    creds.refresh(GoogleAuthRequest())
                    print(f"Gmail token for '{app_user_id}' refreshed successfully.")
                except Exception as e:
                    print(f"Error refreshing Gmail token for '{app_user_id}': {e}. Proceeding to full re-auth.")
                    creds = None

            if not creds:
                if not os.path.exists(self.credentials_file):
                    print(f"OAuth credentials file '{self.credentials_file}' not found. Cannot initiate new auth flow.")
                    db.close()
                    return None
                try:
                    print(f"Running new Gmail authentication flow for user '{app_user_id}'...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, self.SCOPES)
                    creds = flow.run_local_server(port=0)
                    print(f"Gmail authentication for '{app_user_id}' successful via new flow.")
                except FileNotFoundError:
                    print(f"Credentials file '{self.credentials_file}' not found during flow.")
                    db.close()
                    return None
                except Exception as e:
                    print(f"Error during Gmail authentication flow for '{app_user_id}': {e}")
                    db.close()
                    return None

            if creds:
                try:
                    token_info_for_db = {
                        'access_token': creds.token, 'refresh_token': creds.refresh_token,
                        'expires_dt': creds.expiry, 'scopes': creds.scopes,
                        'token_uri': creds.token_uri, 'client_id': creds.client_id,
                        'client_secret': creds.client_secret,
                    }
                    print(f"Attempting to save token for user '{app_user_id}', platform 'gmail' to DB.")
                    persistence_crud.save_token(db, user_identifier=app_user_id, platform='gmail', token_info=token_info_for_db)
                    print(f"Token for '{app_user_id}' (re)saved to DB.")
                except Exception as e:
                    print(f"CRITICAL: Error saving token to DB for '{app_user_id}': {e}. Token not persisted.")

        if not creds or not creds.valid:
            print(f"Failed to obtain valid Gmail credentials for user '{app_user_id}'.")
            db.close()
            return None

        try:
            self.service = build('gmail', 'v1', credentials=creds)
            print(f"Gmail API service built successfully for user '{app_user_id}'.")
            db.close()
            return self.service
        except HttpError as error:
            print(f'An error occurred building Gmail service for {app_user_id}: {error}')
            db.close()
            self.service = None
            return None
        except Exception as e:
            print(f'An unexpected error occurred building Gmail service for {app_user_id}: {e}')
            db.close()
            self.service = None
            return None

    def _parse_email_parts(self, payload):
        plain_text_body = ""
        html_body = ""
        if not payload: return "", ""
        parts_to_process = []
        if 'parts' in payload: parts_to_process.extend(payload['parts'])
        elif 'body' in payload and 'data' in payload['body']: parts_to_process.append(payload)
        for part in parts_to_process:
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data')
            if body_data:
                try:
                    decoded_data = base64.urlsafe_b64decode(body_data).decode('utf-8')
                    if mime_type == 'text/plain': plain_text_body += decoded_data + "\n"
                    elif mime_type == 'text/html': html_body += decoded_data + "\n"
                    elif not payload.get('parts') and mime_type not in ['text/plain', 'text/html']:
                        plain_text_body += decoded_data + "\n"
                except Exception as e: print(f"Error decoding part (MIME: {mime_type}): {e}")
            if 'parts' in part:
                nested_plain, nested_html = self._parse_email_parts(part)
                if nested_plain: plain_text_body += nested_plain + "\n"
                if nested_html: html_body += nested_html + "\n"
        return plain_text_body.strip(), html_body.strip()

    def fetch_messages(self, user_id='me', max_results=10, since_date_str=None):
        if not self.service:
            print("Gmail service not authenticated. Attempting to authenticate with default user...")
            if not self.authenticate_gmail():
                print("Authentication failed. Cannot fetch messages.")
                return []

        fetched_emails = []
        query = None
        if since_date_str:
            try:
                datetime.strptime(since_date_str, "%Y-%m-%d")
                query = f"after:{since_date_str.replace('-', '/')}"
            except ValueError:
                print(f"Invalid since_date_str format: {since_date_str}. Ignoring date filter.")

        try:
            print(f"Fetching list of messages with query: '{query if query else 'None'}' (max: {max_results})...")
            results = self.service.users().messages().list(
                userId=user_id, maxResults=max_results, q=query).execute()
            messages = results.get('messages', [])
            if not messages: print("No messages found matching criteria."); return []
            print(f"Found {len(messages)} message(s) in list. Fetching full details...")
            for msg_summary in messages:
                msg_id = msg_summary['id']
                try:
                    message_data = self.service.users().messages().get(
                        userId=user_id, id=msg_id, format='full').execute()
                    headers_dict = {
                        h['name'].lower(): h['value'] for h in message_data.get('payload', {}).get('headers', [])
                        if h['name'].lower() in ['subject', 'from', 'to', 'date', 'return-path', 'message-id']
                    }
                    plain_body, html_body = self._parse_email_parts(message_data.get('payload'))
                    email_details = {
                        'id': msg_id, 'thread_id': message_data.get('threadId'),
                        'internal_date_ts': message_data.get('internalDate'),
                        'snippet': message_data.get('snippet', ''), 'headers': headers_dict,
                        'body_plain': plain_body, 'body_html': html_body, 'source': 'gmail'
                    }
                    fetched_emails.append(email_details)
                    print(f"Successfully processed message ID: {msg_id}, Subject: '{headers_dict.get('subject', 'N/A')[:50]}...'")
                except HttpError as error: print(f'Error fetching details for message ID {msg_id}: {error}')
                except Exception as e: print(f'Unexpected error processing message ID {msg_id}: {e}')
            print(f"\nFinished fetching details for {len(fetched_emails)} messages.")
            return fetched_emails
        except HttpError as error: print(f'Error listing messages: {error}'); return []
        except Exception as e: print(f'Unexpected error during message listing phase: {e}'); return []

if __name__ == '__main__':
    print("Testing GmailAgent with DB Token Storage...")
    if not os.path.exists('credentials.json'):
        print("FATAL: 'credentials.json' not found. Please set it up as per docs/gmail_setup.md")
    else:
        agent = GmailAgent(credentials_file='credentials.json')
        test_app_user = "test_gmail_user_db_001"
        print(f"Attempting authentication for user: {test_app_user}")
        gmail_service = agent.authenticate_gmail(app_user_id=test_app_user)
        if gmail_service:
            print(f"Authentication successful for {test_app_user}.")
            print("Fetching up to 2 recent emails...")
            emails = agent.fetch_messages(max_results=2)
            if emails:
                print(f"Successfully fetched {len(emails)} emails for {test_app_user}:")
                for i, email_info in enumerate(emails):
                    print(f"  Email {i+1}: Subject: {email_info['headers'].get('subject', 'N/A')}")
            else:
                print(f"No emails fetched for {test_app_user}.")
        else:
            print(f"Authentication failed for {test_app_user}.")
            print("Ensure 'credentials.json' is valid and you've completed the OAuth flow if prompted.")
            print("Also check database connectivity and the SourceToken table schema.")

# --- New Imports for KakaoAgent (Playwright) ---
from playwright.sync_api import Playwright, BrowserContext, Page, Browser, Error as PlaywrightError
from typing import List, Dict, Optional # Added for KakaoAgent type hints
# --- End New Imports ---

class KakaoAgent:
    """
    Agent for interacting with KakaoTalk using Playwright.
    Note: Automating KakaoTalk can be challenging due to its structure
    and potential for changes. This implementation will be experimental.
    """
    def __init__(self, playwright_instance: Playwright, user_data_dir: Optional[str] = None, headless: bool = False):
        """
        Initializes the KakaoAgent.

        Args:
            playwright_instance: An active Playwright object (from `with sync_playwright() as p:`).
            user_data_dir: Optional path to a directory for persistent browser user data (for logins).
            headless: Whether to run the browser in headless mode. Default is False for KakaoTalk.
        """
        self.pw_instance: Playwright = playwright_instance
        self.user_data_dir: Optional[str] = user_data_dir
        self.headless: bool = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        print(f"KakaoAgent initialized. User data dir: {self.user_data_dir}, Headless: {self.headless}")


    def login(self, timeout_ms: int = 60000) -> bool:
        """
        Launches a browser for KakaoTalk interaction.
        This initial version relies on the user manually logging into their KakaoTalk PC client.
        Playwright launches a browser that can be used for other web tasks, or potentially
        to interact with a web-based Kakao interface if one is used/targeted in the future.
        The primary goal here is to have a browser context ready.

        Args:
            timeout_ms: Maximum time to wait for page navigation (in milliseconds).

        Returns:
            True if browser setup is successful, False otherwise.
        """
        print(f"KakaoAgent: Initializing browser for KakaoTalk interaction.")
        # Important Note on KakaoTalk PC Automation is in the class docstring / previous comments.

        if self.context and self.page: # Check if already initialized
            print("  Browser context and page already exist. Assuming active session.")
            # Optionally, could try a quick self.page.url() or a lightweight check here.
            return True

        try:
            launch_args_default = ['--disable-blink-features=AutomationControlled']
            # Headless argument for chromium.launch is a boolean, not in args list directly for that.
            # For launch_persistent_context, headless is a direct param, and args can supplement.

            if self.user_data_dir:
                print(f"  Launching persistent browser context using user_data_dir: {self.user_data_dir}")
                self.context = self.pw_instance.chromium.launch_persistent_context(
                    self.user_data_dir,
                    headless=self.headless,
                    args=launch_args_default,
                    # viewport=None, # Let it use default or be set later if needed
                    # no_viewport=True if self.headless else None # Use with caution, can affect layout
                )
                # For persistent context, self.browser is technically self.context.browser but we don't manage its lifecycle.
                self.browser = None # Explicitly set to None as we don't "own" this browser lifecycle

                if not self.context.pages():
                    self.page = self.context.new_page()
                else:
                    self.page = self.context.pages[0]
                print("  Persistent browser context launched.")
            else:
                print("  Launching new browser instance (non-persistent).")
                self.browser = self.pw_instance.chromium.launch(headless=self.headless, args=launch_args_default)
                self.context = self.browser.new_context(
                    # viewport=None
                )
                self.page = self.context.new_page()
                print("  New browser instance launched.")

            if not self.page: # Should not happen if logic above is correct
                print("  [Error] Page object was not created.")
                self.close()
                return False

            print("  Navigating to a test page (google.com) to verify browser control...")
            self.page.goto("https://google.com", timeout=timeout_ms // 2)
            page_title = self.page.title() # Get title after navigation
            print(f"  Successfully navigated to: {page_title}")

            print("  Browser is ready. IMPORTANT: Please ensure KakaoTalk PC client is running and logged in manually.")
            print("  KakaoAgent.login() successful (browser launched and test page loaded).")
            return True

        except PlaywrightError as e:
            print(f"  Playwright error during KakaoAgent login/setup: {e}")
            self.close()
            return False
        except Exception as e:
            print(f"  Unexpected error during KakaoAgent login/setup: {e}")
            self.close()
            return False

    def select_chat(self, chat_name: str, timeout_ms: int = 30000) -> bool:
        method_name = "KakaoAgent.select_chat"
        print(f"{method_name}: Attempting to select chat: '{chat_name}' (timeout: {timeout_ms}ms)...")

        if not self.page:
            print(f"Error ({method_name}): Page object not available. Login must be successful first.")
            return False

        # --- CONCEPTUAL SELECTOR ---
        # This needs to be replaced with actual selectors from KakaoTalk DOM inspection.
        # Using Playwright's role and text based locator as a robust example.
        print(f"  ({method_name}): Using conceptual locator strategy (get_by_role 'listitem', name='{chat_name}').")

        try:
            # Attempt to find a list item (common for chat lists) that has the specified name (aria-label or text content).
            # .first is used if multiple items might match the role but the name makes it specific.
            chat_item_locator = self.page.get_by_role("listitem", name=chat_name).first

            print(f"  ({method_name}): Attempting to click chat item '{chat_name}'...")
            # Default timeout for click is often sufficient if element is readily available.
            # Can specify timeout: chat_item_locator.click(timeout=timeout_ms)
            chat_item_locator.click(timeout=timeout_ms)

            # TODO: Add a verification step after clicking to confirm the chat opened.
            # This is crucial for robust automation.
            # Example (conceptual):
            # active_chat_header_locator = self.page.locator(f"header[data-testid='active-chat-title']:has-text('{chat_name}')")
            # active_chat_header_locator.wait_for(state='visible', timeout=5000) # Wait for header to be visible

            print(f"Success ({method_name}): Clicked on chat item '{chat_name}'. (Post-click verification needed).")
            return True

        except PlaywrightError as e:
            # This can catch various Playwright-specific errors, including timeout errors if element not found.
            print(f"Error ({method_name}): Playwright error selecting chat '{chat_name}' (e.g., element not found or timeout): {e}")
            return False
        except Exception as e:
            # Catch any other unexpected errors during the process.
            print(f"Error ({method_name}): Unexpected error while selecting chat '{chat_name}': {e}")
            return False

    def read_messages(self, num_messages_to_capture: int = 20, scroll_attempts: int = 3) -> List[Dict]:
    def read_messages(self, num_messages_to_capture: int = 20, scroll_attempts: int = 0) -> List[Dict]:
        """
        Reads messages from the currently selected chat using Playwright.
        Uses CONCEPTUAL selectors that need to be replaced with actual ones.
        Initial version focuses on visible messages; scrolling is a TODO.

        Args:
            num_messages_to_capture: Target number of recent messages to try to capture.
                                     (Currently will fetch visible, up to this number)
            scroll_attempts: Number of times to scroll up (Not implemented in this version).

        Returns:
            A list of dictionaries, each representing a message.
            Example: {'id': 'k_...', 'sender': 'SenderName',
                      'timestamp_str': '오후 3:45', 'text': 'Message content'}
        """
        method_name = "KakaoAgent.read_messages"
        print(f"{method_name}: Reading up to {num_messages_to_capture} messages...")

        if not self.page:
            print(f"Error ({method_name}): Page object not available. A chat must be selected first.")
            return []

        if scroll_attempts > 0:
            print(f"  Info ({method_name}): Scrolling ({scroll_attempts} attempts) is not yet implemented. Reading visible messages only.")
            # TODO: Implement scrolling logic here in the future.
            # For example:
            # for _ in range(scroll_attempts):
            #     self.page.keyboard.press("PageUp") # Or mouse wheel scroll on message container
            #     self.page.wait_for_timeout(500) # Wait for content to load

        messages: List[Dict] = []

        # --- CONCEPTUAL SELECTORS for message components ---
        # These need to be replaced with actual selectors from KakaoTalk DOM inspection.
        # Example: message_elements_locator = self.page.locator("div.chat_message_bubble")
        message_elements_locator = self.page.locator("div[role='listitem'][aria-label*='message']") # Conceptual: finds message list items

        print(f"  ({method_name}): Attempting to locate message elements using conceptual selector...")

        try:
            # Fetch all currently visible/DOM-rendered message elements matching the locator
            visible_message_elements = message_elements_locator.all() # Gets all current matches as Locator list
            print(f"  ({method_name}): Found {len(visible_message_elements)} potential message elements in DOM.")

            # Process messages, typically from bottom up (most recent) if that's how they appear in DOM
            # Slicing to get the last num_messages_to_capture elements
            elements_to_process = visible_message_elements[-num_messages_to_capture:]

            for i, msg_element_locator in enumerate(elements_to_process):
                # msg_element_locator is now a Playwright Locator for a single message element
                print(f"  ({method_name}): Processing message element {i+1}...")
                try:
                    # Conceptual sub-selectors relative to the msg_element_locator
                    # These data-testid attributes are purely examples.
                    sender_locator = msg_element_locator.locator("span[data-testid='sender']")
                    text_locator = msg_element_locator.locator("div[data-testid='message-text']")
                    timestamp_locator = msg_element_locator.locator("span[data-testid='timestamp']")

                    sender = sender_locator.text_content(timeout=500) if sender_locator.count() > 0 else "Unknown Sender"
                    text = text_locator.text_content(timeout=500) if text_locator.count() > 0 else ""
                    timestamp_str = timestamp_locator.text_content(timeout=500) if timestamp_locator.count() > 0 else "Unknown Time"

                    sender = sender.strip()
                    text = text.strip()
                    timestamp_str = timestamp_str.strip()

                    if not text and sender == "Unknown Sender": # Skip if no text and sender is also unknown
                        print(f"    ({method_name}): Skipping message with empty text and unknown sender.")
                        continue

                    # Generate a simple ID (can be improved with more message metadata if available)
                    msg_id_str = f"{sender}_{timestamp_str}_{text[:20]}" # Use first 20 chars of text for hash
                    msg_id = f"k_{hashlib.sha1(msg_id_str.encode('utf-8')).hexdigest()[:10]}"

                    messages.append({
                        'id': msg_id,
                        'sender': sender,
                        'timestamp_str': timestamp_str,
                        'text': text
                    })
                    print(f"    ({method_name}): Extracted: Sender='{sender}', Time='{timestamp_str}', Text='{text[:30].replace(chr(10), ' ')}...'")

                except PlaywrightError as e_msg:
                    print(f"  Warning ({method_name}): Playwright error extracting details for a message: {e_msg}")
                except Exception as e_u:
                    print(f"  Warning ({method_name}): Unexpected error extracting details for a message: {e_u}")

            print(f"  ({method_name}): Successfully extracted {len(messages)} messages.")

        except PlaywrightError as e:
            print(f"Error ({method_name}): Playwright error locating message list or messages: {e}")
            return []
        except Exception as e:
            print(f"Error ({method_name}): Unexpected error reading messages: {e}")
            return []

        return messages

    def close(self):
        """
        Closes the Playwright browser and context.
        """
        print("KakaoAgent: Closing browser resources...")
        closed_something = False
        if self.page:
            try:
                self.page.close()
                self.page = None
                closed_something = True
                print("  Page closed.")
            except Exception as e: print(f"  Error closing page: {e}")

        if self.context:
            try:
                self.context.close()
                self.context = None
                closed_something = True
                print("  Browser context closed.")
            except Exception as e: print(f"  Error closing context: {e}")

        # self.browser is primarily for non-persistent contexts.
        # Persistent contexts manage their browser lifecycle implicitly when context is closed.
        if self.browser:
            try:
                self.browser.close()
                self.browser = None
                closed_something = True
                print("  Browser closed.")
            except Exception as e: print(f"  Error closing browser: {e}")

        if closed_something:
            print("KakaoAgent: Browser resources released.")
        else:
            print("KakaoAgent: No active Playwright resources were explicitly closed by this agent instance (might be normal for persistent context if browser was pre-existing or if already closed).")

# Example of __all__ if this file is treated as a package's __init__.py or for explicit exports
# __all__ = ["GmailAgent", "KakaoAgent"]
