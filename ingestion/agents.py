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

# --- Imports for KakaoAgent ---
from playwright.sync_api import Playwright, BrowserContext, Page, Browser, Error as PlaywrightError, Locator
from typing import List, Dict, Optional
import hashlib
import time # For small delays if needed
import sys # For logger fallback
import logging # For KakaoAgent logger
# --- End Imports for KakaoAgent ---

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
                client_secret_from_db = db_token_record.client_secret
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
                # Validate format if needed, though strftime should produce correct YYYY/MM/DD
                # datetime.strptime(since_date_str, "%Y/%m/%d")
                query = f"after:{since_date_str}" # Gmail uses YYYY/MM/DD for 'after'
            except ValueError:
                print(f"Invalid since_date_str format: {since_date_str}. Must be YYYY/MM/DD. Ignoring date filter.")

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
                    # print(f"Successfully processed message ID: {msg_id}, Subject: '{headers_dict.get('subject', 'N/A')[:50]}...'")
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
            # print("Fetching up to 2 recent emails...")
            # emails = agent.fetch_messages(max_results=2)
            # if emails:
            #     print(f"Successfully fetched {len(emails)} emails for {test_app_user}:")
            #     for i, email_info in enumerate(emails):
            #         print(f"  Email {i+1}: Subject: {email_info['headers'].get('subject', 'N/A')}")
            # else:
            #     print(f"No emails fetched for {test_app_user}.")
        else:
            print(f"Authentication failed for {test_app_user}.")
            print("Ensure 'credentials.json' is valid and you've completed the OAuth flow if prompted.")
            print("Also check database connectivity and the SourceToken table schema.")

