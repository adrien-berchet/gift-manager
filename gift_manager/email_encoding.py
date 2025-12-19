"""Utility functions for encoding and decoding email addresses for privacy."""

import base64


def encode_email(email: str | None) -> str | None:
    """Encode an email address using base64 for privacy.

    Args:
        email: The plain text email address to encode, or None.

    Returns:
        The base64-encoded email address, or None if input is None.
    """
    if email is None or email == "":
        return email
    return base64.b64encode(email.encode("utf-8")).decode("utf-8")


def decode_email(encoded_email: str | None) -> str | None:
    """Decode a base64-encoded email address.

    Args:
        encoded_email: The base64-encoded email address, or None.

    Returns:
        The decoded plain text email address, or None if input is None.
    """
    if encoded_email is None or encoded_email == "":
        return encoded_email
    try:
        return base64.b64decode(encoded_email.encode("utf-8")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        # If decoding fails, assume the email is not encoded (for backwards compatibility)
        return encoded_email


def is_encoded_email(value: str | None) -> bool:
    """Check if a value appears to be a base64-encoded email.

    Args:
        value: The string to check.

    Returns:
        True if the value appears to be base64-encoded, False otherwise.
    """
    if value is None or value == "":
        return False
    try:
        # Try to decode and check if it looks like an email
        decoded = base64.b64decode(value.encode("utf-8")).decode("utf-8")
        return "@" in decoded
    except (ValueError, UnicodeDecodeError):
        return False
