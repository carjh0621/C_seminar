import unittest
from unittest.mock import patch, MagicMock, call, mock_open
import os
import json
from datetime import datetime, timedelta # Added timedelta for tests
import base64 # For helper function

from ingestion.agents import GmailAgent
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.errors import HttpError
from persistence.models import SourceToken # For creating mock token objects from DB

TEST_CREDS_FILE = 'dummy_credentials_for_test.json'
# TEST_TOKEN_FILE = 'dummy_token_for_test.json' # No longer directly used by agent for storage

def b64encode_str(s: str) -> str:
    """Helper to base64url encode a string, returning a string."""
    return base64.urlsafe_b64encode(s.encode('utf-8')).decode('ascii')

class TestGmailAgent(unittest.TestCase):

    def setUp(self):
        self.agent = GmailAgent(credentials_file=TEST_CREDS_FILE)
        # Create a dummy credentials.json for tests that need it to exist
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
        # TEST_TOKEN_FILE is no longer managed here as it's not directly used by agent

    @patch('ingestion.agents.persistence_crud.save_token')
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('ingestion.agents.build')
    @patch('ingestion.agents.InstalledAppFlow.from_client_secrets_file')
    @patch('os.path.exists') # For credentials_file check
    @patch('ingestion.agents.SessionLocal') # Mock the DB Session factory
    def test_authenticate_new_token(self, mock_session_local, mock_os_path_exists,
                                   mock_from_secrets, mock_build,
                                   mock_get_token_db, mock_save_token_db):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session

        mock_get_token_db.return_value = None # Simulate token not in DB
        mock_os_path_exists.return_value = True # For credentials_file existence

        mock_flow = MagicMock()
        mock_creds = MagicMock(spec=Credentials)
        mock_creds.token = "new_mock_token_val"
        mock_creds.refresh_token = 'mock_refresh_token_val'
        mock_creds.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_creds.scopes = GmailAgent.SCOPES
        mock_creds.token_uri = 'https://oauth2.googleapis.com/token'
        mock_creds.client_id = 'test_client_id' # Comes from credentials.json content
        mock_creds.client_secret = 'test_client_secret' # Comes from credentials.json content
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
        self.assertEqual(args[0], mock_db_session) # First arg is db session
        self.assertEqual(kwargs['user_identifier'], "user1_new_token")
        self.assertEqual(kwargs['platform'], "gmail")
        token_info = kwargs['token_info']
        self.assertEqual(token_info['access_token'], "new_mock_token_val")
        self.assertEqual(token_info['refresh_token'], "mock_refresh_token_val")

        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
        mock_db_session.close.assert_called_once()

    @patch('ingestion.agents.build')
    @patch('ingestion.agents.Credentials') # To control the reconstructed Credentials instance
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('os.path.exists', return_value=True) # For credentials_file to load client_id/secret
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
        # Simulate client_id/secret are not in DB, will be loaded from credentials.json
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

        # Mock open for reading credentials.json
        m_open = mock_open(read_data=json.dumps({"installed":{"client_id":"test_client_id","client_secret":"test_client_secret","token_uri":"https://oauth2.googleapis.com/token"}}))
        with patch('builtins.open', m_open):
            service = self.agent.authenticate_gmail(app_user_id="user2_valid_token")

        self.assertEqual(service, mock_service)
        mock_get_token_db.assert_called_once_with(mock_db_session, user_identifier="user2_valid_token", platform='gmail')

        # Check that Credentials was called with info from DB and potentially credentials.json
        m_open.assert_called_once_with(TEST_CREDS_FILE, 'r') # প্রমাণ করে যে এটি client_id/secret এর জন্য খোলা হয়েছে
        mock_creds_class.assert_called_once_with(
            token=mock_db_src_token.access_token,
            refresh_token=mock_db_src_token.refresh_token,
            token_uri=mock_db_src_token.token_uri, # This will be from db_token as it's not None
            client_id="test_client_id", # Loaded from dummy credentials.json
            client_secret="test_client_secret", # Loaded from dummy credentials.json
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
    @patch('os.path.exists', return_value=True) # For credentials_file
    @patch('ingestion.agents.SessionLocal')
    def test_authenticate_expired_token_refresh_success(self, mock_session_local, mock_os_path_exists,
                                                      mock_creds_class, mock_build,
                                                      mock_get_token_db, mock_save_token_db):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session

        mock_db_src_token = MagicMock(spec=SourceToken)
        mock_db_src_token.access_token = "expired_access_token_val"
        mock_db_src_token.refresh_token = "valid_refresh_token_for_refresh"
        mock_db_src_token.expires_dt = datetime.utcnow() - timedelta(hours=1) # Expired
        mock_db_src_token.scopes = " ".join(GmailAgent.SCOPES)
        mock_db_src_token.client_id = None # Force load from file
        mock_db_src_token.client_secret = None # Force load from file
        mock_db_src_token.token_uri = 'https://oauth2.googleapis.com/token'
        mock_get_token_db.return_value = mock_db_src_token

        mock_reconstructed_creds = MagicMock(spec=Credentials)
        mock_reconstructed_creds.valid = False # Initially
        mock_reconstructed_creds.expired = True
        mock_reconstructed_creds.refresh_token = mock_db_src_token.refresh_token
        # These attributes will be set by the refresh logic within the agent
        mock_reconstructed_creds.token = "refreshed_token_val_after_call"
        mock_reconstructed_creds.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_reconstructed_creds.client_id = "test_client_id" # Set after loading from file
        mock_reconstructed_creds.client_secret = "test_client_secret" # Set after loading from file


        def mock_refresh_logic(request):
            self.assertTrue(isinstance(request, GoogleAuthRequest))
            mock_reconstructed_creds.valid = True
            mock_reconstructed_creds.expired = False
            mock_reconstructed_creds.token = "refreshed_token_val_after_call" # Simulate token update
            mock_reconstructed_creds.expiry = datetime.utcnow() + timedelta(hours=1) # Simulate expiry update
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
        self.assertEqual(kwargs_save['token_info']['client_id'], "test_client_id") # Check if it was set before save

        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_reconstructed_creds)
        mock_db_session.close.assert_called_once()

    @patch('ingestion.agents.persistence_crud.save_token')
    @patch('ingestion.agents.persistence_crud.get_token')
    @patch('ingestion.agents.build')
    @patch('ingestion.agents.InstalledAppFlow.from_client_secrets_file')
    @patch('ingestion.agents.Credentials')
    @patch('os.path.exists') # Mock for credentials_file path check
    @patch('ingestion.agents.SessionLocal')
    def test_authenticate_refresh_fail_then_new_flow(self, mock_session_local, mock_os_path_exists,
                                                    mock_creds_class_reconstruct, mock_from_secrets,
                                                    mock_build, mock_get_token_db, mock_save_token_db):
        mock_db_session = MagicMock()
        mock_session_local.return_value = mock_db_session

        # os.path.exists for credentials.json (used for client_id/secret loading, then for new flow)
        mock_os_path_exists.return_value = True

        mock_db_src_token = MagicMock(spec=SourceToken) # Token from DB that's expired
        mock_db_src_token.refresh_token = "old_refresh_token"
        mock_db_src_token.client_id = None # Force load from file
        mock_get_token_db.return_value = mock_db_src_token

        mock_reconstructed_creds_for_refresh = MagicMock(spec=Credentials)
        mock_reconstructed_creds_for_refresh.valid = False
        mock_reconstructed_creds_for_refresh.expired = True
        mock_reconstructed_creds_for_refresh.refresh_token = "old_refresh_token"
        mock_reconstructed_creds_for_refresh.refresh.side_effect = Exception("Simulated Refresh API Failed")
        mock_creds_class_reconstruct.return_value = mock_reconstructed_creds_for_refresh

        # Mocks for the new flow part
        mock_flow_for_new = MagicMock()
        mock_new_creds_from_flow = MagicMock(spec=Credentials, valid=True, expired=False, refresh_token='newly_flowed_refresh_token')
        mock_new_creds_from_flow.token = "new_token_from_flow"
        mock_new_creds_from_flow.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_new_creds_from_flow.scopes = GmailAgent.SCOPES
        mock_new_creds_from_flow.client_id = "test_client_id" # from credentials.json
        mock_new_creds_from_flow.client_secret = "test_client_secret"
        mock_new_creds_from_flow.token_uri = "https://oauth2.googleapis.com/token"

        mock_flow_for_new.run_local_server.return_value = mock_new_creds_from_flow
        mock_from_secrets.return_value = mock_flow_for_new

        mock_service = MagicMock()
        mock_build.return_value = mock_service

        m_open = mock_open(read_data=json.dumps({"installed":{"client_id":"test_client_id","client_secret":"test_client_secret","token_uri":"https://oauth2.googleapis.com/token"}}))
        with patch('builtins.open', m_open): # Mocks open for reading credentials.json
            service = self.agent.authenticate_gmail(app_user_id="user4_refresh_fail")

        self.assertEqual(service, mock_service)
        mock_get_token_db.assert_called_once()
        mock_reconstructed_creds_for_refresh.refresh.assert_called_once() # Refresh was attempted
        mock_from_secrets.assert_called_once_with(TEST_CREDS_FILE, GmailAgent.SCOPES) # New flow was run

        mock_save_token_db.assert_called_once()
        args_save, kwargs_save = mock_save_token_db.call_args
        self.assertEqual(kwargs_save['token_info']['access_token'], "new_token_from_flow") # Token from new flow saved

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
            return {} # Should not happen in this test
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
