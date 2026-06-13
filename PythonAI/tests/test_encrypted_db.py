"""
Tests for src.utils.encrypted_db — AES-256 encrypted SQLite database wrapper.

Covers:
- Key derivation (PBKDF2-SHA256)
- Fernet backend (file-level encryption)
- sqlcipher backend (when available)
- Connection lifecycle
- Database migration (plaintext → encrypted)
- Diagnostics / status reporting
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.encrypted_db import (
    SQLCIPHER_AVAILABLE,
    EncryptedDB,
    create_encrypted_db,
    derive_encryption_key,
    derive_fernet_key,
    derive_pragma_key,
    get_encryption_status,
    get_machine_id,
)


# ═══════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════


@pytest.fixture
def temp_db_path() -> Path:
    """Return a temporary path for an encrypted test database."""
    tmpdir = Path(tempfile.mkdtemp(prefix="forgeai_encrypted_test_"))
    yield tmpdir / "test_signals.db"
    # Cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def plaintext_db_path() -> Path:
    """Create a plaintext SQLite database for migration testing."""
    tmpdir = Path(tempfile.mkdtemp(prefix="forgeai_plaintext_test_"))
    db_path = tmpdir / "plaintext.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'hello'), (2, 'world')")
    conn.commit()
    conn.close()
    yield db_path
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════
# Key Derivation Tests
# ═══════════════════════════════════════════════


class TestKeyDerivation:
    """PBKDF2-SHA256 key derivation from machine ID."""

    def test_derive_encryption_key_returns_bytes(self):
        key, salt = derive_encryption_key(passphrase="test-passphrase")
        assert isinstance(key, bytes)
        assert len(key) == 32  # AES-256
        assert isinstance(salt, bytes)
        assert len(salt) == 32

    def test_derive_encryption_key_deterministic_same_passphrase(self):
        key1, salt1 = derive_encryption_key(passphrase="same-pass", salt=b"fixed-salt-test")
        key2, salt2 = derive_encryption_key(passphrase="same-pass", salt=b"fixed-salt-test")
        assert key1 == key2
        assert salt1 == salt2

    def test_derive_encryption_key_different_passphrase_different_key(self):
        key1, _ = derive_encryption_key(passphrase="passphrase-a", salt=b"fixed-salt-test")
        key2, _ = derive_encryption_key(passphrase="passphrase-b", salt=b"fixed-salt-test")
        assert key1 != key2

    def test_derived_fernet_key_is_valid_base64(self):
        fernet_key = derive_fernet_key(passphrase="test")
        assert isinstance(fernet_key, bytes)
        assert len(fernet_key) == 44  # 32 bytes base64-encoded = 44 chars
        # Should be valid Fernet key format (no trailing newline, URL-safe base64)
        from cryptography.fernet import Fernet
        f = Fernet(fernet_key)
        assert f is not None

    def test_pragma_key_hex_format(self):
        pragma_key = derive_pragma_key(passphrase="test")
        assert isinstance(pragma_key, str)
        assert len(pragma_key) == 64  # 32 bytes = 64 hex chars
        int(pragma_key, 16)  # Should be valid hex

    def test_machine_id_stable(self):
        id1 = get_machine_id()
        id2 = get_machine_id()
        assert id1 == id2
        assert len(id1) > 0

    def test_key_iterations_default(self):
        import time
        start = time.time()
        derive_encryption_key(passphrase="quick-test", salt=b"quick-salt-test", iterations=1000)
        elapsed = time.time() - start
        # Should be fast with only 1000 iterations
        assert elapsed < 2.0


# ═══════════════════════════════════════════════
# Fernet Backend Tests (default, no sqlcipher)
# ═══════════════════════════════════════════════


class TestFernetBackend:
    """File-level encryption via Fernet + PBKDF2."""

    def test_create_encrypted_db(self, temp_db_path: Path):
        """EncryptedDB should create and open without error."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        conn = db.connect()
        assert conn is not None
        conn.execute("CREATE TABLE foo (x INTEGER)")
        conn.execute("INSERT INTO foo VALUES (42)")
        conn.commit()
        conn.close()
        db.close()

    def test_encrypted_blob_created(self, temp_db_path: Path):
        """A Fernet encrypted blob should exist after close()."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        conn = db.connect()
        conn.execute("CREATE TABLE foo (x INTEGER)")
        conn.execute("INSERT INTO foo VALUES (1)")
        conn.commit()
        conn.close()
        db.close()

        # The encrypted blob should exist and not be a plain SQLite file
        encrypted_path = temp_db_path.with_suffix(temp_db_path.suffix + ".encrypted")
        assert encrypted_path.exists(), "Encrypted blob should exist after close"
        blob = encrypted_path.read_bytes()
        assert not blob.startswith(b"SQLite format 3\x00"), "Blob should not be plaintext SQLite"

    def test_read_and_write_cycle(self, temp_db_path: Path):
        """Write data, close, reopen, read — data should persist."""
        key = "test-key-1234"
        # First session: write
        db1 = EncryptedDB(temp_db_path, encryption_key=key, prefer_sqlcipher=False)
        conn1 = db1.connect()
        conn1.execute("CREATE TABLE test (k TEXT PRIMARY KEY, v INTEGER)")
        conn1.execute("INSERT INTO test VALUES ('a', 10), ('b', 20)")
        conn1.commit()
        conn1.close()
        db1.close()

        # Second session: read
        db2 = EncryptedDB(temp_db_path, encryption_key=key, prefer_sqlcipher=False)
        conn2 = db2.connect()
        rows = conn2.execute("SELECT * FROM test ORDER BY k").fetchall()
        assert rows == [("a", 10), ("b", 20)]
        conn2.close()
        db2.close()

    def test_wrong_key_fails(self, temp_db_path: Path):
        """Opening with a different key should fail to decrypt."""
        db1 = EncryptedDB(temp_db_path, encryption_key="correct-key", prefer_sqlcipher=False)
        conn1 = db1.connect()
        conn1.execute("CREATE TABLE t (x INTEGER)")
        conn1.execute("INSERT INTO t VALUES (1)")
        conn1.commit()
        conn1.close()
        db1.close()

        # Reopen with wrong key
        db2 = EncryptedDB(temp_db_path, encryption_key="wrong-key", prefer_sqlcipher=False)
        with pytest.raises(Exception):
            conn2 = db2.connect()
            conn2.execute("SELECT * FROM t")
            conn2.close()
            db2.close()

    def test_multiple_connections(self, temp_db_path: Path):
        """Multiple connections to the same encrypted DB should work."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        conn1 = db.connect()
        conn1.execute("CREATE TABLE test (x INTEGER)")
        conn1.execute("INSERT INTO test VALUES (100)")
        conn1.commit()

        conn2 = db.connect()
        rows = conn2.execute("SELECT * FROM test").fetchall()
        assert rows == [(100,)]
        conn1.close()
        conn2.close()
        db.close()

    def test_context_manager(self, temp_db_path: Path):
        """EncryptedDB should work as a context manager."""
        with EncryptedDB(temp_db_path, prefer_sqlcipher=False) as db:
            conn = db.connect()
            conn.execute("CREATE TABLE ctx (v TEXT)")
            conn.execute("INSERT INTO ctx VALUES ('works')")
            conn.commit()
            conn.close()

        # After context exit, DB should be re-encrypted
        encrypted_path = temp_db_path.with_suffix(temp_db_path.suffix + ".encrypted")
        assert encrypted_path.exists()

    def test_auto_migrate_plaintext(self, temp_db_path: Path, plaintext_db_path: Path):
        """Auto-migrate should detect and encrypt existing plaintext DB."""
        # Replace temp_db_path with a copy of the plaintext DB
        import shutil
        shutil.copy(plaintext_db_path, temp_db_path)

        # Create EncryptedDB with auto_migrate — should migrate the plaintext DB
        db = create_encrypted_db(temp_db_path, prefer_sqlcipher=False, auto_migrate=True)
        conn = db.connect()
        rows = conn.execute("SELECT * FROM test ORDER BY id").fetchall()
        assert rows == [(1, "hello"), (2, "world")]
        conn.close()
        db.close()

        # Original plaintext should be replaced by encrypted blob
        assert not temp_db_path.exists(), "Plaintext should be removed after migration"
        encrypted_path = temp_db_path.with_suffix(temp_db_path.suffix + ".encrypted")
        assert encrypted_path.exists(), "Encrypted blob should exist after migration"

    def test_status_report(self, temp_db_path: Path):
        """get_encryption_status should report correct info."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        conn = db.connect()
        conn.execute("CREATE TABLE s (x INTEGER)")
        conn.commit()
        conn.close()
        db.close()

        status = get_encryption_status(temp_db_path)
        assert status["exists"] is False  # Plaintext DB removed after encryption
        assert status["encrypted_blob_exists"] is True
        assert status["sqlcipher_available"] == SQLCIPHER_AVAILABLE
        assert status["key_derivation"] == "PBKDF2-SHA256"

    def test_temp_file_cleaned_on_close(self, temp_db_path: Path):
        """Temporary decrypted file should be securely deleted on close."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        conn = db.connect()
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.commit()
        temp_path = db._temp_db_path
        assert temp_path is not None and temp_path.exists()
        conn.close()
        db.close()
        assert temp_path is not None and not temp_path.exists(), "Temp file should be deleted"


