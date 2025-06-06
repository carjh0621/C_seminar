# obsidian_sync/parser.py
import re
from typing import List, Dict, Optional, Tuple, Pattern

# Regex for date section header, e.g., "## 2023-10-27 (금)"
# Captures YYYY-MM-DD in group 1
RE_DATE_HEADER: Pattern[str] = re.compile(r"^##\s*(\d{4}-\d{2}-\d{2})\s*\(.+\)\s*$")

# Regex for the basic task line structure
# Group 1: Status marker like "[ ]", "[x]", "[c]"
# Group 2: Optional time like "HH:MM " (note the space included in optional group)
# Group 3: The rest of the line after status and time
RE_TASK_LINE_BASE: Pattern[str] = re.compile(r"^\s*-\s*(\[.?\])\s*(?:(\d{2}:\d{2})\s+)?(.*)$")

# Regex to find all tags (e.g., #tag1, #project_alpha) in a string
RE_TAGS: Pattern[str] = re.compile(r"(#\S+)")

# Regex to find and remove the D-Day string, e.g., (D-Day), (D-3 남음), (D+7 지남)
# Includes optional leading space and aims to match the entire D-Day parenthetical.
RE_D_DAY_STRING: Pattern[str] = re.compile(r"\s*\((?:D-Day|D-\d+\s*남음|D\+\d+\s*지남)\)")

# Regex to find and remove the (Cancelled) marker string
RE_CANCELLED_MARKER: Pattern[str] = re.compile(r"\s*\(Cancelled\)\s*$", re.IGNORECASE)


def _extract_title_and_tags_from_line_segment(line_segment: str) -> Tuple[str, List[str]]:
    """
    Helper to extract title and tags from the part of the task line
    after the status marker and optional time.
    Tags, D-Day string, and (Cancelled) marker are removed to isolate the title.
    """
    # 1. Extract all tags first
    found_tags_raw = RE_TAGS.findall(line_segment)
    # Create a working copy of the line to remove parts from
    work_line = line_segment

    # 2. Remove tags from the working line to avoid them being part of the title
    work_line = RE_TAGS.sub("", work_line).strip()

    # 3. Remove D-Day string from the working line
    work_line = RE_D_DAY_STRING.sub("", work_line).strip()

    # 4. Remove (Cancelled) marker string from the working line
    work_line = RE_CANCELLED_MARKER.sub("", work_line).strip()

    # What remains is considered the title
    title_candidate = work_line.strip()

    # Clean up extracted tags (strip each tag, ensure they start with #, and are unique)
    cleaned_tags = []
    seen_tags = set()
    for tag in found_tags_raw:
        t = tag.strip()
        if t.startswith("#") and t not in seen_tags:
            cleaned_tags.append(t)
            seen_tags.add(t)

    return title_candidate, cleaned_tags


def parse_markdown_agenda_file(filepath: str) -> List[Dict[str, Optional[List[str] | str]]]:
    """
    Parses an Obsidian Markdown agenda file and extracts task information.

    Args:
        filepath: The path to the Markdown agenda file.

    Returns:
        A list of dictionaries, where each dictionary represents a task
        with keys: "date_str", "status_md", "time_str", "title_md", "tags_md".
    """
    parsed_tasks: List[Dict[str, Optional[List[str] | str]]] = []
    current_date_str: Optional[str] = None

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line_content in enumerate(f, 1):
                line = line_content.strip()

                if not line: # Skip empty lines
                    continue

                date_match = RE_DATE_HEADER.match(line)
                if date_match:
                    current_date_str = date_match.group(1)
                    # print(f"DEBUG Parser: Found date header: {current_date_str} on line {line_num}")
                    continue

                if not current_date_str: # Skip lines until a date header is found
                    # print(f"DEBUG Parser: Skipping line {line_num} as no current_date_str: '{line}'")
                    continue

                task_base_match = RE_TASK_LINE_BASE.match(line)
                if task_base_match:
                    status_md = task_base_match.group(1)
                    time_str = task_base_match.group(2) # Can be None if no time was matched
                    rest_of_line = task_base_match.group(3).strip()

                    # print(f"DEBUG Parser: Matched task base on line {line_num}: Status='{status_md}', Time='{time_str}', Rest='{rest_of_line}'")

                    title_md, tags_md_list = _extract_title_and_tags_from_line_segment(rest_of_line)

                    # If, after processing, title_md is empty, we might decide to skip it
                    # or use a placeholder. For now, we'll keep it if status_md was found.
                    if not title_md and status_md: # e.g. "- [ ]" with no text
                         # print(f"Warning: Line {line_num} parsed with empty title: '{line_content.strip()}'")
                         title_md = "Untitled Task" # Or skip by 'continue'

                    parsed_tasks.append({
                        "date_str": current_date_str,
                        "status_md": status_md,
                        "time_str": time_str, # This will be None if no time, or "HH:MM" string
                        "title_md": title_md,
                        "tags_md": tags_md_list # List of strings, e.g., ["#tag1", "#project"]
                    })
                # else:
                    # print(f"DEBUG Parser: Line {line_num} not a date or task: '{line}'")
    except FileNotFoundError:
        print(f"Error: File not found at {filepath}")
        return []
    except Exception as e:
        print(f"An error occurred while parsing {filepath}: {e}")
        return []

    return parsed_tasks

