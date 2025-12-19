"""Utility functions for encrypting and decrypting email addresses for privacy.

This module uses Fernet symmetric encryption to securely store email addresses.
The encryption key is stored in Django settings as EMAIL_ENCRYPTION_KEY.
"""

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from django.conf import settings


def _get_cipher() -> Fernet:
    """Get the Fernet cipher using the configured encryption key.

    Returns:
        A Fernet cipher instance.

    Raises:
        ValueError: If EMAIL_ENCRYPTION_KEY is not configured in settings.
    """
    key = getattr(settings, "EMAIL_ENCRYPTION_KEY", None)
    if not key:
        raise ValueError(
            "EMAIL_ENCRYPTION_KEY must be configured in Django settings. "
            "Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    # Ensure key is bytes
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        A new encryption key as a string.
    """
    return Fernet.generate_key().decode("utf-8")


def encrypt_email(email: str | None) -> str | None:
    """Encrypt an email address using Fernet encryption.

    Args:
        email: The plain text email address to encrypt, or None.

    Returns:
        The encrypted email address as a string, or None if input is None.
    """
    if email is None or email == "":
        return email
    cipher = _get_cipher()
    encrypted = cipher.encrypt(email.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_email(encrypted_email: str | None) -> str | None:
    """Decrypt an encrypted email address.

    Args:
        encrypted_email: The encrypted email address, or None.

    Returns:
        The decrypted plain text email address, or None if input is None.
    """
    if encrypted_email is None or encrypted_email == "":
        return encrypted_email
    try:
        cipher = _get_cipher()
        decrypted = cipher.decrypt(encrypted_email.encode("utf-8"))
        return decrypted.decode("utf-8")
    except (InvalidToken, ValueError):
        # If decryption fails, return the original value
        # This handles backwards compatibility with non-encrypted data
        return encrypted_email


def is_encrypted_email(value: str | None) -> bool:
    """Check if a value appears to be an encrypted email.

    Args:
        value: The string to check.

    Returns:
        True if the value can be decrypted to an email, False otherwise.
    """
    if value is None or value == "":
        return False
    try:
        cipher = _get_cipher()
        decrypted = cipher.decrypt(value.encode("utf-8")).decode("utf-8")
        return "@" in decrypted
    except (InvalidToken, ValueError):
        return False


# Aliases for backwards compatibility with existing code
encode_email = encrypt_email
decode_email = decrypt_email
is_encoded_email = is_encrypted_email