# ═══════════════════════════════════════════════
# sqlcipher Backend Tests (if available)
# ═══════════════════════════════════════════════

@pytest.mark.skipif(not SQLCIPHER_AVAILABLE, reason="sqlcipher not installed")
class TestSqlcipherBackend:
    """Full DB encryption via pysqlcipher3 / rotki-pysqlcipher3."""

    def test_create_sqlcipher_db(self, temp_db_path: Path):
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=True)
        conn = db.connect()
        assert conn is not None
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        rows = conn.execute("SELECT * FROM t").fetchall()
        assert rows == [(42,)]
        conn.close()
        db.close()

    def test_sqlcipher_file_encrypted(self, temp_db_path: Path):
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=True)
        conn = db.connect()
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        db.close()

        # The file should exist but NOT be a plain SQLite file
        # (sqlcipher encrypts the entire file, so the header is different)
        assert temp_db_path.exists()
        header = temp_db_path.read_bytes()[:16]
        assert header != b"SQLite format 3\x00", "sqlcipher file should not have plaintext SQLite header"

    def test_sqlcipher_read_after_reopen(self, temp_db_path: Path):
        key = "test-sqlcipher-key"
        db1 = EncryptedDB(temp_db_path, encryption_key=key, prefer_sqlcipher=True)
        conn1 = db1.connect()
        conn1.execute("CREATE TABLE t (k TEXT, v INTEGER)")
        conn1.execute("INSERT INTO t VALUES ('a', 1), ('b', 2)")
        conn1.commit()
        conn1.close()
        db1.close()

        db2 = EncryptedDB(temp_db_path, encryption_key=key, prefer_sqlcipher=True)
        conn2 = db2.connect()
        rows = conn2.execute("SELECT * FROM t ORDER BY k").fetchall()
        assert rows == [("a", 1), ("b", 2)]
        conn2.close()
        db2.close()

    def test_sqlcipher_wrong_key_fails(self, temp_db_path: Path):
        db1 = EncryptedDB(temp_db_path, encryption_key="correct", prefer_sqlcipher=True)
        conn1 = db1.connect()
        conn1.execute("CREATE TABLE t (x INTEGER)")
        conn1.execute("INSERT INTO t VALUES (1)")
        conn1.commit()
        conn1.close()
        db1.close()

        db2 = EncryptedDB(temp_db_path, encryption_key="wrong", prefer_sqlcipher=True)
        with pytest.raises(RuntimeError, match="decryption failed"):
            conn2 = db2.connect()

    def test_migrate_plaintext_to_sqlcipher(self, temp_db_path: Path, plaintext_db_path: Path):
        import shutil
        shutil.copy(plaintext_db_path, temp_db_path)

        db = EncryptedDB(temp_db_path, encryption_key="migration-key", prefer_sqlcipher=True)
        result = db.migrate_from_plaintext(temp_db_path)
        assert result is True

        # Verify data is readable with the new key
        db2 = EncryptedDB(temp_db_path, encryption_key="migration-key", prefer_sqlcipher=True)
        conn = db2.connect()
        rows = conn.execute("SELECT * FROM test ORDER BY id").fetchall()
        assert rows == [(1, "hello"), (2, "world")]
        conn.close()
        db2.close()


