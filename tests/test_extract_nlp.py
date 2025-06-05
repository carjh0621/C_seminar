import unittest
from datetime import datetime, date, timedelta
from extract_nlp.classifiers import resolve_date
# For mocking current date in tests if needed, though dateparser handles relative dates well.
# from unittest.mock import patch

class TestDateResolver(unittest.TestCase):

    def test_absolute_dates(self):
        self.assertEqual(resolve_date("2025-07-15"), datetime(2025, 7, 15))
        self.assertEqual(resolve_date("August 22, 2023 10:00"), datetime(2023, 8, 22, 10, 0))
        # dateparser default for DD/MM/YYYY vs MM/DD/YYYY can be tricky.
        # It often tries to infer or uses a common format.
        # For "10/15/2024", it's likely MDY.
        self.assertEqual(resolve_date("10/15/2024"), datetime(2024, 10, 15))
        # Test DMY explicitly if needed by settings or if it's the primary format.
        # e.g. self.assertEqual(resolve_date("15/10/2024", custom_settings={'DATE_ORDER': 'DMY'}), datetime(2024, 10, 15))


    def test_relative_dates(self):
        # For "tomorrow", "next monday", etc., the exact date depends on when the test is run.
        # We check if a datetime is returned and it's plausible.

        # Tomorrow
        tomorrow_dt = resolve_date("tomorrow")
        self.assertIsNotNone(tomorrow_dt)
        # It should be tomorrow's date, with time components possibly zeroed or current.
        self.assertAlmostEqual(tomorrow_dt.date(), (datetime.now() + timedelta(days=1)).date(), delta=timedelta(seconds=1))


        # Next Monday
        next_monday_dt = resolve_date("next monday")
        self.assertIsNotNone(next_monday_dt)
        self.assertGreaterEqual(next_monday_dt.date(), date.today()) # Should be today or in future
        self.assertEqual(next_monday_dt.weekday(), 0) # Monday is 0
        # Ensure it's actually in the future if today isn't Monday, or it's next week's Monday
        if date.today().weekday() == 0: # If today is Monday
             self.assertGreaterEqual(next_monday_dt.date(), (date.today() + timedelta(days=1))) # Must be at least next week or later today if time is specified
        else:
            self.assertGreater(next_monday_dt.date(), date.today())


        # In 3 days
        in_3_days_dt = resolve_date("in 3 days")
        self.assertIsNotNone(in_3_days_dt)
        expected_date = (datetime.now() + timedelta(days=3)).date()
        self.assertEqual(in_3_days_dt.date(), expected_date)

    def test_dates_with_times(self):
        # next Tuesday at 3pm
        tuesday_3pm_dt = resolve_date("next Tuesday at 3pm")
        self.assertIsNotNone(tuesday_3pm_dt)
        self.assertGreaterEqual(tuesday_3pm_dt.date(), date.today())
        self.assertEqual(tuesday_3pm_dt.weekday(), 1) # Tuesday is 1
        self.assertEqual(tuesday_3pm_dt.hour, 15)

        # today at 17:00
        # This test can be flaky if run exactly at 17:00 or if "today at 17:00" is interpreted as "next 17:00"
        # Using PREFER_DATES_FROM: 'current_period' or similar might be needed for stability
        # For now, assume it means current day's 17:00 if 17:00 hasn't passed, or next day's 17:00 if it has.
        # dateparser's behavior might default to future if time has passed.
        today_5pm_dt = resolve_date("today at 17:00", custom_settings={'PREFER_DATES_FROM': 'current_period'})
        self.assertIsNotNone(today_5pm_dt)
        if datetime.now().time() <= datetime(1,1,1,17,0).time():
            self.assertEqual(today_5pm_dt.date(), date.today())
        else:
            # If 5 PM has passed, dateparser might return next day or still today with 'current_period'
            # This specific assertion might need adjustment based on observed dateparser behavior
            self.assertIn(today_5pm_dt.date(), [date.today(), (date.today() + timedelta(days=1))])
        self.assertEqual(today_5pm_dt.hour, 17)


    def test_no_date_present(self):
        self.assertIsNone(resolve_date("This string has no date."))
        self.assertIsNone(resolve_date("completely random words without any temporal reference"))
        self.assertIsNone(resolve_date(""))
        self.assertIsNone(resolve_date(None))

    def test_settings_prefer_future(self):
        # This test is sensitive to the current date.
        # Let's use a date like "March 10th".
        # If current date is, say, April 2024, "March 10th" (no year) is past.
        # With PREFER_DATES_FROM: 'future', it should parse as March 10th of the *next* year.

        ambiguous_date_str = "March 10th"

        # Default behavior (dateparser might pick current year or next based on context)
        parsed_ambiguous_default = resolve_date(ambiguous_date_str)
        self.assertIsNotNone(parsed_ambiguous_default)

        # With PREFER_DATES_FROM: 'future'
        future_settings = {'PREFER_DATES_FROM': 'future'}
        parsed_ambiguous_future = resolve_date(ambiguous_date_str, custom_settings=future_settings)
        self.assertIsNotNone(parsed_ambiguous_future)

        # Assert that the future-preferred date is indeed in the future or today (if "March 10th" is today)
        self.assertGreaterEqual(parsed_ambiguous_future.date(), date.today())

        # If the default parsing resulted in a past date,
        # the future-preferred one should be later.
        if parsed_ambiguous_default.date() < date.today():
            self.assertGreater(parsed_ambiguous_future.date(), parsed_ambiguous_default.date())
            self.assertEqual(parsed_ambiguous_future.year, parsed_ambiguous_default.year + 1 if parsed_ambiguous_default.month >=3 else parsed_ambiguous_default.year )


    def test_language_specific_dates(self):
        # Test French date
        french_date_str = "15 août 2024" # August 15, 2024
        # With explicit language setting
        parsed_dt_fr = resolve_date(french_date_str, custom_settings={'LANGUAGES': ['fr']})
        self.assertEqual(parsed_dt_fr, datetime(2024, 8, 15))

        # Test Spanish date
        spanish_date_str = "20 de enero de 2025" # January 20, 2025
        parsed_dt_es = resolve_date(spanish_date_str, custom_settings={'LANGUAGES': ['es']})
        self.assertEqual(parsed_dt_es, datetime(2025, 1, 20))

        # Test without explicit, relying on auto-detection (can be less reliable)
        # This part is commented out as auto-detection can vary.
        # parsed_dt_auto_fr = resolve_date(french_date_str)
        # self.assertEqual(parsed_dt_auto_fr, datetime(2024, 8, 15))

