import os

# Placeholder for configuration settings
# print("Configuration settings initialized") # Commenting out default print

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agenda.db")

# For production, prefer environment variables for sensitive keys:
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# if not OPENAI_API_KEY:
#     print("Warning: OPENAI_API_KEY environment variable not set.")
# For local development, you can temporarily set it here but DO NOT COMMIT actual keys.
OPENAI_API_KEY = "YOUR_API_KEY_HERE" # Replace with your actual key or use environment variable

print(f"Config initialized. DATABASE_URL set. OpenAI API Key is {'SET' if OPENAI_API_KEY != 'YOUR_API_KEY_HERE' else 'NOT SET (using placeholder)'}.")
