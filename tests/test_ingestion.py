import unittest
from unittest.mock import patch, MagicMock, call, mock_open
import os
import json
from datetime import datetime, timedelta
import base64

from ingestion.agents import GmailAgent
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.errors import HttpError
from persistence.models import SourceToken

# --- New Imports for TestKakaoAgent ---
from ingestion.agents import KakaoAgent
from playwright.sync_api import Playwright, Browser, BrowserContext, Page, Error as PlaywrightError
from typing import List, Dict, Optional as TypingOptional # Renamed to avoid conflict
# --- End New Imports ---

TEST_CREDS_FILE = 'dummy_credentials_for_test.json'

def b64encode_str(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode('utf-8')).decode('ascii')

class TestGmailAgent(unittest.TestCase):

    def setUp(self):
        self.agent = GmailAgent(credentials_file=TEST_CREDS_FILE)
        dummy_creds_data = {
            "installed": {
                "client_id": "test_client_id", "project_id": "test_project",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_secret": "test_client_secret",
                "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]
            }
        }
        with open(TEST_CREDS_FILE, 'w') as f:
            json.dump(dummy_creds_data, f)

    def tearDown(self):
        if os.path.exists(TEST_CREDS_FILE):
            os.remove(TEST_CREDS_FILE)

    @patch('ingestion.agents.persistence_crud.save_token')
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('ingestion.agents.build')
    @patch('ingestion.agents.InstalledAppFlow.from_client_secrets_file')
    @patch('os.path.exists')
    @patch('ingestion.agents.SessionLocal')
    def test_authenticate_new_token(self, mock_session_local, mock_os_path_exists,
                                   mock_from_secrets, mock_build,
                                   mock_get_token_db, mock_save_token_db):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session
        mock_get_token_db.return_value = None
        mock_os_path_exists.return_value = True

        mock_flow = MagicMock()
        mock_creds = MagicMock(spec=Credentials)
        mock_creds.token = "new_mock_token_val"
        mock_creds.refresh_token = 'mock_refresh_token_val'
        mock_creds.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_creds.scopes = GmailAgent.SCOPES
        mock_creds.token_uri = 'https://oauth2.googleapis.com/token'
        mock_creds.client_id = 'test_client_id'
        mock_creds.client_secret = 'test_client_secret'
        mock_creds.valid = True
        mock_flow.run_local_server.return_value = mock_creds
        mock_from_secrets.return_value = mock_flow
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        service = self.agent.authenticate_gmail(app_user_id="user1_new_token")

        self.assertEqual(service, mock_service)
        mock_get_token_db.assert_called_once_with(mock_db_session, user_identifier="user1_new_token", platform='gmail')
        mock_from_secrets.assert_called_once_with(TEST_CREDS_FILE, GmailAgent.SCOPES)
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_save_token_db.assert_called_once()
        args, kwargs = mock_save_token_db.call_args
        self.assertEqual(args[0], mock_db_session)
        self.assertEqual(kwargs['user_identifier'], "user1_new_token")
        self.assertEqual(kwargs['platform'], "gmail")
        token_info = kwargs['token_info']
        self.assertEqual(token_info['access_token'], "new_mock_token_val")
        self.assertEqual(token_info['refresh_token'], "mock_refresh_token_val")
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
        mock_db_session.close.assert_called_once()

    @patch('ingestion.agents.build')
    @patch('ingestion.agents.Credentials')
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('os.path.exists', return_value=True)
    @patch('ingestion.agents.SessionLocal')
    def test_authenticate_existing_valid_token(self, mock_session_local, mock_os_path_exists,
                                               mock_get_token_db, mock_creds_class, mock_build):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session
        mock_db_src_token = MagicMock(spec=SourceToken)
        mock_db_src_token.access_token = "db_access_token_valid"
        mock_db_src_token.refresh_token = "db_refresh_token_valid"
        mock_db_src_token.expires_dt = datetime.utcnow() + timedelta(hours=1)
        mock_db_src_token.scopes = " ".join(GmailAgent.SCOPES)
        mock_db_src_token.token_uri = 'https://oauth2.googleapis.com/token'
        mock_db_src_token.client_id = None
        mock_db_src_token.client_secret = None
        mock_get_token_db.return_value = mock_db_src_token
        mock_reconstructed_creds = MagicMock(spec=Credentials)
        mock_reconstructed_creds.valid = True
        mock_reconstructed_creds.expired = False
        mock_reconstructed_creds.token = mock_db_src_token.access_token
        mock_creds_class.return_value = mock_reconstructed_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        m_open = mock_open(read_data=json.dumps({"installed":{"client_id":"test_client_id","client_secret":"test_client_secret","token_uri":"https://oauth2.googleapis.com/token"}}))
        with patch('builtins.open', m_open):
            service = self.agent.authenticate_gmail(app_user_id="user2_valid_token")
        self.assertEqual(service, mock_service)
        mock_get_token_db.assert_called_once_with(mock_db_session, user_identifier="user2_valid_token", platform='gmail')
        m_open.assert_called_once_with(TEST_CREDS_FILE, 'r')
        mock_creds_class.assert_called_once_with(
            token=mock_db_src_token.access_token,
            refresh_token=mock_db_src_token.refresh_token,
            token_uri=mock_db_src_token.token_uri,
            client_id="test_client_id",
            client_secret="test_client_secret",
            scopes=mock_db_src_token.scopes.split(' '),
            expiry=mock_db_src_token.expires_dt
        )
        mock_reconstructed_creds.refresh.assert_not_called()
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_reconstructed_creds)
        mock_db_session.close.assert_called_once()

    @patch('ingestion.agents.persistence_crud.save_token')
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('ingestion.agents.build')
    @patch('ingestion.agents.Credentials')
    @patch('os.path.exists', return_value=True)
    @patch('ingestion.agents.SessionLocal')
    def test_authenticate_expired_token_refresh_success(self, mock_session_local, mock_os_path_exists,
                                                      mock_creds_class, mock_build,
                                                      mock_get_token_db, mock_save_token_db):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session
        mock_db_src_token = MagicMock(spec=SourceToken)
        mock_db_src_token.access_token = "expired_access_token_val"
        mock_db_src_token.refresh_token = "valid_refresh_token_for_refresh"
        mock_db_src_token.expires_dt = datetime.utcnow() - timedelta(hours=1)
        mock_db_src_token.scopes = " ".join(GmailAgent.SCOPES)
        mock_db_src_token.client_id = None
        mock_db_src_token.client_secret = None
        mock_db_src_token.token_uri = 'https://oauth2.googleapis.com/token'
        mock_get_token_db.return_value = mock_db_src_token
        mock_reconstructed_creds = MagicMock(spec=Credentials)
        mock_reconstructed_creds.valid = False
        mock_reconstructed_creds.expired = True
        mock_reconstructed_creds.refresh_token = mock_db_src_token.refresh_token
        mock_reconstructed_creds.token = "refreshed_token_val_after_call"
        mock_reconstructed_creds.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_reconstructed_creds.client_id = "test_client_id"
        mock_reconstructed_creds.client_secret = "test_client_secret"
        def mock_refresh_logic(request):
            self.assertTrue(isinstance(request, GoogleAuthRequest))
            mock_reconstructed_creds.valid = True
            mock_reconstructed_creds.expired = False
            mock_reconstructed_creds.token = "refreshed_token_val_after_call"
            mock_reconstructed_creds.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_reconstructed_creds.refresh = MagicMock(side_effect=mock_refresh_logic)
        mock_creds_class.return_value = mock_reconstructed_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        m_open = mock_open(read_data=json.dumps({"installed":{"client_id":"test_client_id","client_secret":"test_client_secret","token_uri":"https://oauth2.googleapis.com/token"}}))
        with patch('builtins.open', m_open):
            service = self.agent.authenticate_gmail(app_user_id="user3_refresh_success")
        self.assertEqual(service, mock_service)
        mock_get_token_db.assert_called_once_with(mock_db_session, user_identifier="user3_refresh_success", platform='gmail')
        mock_reconstructed_creds.refresh.assert_called_once_with(unittest.mock.ANY)
        mock_save_token_db.assert_called_once()
        args_save, kwargs_save = mock_save_token_db.call_args
        self.assertEqual(kwargs_save['token_info']['access_token'], "refreshed_token_val_after_call")
        self.assertEqual(kwargs_save['token_info']['client_id'], "test_client_id")
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_reconstructed_creds)
        mock_db_session.close.assert_called_once()

    @patch('ingestion.agents.persistence_crud.save_token')
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('ingestion.agents.build')
    @patch('ingestion.agents.InstalledAppFlow.from_client_secrets_file')
    @patch('ingestion.agents.Credentials')
    @patch('os.path.exists')
    @patch('ingestion.agents.SessionLocal')
    def test_authenticate_refresh_fail_then_new_flow(self, mock_session_local, mock_os_path_exists,
                                                    mock_creds_class_reconstruct, mock_from_secrets,
                                                    mock_build, mock_get_token_db, mock_save_token_db):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session
        mock_os_path_exists.return_value = True
        mock_db_src_token = MagicMock(spec=SourceToken)
        mock_db_src_token.refresh_token = "old_refresh_token"
        mock_db_src_token.client_id = None
        mock_get_token_db.return_value = mock_db_src_token
        mock_reconstructed_creds_for_refresh = MagicMock(spec=Credentials)
        mock_reconstructed_creds_for_refresh.valid = False
        mock_reconstructed_creds_for_refresh.expired = True
        mock_reconstructed_creds_for_refresh.refresh_token = "old_refresh_token"
        mock_reconstructed_creds_for_refresh.refresh.side_effect = Exception("Simulated Refresh API Failed")
        mock_creds_class_reconstruct.return_value = mock_reconstructed_creds_for_refresh
        mock_flow_for_new = MagicMock()
        mock_new_creds_from_flow = MagicMock(spec=Credentials, valid=True, expired=False, refresh_token='newly_flowed_refresh_token')
        mock_new_creds_from_flow.token = "new_token_from_flow"
        mock_new_creds_from_flow.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_new_creds_from_flow.scopes = GmailAgent.SCOPES
        mock_new_creds_from_flow.client_id = "test_client_id"
        mock_new_creds_from_flow.client_secret = "test_client_secret"
        mock_new_creds_from_flow.token_uri = "https://oauth2.googleapis.com/token"
        mock_flow_for_new.run_local_server.return_value = mock_new_creds_from_flow
        mock_from_secrets.return_value = mock_flow_for_new
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        m_open = mock_open(read_data=json.dumps({"installed":{"client_id":"test_client_id","client_secret":"test_client_secret","token_uri":"https://oauth2.googleapis.com/token"}}))
        with patch('builtins.open', m_open):
            service = self.agent.authenticate_gmail(app_user_id="user4_refresh_fail")
        self.assertEqual(service, mock_service)
        mock_get_token_db.assert_called_once()
        mock_reconstructed_creds_for_refresh.refresh.assert_called_once()
        mock_from_secrets.assert_called_once_with(TEST_CREDS_FILE, GmailAgent.SCOPES)
        mock_save_token_db.assert_called_once()
        args_save, kwargs_save = mock_save_token_db.call_args
        self.assertEqual(kwargs_save['token_info']['access_token'], "new_token_from_flow")
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_new_creds_from_flow)
        mock_db_session.close.assert_called_once()

    @patch.object(GmailAgent, 'authenticate_gmail')
    def test_fetch_messages_success(self, mock_auth_gmail_method):
        mock_service_instance = MagicMock()
        self.agent.service = mock_service_instance
        mock_auth_gmail_method.return_value = mock_service_instance
        mock_service_instance.users().messages().list().execute.return_value = {'messages': [{'id': 'msg1'}, {'id': 'msg2'}]}
        mock_msg1_payload = {'id': 'msg1', 'snippet': 'Snippet 1', 'internalDate': '1600000000000', 'payload': {'headers': [{'name': 'Subject', 'value': 'Subj1'}], 'body': {'data': b64encode_str("Body1Text")}}}
        mock_msg2_payload = {'id': 'msg2', 'snippet': 'Snippet 2', 'internalDate': '1600000000001', 'payload': {'headers': [{'name': 'Subject', 'value': 'Subj2'}], 'parts': [{'mimeType': 'text/plain', 'body': {'data': b64encode_str("Body2Plain")}}]}}
        def get_side_effect(*args, **kwargs):
            msg_id = kwargs.get('id')
            if msg_id == 'msg1': return mock_msg1_payload
            if msg_id == 'msg2': return mock_msg2_payload
            return {}
        mock_service_instance.users().messages().get().execute.side_effect = get_side_effect
        emails = self.agent.fetch_messages(max_results=2)
        self.assertEqual(len(emails), 2)
        self.assertEqual(emails[0]['id'], 'msg1')
        self.assertEqual(emails[0]['body_plain'], 'Body1Text')
        mock_service_instance.users().messages().list.assert_called_once_with(userId='me', maxResults=2, q=None)
        get_calls = [call(userId='me', id='msg1', format='full'), call(userId='me', id='msg2', format='full')]
        mock_service_instance.users().messages().get.assert_has_calls(get_calls, any_order=True)

    @patch.object(GmailAgent, 'authenticate_gmail')
    def test_fetch_messages_no_service_auth_fails(self, mock_auth_gmail_method):
        self.agent.service = None
        mock_auth_gmail_method.return_value = None
        emails = self.agent.fetch_messages()
        self.assertEqual(emails, [])
        mock_auth_gmail_method.assert_called_once()

    @patch.object(GmailAgent, 'authenticate_gmail')
    def test_fetch_messages_api_error_on_list(self, mock_auth_gmail_method):
        mock_service_instance = MagicMock()
        self.agent.service = mock_service_instance
        mock_auth_gmail_method.return_value = mock_service_instance
        mock_resp = MagicMock(status=403)
        error_content = b'{"error": {"message": "Forbidden"}}'
        mock_service_instance.users().messages().list().execute.side_effect = HttpError(mock_resp, error_content)
        emails = self.agent.fetch_messages()
        self.assertEqual(emails, [])

