import json
import threading

import pytest

from quiz_app.storage import Database, StorageError
from quiz_app.storage.json_store import JsonStore, StorageLock, list_document


def make_store(tmp_path, name="items.json", key="items"):
    default, normalize = list_document(key)
    return JsonStore(tmp_path / name, default=default, normalize=normalize, lock=StorageLock(tmp_path / ".lock"))


def test_missing_file_is_created_from_default(tmp_path):
    store = make_store(tmp_path)
    assert store.read() == {"version": 1, "items": []}
    assert (tmp_path / "items.json").exists()


def test_write_then_read_round_trip_without_temp_files(tmp_path):
    store = make_store(tmp_path)
    store.write({"version": 1, "items": [{"id": "a", "name": "Zoë"}]})
    assert store.read()["items"][0]["name"] == "Zoë"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_corrupted_json_is_quarantined_and_replaced(tmp_path):
    path = tmp_path / "items.json"
    path.write_text("{ this is not json", encoding="utf-8")
    store = make_store(tmp_path)
    assert store.read() == {"version": 1, "items": []}
    backups = list(tmp_path.glob("items.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{ this is not json"
    assert json.loads(path.read_text(encoding="utf-8"))["items"] == []


def test_empty_file_is_treated_as_corrupted(tmp_path):
    (tmp_path / "items.json").write_text("", encoding="utf-8")
    assert make_store(tmp_path).read()["items"] == []
    assert len(list(tmp_path.glob("items.json.corrupt-*"))) == 1


def test_wrong_structure_is_treated_as_corrupted(tmp_path):
    (tmp_path / "items.json").write_text(json.dumps({"items": "not a list"}), encoding="utf-8")
    assert make_store(tmp_path).read()["items"] == []
    assert len(list(tmp_path.glob("items.json.corrupt-*"))) == 1


def test_invalid_utf8_is_treated_as_corrupted(tmp_path):
    (tmp_path / "items.json").write_bytes(b"\xff\xfe\x00bad")
    assert make_store(tmp_path).read()["items"] == []


def test_write_refuses_invalid_structure(tmp_path):
    store = make_store(tmp_path)
    store.write({"version": 1, "items": [1]})
    with pytest.raises(StorageError):
        store.write({"version": 1, "items": "oops"})
    assert store.read()["items"] == [1]


def test_failed_write_leaves_previous_data_intact(tmp_path):
    store = make_store(tmp_path)
    store.write({"version": 1, "items": ["keep"]})
    with pytest.raises(TypeError):
        store.write({"version": 1, "items": [object()]})
    assert store.read()["items"] == ["keep"]
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_update_returns_mutator_result_and_persists(tmp_path):
    store = make_store(tmp_path)
    count = store.update(lambda data: data["items"].append("x") or len(data["items"]))
    assert count == 1
    assert store.read()["items"] == ["x"]


def test_concurrent_updates_do_not_lose_writes(tmp_path):
    store = make_store(tmp_path)

    def worker():
        for _ in range(10):
            store.update(lambda data: data["items"].append(1))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store.read()["items"]) == 80


def test_database_seeds_questions_from_sample_file(db):
    questions = db.questions.read()["questions"]
    assert len(questions) >= 50
    assert {q["difficulty"] for q in questions} == {"easy", "medium", "hard"}


def test_database_without_sample_starts_empty(tmp_path):
    assert Database(tmp_path / "d").questions.read()["questions"] == []


def test_corrupted_questions_file_is_reseeded(tmp_path):
    from conftest import SAMPLE

    data_dir = tmp_path / "d"
    data_dir.mkdir()
    (data_dir / "questions.json").write_text("garbage", encoding="utf-8")
    database = Database(data_dir, SAMPLE)
    assert len(database.questions.read()["questions"]) >= 50
    assert list(data_dir.glob("questions.json.corrupt-*"))
