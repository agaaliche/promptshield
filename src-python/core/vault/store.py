"""Token vault — stores token ↔ original text mappings in SQLite (plaintext)."""

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

from core.config import config
from models.schemas import PIIType, TokenMapping

logger = logging.getLogger(__name__)


class TokenVault:
    """
    Token vault using SQLite — stores token-to-original-text mappings.

    The vault stores mappings in plaintext (no passphrase required).
    It auto-initialises on first access.
    """

    # SQL schema — plaintext columns (no encryption)
    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS tokens (
        token_id TEXT PRIMARY KEY,
        token_string TEXT UNIQUE NOT NULL,
        original_text TEXT NOT NULL,
        pii_type TEXT NOT NULL,
        source_document TEXT DEFAULT '',
        context_snippet TEXT DEFAULT '',
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
        self._is_unlocked = False
        self._lock = threading.Lock()  # Protects all SQLite operations

    @property
    def is_unlocked(self) -> bool:
        return self._is_unlocked

    @property
    def db_path(self) -> Path:
        return self._db_path

    # ------------------------------------------------------------------
    # Initialisation — no passphrase needed
    # ------------------------------------------------------------------

    def initialize(self, passphrase: str | None = None) -> None:
        """Open (or create) the vault.

        The *passphrase* parameter is accepted but **ignored** — it is
        kept only for backward-compatible call-sites that still pass one.
        """
        with self._lock:
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self._SCHEMA)

        # Migrate from encrypted schema if needed
        self._migrate_if_needed()

        self._is_unlocked = True
        logger.info(f"Vault ready at {self._db_path}")

    def ensure_ready(self) -> None:
        """Auto-initialise if not yet open.  Call from any code path that
        needs the vault without going through the unlock API."""
        if not self._is_unlocked:
            self.initialize()

    def _migrate_if_needed(self) -> None:
        """Transparently rename old encrypted columns to plaintext names.

        Previous schema had ``original_text_enc BLOB`` and
        ``context_snippet_enc BLOB``.  If the new column names don't
        exist we rename them so existing data keeps working.
        """
        assert self._conn is not None
        cols = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(tokens)").fetchall()
        }
        if "original_text_enc" in cols and "original_text" not in cols:
            logger.info("Migrating vault schema: renaming encrypted columns")
            self._conn.execute(
                "ALTER TABLE tokens RENAME COLUMN original_text_enc TO original_text"
            )
            self._conn.execute(
                "ALTER TABLE tokens RENAME COLUMN context_snippet_enc TO context_snippet"
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------

    def _store_meta(self, key: str, value: str) -> None:
        if self._conn is None:
            raise RuntimeError("Vault database connection not open")
        self._conn.execute(
            "INSERT OR REPLACE INTO vault_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    def _get_meta(self, key: str) -> Optional[str]:
        if self._conn is None:
            raise RuntimeError("Vault database connection not open")
        row = self._conn.execute(
            "SELECT value FROM vault_meta WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def _ensure_unlocked(self) -> None:
        if not self._is_unlocked:
            # Auto-initialise instead of raising
            self.initialize()

    # -----------------------------------------------------------------------
    # Token operations
    # -----------------------------------------------------------------------

    _TYPE_LETTER: dict[str, str] = {
        "PERSON": "P",
        "ORG": "O",
        "EMAIL": "E",
        "PHONE": "T",
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
        """Generate a compact unique token like [P38291]."""
        type_str = pii_type.value if isinstance(pii_type, PIIType) else str(pii_type)
        letter = self._TYPE_LETTER.get(type_str, "U")
        with self._lock:
            digits = str(secrets.randbelow(100_000)).zfill(5)
            token = f"[{letter}{digits}]"
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
                   (token_id, token_string, original_text, pii_type,
                    source_document, context_snippet, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    mapping.token_id,
                    mapping.token_string,
                    mapping.original_text,
                    mapping.pii_type.value if isinstance(mapping.pii_type, PIIType) else str(mapping.pii_type),
                    mapping.source_document,
                    mapping.context_snippet or "",
                    mapping.created_at.isoformat(),
                ),
            )
            self._conn.commit()

    def resolve_token(self, token_string: str) -> Optional[TokenMapping]:
        """Look up a token and return the mapping."""
        self._ensure_unlocked()
        with self._lock:
            if self._conn is None:
                raise RuntimeError("Vault database connection not open")
            row = self._conn.execute(
                """SELECT token_id, token_string, original_text, pii_type,
                          source_document, context_snippet, created_at
                   FROM tokens WHERE token_string = ?""",
                (token_string,),
            ).fetchone()

        if row is None:
            return None

        return TokenMapping(
            token_id=row[0],
            token_string=row[1],
            original_text=row[2],
            pii_type=PIIType(row[3]),
            source_document=row[4],
            context_snippet=row[5] or "",
            created_at=datetime.fromisoformat(row[6]),
        )

    def resolve_all_tokens(self, text: str) -> tuple[str, int, list[str]]:
        """Find and replace all tokens in *text* with their original values."""
        import re

        self._ensure_unlocked()

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
                original_text=row[2],
                pii_type=PIIType(row[3]),
                source_document=row[4],
                context_snippet=row[5] or "",
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
    # Export / Import  (plaintext JSON)
    # -----------------------------------------------------------------------

    def export_vault(self) -> str:
        """Export all tokens as a JSON string."""
        self._ensure_unlocked()
        tokens = self.list_tokens()
        data = {
            "version": 2,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tokens": [t.model_dump(mode="json") for t in tokens],
        }
        return json.dumps(data)

    def import_vault(self, export_json: str) -> dict:
        """Import tokens from an export JSON string.

        Returns dict with 'imported', 'skipped', 'errors' counts.
        """
        self._ensure_unlocked()

        data = json.loads(export_json)

        # Support both v1 (old encrypted envelope — not supported) and v2 (plaintext)
        if "tokens" in data:
            tokens_list = data["tokens"]
        else:
            raise ValueError("Unrecognised export format — missing 'tokens' key")

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
                with self._lock:
                    if self._token_string_exists(mapping.token_string):
                        skipped += 1
                        continue
                self.store_token(mapping)
                imported += 1
            except sqlite3.IntegrityError:
                skipped += 1
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
            self._is_unlocked = False


# Singleton vault instance
vault = TokenVault()
