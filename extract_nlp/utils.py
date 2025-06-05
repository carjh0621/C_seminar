# extract_nlp/utils.py
import hashlib
import re
from datetime import datetime

def normalize_title_for_fingerprint(title: str) -> str:
    """
    Normalizes a task title for fingerprint generation.
    - Converts to lowercase.
    - Removes common punctuation.
    - Normalizes whitespace (strips and collapses multiple spaces).
    """
    if not title:
        return ""

    # Lowercase
    normalized_title = title.lower()

    # Remove common punctuation. This aims to remove decorative punctuation
    # while trying to preserve some that might be meaningful (e.g., hyphens in words).
    # This can be adjusted. For now, remove: .,;!?'"`’‘“”()*[]{}
    normalized_title = re.sub(r'[\.,;!?\'"`’‘“”()*\[\]{}]', '', normalized_title)

    # Normalize whitespace (collapse multiple spaces to one, strip leading/trailing)
    normalized_title = re.sub(r'\s+', ' ', normalized_title).strip()

    return normalized_title

def generate_task_fingerprint(title: str, due_dt: datetime | None) -> str:
    """
    Generates a SHA256 fingerprint for a task based on its normalized title and due date.

    Args:
        title: The raw title of the task.
        due_dt: The due date (datetime object) of the task, or None.

    Returns:
        A SHA256 hex digest string representing the task's fingerprint.
    """
    if not title: # Should not happen if called after title is confirmed, but good check
        raise ValueError("Title cannot be empty for fingerprint generation.")

    normalized_title = normalize_title_for_fingerprint(title)

    if due_dt:
        # Consistent ISO 8601 format including time for precision.
        # Using timespec='seconds' to ignore microseconds for broader matching if needed,
        # but for exact match, default isoformat() or including microseconds might be preferred.
        # For deduplication, being slightly more general (ignoring microseconds) can be good.
        # Timezone handling: If due_dt can have varying timezones, convert to UTC first:
        # if due_dt.tzinfo:
        #     due_dt_str = due_dt.astimezone(timezone.utc).isoformat(timespec='seconds')
        # else: # Naive datetime
        #     due_dt_str = due_dt.isoformat(timespec='seconds')
        # For now, assuming naive or consistent timezone from upstream processing.
        due_dt_str = due_dt.isoformat(timespec='seconds')
    else:
        due_dt_str = "NO_DUE_DATE" # Special marker for tasks without a due date

    concatenated_string = f"title:{normalized_title}::due:{due_dt_str}"

    fingerprint_hash = hashlib.sha256(concatenated_string.encode('utf-8')).hexdigest()

    return fingerprint_hash

if __name__ == '__main__':
    # Test cases for fingerprint generation
    print("--- Testing Fingerprint Generation ---")

    title1 = "  Project Review Meeting, please attend! "
    due1 = datetime(2024, 8, 15, 10, 30, 0)
    fp1 = generate_task_fingerprint(title1, due1)
    print(f"Input Title: '{title1}', Normalized: '{normalize_title_for_fingerprint(title1)}', Due: {due1} -> FP: {fp1}")

    title2 = "Project review meeting please attend" # Slightly different title
    due2 = datetime(2024, 8, 15, 10, 30, 0) # Same due date
    fp2 = generate_task_fingerprint(title2, due2)
    print(f"Input Title: '{title2}', Normalized: '{normalize_title_for_fingerprint(title2)}', Due: {due2} -> FP: {fp2} (Should match fp1: {fp1 == fp2})")

    title3 = "  project review meeting, please attend! " # Case difference
    fp3 = generate_task_fingerprint(title3, due1)
    print(f"Input Title: '{title3}', Normalized: '{normalize_title_for_fingerprint(title3)}', Due: {due1} -> FP: {fp3} (Should match fp1: {fp1 == fp3})")

    title4 = "Different Task"
    fp4 = generate_task_fingerprint(title4, due1)
    print(f"Input Title: '{title4}', Normalized: '{normalize_title_for_fingerprint(title4)}', Due: {due1} -> FP: {fp4} (Should NOT match fp1: {fp1 != fp4})")

    title5 = "Project Review Meeting, please attend!" # No trailing space
    fp5 = generate_task_fingerprint(title5, due1)
    print(f"Input Title: '{title5}', Normalized: '{normalize_title_for_fingerprint(title5)}', Due: {due1} -> FP: {fp5} (Should match fp1: {fp1 == fp5})")

    title6 = "Task with no due date"
    fp6 = generate_task_fingerprint(title6, None)
    print(f"Input Title: '{title6}', Normalized: '{normalize_title_for_fingerprint(title6)}', Due: None -> FP: {fp6}")

    title7 = "Task with no due date" # Same as title6, no due date
    fp7 = generate_task_fingerprint(title7, None)
    print(f"Input Title: '{title7}', Normalized: '{normalize_title_for_fingerprint(title7)}', Due: None -> FP: {fp7} (Should match fp6: {fp6 == fp7})")

    title8 = "Task with slightly different punctuation!!! Project Alpha."
    due8 = datetime(2024, 9, 1, 12, 0, 0)
    fp8 = generate_task_fingerprint(title8, due8)
    print(f"Input Title: '{title8}', Normalized: '{normalize_title_for_fingerprint(title8)}', Due: {due8} -> FP: {fp8}")

    title9 = "Task with slightly different punctuation Project Alpha" # Punctuation removed by normalize
    fp9 = generate_task_fingerprint(title9, due8)
    print(f"Input Title: '{title9}', Normalized: '{normalize_title_for_fingerprint(title9)}', Due: {due8} -> FP: {fp9} (Should match fp8: {fp8 == fp9})")

    title10 = "Buy milk"
    due10 = datetime(2024, 8, 15) # Date only, time will be 00:00:00
    fp10 = generate_task_fingerprint(title10, due10)
    print(f"Input Title: '{title10}', Normalized: '{normalize_title_for_fingerprint(title10)}', Due: {due10} (date only) -> FP: {fp10}")

    title11 = "Buy milk"
    due11 = datetime(2024, 8, 15, 0, 0, 0) # Same date, explicit midnight
    fp11 = generate_task_fingerprint(title11, due11)
    print(f"Input Title: '{title11}', Normalized: '{normalize_title_for_fingerprint(title11)}', Due: {due11} (explicit midnight) -> FP: {fp11} (Should match fp10: {fp10 == fp11})")

    try:
        generate_task_fingerprint("", datetime.now())
    except ValueError as e:
        print(f"Correctly caught error for empty title: {e}")
