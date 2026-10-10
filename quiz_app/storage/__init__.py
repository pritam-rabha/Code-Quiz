"""Storage layer: one JSON file per concern, behind a single Database object."""
from __future__ import annotations

from pathlib import Path

from ..constants import DEFAULT_SETTINGS
from .json_store import JsonStore, StorageError, StorageLock, list_document, object_document

__all__ = ["Database", "JsonStore", "StorageError", "StorageLock"]


class Database:
    """Aggregates the JSON stores. ``transaction()`` serialises multi-file updates."""

    def __init__(self, data_dir: Path | str, sample_questions_path: Path | str | None = None):
        self.data_dir = Path(data_dir)
        self.lock = StorageLock(self.data_dir / ".lock")

        def make(name, default, normalize, seed=None):
            return JsonStore(
                self.data_dir / name,
                default=default,
                normalize=normalize,
                lock=self.lock,
                seed_path=seed,
            )

        q_default, q_norm = list_document("questions")
        p_default, p_norm = list_document("participants")
        r_default, r_norm = list_document("results")
        a_default, a_norm = list_document("attempts")

        self.questions = make("questions.json", q_default, q_norm, sample_questions_path)
        self.participants = make("participants.json", p_default, p_norm)
        self.results = make("results.json", r_default, r_norm)
        self.attempts = make("attempts.json", a_default, a_norm)
        self.settings = make("settings.json", lambda: dict(DEFAULT_SETTINGS), object_document)
        self.admin = make("admin.json", dict, object_document)

    def transaction(self):
        return self.lock.hold()
