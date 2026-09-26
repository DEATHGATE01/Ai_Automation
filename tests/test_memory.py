from secops_agent.memory import MemoryStore


def test_records_and_recalls_by_overlap(tmp_path):
    store = MemoryStore(tmp_path / "memory.json")
    store.record("run-1", goal="triage critical findings on vpn edge", summary="escalated F-004")
    store.record("run-2", goal="open tickets for the database asset", summary="opened 2 tickets")

    hits = store.recall("critical findings on the vpn edge appliance", limit=1)
    assert len(hits) == 1
    assert hits[0]["run_id"] == "run-1"


def test_recall_is_empty_on_a_fresh_store(tmp_path):
    assert MemoryStore(tmp_path / "memory.json").recall("anything") == []


def test_survives_a_corrupt_file(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("{not json", encoding="utf-8")
    store = MemoryStore(path)
    assert store.recall("anything") == []
    store.record("run-9", goal="g", summary="s")
    assert store.recall("g")[0]["run_id"] == "run-9"
