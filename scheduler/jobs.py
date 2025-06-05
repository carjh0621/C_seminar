# scheduler/jobs.py
import datetime
import sys
# Add project root to sys.path to allow imports from main, persistence etc.
# This is often needed if scheduler is run as a separate process or script,
# or if the main application structure doesn't automatically handle this.
# Example:
# import os
# project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# if project_root not in sys.path:
#    sys.path.insert(0, project_root)

_using_dummy_pipeline = False # Flag to indicate if the dummy function is in use

# Attempt to import the pipeline function from main.py
try:
    from main import run_gmail_ingestion_pipeline
except ImportError as e:
    print(f"Error importing 'run_gmail_ingestion_pipeline' from main: {e}")
    print("Ensure the scheduler is run from a context where 'main.py' (project root) is discoverable,")
    print("or adjust PYTHONPATH / sys.path in jobs.py or the runner script.")

    def run_gmail_ingestion_pipeline(app_user_id="default_user"): # Must match signature
        print(f"DUMMY: run_gmail_ingestion_pipeline called for {app_user_id} because 'main.run_gmail_ingestion_pipeline' could not be imported.")
        print("This is a placeholder. Actual pipeline did not run.")
    globals()['_using_dummy_pipeline'] = True


def scheduled_job():
    """
    The job function that will be executed by the scheduler.
    This function calls the main Gmail ingestion pipeline.
    """
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] Scheduler job started: Running Gmail ingestion pipeline...")

    global _using_dummy_pipeline

    try:
        target_user_id = "default_gmail_user"

        # Check if the actual pipeline function is available
        if 'run_gmail_ingestion_pipeline' not in globals() or \
           (_using_dummy_pipeline and globals()['run_gmail_ingestion_pipeline'].__module__ == __name__):
            # This condition means the import failed and we are using the dummy,
            # or something is very wrong. The dummy function itself will print a message.
            # If _using_dummy_pipeline is True, the dummy is already set.
            # If it's False but function is still from this module, it means initial import failed
            # but the flag wasn't set (should not happen with current logic).
             if not _using_dummy_pipeline:
                  print("CRITICAL: Real 'run_gmail_ingestion_pipeline' not imported and dummy not set correctly. Cannot run job.")
                  # It's safer to return if the state is unexpected.
                  return

        run_gmail_ingestion_pipeline(app_user_id=target_user_id)

        if not _using_dummy_pipeline:
            current_time_finished = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time_finished}] Scheduler job (actual pipeline) finished.")
        else:
            # Message for dummy run completion is handled by the dummy function itself.
            print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scheduler job (dummy pipeline) attempted.")

    except Exception as e:
        current_time_error = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time_error}] Error during scheduled job execution: {e}")
        # In a real application, log more details, e.g., traceback.

if __name__ == '__main__':
    print("Directly testing scheduled_job()...")

    # Example of how one might adjust sys.path if running this file directly
    # and main.py is in the parent directory.
    # import os
    # current_script_path = os.path.abspath(__file__)
    # project_root_dir = os.path.abspath(os.path.join(os.path.dirname(current_script_path), '..'))
    # if project_root_dir not in sys.path:
    #    print(f"Adding project root to sys.path: {project_root_dir}")
    #    sys.path.insert(0, project_root_dir)
    #    # Try to re-import if needed, though this is tricky for module-level imports.
    #    # It's generally better to run from the project root or have PYTHONPATH set.
    #    try:
    #        from main import run_gmail_ingestion_pipeline as rpip_reimported
    #        globals()['run_gmail_ingestion_pipeline'] = rpip_reimported
    #        globals()['_using_dummy_pipeline'] = False
    #        print("Successfully re-imported run_gmail_ingestion_pipeline after path adjustment.")
    #    except ImportError as e_reimport:
    #        print(f"Re-import failed even after path adjustment: {e_reimport}")

    scheduled_job()
    print("Direct test of scheduled_job() complete.")
