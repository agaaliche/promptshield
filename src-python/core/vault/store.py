"""Encrypted token vault — stores token ↔ original text mappings securely."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from core.config import config
from models.schemas import PIIType, TokenMapping

logger = logging.getLogger(__name__)


class TokenVault:
    """
    Encrypted token vault using SQLite + Fernet field-level encryption.

    The vault stores token-to-original-text mappings. Sensitive fields
    (original_text, context_snippet) are encrypted with a key derived
    from the user's passphrase using PBKDF2.
    """

    # SQL schema
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS tokens (
        token_id TEXT PRIMARY KEY,
        token_string TEXT UNIQUE NOT NULL,
        original_text_enc BLOB NOT NULL,
        pii_type TEXT NOT NULL,
        source_document TEXT DEFAULT '',
        context_snippet_enc BLOB DEFAULT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS documents (
        doc_id TEXT PRIMARY KEY,
        original_filename TEXT NOT NULL,
        anonymized_filename TEXT DEFAULT '',
        processed_at TEXT NOT NULL,
        page_count INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS vault_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_token_string ON tokens(token_string);
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or config.vault_path
        self._conn: Optional[sqlite3.Connection] = None
        self._fernet: Optional[Fernet] = None
        self._is_unlocked = False

    @property
    def is_unlocked(self) -> bool:
        return self._is_unlocked

    @property
    def db_path(self) -> Path:
        return self._db_path

    def initialize(self, passphrase: str) -> None:
        """
        Create or open the vault with the given passphrase.

        If the vault doesn't exist, creates it and stores a verification
        token. If it exists, verifies the passphrase against the stored
        verification token.
        """
        is_new = not self._db_path.exists()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self._SCHEMA)

        if is_new:
            # Generate salt and store it
            salt = secrets.token_bytes(16)
            self._store_meta("salt", base64.b64encode(salt).decode())

            # Derive key
            self._fernet = self._derive_key(passphrase, salt)

            # Store verification token
            verify_text = "VAULT_VERIFICATION_TOKEN"
            encrypted_verify = self._fernet.encrypt(verify_text.encode())
            self._store_meta("verify", base64.b64encode(encrypted_verify).decode())

            self._is_unlocked = True
            logger.info(f"Created new vault at {self._db_path}")

        else:
            # Retrieve salt
            salt_b64 = self._get_meta("salt")
            if salt_b64 is None:
                raise RuntimeError("Vault is corrupted: missing salt")
            salt = base64.b64decode(salt_b64)

            # Derive key and verify
            self._fernet = self._derive_key(passphrase, salt)

            verify_b64 = self._get_meta("verify")
            if verify_b64 is None:
                raise RuntimeError("Vault is corrupted: missing verification token")

            try:
                encrypted_verify = base64.b64decode(verify_b64)
                decrypted = self._fernet.decrypt(encrypted_verify).decode()
                if decrypted != "VAULT_VERIFICATION_TOKEN":
                    raise ValueError()
            except Exception:
                self._fernet = None
                self._is_unlocked = False
                raise ValueError("Incorrect passphrase")

            self._is_unlocked = True
            logger.info(f"Opened existing vault at {self._db_path}")

    def _derive_key(self, passphrase: str, salt: bytes) -> Fernet:
        """Derive a Fernet key from passphrase + salt using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return Fernet(key)

    def _encrypt(self, plaintext: str) -> bytes:
        """Encrypt a string value."""
        assert self._fernet is not None
        return self._fernet.encrypt(plaintext.encode())

    def _decrypt(self, ciphertext: bytes) -> str:
        """Decrypt a bytes value to string."""
        assert self._fernet is not None
        return self._fernet.decrypt(ciphertext).decode()

    def _store_meta(self, key: str, value: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def _get_meta(self, key: str) -> Optional[str]:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT value FROM vault_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def _ensure_unlocked(self) -> None:
        if not self._is_unlocked:
            raise RuntimeError("Vault is locked. Call initialize() first.")

    # -----------------------------------------------------------------------
    # Token operations
    # -----------------------------------------------------------------------

    def generate_token_string(self, pii_type: PIIType) -> str:
        """Generate a unique token string like [ANON_PERSON_A3F2B1]."""
        type_str = pii_type.value if isinstance(pii_type, PIIType) else str(pii_type)
        hex_part = secrets.token_hex(3).upper()  # 6 hex chars
        token = config.token_format.format(
            prefix=config.token_prefix,
            type=type_str,
            hex=hex_part,
        )

        # Ensure uniqueness
        while self._token_string_exists(token):
            hex_part = secrets.token_hex(3).upper()
            token = config.token_format.format(
                prefix=config.token_prefix,
                type=type_str,
                hex=hex_part,
            )

        return token

    def _token_string_exists(self, token_string: str) -> bool:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT 1 FROM tokens WHERE token_string = ?", (token_string,)
        ).fetchone()
        return row is not None

    def store_token(self, mapping: TokenMapping) -> None:
        """Store a token mapping in the vault."""
        self._ensure_unlocked()
        assert self._conn is not None

        self._conn.execute(
            """INSERT INTO tokens
               (token_id, token_string, original_text_enc, pii_type,
                source_document, context_snippet_enc, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                mapping.token_id,
                mapping.token_string,
                self._encrypt(mapping.original_text),
                mapping.pii_type.value if isinstance(mapping.pii_type, PIIType) else str(mapping.pii_type),
                mapping.source_document,
                self._encrypt(mapping.context_snippet) if mapping.context_snippet else None,
                mapping.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def resolve_token(self, token_string: str) -> Optional[TokenMapping]:
        """Look up a token and return the decrypted mapping."""
        self._ensure_unlocked()
        assert self._conn is not None

        row = self._conn.execute(
            """SELECT token_id, token_string, original_text_enc, pii_type,
                      source_document, context_snippet_enc, created_at
               FROM tokens WHERE token_string = ?""",
            (token_string,),
        ).fetchone()

        if row is None:
            return None

        return TokenMapping(
            token_id=row[0],
            token_string=row[1],
            original_text=self._decrypt(row[2]),
            pii_type=PIIType(row[3]),
            source_document=row[4],
            context_snippet=self._decrypt(row[5]) if row[5] else "",
            created_at=datetime.fromisoformat(row[6]),
        )

    def resolve_all_tokens(self, text: str) -> tuple[str, int, list[str]]:
        """
        Find and replace all tokens in a text with their original values.

        Returns:
            (replaced_text, tokens_replaced_count, unresolved_tokens)
        """
        import re

        self._ensure_unlocked()

        # Find all token patterns in the text
        pattern = re.compile(
            r"\[" + re.escape(config.token_prefix) + r"_[A-Z_]+_[A-F0-9]{6}\]"
        )
        found_tokens = pattern.findall(text)

        if not found_tokens:
            return text, 0, []

        replaced_count = 0
        unresolved: list[str] = []
        result = text

        for token_str in set(found_tokens):
            mapping = self.resolve_token(token_str)
            if mapping:
                result = result.replace(token_str, mapping.original_text)
                replaced_count += result.count(mapping.original_text)  # Rough count
            else:
                unresolved.append(token_str)

        # More accurate count
        replaced_count = len(found_tokens) - len(unresolved)
        return result, replaced_count, unresolved

    def list_tokens(
        self,
        source_document: Optional[str] = None,
        pii_type: Optional[PIIType] = None,
    ) -> list[TokenMapping]:
        """List tokens, optionally filtered."""
        self._ensure_unlocked()
        assert self._conn is not None

        query = "SELECT * FROM tokens WHERE 1=1"
        params: list = []

        if source_document:
            query += " AND source_document = ?"
            params.append(source_document)
        if pii_type:
            query += " AND pii_type = ?"
            params.append(pii_type.value if isinstance(pii_type, PIIType) else str(pii_type))

        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()

        return [
            TokenMapping(
                token_id=row[0],
                token_string=row[1],
                original_text=self._decrypt(row[2]),
                pii_type=PIIType(row[3]),
                source_document=row[4],
                context_snippet=self._decrypt(row[5]) if row[5] else "",
                created_at=datetime.fromisoformat(row[6]),
            )
            for row in rows
        ]

    def delete_token(self, token_id: str) -> bool:
        """Delete a token from the vault."""
        self._ensure_unlocked()
        assert self._conn is not None

        cursor = self._conn.execute(
            "DELETE FROM tokens WHERE token_id = ?", (token_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -----------------------------------------------------------------------
    # Document tracking
    # -----------------------------------------------------------------------

    def register_document(
        self,
        doc_id: str,
        original_filename: str,
        page_count: int,
        anonymized_filename: str = "",
    ) -> None:
        """Register a processed document in the vault."""
        self._ensure_unlocked()
        assert self._conn is not None

        self._conn.execute(
            """INSERT OR REPLACE INTO documents
               (doc_id, original_filename, anonymized_filename, processed_at, page_count)
               VALUES (?, ?, ?, ?, ?)""",
            (doc_id, original_filename, anonymized_filename,
             datetime.utcnow().isoformat(), page_count),
        )
        self._conn.commit()

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return vault statistics."""
        self._ensure_unlocked()
        assert self._conn is not None

        token_count = self._conn.execute("SELECT COUNT(*) FROM tokens").fetchone()[0]
        doc_count = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        db_size = os.path.getsize(self._db_path) if self._db_path.exists() else 0

        return {
            "total_tokens": token_count,
            "total_documents": doc_count,
            "vault_size_bytes": db_size,
        }

    # -----------------------------------------------------------------------
    # Export / Import
    # -----------------------------------------------------------------------

    def export_vault(self, passphrase: str) -> str:
        """Export all tokens as an encrypted JSON string."""
        self._ensure_unlocked()
        tokens = self.list_tokens()
        data = {
            "version": 1,
            "exported_at": datetime.utcnow().isoformat(),
            "tokens": [t.model_dump(mode="json") for t in tokens],
        }

        # Encrypt the whole export with a fresh key from the passphrase
        salt = secrets.token_bytes(16)
        fernet = self._derive_key(passphrase, salt)
        payload = json.dumps(data).encode()
        encrypted = fernet.encrypt(payload)

        export_data = {
            "salt": base64.b64encode(salt).decode(),
            "data": base64.b64encode(encrypted).decode(),
        }
        return json.dumps(export_data)

    def close(self) -> None:
        """Close the vault connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._fernet = None
        self._is_unlocked = False


# Singleton vault instance
vault = TokenVault()
