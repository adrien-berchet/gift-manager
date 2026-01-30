def text_in_rendered(text: str, rendered: str) -> bool:
    """Check if text presence in rendered matches expected.

    This helper function is used in tests to verify that specific strings
    are included in the rendered HTML output. It is useful to hide the whole rendered
    content in test assertions for better readability.

    Args:
        text: The text to search for
        rendered: The rendered content to search in

    Returns:
        bool: True if the text in is rendered
    """
    is_present = text in rendered
    return is_present