# ═══════════════════════════════════════════════
# Integration: CaptureEngine with EncryptedDB
# ═══════════════════════════════════════════════


class TestCaptureEngineEncryption:
    """Verify CaptureEngine works correctly with EncryptedDB."""

    def test_capture_engine_uses_encrypted_db(self, temp_db_path: Path):
        """CaptureEngine should use EncryptedDB and work transparently."""
        from src.learning.capture_engine import CaptureEngine
        engine = CaptureEngine(db_path=temp_db_path, prefer_sqlcipher=False)
        assert engine._db is not None
        assert engine._db.backend == "fernet"

        # Basic capture operations should work
        signal_id = engine.capture_accept(
            suggestion="print('hello')",
            file_path="test.py",
            line_number=1,
            language="python",
        )
        assert signal_id is not None

        stats = engine.get_statistics()
        assert stats["total_sessions"] > 0
        assert stats["signals_by_type"].get("accept", 0) > 0

    def test_capture_engine_data_persists_across_sessions(self, temp_db_path: Path):
        """Data written in one session should be readable in another."""
        from src.learning.capture_engine import CaptureEngine

        # Session 1: write data
        engine1 = CaptureEngine(db_path=temp_db_path, project_name="test-proj", prefer_sqlcipher=False)
        engine1.capture_accept(
            suggestion="def foo(): pass",
            file_path="test.py",
            line_number=1,
            language="python",
        )
        engine1.capture_reject(
            suggestion="bad code",
            file_path="bad.py",
            line_number=1,
            language="python",
        )

        # Force close the encrypted DB to flush data to encrypted blob
        engine1._db.close()

        # Session 2: read data back
        engine2 = CaptureEngine(db_path=temp_db_path, project_name="test-proj", prefer_sqlcipher=False)
        stats = engine2.get_statistics()
        assert stats["total_sessions"] >= 1
        assert stats["signals_by_type"].get("accept", 0) >= 1
        assert stats["signals_by_type"].get("reject", 0) >= 1

    def test_capture_engine_migration(self, temp_db_path: Path, plaintext_db_path: Path):
        """CaptureEngine should auto-migrate existing plaintext DBs."""
        import shutil
        shutil.copy(plaintext_db_path, temp_db_path)

        from src.learning.capture_engine import CaptureEngine
        engine = CaptureEngine(db_path=temp_db_path, prefer_sqlcipher=False)

        # After init, the plaintext should be migrated
        encrypted_path = temp_db_path.with_suffix(temp_db_path.suffix + ".encrypted")
        assert encrypted_path.exists()
        assert not temp_db_path.exists(), "Plaintext should be removed after migration"


