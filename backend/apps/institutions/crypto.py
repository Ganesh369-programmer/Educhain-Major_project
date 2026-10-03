"""
Cryptographic utilities for custodial wallet encryption at rest using Fernet.
Keyed off WALLET_ENCRYPTION_KEY (separate from DJANGO_SECRET_KEY).
"""

import os
import logging
from cryptography.fernet import Fernet
from django.conf import settings

logger = logging.getLogger(__name__)


def get_fernet_key() -> bytes:
    key = getattr(settings, 'WALLET_ENCRYPTION_KEY', None) or os.getenv('WALLET_ENCRYPTION_KEY')
    if not key or not str(key).strip():
        raise ValueError("WALLET_ENCRYPTION_KEY environment variable or setting is not configured.")
    if isinstance(key, str):
        key = key.strip().encode('utf-8')
    return key


def encrypt_private_key(raw_private_key: str) -> str:
    """
    Encrypts a raw private key string using Fernet symmetric encryption.
    Returns the URL-safe base64-encoded ciphertext token.
    Never stores or returns plaintext.
    """
    if not raw_private_key:
        return ""
    fernet = Fernet(get_fernet_key())
    return fernet.encrypt(raw_private_key.strip().encode('utf-8')).decode('utf-8')


def decrypt_private_key(encrypted_token: str) -> str:
    """
    Decrypts a Fernet ciphertext token back to raw private key in memory.
    The decrypted string must NEVER be logged, serialized, or stored.
    """
    if not encrypted_token:
        return ""
    fernet = Fernet(get_fernet_key())
    return fernet.decrypt(encrypted_token.strip().encode('utf-8')).decode('utf-8')
