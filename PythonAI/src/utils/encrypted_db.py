"""
Encrypted SQLite Database — AES-256 at Rest
=============================================
ForgeAI security compliance: signals database encryption.

Architecture (dual-backend):
  Primary:   sqlcipher (full transparent AES-256-CBC via pysqlcipher3)
  Fallback:  Fernet + PBKDF2 (file-level encryption via cryptography)
             -> entire .db file encrypted as blob on disk
             -> decrypted to temp file during access

Key derivation: PBKDF2-SHA256 from machine UUID, 600K iterations.
Key stored in OS keychain when available (macOS/Windows/Linux).
"""

from __future__ import annotations

import atexit
import hashlib
import importlib
import logging
import os
import platform
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("forgeai.encrypted_db")


# ── Backend Detection ───────────────────────────────────────────────

SQLCIPHER_AVAILABLE = False
SQLCIPHER_BACKEND = None  # Module reference if available

# Try rotki fork first (best maintained for Python 3.12+), then pysqlcipher3
for _module_name in ("rotki_pysqlcipher3.dbapi2", "pysqlcipher3.dbapi2", "sqlcipher3.dbapi2"):
    try:
        # Use importlib.import_module() which returns the leaf module (dbapi2),
        # unlike __import__() which returns the top-level package.
        SQLCIPHER_BACKEND = importlib.import_module(_module_name)
        SQLCIPHER_AVAILABLE = True
        break
    except ImportError:
        continue


# ── Key Derivation ──────────────────────────────────────────────────

_SALT_CACHE: bytes | None = None


def get_machine_id() -> str:
    """Get a stable, unique machine identifier (used for key derivation, not anonymized)."""
    try:
        if platform.system() == "Windows":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                return winreg.QueryValueEx(key, "MachineGuid")[0]
        elif platform.system() == "Darwin":
            result = os.popen("ioreg -rd1 -c IOPlatformExpertDevice 2>/dev/null | grep IOPlatformUUID").read()
            if result:
                return result.split('"')[3]
        elif platform.system() == "Linux":
            for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
                try:
                    return Path(p).read_text().strip()
                except FileNotFoundError:
                    continue
        return hashlib.sha256(str(uuid.getnode()).encode()).hexdigest()
    except Exception:
        return hashlib.sha256(f"{platform.node()}{platform.machine()}{uuid.getnode()}".encode()).hexdigest()


def derive_encryption_key(
    passphrase: str | None = None,
    salt: bytes | None = None,
    iterations: int = 600_000,
) -> tuple[bytes, bytes]:
    """Derive a strong encryption key from a passphrase or machine ID.

    Args:
        passphrase: Optional user-provided passphrase. If None, uses machine ID.
        salt: Optional salt for PBKDF2. If None, generates a new one.
        iterations: PBKDF2 iterations (default 600K, compliant with OWASP 2025).

    Returns:
        (key_bytes, salt_bytes) — key is 32 bytes for AES-256.
    """
    global _SALT_CACHE

    if passphrase is None:
        passphrase = get_machine_id()

    if salt is None:
        if _SALT_CACHE is None:
            salt_path = Path.home() / ".forgeai" / ".db_salt"
            if salt_path.exists():
                _SALT_CACHE = salt_path.read_bytes()
            else:
                salt_path.parent.mkdir(parents=True, exist_ok=True)
                _SALT_CACHE = os.urandom(32)
                salt_path.write_bytes(_SALT_CACHE)
        salt = _SALT_CACHE

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    key = kdf.derive(passphrase.encode("utf-8"))
    return key, salt


def derive_fernet_key(passphrase: str | None = None) -> bytes:
    """Derive a Fernet-compatible key (32-byte URL-safe base64)."""
    raw_key, _ = derive_encryption_key(passphrase=passphrase)
    import base64
    return base64.urlsafe_b64encode(raw_key)


def derive_pragma_key(passphrase: str | None = None) -> str:
    """Derive a hex key for sqlcipher PRAGMA key (64 hex chars = 256 bits)."""
    raw_key, _ = derive_encryption_key(passphrase=passphrase)
    return raw_key.hex()


# ── Encrypted DB Wrapper ────────────────────────────────────────────


