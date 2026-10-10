"""Safe JSON file storage.

Features:
* atomic writes (temp file + fsync + os.replace) so readers never see partial data
* a re-entrant, cross-process lock for read-modify-write transactions
* missing files are created from a default (or a seed file)
* corrupted files are moved aside (``*.corrupt-<timestamp>``) and replaced
"""
from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

try:  # POSIX only; Windows falls back to the in-process lock.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

log = logging.getLogger(__name__)


class StorageError(RuntimeError):
    """Raised when a storage operation fails in an unrecoverable way."""


class StorageLock:
    """Re-entrant lock: a thread lock plus an advisory file lock across processes."""

    def __init__(self, lock_path: Path | str):
        self._path = Path(lock_path)
        self._rlock = threading.RLock()
        self._depth = 0
        self._handle = None

    @contextmanager
    def hold(self):
        with self._rlock:
            if self._depth == 0 and fcntl is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                self._handle = open(self._path, "a+")
                fcntl.flock(self._handle, fcntl.LOCK_EX)
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0 and self._handle is not None:
                    try:
                        fcntl.flock(self._handle, fcntl.LOCK_UN)
                    finally:
                        self._handle.close()
                        self._handle = None


def list_document(key: str) -> tuple[Callable[[], dict], Callable[[Any], dict]]:
    """Return (default_factory, normalizer) for a ``{"version": 1, key: [...]}`` file."""

    def default() -> dict:
        return {"version": 1, key: []}

    def normalize(data: Any) -> dict:
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value must be an object")
        if not isinstance(data.get(key), list):
            raise ValueError(f"'{key}' must be a list")
        data.setdefault("version", 1)
        return data

    return default, normalize


def object_document(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value must be an object")
    return data


class JsonStore:
    def __init__(
        self,
        path: Path | str,
        *,
        default: Callable[[], dict],
        normalize: Callable[[Any], dict],
        lock: StorageLock,
        seed_path: Path | str | None = None,
    ):
        self.path = Path(path)
        self._default = default
        self._normalize = normalize
        self._lock = lock
        self._seed_path = Path(seed_path) if seed_path else None

    # ------------------------------------------------------------------ read
    def read(self) -> dict:
        """Return a fresh copy of the stored document."""
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return self._create_initial()
        except OSError as exc:
            raise StorageError(f"Cannot read {self.path.name}: {exc}") from exc
        try:
            return self._normalize(json.loads(raw.decode("utf-8")))
        except (ValueError, TypeError) as exc:
            log.error("Corrupted data file %s: %s", self.path.name, exc)
            return self._recover()

    # ----------------------------------------------------------------- write
    def write(self, data: dict) -> None:
        with self._lock.hold():
            try:
                clean = self._normalize(copy.deepcopy(data))
            except (ValueError, TypeError) as exc:
                raise StorageError(f"Refusing to write invalid {self.path.name}: {exc}") from exc
            self._atomic_write(clean)

    def update(self, mutator: Callable[[dict], Any]) -> Any:
        """Read, mutate in place and write back under the lock; returns mutator's result."""
        with self._lock.hold():
            data = self.read()
            result = mutator(data)
            self.write(data)
            return result

    # -------------------------------------------------------------- internals
    def _atomic_write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _build_initial(self) -> dict:
        if self._seed_path and self._seed_path.exists():
            try:
                return self._normalize(json.loads(self._seed_path.read_text(encoding="utf-8")))
            except (ValueError, OSError) as exc:
                log.error("Seed file %s is unusable: %s", self._seed_path, exc)
        return self._normalize(self._default())

    def _create_initial(self) -> dict:
        with self._lock.hold():
            if self.path.exists():  # another process created it meanwhile
                return self.read()
            data = self._build_initial()
            self._atomic_write(data)
            log.info("Created %s", self.path.name)
            return data

    def _recover(self) -> dict:
        with self._lock.hold():
            try:  # another process may already have repaired the file
                return self._normalize(json.loads(self.path.read_bytes().decode("utf-8")))
            except FileNotFoundError:
                return self._create_initial()
            except (ValueError, TypeError, OSError):
                pass
            stamp = time.strftime("%Y%m%d%H%M%S")
            backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}-{os.getpid()}")
            try:
                os.replace(self.path, backup)
                log.error("Moved corrupted file to %s", backup.name)
            except OSError as exc:
                raise StorageError(f"Cannot quarantine {self.path.name}: {exc}") from exc
            data = self._build_initial()
            self._atomic_write(data)
            return data
