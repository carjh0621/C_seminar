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

                # If essential OAuth client details are not stored with the token, load from credentials_file
                # This is common because client_secret is highly sensitive.
                client_id_for_refresh = client_id_from_db
                client_secret_for_refresh = client_secret_from_db
                token_uri_for_refresh = token_uri_from_db or 'https://oauth2.googleapis.com/token'

                if not client_id_for_refresh or not client_secret_for_refresh: # Or if preferring file for these
                    if os.path.exists(self.credentials_file):
                        try:
                            with open(self.credentials_file, 'r') as f:
                                client_config_json = json.load(f)
                            # Determine if 'installed' or 'web' structure in credentials.json
                            if 'installed' in client_config_json:
                                config_key = 'installed'
                            elif 'web' in client_config_json:
                                config_key = 'web'
                            else:
                                config_key = None

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
                    expiry=db_token_record.expires_dt # Assumes this is a UTC datetime object from DB
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
                    # Ensure creds has client_id, client_secret for refresh if they are required by Google's lib
                    if not creds.client_id or not creds.client_secret:
                         print("Warning: Client ID or Secret missing from reconstructed creds. Refresh might fail.")
                    creds.refresh(GoogleAuthRequest())
                    print(f"Gmail token for '{app_user_id}' refreshed successfully.")
                except Exception as e:
                    print(f"Error refreshing Gmail token for '{app_user_id}': {e}. Proceeding to full re-auth.")
                    creds = None

            if not creds: # No token in DB, or it was invalid/expired and refresh failed/not possible
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

            if creds: # If refresh succeeded or new flow succeeded
                try:
                    token_info_for_db = {
                        'access_token': creds.token,
                        'refresh_token': creds.refresh_token,
                        'expires_dt': creds.expiry,
                        'scopes': creds.scopes,
                        'token_uri': creds.token_uri,
                        'client_id': creds.client_id,
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
            # This uses the default app_user_id="default_user" from authenticate_gmail
            if not self.authenticate_gmail():
                print("Authentication failed. Cannot fetch messages.")
                return []

        fetched_emails = []
        query = None
        if since_date_str:
            try:
                datetime.strptime(since_date_str, "%Y-%m-%d") # Validate format
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
    # For this test to run meaningfully, ensure your database is initialized
    # and the SourceToken table exists with the new schema.
    # You might need to run `python -m persistence.database` if you have a main block there
    # that calls create_db_tables().
    # from persistence.database import create_db_tables
    # print("Ensuring database tables are created...")
    # create_db_tables()

    # Ensure credentials.json exists for the test.
    # If it's the first time or token is invalid, this will trigger OAuth flow.
    if not os.path.exists('credentials.json'):
        print("FATAL: 'credentials.json' not found. Please set it up as per docs/gmail_setup.md")
        # Exiting because dummy won't work with DB persistence properly for a real test.
    else:
        agent = GmailAgent(credentials_file='credentials.json')

        test_app_user = "test_gmail_user_db_001" # Use a distinct user ID for DB testing
        print(f"Attempting authentication for user: {test_app_user}")
        gmail_service = agent.authenticate_gmail(app_user_id=test_app_user)

        if gmail_service:
            print(f"Authentication successful for {test_app_user}.")
            print("Fetching up to 2 recent emails...")
            emails = agent.fetch_messages(max_results=2) # Uses the authenticated service
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