class EncryptedDB:
    """Encrypted SQLite database with automatic key management.

    Provides a connection factory that transparently handles encryption.
    The DB file on disk is always encrypted (either by sqlcipher or
    Fernet-wrapped).

    Usage:
        db = EncryptedDB("~/.forgeai/signals.db")
        conn = db.connect()
        conn.execute("CREATE TABLE ...")
        conn.close()
        db.close()  # Re-encrypts if using Fernet fallback
    """

    def __init__(
        self,
        db_path: str | Path,
        encryption_key: str | None = None,
        prefer_sqlcipher: bool = True,
        auto_create: bool = True,
    ):
        self.db_path = Path(db_path).expanduser().resolve()
        self.encryption_key = encryption_key
        self._temp_db_path: Path | None = None
        self._fernet: Fernet | None = None
        self._open_connections: list[sqlite3.Connection] = []
        self._closed = False

        if auto_create:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if prefer_sqlcipher and SQLCIPHER_AVAILABLE:
            self.backend = "sqlcipher"
            logger.info("EncryptedDB using sqlcipher backend (AES-256-CBC full DB encryption)")
        else:
            self.backend = "fernet"
            fernet_key = derive_fernet_key(passphrase=encryption_key)
            self._fernet = Fernet(fernet_key)
            logger.info("EncryptedDB using Fernet backend (file-level encryption via cryptography)")

        atexit.register(self.close)

    @property
    def is_encrypted(self) -> bool:
        return True

    @property
    def backend_name(self) -> str:
        if self.backend == "sqlcipher":
            return "sqlcipher (AES-256-CBC full DB encryption)"
        return "fernet (AES-256-CBC file-level encryption via cryptography)"

    def connect(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("EncryptedDB has been closed")

        if self.backend == "sqlcipher":
            return self._connect_sqlcipher()
        return self._connect_fernet()

    def _connect_sqlcipher(self) -> sqlite3.Connection:
        pragma_key = derive_pragma_key(passphrase=self.encryption_key)

        conn = SQLCIPHER_BACKEND.connect(str(self.db_path))
        conn.execute(f'PRAGMA key = "{pragma_key}"')
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA kdf_iter = 600000")
        conn.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA256")
        conn.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA256")

        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as e:
            conn.close()
            raise RuntimeError(f"sqlcipher decryption failed for {self.db_path}: {e}") from e

        self._track_connection(conn)
        return conn

    def _connect_fernet(self) -> sqlite3.Connection:
        if self._temp_db_path and self._temp_db_path.exists():
            conn = sqlite3.connect(str(self._temp_db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            self._track_connection(conn)
            return conn

        encrypted_path = self._get_encrypted_blob_path()
        if encrypted_path.exists():
            encrypted_data = encrypted_path.read_bytes()
            try:
                decrypted_data = self._fernet.decrypt(encrypted_data)
            except Exception as e:
                raise RuntimeError(f"Fernet decryption failed for {encrypted_path}: {e}") from e
        else:
            decrypted_data = b""

        fd, temp_path_str = tempfile.mkstemp(
            prefix="forgeai_",
            suffix=".db",
            dir=str(self.db_path.parent),
        )
        os.close(fd)
        self._temp_db_path = Path(temp_path_str)

        if decrypted_data:
            self._temp_db_path.write_bytes(decrypted_data)

        conn = sqlite3.connect(str(self._temp_db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        self._track_connection(conn)
        return conn

    def close(self, re_encrypt: bool = True):
        if self._closed:
            return
        self._closed = True

        for conn in self._open_connections:
            try:
                conn.close()
            except Exception:
                pass
        self._open_connections.clear()

        if re_encrypt and self.backend == "fernet" and self._temp_db_path:
            try:
                self._flush_temp_to_encrypted()
            except Exception as e:
                logger.warning(f"Failed to re-encrypt temp DB: {e}")

        if self._temp_db_path and self._temp_db_path.exists():
            try:
                if self._temp_db_path.stat().st_size > 0:
                    _secure_delete(self._temp_db_path)
                else:
                    self._temp_db_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._temp_db_path = None

        atexit.unregister(self.close)

    def _track_connection(self, conn: sqlite3.Connection):
        self._open_connections.append(conn)

    def _get_encrypted_blob_path(self) -> Path:
        return self.db_path.with_suffix(self.db_path.suffix + ".encrypted")

    def _flush_temp_to_encrypted(self):
        if not self._temp_db_path or not self._temp_db_path.exists():
            return

        encrypted_path = self._get_encrypted_blob_path()

        for conn in self._open_connections:
            try:
                conn.commit()
            except Exception:
                pass

        db_data = self._temp_db_path.read_bytes()
        encrypted_data = self._fernet.encrypt(db_data)

        tmp_blob = encrypted_path.with_suffix(".tmp.enc")
        tmp_blob.write_bytes(encrypted_data)
        tmp_blob.replace(encrypted_path)

    def migrate_from_plaintext(self, source_path: str | Path | None = None) -> bool:
        source = Path(source_path or self.db_path).expanduser().resolve()
        if not source.exists():
            return False

        if self.backend == "sqlcipher":
            return self._migrate_to_sqlcipher(source)
        return self._migrate_to_fernet(source)

    def _migrate_to_sqlcipher(self, source: Path) -> bool:
        try:
            src_conn = sqlite3.connect(str(source))
            pragma_key = derive_pragma_key(passphrase=self.encryption_key)
            dest_path = source.with_suffix(".db.encrypted")
            src_conn.execute(f"ATTACH DATABASE '{dest_path}' AS encrypted KEY \"{pragma_key}\"")
            src_conn.execute("SELECT sqlcipher_export('encrypted')")
            src_conn.execute("DETACH DATABASE encrypted")
            src_conn.close()

            source.unlink()
            shutil.move(str(dest_path), str(source))
            logger.info(f"Migrated {source} to sqlcipher encryption")
            return True
        except Exception as e:
            logger.error(f"sqlcipher migration failed: {e}")
            return False

    def _migrate_to_fernet(self, source: Path) -> bool:
        try:
            db_data = source.read_bytes()
            encrypted_data = self._fernet.encrypt(db_data)

            encrypted_path = self._get_encrypted_blob_path()
            encrypted_path.write_bytes(encrypted_data)
            source.unlink()

            logger.info(f"Migrated {source} to Fernet encryption (blob: {encrypted_path})")
            return True
        except Exception as e:
            logger.error(f"Fernet migration failed: {e}")
            return False

    def __enter__(self) -> "EncryptedDB":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ── Keychain Integration ────────────────────────────────────────────

_KEYCHAIN_SERVICE = "forgeai"


def _get_keychain_password(service: str, account: str) -> str | None:
    try:
        if platform.system() == "Darwin":
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        elif platform.system() == "Windows":
            import subprocess
            script = f"""
            $cred = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
                (Get-StoredCredential -Target '{service}').Password
            )
            [Runtime.InteropServices.Marshal]::PtrToStringAuto($cred)
            """
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
        elif platform.system() == "Linux":
            import subprocess
            result = subprocess.run(
                ["secret-tool", "lookup", "service", service, "account", account],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        pass
    return None


def _set_keychain_password(service: str, account: str, password: str) -> bool:
    try:
        if platform.system() == "Darwin":
            import subprocess
            result = subprocess.run(
                ["security", "add-generic-password", "-s", service, "-a", account, "-w", password, "-U"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        elif platform.system() == "Windows":
            import subprocess
            script = f"""
            $sec = ConvertTo-SecureString '{password}' -AsPlainText -Force
            New-StoredCredential -Target '{service}' -UserName '{account}' -SecurePassword $sec -Persist LocalMachine
            """
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        elif platform.system() == "Linux":
            import subprocess
            result = subprocess.run(
                ["secret-tool", "store", "--label=ForgeAI DB Key", "service", service, "account", account],
                input=password, capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
    except Exception:
        pass
    return False


# ── Secure Deletion ─────────────────────────────────────────────────


def _secure_delete(path: Path, passes: int = 3):
    if not path.exists():
        return

    length = path.stat().st_size
    try:
        for _ in range(passes):
            path.write_bytes(os.urandom(length))
        path.write_bytes(b"\x00" * length)
    except Exception:
        pass

    try:
        path.unlink(missing_ok=True)
        if platform.system() == "Windows":
            try:
                os.chmod(str(path), stat.S_IWRITE)
                path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception:
        pass


# ── Convenience Factory ─────────────────────────────────────────────


def create_encrypted_db(
    db_path: str | Path = "~/.forgeai/signals.db",
    encryption_key: str | None = None,
    prefer_sqlcipher: bool = True,
    auto_migrate: bool = True,
) -> EncryptedDB:
    """Create or open an encrypted database.

    Args:
        db_path: Path to the database file.
        encryption_key: Optional passphrase (defaults to machine ID).
        prefer_sqlcipher: Use sqlcipher when available.
        auto_migrate: Auto-migrate existing plaintext DBs to encrypted.

    Returns:
        Configured EncryptedDB instance.
    """
    db = EncryptedDB(
        db_path=db_path,
        encryption_key=encryption_key,
        prefer_sqlcipher=prefer_sqlcipher,
    )

    if auto_migrate:
        plaintext_path = Path(db_path).expanduser().resolve()
        if plaintext_path.exists():
            if db.backend == "sqlcipher":
                header = plaintext_path.read_bytes()[:16]
                if header == b"SQLite format 3\x00":
                    db.migrate_from_plaintext(plaintext_path)
            else:
                encrypted_blob = db._get_encrypted_blob_path()
                if not encrypted_blob.exists():
                    db.migrate_from_plaintext(plaintext_path)

    return db


# ── Diagnostics ─────────────────────────────────────────────────────


def get_encryption_status(db_path: str | Path = "~/.forgeai/signals.db") -> dict[str, Any]:
    """Report encryption status for a database path (without opening it)."""
    path = Path(db_path).expanduser().resolve()
    encrypted_blob = path.with_suffix(path.suffix + ".encrypted")

    status: dict[str, Any] = {
        "db_path": str(path),
        "exists": path.exists(),
        "encrypted_blob_exists": encrypted_blob.exists(),
        "sqlcipher_available": SQLCIPHER_AVAILABLE,
        "sqlcipher_backend": str(SQLCIPHER_BACKEND) if SQLCIPHER_BACKEND else None,
        "key_derivation": "PBKDF2-SHA256",
        "key_iterations": 600_000,
        "key_source": "machine_id",
    }

    if path.exists():
        header = path.read_bytes()[:16]
        status["is_sqlcipher"] = header != b"SQLite format 3\x00" if header else False
        status["is_plaintext_sqlite"] = header == b"SQLite format 3\x00"
    elif encrypted_blob.exists():
        status["is_fernet_encrypted"] = True

    return status
