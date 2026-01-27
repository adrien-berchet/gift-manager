def text_in_rendered(text: str, rendered: str) -> bool:
    """Check if the given text is present in the rendered content.

    This helper function is used in tests to verify that specific strings
    are included in the rendered HTML output. It is useful to hide the whole rendered
    content in test assertions for better readability.
    """
    return text in rendered
