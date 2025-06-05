import dateparser # Keep for resolve_date
from datetime import datetime # Keep for resolve_date
import os # For API Key
import json # For parsing LLM JSON output
import openai # New import
from openai import OpenAIError # New import for error handling

# --- Import configuration for API Key ---
import config
# --- End import for configuration ---

# Existing resolve_date function - keep as is
def resolve_date(text_with_date: str, custom_settings: dict = None) -> datetime | None:
    if not text_with_date: return None
    # Example of how default settings could be structured if needed:
    # settings = {'PREFER_DATES_FROM': 'current_period'}
    # if custom_settings:
    #    settings.update(custom_settings)
    # else:
    #    settings = custom_settings
    try:
        parsed_date = dateparser.parse(text_with_date, settings=custom_settings)
        return parsed_date
    except Exception as e:
        print(f"Dateparser error for input '{text_with_date}': {e}")
        return None


class TaskClassifier:
    def __init__(self, api_key: str = None):
        """
        Initializes the TaskClassifier with an OpenAI API client.
        Args:
            api_key: OpenAI API key. If None, attempts to load from config.py or environment.
        """
        effective_api_key = api_key or getattr(config, 'OPENAI_API_KEY', "YOUR_API_KEY_HERE")

        if effective_api_key == "YOUR_API_KEY_HERE" or not effective_api_key:
            # Fallback to environment variable if config still has placeholder or is empty/missing attribute
            effective_api_key = os.getenv("OPENAI_API_KEY")

        if not effective_api_key or effective_api_key == "YOUR_API_KEY_HERE": # Check again after env fallback
            raise ValueError("OpenAI API key not configured. Please set it in config.py or as an environment variable OPENAI_API_KEY.")

        try:
            self.client = openai.OpenAI(api_key=effective_api_key)
            print("TaskClassifier initialized with OpenAI client.")
        except Exception as e:
            raise ValueError(f"Failed to initialize OpenAI client: {e}")


    def classify_task(self, text: str, source_id: str = "unknown") -> dict | None:
        """
        Classifies text to extract task details using the OpenAI API (GPT model).

        Args:
            text: The input text to classify.
            source_id: An identifier for the source of this text.

        Returns:
            A dictionary with task details if successful, None otherwise.
            Structure: {"type": str, "title": str, "due": str (natural lang or ISO),
                        "body": str, "source_id": str, "confidence": float}
        """
        print(f"TaskClassifier.classify_task called with text (first 100 chars): '{text[:100].replace(chr(10), ' ')}...'")

        function_schema = {
            "name": "extract_task_details",
            "description": "Extracts task details from a given text if it represents a task, assignment, meeting, or personal appointment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "is_task": {
                        "type": "boolean",
                        "description": "True if the text describes an actionable task, assignment, meeting, or appointment. False otherwise."
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["meeting", "assignment", "personal", "reminder", "other"],
                        "description": "The type of task (e.g., meeting, assignment, personal errand, general reminder)."
                    },
                    "title": {
                        "type": "string",
                        "description": "A concise title for the task (max 10-15 words)."
                    },
                    "due_date_description": {
                        "type": "string",
                        "description": "The due date and time as described in the text (e.g., 'next Monday at 3pm', '2024-12-25 10:00 EST', 'in two weeks'). If no specific time, can be just the date. If no date, this can be null or omitted."
                    },
                    "body_summary": {
                        "type": "string",
                        "description": "A brief summary of the task details or context (1-2 sentences)."
                    }
                },
                "required": ["is_task"]
            }
        }

        system_prompt = """You are an intelligent assistant helping to extract structured task information from text.
Analyze the provided text and determine if it describes an actionable task, assignment, meeting, or personal appointment.
If it is, extract the details. If not, indicate it's not a task.
Focus on specific commitments or actions. General statements or questions without clear actions are not tasks.
If a due date is mentioned, extract it as described. If a specific time is part of the due date, include it.
The title should be short and to the point. The body summary should capture key details.
If 'is_task' is true, 'title', 'task_type', and 'body_summary' should ideally be provided. 'due_date_description' is optional.
"""

        user_prompt = f"Please analyze the following text and extract task details if applicable:\n\n---\n{text}\n---"

        try:
            print("Calling OpenAI API for task classification...")
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo-0125",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                functions=[function_schema],
                function_call={"name": "extract_task_details"}
            )

            message = response.choices[0].message
            if message.function_call:
                function_args_str = message.function_call.arguments
                print(f"LLM raw function call arguments: {function_args_str}")
                try:
                    extracted_data = json.loads(function_args_str)
                except json.JSONDecodeError as json_err:
                    print(f"Error: LLM returned invalid JSON for function arguments: {function_args_str}. Error: {json_err}")
                    return None

                is_task = extracted_data.get("is_task", False)
                if not is_task:
                    print("LLM determined the text is not a task.")
                    return None

                title = extracted_data.get("title")
                if not title:
                    print("LLM marked as task but provided no title. Discarding as non-actionable.")
                    return None

                task_type = extracted_data.get("task_type", "other")
                due_description = extracted_data.get("due_date_description")
                body_summary = extracted_data.get("body_summary", text[:250]) # Fallback for body

                # Confidence can be set high if is_task is true and title exists
                confidence = 0.90 # Default high confidence if LLM forced function call & title exists

                result = {
                    "type": task_type.lower(),
                    "title": title,
                    "due": due_description,
                    "body": body_summary,
                    "source_id": source_id,
                    "confidence": confidence
                }
                print(f"LLM classification successful: Type='{result['type']}', Title='{result['title']}'")
                return result
            else:
                print("LLM did not call the function. No task details extracted.")
                return None

        except OpenAIError as e:
            print(f"OpenAI API error during task classification: {e}")
            # Specific error details if available
            if hasattr(e, 'response') and e.response:
                 print(f"API Response Error Details: {e.response.text}")
            elif hasattr(e, 'body') and e.body: # For newer versions of openai lib
                 print(f"API Error Body: {e.body}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during task classification: {e}")
            return None