if __name__ == '__main__':
    unittest.main()

# --- New Test Class for KakaoAgent ---
class TestKakaoAgent(unittest.TestCase):

    @patch('ingestion.agents.Playwright')
    def setUp(self, MockPlaywrightModule):
        self.mock_pw_instance_for_agent = MagicMock(spec=Playwright)

        self.mock_browser = MagicMock(spec=Browser)
        self.mock_context = MagicMock(spec=BrowserContext)
        self.mock_page = MagicMock(spec=Page)

        self.mock_pw_instance_for_agent.chromium = MagicMock()
        self.mock_pw_instance_for_agent.chromium.launch.return_value = self.mock_browser
        self.mock_pw_instance_for_agent.chromium.launch_persistent_context.return_value = self.mock_context

        self.mock_browser.new_context.return_value = self.mock_context
        self.mock_context.new_page.return_value = self.mock_page
        self.mock_context.pages.return_value = []

        self.agent = KakaoAgent(playwright_instance=self.mock_pw_instance_for_agent, headless=True)

    def test_kakao_agent_init(self):
        self.assertEqual(self.agent.pw_instance, self.mock_pw_instance_for_agent)
        self.assertTrue(self.agent.headless)
        self.assertIsNone(self.agent.browser)
        self.assertIsNone(self.agent.context)
        self.assertIsNone(self.agent.page)

    def test_login_launches_new_browser_and_navigates(self):
        self.agent.user_data_dir = None
        self.agent.headless = False

        self.mock_page.title.return_value = "Google Test Title"

        success = self.agent.login(timeout_ms=2000)

        self.assertTrue(success)
        self.mock_pw_instance_for_agent.chromium.launch.assert_called_once_with(headless=False, args=unittest.mock.ANY)
        self.mock_browser.new_context.assert_called_once()
        self.mock_context.new_page.assert_called_once()
        self.mock_page.goto.assert_called_once_with("https://google.com", timeout=1000)
        self.assertEqual(self.agent.browser, self.mock_browser)
        self.assertEqual(self.agent.context, self.mock_context)
        self.assertEqual(self.agent.page, self.mock_page)

    def test_login_launches_persistent_context_and_navigates(self):
        test_user_dir = "./test_kakao_user_data_dir_for_test"
        self.agent.user_data_dir = test_user_dir
        self.agent.headless = True

        self.mock_context.pages.return_value = []
        self.mock_page.title.return_value = "Google Persistent Test"

        success = self.agent.login(timeout_ms=2000)

        self.assertTrue(success)
        self.mock_pw_instance_for_agent.chromium.launch_persistent_context.assert_called_once_with(
            test_user_dir,
            headless=True,
            args=unittest.mock.ANY,
        )
        self.mock_context.new_page.assert_called_once()

        self.mock_page.goto.assert_called_once_with("https://google.com", timeout=1000)
        self.assertIsNone(self.agent.browser)
        self.assertEqual(self.agent.context, self.mock_context)
        self.assertEqual(self.agent.page, self.mock_page)

    def test_login_playwright_error_on_launch(self):
        self.mock_pw_instance_for_agent.chromium.launch.side_effect = PlaywrightError("Simulated Launch failed")
        self.agent.user_data_dir = None

        success = self.agent.login()
        self.assertFalse(success)
        self.assertIsNone(self.agent.page, "Page should be None after close attempt on error.")
        self.assertIsNone(self.agent.context, "Context should be None after close attempt on error.")
        self.assertIsNone(self.agent.browser, "Browser should be None after close attempt on error.")

    def test_select_chat_placeholder_success(self):
        self.agent.page = self.mock_page
        result = self.agent.select_chat("Any Chat Name")
        self.assertTrue(result)

    def test_select_chat_no_page_available(self):
        self.agent.page = None
        result = self.agent.select_chat("Any Chat Name")
        self.assertFalse(result)

    def test_read_messages_placeholder_success(self):
        self.agent.page = self.mock_page

        messages = self.agent.read_messages(num_messages_to_capture=5)
        self.assertIsInstance(messages, list)
        self.assertTrue(1 <= len(messages) <= 3)
        if messages:
            self.assertIn('id', messages[0])
            self.assertIn('text', messages[0])

    def test_read_messages_no_page_available(self):
        self.agent.page = None
        messages = self.agent.read_messages()
        self.assertEqual(messages, [])

    def test_close_non_persistent_context_resources(self):
        self.agent.browser = self.mock_browser
        self.agent.context = self.mock_context
        self.agent.page = self.mock_page
        self.agent.user_data_dir = None

        self.agent.close()

        self.mock_page.close.assert_called_once()
        self.mock_context.close.assert_called_once()
        self.mock_browser.close.assert_called_once()
        self.assertIsNone(self.agent.page)
        self.assertIsNone(self.agent.context)
        self.assertIsNone(self.agent.browser)

    def test_close_persistent_context_resources(self):
        self.agent.context = self.mock_context
        self.agent.page = self.mock_page
        self.agent.user_data_dir = "./persistent_data_dir_test"
        self.agent.browser = None

        self.agent.close()

        self.mock_page.close.assert_called_once()
        self.mock_context.close.assert_called_once()
        self.mock_browser.close.assert_not_called()
        self.assertIsNone(self.agent.page)
        self.assertIsNone(self.agent.context)
        self.assertIsNone(self.agent.browser)

    def test_select_chat_success(self):
        self.agent.page = self.mock_page # Ensure page is set for the test

        # Mock the locator chain for finding the chat item
        mock_chat_item_locator = MagicMock(spec=Locator)
        # Configure self.mock_page.get_by_role(...).first to return our specific locator mock
        self.mock_page.get_by_role.return_value.first = mock_chat_item_locator

        success = self.agent.select_chat("Test Chat", timeout_ms=1000)

        self.assertTrue(success)
        # Verify get_by_role was called correctly
        self.mock_page.get_by_role.assert_called_once_with("listitem", name="Test Chat")
        # Verify click was called on the locator returned by .first
        mock_chat_item_locator.click.assert_called_once_with(timeout=1000)

    def test_select_chat_not_found_timeout(self):
        self.agent.page = self.mock_page

        mock_chat_item_locator = MagicMock(spec=Locator)
        mock_chat_item_locator.click.side_effect = PlaywrightError("Timeout waiting for element")
        self.mock_page.get_by_role.return_value.first = mock_chat_item_locator

        success = self.agent.select_chat("NonExistentChat", timeout_ms=500)

        self.assertFalse(success)
        self.mock_page.get_by_role.assert_called_once_with("listitem", name="NonExistentChat")
        mock_chat_item_locator.click.assert_called_once_with(timeout=500)

    def test_select_chat_no_page_available(self): # Already present from previous step, verified
        self.agent.page = None # Simulate no page (login failed)
        success = self.agent.select_chat("AnyChat")
        self.assertFalse(success)

    def test_read_messages_success(self):
        self.agent.page = self.mock_page

        # Create mock Locator objects for individual message elements
        mock_msg_element1 = MagicMock(spec=Locator)
        mock_msg_element2 = MagicMock(spec=Locator)

        # Configure the main locator for message elements to return these mocks
        self.mock_page.locator.return_value.all.return_value = [mock_msg_element1, mock_msg_element2]

        # Configure sub-locators and their text_content for Message 1
        # Ensure the sub-locator calls on mock_msg_element1 return distinct mocks for .locator()
        mock_sender_loc1 = MagicMock(spec=Locator); mock_sender_loc1.text_content.return_value = "Alice"; mock_sender_loc1.count.return_value = 1
        mock_text_loc1 = MagicMock(spec=Locator); mock_text_loc1.text_content.return_value = "Hello Bob"; mock_text_loc1.count.return_value = 1
        mock_ts_loc1 = MagicMock(spec=Locator); mock_ts_loc1.text_content.return_value = "오후 1:00"; mock_ts_loc1.count.return_value = 1

        def msg1_locator_side_effect(selector):
            if selector == "span[data-testid='sender']": return mock_sender_loc1
            if selector == "div[data-testid='message-text']": return mock_text_loc1
            if selector == "span[data-testid='timestamp']": return mock_ts_loc1
            return MagicMock(spec=Locator, count=0) # Default for unexpected selectors
        mock_msg_element1.locator.side_effect = msg1_locator_side_effect

        # Configure sub-locators and their text_content for Message 2
        mock_sender_loc2 = MagicMock(spec=Locator); mock_sender_loc2.text_content.return_value = "Bob"; mock_sender_loc2.count.return_value = 1
        mock_text_loc2 = MagicMock(spec=Locator); mock_text_loc2.text_content.return_value = "Hi Alice"; mock_text_loc2.count.return_value = 1
        mock_ts_loc2 = MagicMock(spec=Locator); mock_ts_loc2.text_content.return_value = "오후 1:01"; mock_ts_loc2.count.return_value = 1

        def msg2_locator_side_effect(selector):
            if selector == "span[data-testid='sender']": return mock_sender_loc2
            if selector == "div[data-testid='message-text']": return mock_text_loc2
            if selector == "span[data-testid='timestamp']": return mock_ts_loc2
            return MagicMock(spec=Locator, count=0)
        mock_msg_element2.locator.side_effect = msg2_locator_side_effect

        messages = self.agent.read_messages(num_messages_to_capture=2)

        self.assertEqual(len(messages), 2)
        # Check main locator call
        self.mock_page.locator.assert_called_with("div[role='listitem'][aria-label*='message']")

        # Check details of first message
        self.assertEqual(messages[0]['sender'], "Alice")
        self.assertEqual(messages[0]['text'], "Hello Bob")
        self.assertEqual(messages[0]['timestamp_str'], "오후 1:00")
        self.assertTrue(messages[0]['id'].startswith("k_"))

        # Check details of second message
        self.assertEqual(messages[1]['sender'], "Bob")
        self.assertEqual(messages[1]['text'], "Hi Alice")
        self.assertEqual(messages[1]['timestamp_str'], "오후 1:01")

        # Verify calls to sub-locators for message 1
        mock_msg_element1.locator.assert_any_call("span[data-testid='sender']")
        mock_msg_element1.locator.assert_any_call("div[data-testid='message-text']")
        mock_msg_element1.locator.assert_any_call("span[data-testid='timestamp']")

        # Verify calls to sub-locators for message 2
        mock_msg_element2.locator.assert_any_call("span[data-testid='sender']")
        mock_msg_element2.locator.assert_any_call("div[data-testid='message-text']")
        mock_msg_element2.locator.assert_any_call("span[data-testid='timestamp']")


    def test_read_messages_locating_message_list_fails(self):
        self.agent.page = self.mock_page
        self.mock_page.locator.return_value.all.side_effect = PlaywrightError("Cannot find message list container")

        messages = self.agent.read_messages()
        self.assertEqual(messages, [])

    def test_read_messages_no_page_available(self): # Already present, verified
        self.agent.page = None
        messages = self.agent.read_messages()
        self.assertEqual(messages, [])

    def test_read_messages_partial_extraction_failure(self):
        self.agent.page = self.mock_page

        mock_msg_element_fail = MagicMock(spec=Locator)
        self.mock_page.locator.return_value.all.return_value = [mock_msg_element_fail]

        mock_sender_loc = MagicMock(spec=Locator); mock_sender_loc.text_content.return_value = "Charlie"; mock_sender_loc.count.return_value = 1
        mock_text_loc_fail = MagicMock(spec=Locator); mock_text_loc_fail.text_content.side_effect = PlaywrightError("Cannot get text"); mock_text_loc_fail.count.return_value = 1 # text_content fails
        mock_ts_loc = MagicMock(spec=Locator); mock_ts_loc.text_content.return_value = "오후 3:00"; mock_ts_loc.count.return_value = 1

        def msg_fail_locator_side_effect(selector):
            if selector == "span[data-testid='sender']": return mock_sender_loc
            if selector == "div[data-testid='message-text']": return mock_text_loc_fail
            if selector == "span[data-testid='timestamp']": return mock_ts_loc
            return MagicMock(spec=Locator, count=0)
        mock_msg_element_fail.locator.side_effect = msg_fail_locator_side_effect

        messages = self.agent.read_messages(num_messages_to_capture=1)

        self.assertEqual(len(messages), 0, "Message with partial extraction failure should be skipped.")
