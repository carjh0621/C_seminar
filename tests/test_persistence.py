import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as SQLAlchemySession # Alias to avoid clash if Session is used locally
from datetime import datetime, timedelta

# Adjust imports based on your project structure
# Assuming 'persistence' is a top-level directory or in PYTHONPATH
from persistence.models import Base, Task, TaskStatus
from persistence import crud

class TestPersistenceCRUD(unittest.TestCase):

    engine = None
    SessionLocalTest = None # Use a distinct name for the test session factory

    @classmethod
    def setUpClass(cls):
        # In-memory SQLite database for tests
        cls.engine = create_engine("sqlite:///:memory:")
        # Create all tables in the in-memory database
        Base.metadata.create_all(cls.engine)
        # Create a session factory for the tests
        cls.SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        # Drop all tables after tests are done
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        # Each test will use its own transaction and session
        # This ensures test isolation
        self.connection = self.engine.connect()
        self.trans = self.connection.begin()
        # Create a new session for each test, bound to the connection
        self.db: SQLAlchemySession = self.SessionLocalTest(bind=self.connection)


    def tearDown(self):
        # Rollback any changes made during the test
        self.db.close()
        self.trans.rollback()
        self.connection.close()

    def test_create_task(self):
        task_data = {
            "source": "email",
            "title": "Test Task 1",
            "body": "Body for test task 1",
            "due_dt": datetime.utcnow() + timedelta(days=1),
            "status": "TODO", # Test with string status
            "countdown_int": 1
        }
        created_task = crud.create_task(self.db, task_data)
        self.assertIsNotNone(created_task.id)
        self.assertEqual(created_task.title, "Test Task 1")
        self.assertEqual(created_task.status, TaskStatus.TODO)
        self.assertEqual(created_task.countdown_int, 1)

        # Verify it's in DB by querying directly (optional, crud.get_task also tests this)
        retrieved_task = self.db.query(Task).filter(Task.id == created_task.id).first()
        self.assertIsNotNone(retrieved_task)
        self.assertEqual(retrieved_task.title, "Test Task 1")

    def test_get_task(self):
        task_data = {"title": "G Task 1", "source": "test", "status": "DONE", "countdown_int": 0}
        created_task = crud.create_task(self.db, task_data)

        fetched_task = crud.get_task(self.db, created_task.id)
        self.assertIsNotNone(fetched_task)
        self.assertEqual(fetched_task.id, created_task.id)
        self.assertEqual(fetched_task.title, "G Task 1")

        non_existent_task = crud.get_task(self.db, 99999)
        self.assertIsNone(non_existent_task)

    def test_get_tasks(self):
        crud.create_task(self.db, {"title": "List Task 1", "source": "test", "status": "TODO", "countdown_int": 1})
        crud.create_task(self.db, {"title": "List Task 2", "source": "test", "status": "DONE", "countdown_int": 0})

        tasks_limit_1 = crud.get_tasks(self.db, limit=1)
        self.assertEqual(len(tasks_limit_1), 1)

        tasks_skip_1_limit_1 = crud.get_tasks(self.db, skip=1, limit=1)
        self.assertEqual(len(tasks_skip_1_limit_1), 1)
        # Order is not guaranteed unless explicitly set, so check if title is one of expected
        self.assertIn(tasks_skip_1_limit_1[0].title, ["List Task 1", "List Task 2"])


        all_tasks = crud.get_tasks(self.db, limit=10)
        self.assertEqual(len(all_tasks), 2)

    def test_update_task(self):
        task_data = {"title": "Update Task 1", "status": "TODO", "source": "test", "countdown_int": 5}
        created_task = crud.create_task(self.db, task_data)

        update_data = {"title": "Updated Title", "status": TaskStatus.DONE, "countdown_int": 0} # Test with enum
        updated_task = crud.update_task(self.db, created_task.id, update_data)

        self.assertIsNotNone(updated_task)
        self.assertEqual(updated_task.title, "Updated Title")
        self.assertEqual(updated_task.status, TaskStatus.DONE)
        self.assertEqual(updated_task.countdown_int, 0)

        # Test updating non-existent task
        non_existent_update = crud.update_task(self.db, 99999, {"title": "ghost"})
        self.assertIsNone(non_existent_update)

        # Test updating with string status
        update_data_str_status = {"status": "CANCELLED"}
        updated_task_str_status = crud.update_task(self.db, created_task.id, update_data_str_status)
        self.assertIsNotNone(updated_task_str_status)
        self.assertEqual(updated_task_str_status.status, TaskStatus.CANCELLED)


    def test_delete_task(self):
        task_data = {"title": "Delete Task 1", "source": "test", "status": "TODO", "countdown_int": 1}
        created_task = crud.create_task(self.db, task_data)

        task_id_to_delete = created_task.id
        deleted_task_obj = crud.delete_task(self.db, task_id_to_delete)
        self.assertIsNotNone(deleted_task_obj)
        self.assertEqual(deleted_task_obj.id, task_id_to_delete)

        fetched_after_delete = crud.get_task(self.db, task_id_to_delete)
        self.assertIsNone(fetched_after_delete)

        # Test deleting non-existent task
        non_existent_delete = crud.delete_task(self.db, 99999)
        self.assertIsNone(non_existent_delete)

if __name__ == '__main__':
    unittest.main()


