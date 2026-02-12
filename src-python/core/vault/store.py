"""Encrypted token vault — stores token ↔ original text mappings securely."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
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
        self._lock = threading.Lock()  # Protects all SQLite operations

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
        with self._lock:
            self._initialize_locked(passphrase)

    def _initialize_locked(self, passphrase: str) -> None:
        is_new = not self._db_path.exists()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
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
        if self._fernet is None:
            raise RuntimeError("Vault encryption key not initialized")
        return self._fernet.encrypt(plaintext.encode())

    def _decrypt(self, ciphertext: bytes) -> str:
        """Decrypt a bytes value to string."""
        if self._fernet is None:
            raise RuntimeError("Vault encryption key not initialized")
        return self._fernet.decrypt(ciphertext).decode()

    def _store_meta(self, key: str, value: str) -> None:
        """Store metadata (must be called under self._lock)."""
        if self._conn is None:
            raise RuntimeError("Vault database connection not open")
        self._conn.execute(
            "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def _get_meta(self, key: str) -> Optional[str]:
        """Read metadata (must be called under self._lock)."""
        if self._conn is None:
            raise RuntimeError("Vault database connection not open")
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

    # Map each PIIType to a single-letter prefix for compact tokens
    _TYPE_LETTER: dict[str, str] = {
        "PERSON": "P",
        "ORG": "O",
        "EMAIL": "E",
        "PHONE": "T",       # T for telephone
        "SSN": "S",
        "CREDIT_CARD": "C",
        "DATE": "D",
        "ADDRESS": "A",
        "LOCATION": "L",
        "IP_ADDRESS": "I",
        "IBAN": "B",
        "PASSPORT": "X",
        "DRIVER_LICENSE": "R",
        "CUSTOM": "K",
        "UNKNOWN": "U",
    }

    def generate_token_string(self, pii_type: PIIType) -> str:
        """Generate a compact unique token like [P38291].

        Format: ``[<letter><5 digits>]`` — 8 chars total.
        The letter encodes the entity type (P=person, E=email, etc.).
        100 000 unique tokens per type before collision retry.
        """
        type_str = pii_type.value if isinstance(pii_type, PIIType) else str(pii_type)
        letter = self._TYPE_LETTER.get(type_str, "U")
        with self._lock:
            digits = str(secrets.randbelow(100_000)).zfill(5)
            token = f"[{letter}{digits}]"

            # Ensure uniqueness
            while self._token_string_exists(token):
                digits = str(secrets.randbelow(100_000)).zfill(5)
                token = f"[{letter}{digits}]"

            return token

    def _token_string_exists(self, token_string: str) -> bool:
        if self._conn is None:
            raise RuntimeError("Vault database connection not open")
        row = self._conn.execute(
            "SELECT 1 FROM tokens WHERE token_string = ?", (token_string,)
        ).fetchone()
        return row is not None

    def store_token(self, mapping: TokenMapping) -> None:
        """Store a token mapping in the vault."""
        self._ensure_unlocked()
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
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
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
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

        # Find all token patterns in the text.
        # Supports both new compact format [P38291] and legacy [ANON_TYPE_HEX].
        pattern = re.compile(
            r"\[[A-Z]\d{5}\]"
            r"|\[" + re.escape(config.token_prefix) + r"_[A-Z_]+_[A-F0-9]{6,12}\]"
        )
        found_tokens = pattern.findall(text)

        if not found_tokens:
            return text, 0, []

        unresolved: list[str] = []
        result = text

        for token_str in set(found_tokens):
            mapping = self.resolve_token(token_str)
            if mapping:
                result = result.replace(token_str, mapping.original_text)
            else:
                unresolved.append(token_str)

        replaced_count = len(found_tokens) - len(unresolved)
        return result, replaced_count, unresolved

    def list_tokens(
        self,
        source_document: Optional[str] = None,
        pii_type: Optional[PIIType] = None,
    ) -> list[TokenMapping]:
        """List tokens, optionally filtered."""
        self._ensure_unlocked()
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
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
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
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
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
            self._conn.execute(
            """INSERT OR REPLACE INTO documents
               (doc_id, original_filename, anonymized_filename, processed_at, page_count)
               VALUES (?, ?, ?, ?, ?)""",
            (doc_id, original_filename, anonymized_filename,
                 datetime.now(timezone.utc).isoformat(), page_count),
            )
            self._conn.commit()

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return vault statistics."""
        self._ensure_unlocked()
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
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
            "exported_at": datetime.now(timezone.utc).isoformat(),
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

    def import_vault(self, export_json: str, passphrase: str) -> dict:
        """
        Import tokens from an encrypted export JSON string.

        Returns dict with 'imported', 'skipped', 'errors' counts.
        """
        self._ensure_unlocked()

        # Parse the outer envelope
        envelope = json.loads(export_json)
        salt = base64.b64decode(envelope["salt"])
        encrypted = base64.b64decode(envelope["data"])

        # Derive key from export passphrase
        fernet = self._derive_key(passphrase, salt)
        try:
            decrypted = fernet.decrypt(encrypted)
        except Exception:
            raise ValueError("Incorrect export passphrase — cannot decrypt backup")

        data = json.loads(decrypted)
        tokens_list = data.get("tokens", [])

        imported = 0
        skipped = 0
        errors = 0

        for t in tokens_list:
            try:
                mapping = TokenMapping(
                    token_id=t["token_id"],
                    token_string=t["token_string"],
                    original_text=t["original_text"],
                    pii_type=PIIType(t["pii_type"]),
                    source_document=t.get("source_document", ""),
                    context_snippet=t.get("context_snippet", ""),
                    created_at=datetime.fromisoformat(t["created_at"]),
                )
                # Skip if token_string already exists
                with self._lock:
                    if self._token_string_exists(mapping.token_string):
                        skipped += 1
                        continue
                self.store_token(mapping)
                imported += 1
            except sqlite3.IntegrityError:
                skipped += 1  # token_id primary key collision
            except Exception as exc:
                logger.warning("Failed to import token %s: %s", t.get("token_id", "?"), exc)
                errors += 1

        return {"imported": imported, "skipped": skipped, "errors": errors}

    def close(self) -> None:
        """Close the vault connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
            self._fernet = None
            self._is_unlocked = False


# Singleton vault instance
vault = TokenVault()
