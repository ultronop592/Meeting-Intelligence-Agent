"""core/encryption.py — Phase 4 Security: Credential Encryption & Key Rotation.

Provides authenticated encryption (AES-256-GCM via Fernet-style wrapper using
the ``cryptography`` library) for sensitive per-user credentials stored in the
database (e.g. Google OAuth refresh tokens, Jira API keys).

Design decisions:
  * The encryption key lives OUTSIDE the database in an environment variable
    (``CREDENTIAL_ENCRYPTION_KEY``).  Even a full DB dump is useless without
    the key.
  * Key rotation is supported: set ``CREDENTIAL_ENCRYPTION_KEY_PREVIOUS`` to
    the old key.  Decryption tries the current key first, then falls back to
    the previous key automatically.
  * AES-256-GCM provides both confidentiality AND integrity (the ciphertext
    cannot be tampered with undetected).
  * Each ``encrypt()`` call generates a fresh random 96-bit nonce, so
    encrypting the same value twice produces different ciphertext (semantic
    security).

Wire format (base64url, no padding):
    ``<12-byte nonce> || <ciphertext> || <16-byte auth tag>``

Usage::

    from core.encryption import CredentialEncryption

    enc = CredentialEncryption()
    token  = enc.encrypt("ghp_secrettoken")
    stored = token                         # save this to DB
    plain  = enc.decrypt(stored)           # retrieve original

Requirements:
    pip install cryptography>=41.0.0
"""

from __future__ import annotations

import base64
import logging
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# Byte sizes
_NONCE_BYTES = 12   # 96-bit nonce for AES-GCM (NIST recommendation)
_KEY_BYTES   = 32   # 256-bit AES key


def _load_key(env_var: str) -> bytes | None:
    """Load and validate a base64url-encoded AES-256 key from an env var."""
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return None
    try:
        key = base64.urlsafe_b64decode(raw + "==")  # pad for decoding
        if len(key) != _KEY_BYTES:
            raise ValueError(f"Key must be exactly {_KEY_BYTES} bytes (got {len(key)})")
        return key
    except Exception as exc:
        logger.error("Failed to load encryption key from %s: %s", env_var, exc)
        return None


def generate_new_key() -> str:
    """Generate a new random AES-256 key, returned as base64url string.

    Run once to bootstrap:
        python -c "from core.encryption import generate_new_key; print(generate_new_key())"

    Add the output to .env as CREDENTIAL_ENCRYPTION_KEY=<output>.
    """
    key_bytes = secrets.token_bytes(_KEY_BYTES)
    return base64.urlsafe_b64encode(key_bytes).decode()


class CredentialEncryption:
    """AES-256-GCM encryption for database-stored credentials.

    Reads keys from environment variables at construction time:
    - ``CREDENTIAL_ENCRYPTION_KEY``          — current (active) key
    - ``CREDENTIAL_ENCRYPTION_KEY_PREVIOUS`` — previous key (for rotation)

    If no key is configured, the class operates in **passthrough mode**
    (values are stored as-is with a ``plain:`` prefix).  This is intentionally
    noisy in logs so operators notice.
    """

    def __init__(self) -> None:
        self._current_key  = _load_key("CREDENTIAL_ENCRYPTION_KEY")
        self._previous_key = _load_key("CREDENTIAL_ENCRYPTION_KEY_PREVIOUS")
        self._passthrough  = self._current_key is None

        if self._passthrough:
            logger.warning(
                "CredentialEncryption: CREDENTIAL_ENCRYPTION_KEY not set — "
                "credentials will be stored in plaintext. Set the key in production!"
            )
        else:
            rotation_status = "key rotation ready" if self._previous_key else "no previous key"
            logger.info("CredentialEncryption: AES-256-GCM active (%s)", rotation_status)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encrypt(self, plaintext: str) -> str:
        """Encrypt *plaintext* and return a base64url-encoded ciphertext string.

        The returned string is safe to store in a VARCHAR/TEXT column.
        """
        if self._passthrough:
            return f"plain:{plaintext}"

        nonce = secrets.token_bytes(_NONCE_BYTES)
        aesgcm = AESGCM(self._current_key)  # type: ignore[arg-type]
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        payload = nonce + ciphertext_with_tag
        return base64.urlsafe_b64encode(payload).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string produced by :meth:`encrypt`.

        Tries the current key first; if that fails, falls back to the previous
        key (key rotation support).

        Raises:
            ValueError: if decryption fails with all available keys.
        """
        if ciphertext.startswith("plain:"):
            return ciphertext[len("plain:"):]

        keys_to_try: list[tuple[str, bytes]] = []
        if self._current_key:
            keys_to_try.append(("current", self._current_key))
        if self._previous_key:
            keys_to_try.append(("previous", self._previous_key))

        if not keys_to_try:
            raise ValueError("No encryption keys available for decryption")

        payload = base64.urlsafe_b64decode(ciphertext + "==")
        if len(payload) < _NONCE_BYTES + 16:  # 16 = GCM auth tag
            raise ValueError("Ciphertext is too short to be valid")

        nonce           = payload[:_NONCE_BYTES]
        ciphertext_body = payload[_NONCE_BYTES:]

        for key_name, key in keys_to_try:
            try:
                aesgcm   = AESGCM(key)
                plaintext = aesgcm.decrypt(nonce, ciphertext_body, None)
                if key_name == "previous":
                    logger.info(
                        "CredentialEncryption: decrypted with previous key — "
                        "re-encrypt this credential with the current key to complete rotation"
                    )
                return plaintext.decode("utf-8")
            except InvalidTag:
                continue

        raise ValueError(
            "Decryption failed: ciphertext could not be authenticated with any available key. "
            "The data may be corrupted or encrypted with an unknown key."
        )

    def re_encrypt_for_rotation(self, ciphertext: str) -> str:
        """Decrypt with any available key and immediately re-encrypt with the current key.

        Use this during a key-rotation sweep to migrate all stored credentials
        from the old key to the new key::

            for credential in session.scalars(select(UserToolCredential)):
                credential.encrypted_value = enc.re_encrypt_for_rotation(
                    credential.encrypted_value
                )
            await session.commit()
        """
        plaintext = self.decrypt(ciphertext)
        return self.encrypt(plaintext)

    @property
    def is_passthrough(self) -> bool:
        """True when operating without encryption (no key configured)."""
        return self._passthrough


# Module-level singleton — import directly:
#   from core.encryption import credential_encryption
credential_encryption = CredentialEncryption()
