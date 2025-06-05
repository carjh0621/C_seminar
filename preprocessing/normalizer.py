from bs4 import BeautifulSoup

# Placeholder for normalizer
print("Normalizer initialized")

def html_to_plaintext(html_content):
    """Converts HTML content to plaintext."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text(separator='\n', strip=True)

def remove_emojis(text):
    """Removes emojis from text. Placeholder for now."""
    # TODO: Implement emoji removal logic (e.g., using a regex or a library)
    print("Emoji removal (not implemented)")
    return text

def normalize(raw_content, content_type='text/html'):
    """
    Normalizes raw content by stripping HTML, removing emojis (placeholder), etc.
    """
    processed_content = raw_content
    if content_type == 'text/html':
        processed_content = html_to_plaintext(processed_content)

    processed_content = remove_emojis(processed_content)

    # Future normalization steps can be added here

    return processed_content

if __name__ == '__main__':
    # Example usage
    sample_html = "<h1>Hello</h1><p>This is a test with <a href='#'>a link</a>.</p>"
    plaintext = normalize(sample_html)
    print("\n--- Sample HTML to Plaintext ---")
    print(plaintext)

    sample_text_with_emoji = "Hello from the normalizer 👋"
    no_emoji_text = normalize(sample_text_with_emoji, content_type='text/plain')
    print("\n--- Sample Emoji Removal (Placeholder) ---")
    print(no_emoji_text)