if __name__ == '__main__':
    unittest.main()


class TestTaskClassifierLLM(unittest.TestCase):

    def setUp(self):
        # Patch openai.OpenAI to control the client instance used by TaskClassifier
        self.openai_client_patch = patch('extract_nlp.classifiers.openai.OpenAI')
        self.MockOpenAIClientClass = self.openai_client_patch.start()

        self.mock_openai_instance = MagicMock()
        self.MockOpenAIClientClass.return_value = self.mock_openai_instance

        # Instantiate TaskClassifier. It will use the mocked OpenAI client.
        # Pass a dummy key to satisfy the constructor's initial check,
        # though it won't be used for actual API calls due to the mock.
        self.classifier = TaskClassifier(api_key="dummy_test_key_for_init")

    def tearDown(self):
        self.openai_client_patch.stop()

    def _prepare_mock_llm_response(self, is_task, task_type=None, title=None, due_date_description=None, body_summary=None):
        """Helper to create a mock OpenAI API response object for function calling."""
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        # If is_task is None, it means we simulate the LLM not calling the function.
        if is_task is None:
            mock_message.function_call = None
        else: # is_task is True or False
            function_args = {"is_task": is_task}
            if is_task: # Only add other details if it's considered a task
                if task_type: function_args["task_type"] = task_type
                if title: function_args["title"] = title
                if due_date_description: function_args["due_date_description"] = due_date_description
                if body_summary: function_args["body_summary"] = body_summary

            mock_function_call = MagicMock()
            mock_function_call.arguments = json.dumps(function_args)
            mock_message.function_call = mock_function_call

        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        return mock_response

    def test_classify_task_successful_full_details(self):
        mock_llm_response = self._prepare_mock_llm_response(
            is_task=True,
            task_type="meeting",
            title="Project Review",
            due_date_description="Next Monday at 10 AM",
            body_summary="Discuss progress on Project X."
        )
        self.mock_openai_instance.chat.completions.create.return_value = mock_llm_response

        input_text = "Team meeting next Monday 10 AM project review"
        result = self.classifier.classify_task(input_text, source_id="email1")

        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'meeting')
        self.assertEqual(result['title'], 'Project Review')
        self.assertEqual(result['due'], 'Next Monday at 10 AM')
        self.assertEqual(result['body'], 'Discuss progress on Project X.')
        self.assertEqual(result['source_id'], 'email1')
        self.assertEqual(result['confidence'], 0.90)
        self.mock_openai_instance.chat.completions.create.assert_called_once()
        # We could also assert the arguments passed to create, e.g., model, messages, functions

    def test_classify_task_is_not_a_task(self):
        mock_llm_response = self._prepare_mock_llm_response(is_task=False)
        self.mock_openai_instance.chat.completions.create.return_value = mock_llm_response

        result = self.classifier.classify_task("Just a casual chat, how are you?", source_id="chat1")

        self.assertIsNone(result)
        self.mock_openai_instance.chat.completions.create.assert_called_once()

    def test_classify_task_llm_returns_no_function_call(self):
        # is_task=None in helper means function_call attribute will be None on the message
        mock_llm_response = self._prepare_mock_llm_response(is_task=None)
        self.mock_openai_instance.chat.completions.create.return_value = mock_llm_response

        result = self.classifier.classify_task("Some ambiguous text that LLM might not understand as function.", source_id="ambiguous1")
        self.assertIsNone(result)

    def test_classify_task_llm_returns_is_task_true_but_no_title(self):
        mock_llm_response = self._prepare_mock_llm_response(
            is_task=True,
            task_type="reminder",
            due_date_description="tomorrow"
            # title is deliberately omitted by mock LLM
        )
        self.mock_openai_instance.chat.completions.create.return_value = mock_llm_response

        result = self.classifier.classify_task("Reminder for tomorrow", source_id="reminder1")
        # Current implementation rejects if title is missing
        self.assertIsNone(result, "Task should be rejected if LLM says is_task=True but provides no title.")

    def test_classify_task_llm_api_error(self):
        # Simulate an API error from OpenAI client
        self.mock_openai_instance.chat.completions.create.side_effect = OpenAIError("Simulated API Connection Error")

        result = self.classifier.classify_task("Any text, this will cause a simulated API error", source_id="error1")
        self.assertIsNone(result)

    def test_classify_task_llm_invalid_json_in_function_args(self):
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_function_call = MagicMock()
        # LLM returns a string that is not valid JSON
        mock_function_call.arguments = "This is not valid JSON {is_task: true, title: 'forgot closing quote}"
        mock_message.function_call = mock_function_call
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        self.mock_openai_instance.chat.completions.create.return_value = mock_response

        result = self.classifier.classify_task("Text leading to LLM returning invalid JSON", source_id="jsonerror1")
        self.assertIsNone(result)

    def test_classify_task_minimal_valid_task_from_llm(self):
        # LLM says it's a task and provides only a title.
        # Other details like type, due, body are omitted by LLM.
        mock_llm_response = self._prepare_mock_llm_response(
            is_task=True,
            title="Minimal Task Title from LLM"
        )
        self.mock_openai_instance.chat.completions.create.return_value = mock_llm_response

        input_text = "A very minimal task description that results in minimal LLM output."
        result = self.classifier.classify_task(input_text, source_id="minimal1")

        self.assertIsNotNone(result, "Expected a task result for minimal valid LLM output.")
        self.assertEqual(result['title'], 'Minimal Task Title from LLM')
        self.assertEqual(result['type'], 'other', "Type should default to 'other'.")
        self.assertIsNone(result['due'], "Due date should be None if not provided by LLM.")
        # Body should fallback to a snippet of the original input text
        self.assertEqual(result['body'], input_text[:250]) # As per current fallback logic in TaskClassifier
        self.assertEqual(result['confidence'], 0.90, "Confidence should be high if LLM confirms task with title.")
