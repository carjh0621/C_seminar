# LLM (OpenAI) API Key Setup

To enable AI-powered task classification using OpenAI's models, you need to obtain an API key from OpenAI and configure it for the Agenda Manager application.

## Steps:

1.  **Create an OpenAI Account**:
    *   If you don't have one, sign up at [https://platform.openai.com/](https://platform.openai.com/).

2.  **Generate an API Key**:
    *   Navigate to the API keys section of your OpenAI account: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).
    *   Click on "**+ Create new secret key**".
    *   Give your key a name (e.g., "AgendaManagerKey").
    *   Click "**Create secret key**".
    *   **Important**: Copy the displayed API key immediately. You will not be able to see it again after closing the dialog. Store it securely.

3.  **Set up Billing**:
    *   Using the OpenAI API incurs costs based on usage. You'll need to set up a payment method in your OpenAI account settings under "Billing". New accounts often come with some free credits, but for continued use, billing information is required.

4.  **Configure the API Key for the Application**:
    There are two main ways to provide the API key to the application:

    *   **(Recommended for Security) Environment Variable**:
        *   Set an environment variable named `OPENAI_API_KEY` to your copied API key.
        *   How to set environment variables depends on your operating system:
            *   **Linux/macOS (bash/zsh)**: `export OPENAI_API_KEY="your_api_key_here"` (add this to your `~/.bashrc`, `~/.zshrc`, or shell profile). For the current session, you can just run this command in your terminal.
            *   **Windows (PowerShell)**: `$Env:OPENAI_API_KEY="your_api_key_here"` (for current session). To set it persistently, search for "environment variables" in Windows settings.
        *   The application (in `config.py`) is designed to read this environment variable if you modify it to use `os.getenv("OPENAI_API_KEY")`.

    *   **(Less Secure - For Development Only) Directly in `config.py`**:
        *   Open the `config.py` file in the project.
        *   Find the line `OPENAI_API_KEY = "YOUR_API_KEY_HERE"`
        *   Replace `"YOUR_API_KEY_HERE"` with your actual API key.
        *   **Warning**: Be extremely careful not to commit your actual API key to version control if you use this method. It's best to use environment variables. If you must use this, ensure `config.py` is in your `.gitignore` file (though this is generally not ideal as `config.py` might have other non-sensitive configurations that should be versioned, like `DATABASE_URL`). The placeholder key itself is safe to commit.

Once the API key is configured, the `TaskClassifier` will be able to use the OpenAI API for processing text.
