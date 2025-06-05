# Gmail API Setup for Agenda Manager

To allow the Agenda Manager application to access your Gmail account and fetch emails, you need to configure the Gmail API through the Google Cloud Console and obtain OAuth 2.0 credentials.

## Steps:

1.  **Go to the Google Cloud Console**:
    *   Navigate to [https://console.cloud.google.com/](https://console.cloud.google.com/).
    *   If you don't have a project, create a new one.

2.  **Enable the Gmail API**:
    *   In the navigation menu, go to **APIs & Services > Library**.
    *   Search for "Gmail API" and select it.
    *   Click the **Enable** button.

3.  **Configure OAuth Consent Screen**:
    *   Go to **APIs & Services > OAuth consent screen**.
    *   Choose **User Type**:
        *   **Internal**: If you are using a Google Workspace account and the app is only for users within your organization.
        *   **External**: For personal Gmail accounts or if users outside your organization will use it. Start with "External" if unsure.
    *   Click **Create**.
    *   **App information**:
        *   **App name**: Enter a name for your application (e.g., "My Agenda Manager" or "Python Gmail Client").
        *   **User support email**: Enter your email address.
        *   **App logo**: Optional.
    *   **Developer contact information**: Enter your email address.
    *   Click **Save and Continue**.
    *   **Scopes**: You can skip adding scopes here for now, as the application will request them. Click **Save and Continue**.
    *   **Test users** (if "External" user type was selected and app is in "Testing" publishing status):
        *   Add your own Gmail address as a test user. This is important, otherwise, you won't be able to authorize the app later.
        *   Click **Add Users** and enter your email.
        *   Click **Save and Continue**.
    *   Review the summary and click **Back to Dashboard**.
    *   Optionally, you might need to "Publish" the app (or keep it in testing if only you are using it). For personal use, "testing" status with your email as a test user is usually sufficient.

4.  **Create OAuth 2.0 Credentials**:
    *   Go to **APIs & Services > Credentials**.
    *   Click **+ Create Credentials** at the top and select **OAuth client ID**.
    *   **Application type**: Choose **Desktop app**.
        *   (Using "Desktop app" is suitable for locally run scripts like this project. The authentication flow `InstalledAppFlow` with `run_local_server` is designed for this type).
    *   **Name**: Give your OAuth client ID a name (e.g., "Agenda Manager Desktop Client").
    *   Click **Create**.
    *   A dialog box will appear showing your "Client ID" and "Client secret". **You don't need to copy these directly from here.**
    *   Instead, click the **Download JSON** button (it might be an icon on the right side of the newly created Client ID in the list, or an option after creation).
    *   Save the downloaded file as `credentials.json`.

5.  **Place `credentials.json` in the Project**:
    *   Move the downloaded `credentials.json` file into the root directory of this project (the same directory where `ingestion/agents.py` is located, or as configured in `GmailAgent`).
    *   **Important**: This file contains sensitive information. Ensure it is not committed to public version control (e.g., add `credentials.json` to your `.gitignore` file).

## First Run & Authorization

When you run the application for the first time after placing `credentials.json`:
*   The `GmailAgent` will detect that it needs authorization.
*   It will attempt to open a web browser window/tab.
*   Log in with the Google account you want to use (the one you added as a "Test User" if your OAuth consent screen is in "testing" mode).
*   You will be asked to grant permission for your application (e.g., "My Agenda Manager") to "Read your Gmail messages" (for the `gmail.readonly` scope).
*   After granting permission, the browser might show a message like "The authentication flow has completed." You can close the browser window.
*   The application will then create a `token.json` file (or the name you configured) in the project directory. This file stores your access and refresh tokens, so the application doesn't need to ask for authorization every time.
*   **Important**: Like `credentials.json`, the `token.json` file is sensitive and should also be added to your `.gitignore` file.

Your application should now be able to access your Gmail messages.