if __name__ == '__main__':
    dummy_md_content = """
## 2024-03-15 (금)
- [ ] 10:00 Morning Meeting (D-Day) #meeting #important
- [x] Finish report (D-1 남음) #work
- [ ] Simple task item
- [c] Cancelled old item (D+5 지남) #old (Cancelled)
- [ ] Task with no time (D-Day) #notime

---
## 2024-03-16 (토)
- [ ] Weekend errand #personal #todo
- [ ] 14:30 Another item for Saturday with specific time (D-2 남음) #errand
    - This is a note on the item, current parser will include it in title or it's stripped by tag/dday logic.
    This line should ideally not be part of the title. (Parser needs enhancement for sub-lines)
- [ ] Item with #multiple #tags #here (D-2 남음) and some text after tags.
- [ ] Item with #duplicate #tag and #duplicate #tag again
---
This is not a task line.
Nor is this.
## 2024-03-17 (일)
- [ ]
- [x] #JustTagNoTitle
    """
    dummy_filepath = "dummy_agenda_for_parser_test.md"
    with open(dummy_filepath, 'w', encoding='utf-8') as f:
        f.write(dummy_md_content)

    print(f"--- Testing Markdown Parser with '{dummy_filepath}' ---")
    tasks = parse_markdown_agenda_file(dummy_filepath)

    if tasks:
        for i, task in enumerate(tasks):
            print(f"Task {i+1}:")
            print(f"  Date    : {task['date_str']}")
            print(f"  Status  : {task['status_md']}")
            print(f"  Time    : {task['time_str'] if task['time_str'] else 'N/A'}")
            print(f"  Title   : '{task['title_md']}'")
            print(f"  Tags    : {task['tags_md']}")
            print("-" * 20)
    else:
        print("No tasks parsed or file not found.")

    import os
    try:
        os.remove(dummy_filepath)
        print(f"\nCleaned up '{dummy_filepath}'.")
    except OSError as e:
        print(f"\nError removing dummy file '{dummy_filepath}': {e}")

    print("\n--- Testing with a non-existent file ---")
    non_existent_tasks = parse_markdown_agenda_file("non_existent_file.md")
    print(f"Result for non-existent file: {len(non_existent_tasks)} tasks found (expected 0).")

    print("\n--- Testing specific line cases ---")
    test_line_1 = "- [ ] 10:30 My Task Title #tag1 (D-1 남음) #tag2"
    match_1 = RE_TASK_LINE_BASE.match(test_line_1)
    if match_1:
        title_res_1, tags_res_1 = _extract_title_and_tags_from_line_segment(match_1.group(3).strip())
        print(f"Line: '{test_line_1}' -> Title: '{title_res_1}', Tags: {tags_res_1}")

    test_line_2 = "- [x] Another Task (D-Day) #projectX"
    match_2 = RE_TASK_LINE_BASE.match(test_line_2)
    if match_2:
        title_res_2, tags_res_2 = _extract_title_and_tags_from_line_segment(match_2.group(3).strip())
        print(f"Line: '{test_line_2}' -> Title: '{title_res_2}', Tags: {tags_res_2}")

    test_line_3 = "- [c] Cancelled Task (D+3 지남) #old (Cancelled)"
    match_3 = RE_TASK_LINE_BASE.match(test_line_3)
    if match_3:
        title_res_3, tags_res_3 = _extract_title_and_tags_from_line_segment(match_3.group(3).strip())
        print(f"Line: '{test_line_3}' -> Title: '{title_res_3}', Tags: {tags_res_3}")

    test_line_4 = "- [ ] Task with #multiple #tags and (D-Day) d-day string in middle #another"
    match_4 = RE_TASK_LINE_BASE.match(test_line_4)
    if match_4:
        title_res_4, tags_res_4 = _extract_title_and_tags_from_line_segment(match_4.group(3).strip())
        print(f"Line: '{test_line_4}' -> Title: '{title_res_4}', Tags: {tags_res_4}")


    test_line_5 = "- [ ] A task with (parentheses in title) and stuff (D-1 남음) #mytag"
    match_5 = RE_TASK_LINE_BASE.match(test_line_5)
    if match_5:
        title_res_5, tags_res_5 = _extract_title_and_tags_from_line_segment(match_5.group(3).strip())
        print(f"Line: '{test_line_5}' -> Title: '{title_res_5}', Tags: {tags_res_5}")

    test_line_6 = "- [ ] Task with no D-Day string #nodday"
    match_6 = RE_TASK_LINE_BASE.match(test_line_6)
    if match_6:
        title_res_6, tags_res_6 = _extract_title_and_tags_from_line_segment(match_6.group(3).strip())
        print(f"Line: '{test_line_6}' -> Title: '{title_res_6}', Tags: {tags_res_6}")

    test_line_7 = "- [ ] " # Task with no title
    match_7 = RE_TASK_LINE_BASE.match(test_line_7)
    if match_7:
        title_res_7, tags_res_7 = _extract_title_and_tags_from_line_segment(match_7.group(3).strip())
        print(f"Line: '{test_line_7}' -> Title: '{title_res_7}', Tags: {tags_res_7}")
        if not title_res_7: print("    (Title correctly empty)")

    test_line_8 = "- [x] #OnlyTags"
    match_8 = RE_TASK_LINE_BASE.match(test_line_8)
    if match_8:
        title_res_8, tags_res_8 = _extract_title_and_tags_from_line_segment(match_8.group(3).strip())
        print(f"Line: '{test_line_8}' -> Title: '{title_res_8}', Tags: {tags_res_8}")
        if not title_res_8: print("    (Title correctly empty)")


    print("\n--- Testing Regex Directly ---")
    print(f"RE_D_DAY_STRING match on ' (D-Day)': {RE_D_DAY_STRING.search(' (D-Day)')}")
    print(f"RE_D_DAY_STRING sub on 'My Title (D-3 남음)': '{RE_D_DAY_STRING.sub('', 'My Title (D-3 남음)').strip()}'")
    print(f"RE_CANCELLED_MARKER sub on 'My Title (Cancelled)': '{RE_CANCELLED_MARKER.sub('', 'My Title (Cancelled)').strip()}'")
    print(f"RE_TAGS findall on 'text #tag1 more #tag2': {RE_TAGS.findall('text #tag1 more #tag2')}")

    print("\n--- Test _extract_title_and_tags_from_line_segment ---")
    line_seg_test_1 = "Morning Meeting (D-Day) #meeting #important"
    title_test_1, tags_test_1 = _extract_title_and_tags_from_line_segment(line_seg_test_1)
    print(f"Segment: '{line_seg_test_1}' -> Title: '{title_test_1}', Tags: {tags_test_1}")

    line_seg_test_2 = "Finish report (D-1 남음) #work"
    title_test_2, tags_test_2 = _extract_title_and_tags_from_line_segment(line_seg_test_2)
    print(f"Segment: '{line_seg_test_2}' -> Title: '{title_test_2}', Tags: {tags_test_2}")

    line_seg_test_3 = "Cancelled old item (D+5 지남) #old (Cancelled)"
    title_test_3, tags_test_3 = _extract_title_and_tags_from_line_segment(line_seg_test_3)
    print(f"Segment: '{line_seg_test_3}' -> Title: '{title_test_3}', Tags: {tags_test_3}")

    line_seg_test_4 = "Item with #multiple #tags #here (D-2 남음) and some text after tags." # This text will remain in title
    title_test_4, tags_test_4 = _extract_title_and_tags_from_line_segment(line_seg_test_4)
    print(f"Segment: '{line_seg_test_4}' -> Title: '{title_test_4}', Tags: {tags_test_4}")

    line_seg_test_5 = "#JustTagNoTitle (D-Day)"
    title_test_5, tags_test_5 = _extract_title_and_tags_from_line_segment(line_seg_test_5)
    print(f"Segment: '{line_seg_test_5}' -> Title: '{title_test_5}', Tags: {tags_test_5}")

    line_seg_test_6 = "Task with (parentheses in title) (D-Day) #tag"
    title_test_6, tags_test_6 = _extract_title_and_tags_from_line_segment(line_seg_test_6)
    print(f"Segment: '{line_seg_test_6}' -> Title: '{title_test_6}', Tags: {tags_test_6}")
