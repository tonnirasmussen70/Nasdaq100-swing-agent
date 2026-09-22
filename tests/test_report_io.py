import json

from report_io import write_json_if_changed


def test_first_write_adds_timestamp(tmp_path):
    path = tmp_path / "report.json"
    written, changed = write_json_if_changed(path, {"value": 1})
    assert changed is True
    assert written["value"] == 1
    assert "generated_at" in written
    assert json.loads(path.read_text(encoding="utf-8"))["value"] == 1


def test_same_payload_does_not_rewrite_timestamp(tmp_path):
    path = tmp_path / "report.json"
    first, changed = write_json_if_changed(path, {"value": 1})
    assert changed is True
    original_text = path.read_text(encoding="utf-8")

    second, changed = write_json_if_changed(path, {"value": 1})
    assert changed is False
    assert second["generated_at"] == first["generated_at"]
    assert path.read_text(encoding="utf-8") == original_text


def test_recursive_volatile_fields_do_not_trigger_rewrite(tmp_path):
    path = tmp_path / "report.json"
    first_payload = {
        "profiles": {
            "challenger": {
                "new_signal": True,
                "resolved_trades": 1,
                "performance": {"closed_trades": 4},
            }
        }
    }
    second_payload = {
        "profiles": {
            "challenger": {
                "new_signal": False,
                "resolved_trades": 0,
                "performance": {"closed_trades": 4},
            }
        }
    }
    _, changed = write_json_if_changed(
        path,
        first_payload,
        volatile_keys={"generated_at", "new_signal", "resolved_trades"},
    )
    assert changed is True
    original_text = path.read_text(encoding="utf-8")

    _, changed = write_json_if_changed(
        path,
        second_payload,
        volatile_keys={"generated_at", "new_signal", "resolved_trades"},
    )
    assert changed is False
    assert path.read_text(encoding="utf-8") == original_text


def test_semantic_change_rewrites_report(tmp_path):
    path = tmp_path / "report.json"
    write_json_if_changed(path, {"performance": {"closed_trades": 4}})
    updated, changed = write_json_if_changed(path, {"performance": {"closed_trades": 5}})
    assert changed is True
    assert updated["performance"]["closed_trades"] == 5
