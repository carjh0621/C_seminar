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

3.  **Target Chat Room Name**:
    *   You need to specify the exact display name of the KakaoTalk chat room you want the agent to monitor. This is set in `config.py` via the `KAKAOTALK_CHAT_NAME_TO_MONITOR` variable.
        ```python
        # In config.py
        KAKAOTALK_CHAT_NAME_TO_MONITOR = "Your Target Chat Room Name"
        ```
    *   This name is used by the `KakaoAgent` when it attempts to select the chat room for reading messages. Ensure it exactly matches what you see in your KakaoTalk client (case-sensitive).

## Current Agent Capabilities (Experimental - Phase 2 Development)

The `KakaoAgent` is under active development. The current capabilities are:

*   **Browser Launch & Manual Login**:
    *   The `login()` method launches a Playwright-controlled Chromium browser.
    *   It still **requires you to manually ensure your KakaoTalk PC client is running and logged in.** The agent does not automate the KakaoTalk PC login itself.
*   **Chat Selection (Conceptual)**:
    *   The `select_chat(chat_name)` method contains logic to *attempt* to find and click on a chat room in the KakaoTalk interface whose name matches the `chat_name` argument (this name would typically be supplied from the `KAKAOTALK_CHAT_NAME_TO_MONITOR` configuration).
    *   **Crucially, this uses placeholder/conceptual Playwright selectors.** These selectors **must be replaced by a developer** with actual, working selectors identified from inspecting your KakaoTalk PC client's UI structure. Without this customization, chat selection will fail.
*   **Message Reading (Conceptual)**:
    *   The `read_messages()` method attempts to find and extract text, sender, and timestamp from message bubbles within the currently (conceptually) selected chat.
    *   This also **relies on placeholder/conceptual Playwright selectors** for message elements and their components. These also **must be customized by a developer.**
    *   Currently, it focuses on visible messages; scrolling to load older messages is not yet implemented.

**In summary: The agent provides a framework for KakaoTalk automation using Playwright, but its core interaction logic (finding chats, reading messages) will only function correctly after a developer inspects their KakaoTalk PC client and replaces the placeholder selectors in `ingestion/agents.py` with actual, working ones.**

## Future Enhancements (Potential)

*   Investigation into reliable methods for selecting specific chat rooms (e.g., using UI element inspection if KakaoTalk PC uses web views, or accessibility APIs).
*   Implementation of message reading from a selected chat.
*   More automated login procedures, if feasible and compliant with KakaoTalk's policies. This is a significant challenge for desktop applications not designed for automation.
*   Robust error handling for various KakaoTalk states (e.g., logged out, chat not found, UI changes).

## Important Considerations

*   Automating desktop applications like KakaoTalk is inherently fragile and can easily break with application updates if it relies on specific UI element structures.
*   Always be mindful of KakaoTalk's Terms of Service regarding automation. Use any automation attempts responsibly and ethically. This agent is for experimental and personal use.
*   Directly controlling the KakaoTalk PC client might be better achieved with tools designed for native UI automation (like `pyautogui`, `pywinauto` for Windows, or `Appium` with a desktop driver) rather than solely relying on Playwright, unless KakaoTalk PC heavily utilizes web-based views for its interface. The choice of Playwright here is based on the initial plan and will be evaluated for suitability.