if __name__ == '__main__':
    print("--- Testing DateResolver ---")
    test_dates_for_resolver = ["tomorrow at 10am", "next wednesday", "15 July 2024 14:30", "gibberish"]
    for text_date_example in test_dates_for_resolver:
        dt = resolve_date(text_date_example)
        print(f"'{text_date_example}' -> {dt}")

    print("\n--- Testing TaskClassifier (with LLM if API key is set) ---")
    try:
        classifier = TaskClassifier()

        test_inputs = [
            "Remember to submit the project report by next Friday.",
            "Team meeting scheduled for tomorrow at 2 PM to discuss Q3 goals.",
            "Need to buy groceries this evening. Get milk, eggs, and bread.",
            "What's the weather like today?",
            "Let's catch up sometime next week.",
            "Finalize presentation slides for the client demo on 2024-08-15.",
            "Dentist appointment on Sep 10th, 3:30pm."
        ]

        for i, input_text in enumerate(test_inputs):
            print(f"\nClassifying text ({i+1}/{len(test_inputs)}): '{input_text}'")
            classification = classifier.classify_task(input_text, source_id=f"test_source_{i+1}")
            if classification:
                print(f"Result: {classification}")
                if classification.get("due"):
                    print(f"  Attempting to resolve due string: '{classification['due']}' -> {resolve_date(classification['due'])}")
            else:
                print("Result: No task classified or an error occurred.")

    except ValueError as e: # Catches API key configuration errors
        print(f"Could not run TaskClassifier test (Configuration Error): {e}")
    except OpenAIError as e: # Catches API operational errors
        print(f"OpenAI API Error during TaskClassifier test run: {e}")
        if hasattr(e, 'body') and e.body: print(f"  Error details: {e.body}")
    except Exception as e: # Catches other unexpected errors
        print(f"Unexpected error during TaskClassifier test run: {e}")
