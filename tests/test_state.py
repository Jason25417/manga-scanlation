from manga_scanlation.state import DONE, FAILED, StateStore


def test_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.update("book-a", status=DONE, pages_src=10, pages_out=10)
    store.save()

    reloaded = StateStore(path)
    record = reloaded.get("book-a")
    assert record.status == DONE
    assert record.pages_src == 10
    assert record.updated


def test_missing_state_file_starts_empty(tmp_path):
    store = StateStore(tmp_path / "absent.json")
    assert store.names() == []
    assert store.get("nothing").status == "pending"


def test_corrupt_state_file_is_ignored(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    store = StateStore(path)
    assert store.names() == []


def test_unknown_field_is_rejected(tmp_path):
    store = StateStore(tmp_path / "state.json")
    try:
        store.update("book", nonexistent_field=1)
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_failure_is_recorded(tmp_path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.update("book-b", status=FAILED, error="engine exit code 1")
    store.save()
    assert StateStore(path).get("book-b").error == "engine exit code 1"