# ═══════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_encrypted_db_closed_twice(self, temp_db_path: Path):
        """Calling close() twice should not raise."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        db.close()
        db.close()  # Should be no-op

    def test_connect_after_close_raises(self, temp_db_path: Path):
        """Connecting after close() should raise RuntimeError."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        db.close()
        with pytest.raises(RuntimeError, match="closed"):
            db.connect()

    def test_new_database_creates_empty(self, temp_db_path: Path):
        """Creating an EncryptedDB for a non-existent path should work."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        conn = db.connect()
        assert conn is not None
        conn.close()
        db.close()

    def test_nonexistent_path_auto_creates(self, temp_db_path: Path):
        """Parent directories should be auto-created."""
        nested_path = temp_db_path.parent / "deep" / "nested" / "db.db"
        db = EncryptedDB(nested_path, prefer_sqlcipher=False)
        assert nested_path.parent.exists(), "Parent dirs should be auto-created"
        conn = db.connect()
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        db.close()

    def test_backend_name_property(self, temp_db_path: Path):
        """backend_name should return a descriptive string."""
        db = EncryptedDB(temp_db_path, prefer_sqlcipher=False)
        name = db.backend_name
        assert "fernet" in name or "sqlcipher" in name
        db.close()

    def test_status_sqlcipher_available_property(self):
        """SQLCIPHER_AVAILABLE should be a bool."""
        assert isinstance(SQLCIPHER_AVAILABLE, bool)

    def test_multiple_encrypted_dbs_independent(self):
        """Two independent EncryptedDB instances should not interfere."""
        tmpdir = Path(tempfile.mkdtemp(prefix="forgeai_multi_db_"))
        try:
            db1_path = tmpdir / "db1.db"
            db2_path = tmpdir / "db2.db"

            db1 = EncryptedDB(db1_path, prefer_sqlcipher=False)
            conn1 = db1.connect()
            conn1.execute("CREATE TABLE t (v TEXT)")
            conn1.execute("INSERT INTO t VALUES ('db1-data')")
            conn1.commit()
            conn1.close()
            db1.close()

            db2 = EncryptedDB(db2_path, prefer_sqlcipher=False)
            conn2 = db2.connect()
            conn2.execute("CREATE TABLE t (v TEXT)")
            conn2.execute("INSERT INTO t VALUES ('db2-data')")
            conn2.commit()
            conn2.close()
            db2.close()

            # Reopen both and verify isolation
            db1r = EncryptedDB(db1_path, prefer_sqlcipher=False)
            c1 = db1r.connect()
            assert c1.execute("SELECT v FROM t").fetchone()[0] == "db1-data"
            c1.close()
            db1r.close()

            db2r = EncryptedDB(db2_path, prefer_sqlcipher=False)
            c2 = db2r.connect()
            assert c2.execute("SELECT v FROM t").fetchone()[0] == "db2-data"
            c2.close()
            db2r.close()
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