class TestPersistenceSourceTokenCRUD(unittest.TestCase):

    engine = None
    SessionLocalTest = None

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.SessionLocalTest = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.trans = self.connection.begin()
        # Use SQLAlchemySession (aliased Session) for type hinting if preferred
        self.db: SQLAlchemySession = self.SessionLocalTest(bind=self.connection)

    def tearDown(self):
        self.db.close()
        self.trans.rollback()
        self.connection.close()

    def test_save_and_get_token_create_new(self):
        user_id = "test_user_st1"
        platform = "test_platform_st"
        token_info = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_dt": datetime.utcnow() + timedelta(hours=1),
            "scopes": ["scope1", "scope2"],
            "token_uri": "https://example.com/token",
            "client_id": "client_id_example",
            # Not testing client_secret storage directly here for safety
        }

        # Save new token
        saved_token = crud.save_token(self.db, user_id, platform, token_info)
        self.assertIsNotNone(saved_token.id, "Saved token should have an ID.")
        self.assertEqual(saved_token.access_token, "access_token_123")
        self.assertEqual(saved_token.user_id, user_id)
        self.assertEqual(saved_token.platform, platform)
        self.assertEqual(saved_token.scopes, "scope1 scope2", "Scopes should be space-separated string.")
        self.assertEqual(saved_token.token_uri, "https://example.com/token")
        self.assertEqual(saved_token.client_id, "client_id_example")
        self.assertIsNotNone(saved_token.created_dt, "created_dt should be set.")
        self.assertIsNotNone(saved_token.last_modified_dt, "last_modified_dt should be set.")

        # Retrieve token
        retrieved_token = crud.get_token(self.db, user_id, platform)
        self.assertIsNotNone(retrieved_token, "Token should be retrievable after saving.")
        self.assertEqual(retrieved_token.id, saved_token.id)
        self.assertEqual(retrieved_token.access_token, "access_token_123")
        self.assertEqual(retrieved_token.scopes, "scope1 scope2")
        self.assertEqual(retrieved_token.refresh_token, "refresh_token_456")

    def test_save_token_update_existing(self):
        user_id = "test_user_st2"
        platform = "test_platform_st_update"
        initial_token_info = {
            "access_token": "initial_access",
            "expires_dt": datetime.utcnow() + timedelta(hours=1),
            "scopes": ["initial_scope"],
            "client_id": "old_client_id"
        }
        # Create initial token
        initial_saved_token = crud.save_token(self.db, user_id, platform, initial_token_info)
        initial_created_dt = initial_saved_token.created_dt # Save for later comparison
        initial_last_modified_dt = initial_saved_token.last_modified_dt

        # Ensure last_modified_dt is distinct enough for a change to be visible
        self.db.flush() # Ensure timestamps are set if they depend on DB flush
        import time; time.sleep(0.01) # Small delay

        updated_token_info = {
            "access_token": "updated_access_token_789",
            "expires_dt": datetime.utcnow() + timedelta(hours=2),
            "refresh_token": "new_refresh_token",
            "scopes": ["updated_scope1", "updated_scope2"],
            "client_id": "new_client_id" # Update client_id
        }

        updated_db_token = crud.save_token(self.db, user_id, platform, updated_token_info)
        self.assertEqual(updated_db_token.id, initial_saved_token.id, "ID should remain the same on update.")
        self.assertEqual(updated_db_token.access_token, "updated_access_token_789")
        self.assertEqual(updated_db_token.refresh_token, "new_refresh_token")
        self.assertEqual(updated_db_token.scopes, "updated_scope1 updated_scope2")
        self.assertEqual(updated_db_token.client_id, "new_client_id")
        self.assertEqual(updated_db_token.created_dt, initial_created_dt, "created_dt should not change on update.")
        self.assertGreater(updated_db_token.last_modified_dt, initial_last_modified_dt, "last_modified_dt should update.")

        all_tokens_for_user = self.db.query(SourceToken).filter(
            SourceToken.user_id == user_id, SourceToken.platform == platform
        ).all()
        self.assertEqual(len(all_tokens_for_user), 1, "Should only be one token record for this user/platform.")
        self.assertEqual(all_tokens_for_user[0].access_token, "updated_access_token_789")

    def test_get_token_not_found(self):
        retrieved_token = crud.get_token(self.db, "non_existent_user", "non_existent_platform")
        self.assertIsNone(retrieved_token)

    def test_delete_token(self):
        user_id = "test_user_st3_delete"
        platform = "test_platform_st_delete"
        token_info = {"access_token": "token_to_delete", "expires_dt": datetime.utcnow()}

        crud.save_token(self.db, user_id, platform, token_info)

        delete_result = crud.delete_token(self.db, user_id, platform)
        self.assertTrue(delete_result, "delete_token should return True on successful deletion.")

        retrieved_token = crud.get_token(self.db, user_id, platform)
        self.assertIsNone(retrieved_token, "Token should not be found after deletion.")

    def test_delete_token_not_found(self):
        delete_result = crud.delete_token(self.db, "non_existent_user_del", "non_existent_platform_del")
        self.assertFalse(delete_result, "delete_token should return False if token does not exist.")

    def test_save_token_minimal_info(self):
        user_id = "test_user_st4_minimal"
        platform = "test_platform_st_minimal"
        token_info = {
            "access_token": "minimal_access",
            "expires_dt": datetime.utcnow() + timedelta(days=1),
            # user_id and platform are passed as arguments to save_token
        }
        saved_token = crud.save_token(self.db, user_id, platform, token_info)
        self.assertIsNotNone(saved_token.id)
        self.assertEqual(saved_token.access_token, "minimal_access")
        self.assertEqual(saved_token.user_id, user_id)
        self.assertEqual(saved_token.platform, platform)
        self.assertIsNone(saved_token.refresh_token)
        self.assertIsNone(saved_token.scopes)
        self.assertIsNone(saved_token.token_uri)
        self.assertIsNone(saved_token.client_id)
        self.assertIsNone(saved_token.client_secret)
        self.assertIsNotNone(saved_token.created_dt)
        self.assertIsNotNone(saved_token.last_modified_dt)

        retrieved = crud.get_token(self.db, user_id, platform)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.access_token, "minimal_access")
