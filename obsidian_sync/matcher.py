# obsidian_sync/matcher.py
from typing import List, Dict, Optional, Any
from datetime import datetime, time

# Attempt to import normalize_title_for_fingerprint from extract_nlp.utils
try:
    from extract_nlp.utils import normalize_title_for_fingerprint
except ImportError:
    print("Warning (obsidian_sync.matcher): Could not import normalize_title_for_fingerprint from extract_nlp.utils. Defining a local fallback.")
    import re
    def normalize_title_for_fingerprint(title: str) -> str: # Fallback
        if not title: return ""
        normalized = title.lower()
        # Simplified punctuation removal for fallback
        normalized = re.sub(r'[\.,;!?"\'`’‘“”()*\[\]{}]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

# Attempt to import Task from persistence.models for type hinting
try:
    from persistence.models import Task
except ImportError:
    print("Warning (obsidian_sync.matcher): Could not import Task from persistence.models. Using a dummy Task class for type hinting.")
    # Define a dummy Task for type hinting if import fails
    class Task: # type: ignore
        id: int
        title: str
        due_dt: Optional[datetime]
        # Add any other fields that might be accessed by the matcher logic if it evolves
        def __init__(self, id: int, title: str, due_dt: Optional[datetime]):
            self.id = id
            self.title = title
            self.due_dt = due_dt
        def __repr__(self):
            return f"<DummyTask(id={self.id}, title='{self.title}', due_dt='{self.due_dt}')>"


def find_matching_task_in_db(
    parsed_md_task: Dict[str, Optional[Any]], # Using Any for value type due to list of strings for tags_md
    db_tasks_on_date: List[Task]
) -> Optional[Task]:
    """
    Attempts to find a matching task in the database for a task parsed from Markdown.

    Args:
        parsed_md_task: A dictionary representing a task parsed from Markdown.
                        Expected keys: "title_md" (str), "time_str" (str HH:MM or None).
        db_tasks_on_date: A list of Task model instances from the database that
                          are due on the same date as parsed_md_task.

    Returns:
        The matching Task object from the database, or None if no confident match is found.
    """
    if not parsed_md_task or not parsed_md_task.get("title_md"):
        # print("DEBUG Matcher: MD task has no title, cannot match.")
        return None

    md_title_normalized = normalize_title_for_fingerprint(str(parsed_md_task["title_md"]))
    md_time_str: Optional[str] = parsed_md_task.get("time_str") # type: ignore

    md_task_time_obj: Optional[time] = None
    if md_time_str:
        try:
            md_task_time_obj = datetime.strptime(md_time_str, "%H:%M").time()
        except ValueError:
            # print(f"Warning (Matcher): Invalid time_str '{md_time_str}' from Markdown task '{md_title_normalized}'. Treating as no specific time.")
            md_task_time_obj = None

    # print(f"DEBUG Matcher: Processing MD Task: Normalized Title='{md_title_normalized}', Time='{md_task_time_obj}'")

    best_match: Optional[Task] = None

    for db_task in db_tasks_on_date:
        if not db_task.title:
            # print(f"DEBUG Matcher: DB Task ID {db_task.id} has no title, skipping.")
            continue

        db_title_normalized = normalize_title_for_fingerprint(db_task.title)
        # print(f"DEBUG Matcher: Comparing with DB Task ID {db_task.id}: Normalized Title='{db_title_normalized}', Due='{db_task.due_dt}'")

        if md_title_normalized == db_title_normalized:
            # Titles match, now check time alignment
            db_task_time_obj: Optional[time] = None
            if db_task.due_dt:
                db_task_time_obj = db_task.due_dt.time()

            if md_task_time_obj is not None: # Markdown task has a specific time
                if db_task_time_obj is not None and md_task_time_obj == db_task_time_obj:
                    # print(f"DEBUG Matcher: Strong match found (title + specific time) with DB Task ID {db_task.id}")
                    best_match = db_task
                    break
            else: # Markdown task is effectively "all-day" (no time specified in MD task line)
                if db_task_time_obj is not None and db_task_time_obj == time(0, 0, 0):
                    # print(f"DEBUG Matcher: Strong match found (title + MD all-day vs DB midnight) with DB Task ID {db_task.id}")
                    best_match = db_task
                    break
                # Add consideration: If MD task is all-day, and DB task due_dt is not None but has no specific time component set by user
                # (meaning it might also be an all-day task if default time is 00:00:00).
                # The current logic correctly handles this by checking db_task_time_obj == time(0,0,0).
                # If DB task has a specific time (not midnight), it won't match an all-day MD task here.

    # if best_match:
    #     print(f"DEBUG Matcher: Final best match for MD Task '{md_title_normalized}' is DB Task ID {best_match.id}.")
    # else:
    #     print(f"DEBUG Matcher: No strong match found for MD Task '{md_title_normalized}' (MD Time: {md_task_time_obj}) among {len(db_tasks_on_date)} DB tasks on that date.")

    return best_match


if __name__ == '__main__':
    print("--- Testing Task Matcher Logic ---")

    # Using the dummy Task class defined above if actual import failed.
    # If 'from persistence.models import Task' succeeded, Task will be the real one.
    # For the __main__ block, explicitly use a local mock for clarity and isolation for this test script.
    class MockMatcherTask:
        def __init__(self, id: int, title: str, due_dt_iso: Optional[str]):
            self.id = id
            self.title = title
            self.due_dt = datetime.fromisoformat(due_dt_iso) if due_dt_iso else None
        def __repr__(self):
            return f"<MockMatcherTask(id={self.id}, title='{self.title}', due='{self.due_dt.isoformat() if self.due_dt else None}')>"

    # Test cases
    md_task1 = {"date_str": "2024-03-18", "status_md": "[ ]", "time_str": "10:00", "title_md": "Team Meeting", "tags_md": ["#work"]}
    md_task2 = {"date_str": "2024-03-18", "status_md": "[x]", "time_str": None, "title_md": "Review Report", "tags_md": ["#project"]} # All-day
    md_task3 = {"date_str": "2024-03-18", "status_md": "[ ]", "time_str": "14:30", "title_md": "Client Call", "tags_md": []}
    md_task4 = {"date_str": "2024-03-18", "status_md": "[ ]", "time_str": "10:00", "title_md": "  team meeting !! ", "tags_md": ["#work"]} # Title needs normalization
    md_task5 = {"date_str": "2024-03-18", "status_md": "[ ]", "time_str": "00:00", "title_md": "Review Report", "tags_md": ["#project"]} # Explicit midnight

    db_tasks_for_date = [
        MockMatcherTask(id=1, title="Team Meeting", due_dt_iso="2024-03-18T10:00:00"),
        MockMatcherTask(id=2, title="Review Report", due_dt_iso="2024-03-18T00:00:00"), # DB all-day (midnight)
        MockMatcherTask(id=3, title="Client Call (Internal)", due_dt_iso="2024-03-18T14:30:00"),
        MockMatcherTask(id=4, title="Team Meeting", due_dt_iso="2024-03-18T11:00:00"),
        MockMatcherTask(id=5, title="Completely Different Task", due_dt_iso="2024-03-18T10:00:00"),
        MockMatcherTask(id=6, title="Review Report", due_dt_iso="2024-03-18T10:00:00"), # Same title as task 2, but specific time
    ]

    test_scenarios = [
        ("MD Task 1 (Specific Time)", md_task1, db_tasks_for_date, 1),
        ("MD Task 2 (All-Day)", md_task2, db_tasks_for_date, 2),
        ("MD Task 3 (Title Mismatch)", md_task3, db_tasks_for_date, None),
        ("MD Task 4 (Normalized Title)", md_task4, db_tasks_for_date, 1),
        ("MD Task 5 (Explicit Midnight)", md_task5, db_tasks_for_date, 2),
        ("MD Task 6 (Specific time vs different specific time)", md_task1, [db_tasks_for_date[3], db_tasks_for_date[4]], None), # Team Meeting @ 10:00 vs @ 11:00
        ("MD Task 7 (All-day vs specific time)", md_task2, [db_tasks_for_date[0], db_tasks_for_date[5]], None), # Review Report (all-day) vs DB items with specific times
        ("MD Task 8 (Specific time vs all-day)", md_task1, [db_tasks_for_date[1]], None), # Team Meeting @ 10:00 vs Review Report (all-day)
    ]

    for desc, md_task, db_list, expected_id in test_scenarios:
        print(f"\n--- {desc} ---")
        print(f"Matching MD Task: '{md_task['title_md']}' @ {md_task.get('time_str', 'All-day')}")
        # print(f"DB List: {[f'(ID:{t.id} T:{t.title} D:{t.due_dt.time() if t.due_dt else None})' for t in db_list]}")
        match = find_matching_task_in_db(md_task, db_list) # type: ignore
        print(f"Found: {match}")
        if expected_id is not None:
            assert match is not None and match.id == expected_id, f"Expected DB Task ID {expected_id}, got {match.id if match else None}"
            print(f"SUCCESS: Matched expected DB Task ID {expected_id}")
        else:
            assert match is None, f"Expected no match (None), got DB Task ID {match.id if match else None}"
            print("SUCCESS: Correctly found no match.")

    print("\n--- Test with MD task having no title ---")
    md_no_title = {"date_str": "2024-03-18", "status_md": "[ ]", "time_str": "10:00", "title_md": None, "tags_md": []}
    match_no_title = find_matching_task_in_db(md_no_title, db_tasks_for_date) # type: ignore
    assert match_no_title is None, "Should not match if MD task has no title."
    print("SUCCESS: Correctly found no match for MD task without title.")

    print("\n--- Test with MD task having malformed time string ---")
    md_malformed_time = {"date_str": "2024-03-18", "status_md": "[ ]", "time_str": "99:99", "title_md": "Review Report", "tags_md": []}
    # This should now match with the all-day "Review Report" (ID 2) because malformed time is treated as None (all-day)
    match_malformed_time = find_matching_task_in_db(md_malformed_time, db_tasks_for_date) # type: ignore
    assert match_malformed_time is not None and match_malformed_time.id == 2, f"Expected DB Task ID 2 for malformed time, got {match_malformed_time.id if match_malformed_time else None}"
    print(f"SUCCESS: Correctly matched ID {match_malformed_time.id} for MD task with malformed time string (treated as all-day).")

    print("\nMatcher tests complete.")