class KakaoAgent:
    # --- BEGIN CONCEPTUAL SELECTORS (Developer must replace these) ---
    CONCEPTUAL_SELECTORS = {
        "chat_list_container": "div[data-testid='chat-list-scroll-area']",
        "chat_list_item_role": "listitem",
        "message_area_container": "div[data-testid='message-scroll-area']",
        "message_bubble_role": "div[role='listitem'][aria-label*='message']",
        "message_sender_selector": "div[data-testid='sender-name']",
        "message_text_selector": "div[data-testid='message-text-content']",
        "message_timestamp_selector": "span[data-testid='message-timestamp']",
    }
    # --- END CONCEPTUAL SELECTORS ---

    def __init__(self, playwright_instance: Playwright, user_data_dir: Optional[str] = None, headless: bool = False):
        self.pw_instance = playwright_instance
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.logger = self._get_logger()
        self.logger.info(f"KakaoAgent initialized. User data dir: {self.user_data_dir}, Headless: {self.headless}")

    def _get_logger(self):
        logger = logging.getLogger(f"agenda_manager.{self.__class__.__name__}")
        if not logger.handlers and not logging.getLogger().handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
        return logger

    def login(self, timeout_ms: int = 60000) -> bool:
        self.logger.info(f"Attempting login (timeout: {timeout_ms}ms)...")
        self.logger.warning("IMPORTANT: KakaoAgent login requires KakaoTalk PC to be running and logged in manually.")
        try:
            if self.context and self.page:
                self.logger.info("Browser context already exists. Assuming active session.")
                return True

            launch_args_default = ['--disable-blink-features=AutomationControlled']
            if self.user_data_dir:
                self.logger.info(f"Launching persistent browser context: {self.user_data_dir}")
                self.context = self.pw_instance.chromium.launch_persistent_context(
                    self.user_data_dir, headless=self.headless, args=launch_args_default
                )
                self.browser = None
                self.page = self.context.pages()[0] if self.context.pages() else self.context.new_page()
            else:
                self.logger.info("Launching new browser instance (non-persistent).")
                self.browser = self.pw_instance.chromium.launch(headless=self.headless, args=launch_args_default)
                self.context = self.browser.new_context()
                self.page = self.context.new_page()

            if not self.page:
                self.logger.error("Page object not created after browser/context launch.")
                self.close()
                return False

            self.logger.info("Navigating to test page (google.com) to verify browser control...")
            self.page.goto("https://google.com", timeout=timeout_ms // 2)
            self.logger.info(f"Successfully navigated to: {self.page.title()}")
            self.logger.info("Browser ready. Ensure KakaoTalk PC is running and logged in.")
            return True
        except PlaywrightError as e:
            self.logger.error(f"Playwright error during login/setup: {e}", exc_info=True)
            self.close()
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during login/setup: {e}", exc_info=True)
            self.close()
            return False

    def select_chat(self, chat_name: str, timeout_ms: int = 30000) -> bool:
        self.logger.info(f"Attempting to select chat: '{chat_name}' (timeout: {timeout_ms}ms)...")
        if not self.page:
            self.logger.error("Page object not available. Login must be successful first.")
            return False

        try:
            chat_item_locator = self.page.get_by_role(
                self.CONCEPTUAL_SELECTORS["chat_list_item_role"], name=chat_name
            ).first

            self.logger.info(f"Attempting to click chat item '{chat_name}' using conceptual selector: "
                             f"role='{self.CONCEPTUAL_SELECTORS['chat_list_item_role']}', name='{chat_name}'.")
            chat_item_locator.click(timeout=timeout_ms)

            self.logger.info(f"Successfully clicked on chat item '{chat_name}'. (Post-click verification needed).")
            return True
        except PlaywrightError as e:
            self.logger.error(f"Playwright error selecting chat '{chat_name}' (e.g., timeout or element not found): {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error selecting chat '{chat_name}': {e}", exc_info=True)
            return False

    def read_messages(self, num_messages_to_capture: int = 20, scroll_attempts: int = 0) -> List[Dict]:
        self.logger.info(f"Reading up to {num_messages_to_capture} messages (scroll attempts: {scroll_attempts})...")
        if not self.page:
            self.logger.error("Page not available. A chat must be selected first.")
            return []

        if scroll_attempts > 0:
            self.logger.info(f"Scrolling ({scroll_attempts} attempts) is not yet implemented. Reading visible messages only.")

        messages: List[Dict] = []
        try:
            message_elements_locator = self.page.locator(
                self.CONCEPTUAL_SELECTORS["message_bubble_role"]
            )
            all_message_locators = message_elements_locator.all()
            self.logger.info(f"Found {len(all_message_locators)} potential message elements in DOM using conceptual selector.")
            elements_to_process = all_message_locators[-num_messages_to_capture:]

            for i, msg_locator in enumerate(elements_to_process):
                try:
                    sender_loc = msg_locator.locator(self.CONCEPTUAL_SELECTORS["message_sender_selector"])
                    text_loc = msg_locator.locator(self.CONCEPTUAL_SELECTORS["message_text_selector"])
                    timestamp_loc = msg_locator.locator(self.CONCEPTUAL_SELECTORS["message_timestamp_selector"])

                    sender = sender_loc.text_content(timeout=500).strip() if sender_loc.count() > 0 else "Unknown Sender"
                    text = text_loc.text_content(timeout=500).strip() if text_loc.count() > 0 else ""
                    timestamp_str = timestamp_loc.text_content(timeout=500).strip() if timestamp_loc.count() > 0 else "Unknown Time"

                    if not text and sender == "Unknown Sender":
                        self.logger.debug(f"Skipping message element {i+1} due to empty text and unknown sender.")
                        continue

                    msg_id_str = f"{sender}_{timestamp_str}_{text[:30]}"
                    msg_id = f"k_{hashlib.sha1(msg_id_str.encode('utf-8')).hexdigest()[:12]}"

                    messages.append({'id': msg_id, 'sender': sender, 'timestamp_str': timestamp_str, 'text': text})
                    self.logger.debug(f"Extracted: Sender='{sender}', Time='{timestamp_str}', Text='{text[:30].replace(chr(10), ' ')}...'")
                except PlaywrightError as e_msg:
                    self.logger.warning(f"Playwright error extracting details for a message element: {e_msg}")
                except Exception as e_u:
                    self.logger.warning(f"Unexpected error extracting details for a message element: {e_u}", exc_info=True)

            self.logger.info(f"Successfully extracted {len(messages)} messages.")
        except PlaywrightError as e:
            self.logger.error(f"Playwright error locating message list or messages: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error reading messages: {e}", exc_info=True)
        return messages

    def close(self):
        self.logger.info("Closing browser resources...")
        closed_something = False
        if self.page:
            try: self.page.close(); closed_something = True; self.logger.debug("Page closed.")
            except Exception as e: self.logger.error(f"Error closing page: {e}", exc_info=True)
        self.page = None

        if self.context:
            try: self.context.close(); closed_something = True; self.logger.debug("Browser context closed.")
            except Exception as e: self.logger.error(f"Error closing context: {e}", exc_info=True)
        self.context = None

        if self.browser:
            try: self.browser.close(); closed_something = True; self.logger.debug("Browser closed.")
            except Exception as e: self.logger.error(f"Error closing browser: {e}", exc_info=True)
        self.browser = None

        if closed_something: self.logger.info("Browser resources released.")
        else: self.logger.info("No active browser resources were explicitly closed by this agent instance or already closed.")

# __all__ = ["GmailAgent", "KakaoAgent"]
