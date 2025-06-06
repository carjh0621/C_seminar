# KakaoTalk Ingestion Setup (Experimental)

**Note:** Automating KakaoTalk for message ingestion is experimental and can be challenging due to the nature of desktop applications. This guide outlines the initial setup required to use the `KakaoAgent`. The current agent relies on you manually logging into the KakaoTalk PC client.

## Prerequisites

1.  **KakaoTalk PC Client**: Ensure you have the latest version of the KakaoTalk PC client installed on your system (Windows or macOS).
2.  **Playwright Browsers**: The `KakaoAgent` uses Playwright for browser automation tasks (even if direct KakaoTalk PC control is limited and might shift to other UI automation if pure web views are not available). You need to install the necessary browser binaries for Playwright.
    *   After installing project dependencies (`pip install -r requirements.txt`, which includes `playwright`), run the following command in your terminal:
        ```bash
        playwright install
        ```
        This will download browser binaries (e.g., Chromium, Firefox, WebKit) that Playwright can control. The `KakaoAgent` currently defaults to using Chromium via Playwright.

## Initial Setup for `KakaoAgent`

1.  **Manual Login to KakaoTalk PC**:
    *   Before running any pipeline that includes KakaoTalk ingestion via the `KakaoAgent`, **you must manually open and log in to your KakaoTalk PC client.**
    *   The current `KakaoAgent`'s `login()` method primarily sets up a Playwright-controlled browser instance; it does **not** automate the KakaoTalk PC application's login process itself. It relies on your KakaoTalk PC application being already authenticated and running.

2.  **(Optional) Playwright User Data Directory for Browser Persistence**:
    *   The `KakaoAgent` can be configured to use a persistent user data directory for the Playwright-controlled browser instance.
    *   While this doesn't directly persist your KakaoTalk PC application login (which is separate), it can be useful if future developments of the agent interact with web-based Kakao services, or if you want the specific browser instance launched by Playwright to remember its own state (e.g., cookies for other websites, browsing history) across runs.
    *   To use this, you can define a path in `config.py` (this variable is not yet used by `KakaoAgent.__init__` but is anticipated):
        ```python
        # Example in config.py (conceptual for now)
        # KAKAOTALK_USER_DATA_DIR = "./kakaotalk_playwright_user_data"
        ```
    *   If you create such a directory within your project, ensure it's added to your `.gitignore` file, as it will contain browser session data:
        ```gitignore
        # Example for .gitignore
        kakaotalk_playwright_user_data/
        ```
    *   The `KakaoAgent`'s `__init__` method takes a `user_data_dir` argument. If you plan to use this, you would pass the configured path when instantiating the agent.

3.  **Target Chat Room Name (for future use)**:
    *   For future functionality where the agent reads messages, you will need to specify the exact display name of the KakaoTalk chat room you want the agent to monitor. This would typically be set in `config.py`:
        ```python
        # Example in config.py (conceptual for now)
        # KAKAOTALK_CHAT_NAME_TO_MONITOR = "Your Target Chat Room Name"
        ```
        For example, many users have a "chat with myself" (나와의 채팅) which can be used for sending notes or links to oneself.

## How it Currently Works (Initial Phase)

*   When the `KakaoAgent`'s `login()` method is called:
    *   It launches a new Chromium browser instance controlled by Playwright (or attempts to reuse/create a persistent browser context if `user_data_dir` is specified and implemented).
    *   It navigates this Playwright-controlled browser to a generic page (e.g., google.com) to confirm that the browser instance is operational under Playwright's control.
    *   **Crucially, it does NOT automatically log into your KakaoTalk PC client or directly interact with it at this stage.**
*   You, the user, are responsible for ensuring your KakaoTalk PC client is already running and logged in independently of the Playwright-launched browser.
*   Subsequent methods like `select_chat()` and `read_messages()` (which are currently placeholders) would be where the experimental logic to interact with KakaoTalk's UI (if it uses web-renderable components accessible to Playwright, or via OS-level GUI automation as a fallback strategy) would reside. This interaction is complex and highly dependent on KakaoTalk's application architecture.

## Future Enhancements (Potential)

*   Investigation into reliable methods for selecting specific chat rooms (e.g., using UI element inspection if KakaoTalk PC uses web views, or accessibility APIs).
*   Implementation of message reading from a selected chat.
*   More automated login procedures, if feasible and compliant with KakaoTalk's policies. This is a significant challenge for desktop applications not designed for automation.
*   Robust error handling for various KakaoTalk states (e.g., logged out, chat not found, UI changes).

## Important Considerations

*   Automating desktop applications like KakaoTalk is inherently fragile and can easily break with application updates if it relies on specific UI element structures.
*   Always be mindful of KakaoTalk's Terms of Service regarding automation. Use any automation attempts responsibly and ethically. This agent is for experimental and personal use.
*   Directly controlling the KakaoTalk PC client might be better achieved with tools designed for native UI automation (like `pyautogui`, `pywinauto` for Windows, or `Appium` with a desktop driver) rather than solely relying on Playwright, unless KakaoTalk PC heavily utilizes web-based views for its interface. The choice of Playwright here is based on the initial plan and will be evaluated for suitability.
