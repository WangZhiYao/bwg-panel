import json

from app.db import Database
from app import models


def make_db(tmp_path):
    return Database(str(tmp_path / "t.db"))


def test_server_crud(tmp_path):
    db = make_db(tmp_path)
    s = models.create_server(db, name="VPS-A", veid="9000001", api_key="k1")
    assert s["id"] == 1 and s["name"] == "VPS-A"

    assert models.get_server(db, 1)["veid"] == "9000001"
    assert models.get_server(db, 999) is None
    assert models.get_server_by_veid(db, "9000001")["id"] == 1

    updated = models.update_server(db, 1, name="VPS-A2")
    assert updated["name"] == "VPS-A2"

    assert models.delete_server(db, 1) is True
    assert models.delete_server(db, 1) is False
    db.close()


def test_update_profile_fields(tmp_path):
    db = make_db(tmp_path)
    models.create_server(db, name="A", veid="1", api_key="k")
    profile = {
        "node_location": "DC9",
        "os": "Debian 12",
        "vm_type": "kvm",
        "ip_addresses": json.dumps(["1.2.3.4"]),
        "plan_disk": "20 G",
        "plan_ram": "1.0 G",
        "plan_swap": "256 MB",
        "plan_monthly_data": 1024**4,
        "monthly_data_multiplier": 1.0,
        "data_next_reset": "2026-10-01T00:00:00+00:00",
    }
    s = models.update_server(db, 1, profile=profile)
    assert s["node_location"] == "DC9"
    assert s["plan_monthly_data"] == 1024**4
    db.close()


def test_settings_roundtrip(tmp_path):
    db = make_db(tmp_path)
    assert models.get_setting(db, "missing", "dft") == "dft"
    models.set_setting(db, "smtp", {"host": "smtp.x.com", "port": 465})
    models.set_setting(db, "threshold_warn", 0.8)
    models.set_setting(db, "threshold_warn", 0.9)  # 覆盖同键（UPSERT update 分支）
    assert models.get_setting(db, "smtp") == {"host": "smtp.x.com", "port": 465}
    assert models.get_setting(db, "threshold_warn") == 0.9
    db.close()


def test_log_op_writes_row_with_json_detail(tmp_path):
    db = make_db(tmp_path)
    server = models.create_server(db, name="S1", veid="9000001", api_key="k")
    op_id = models.log_op(
        db, server_id=server["id"], action="power.kill",
        result="ok", detail={"code": 0, "response": {}},
    )
    row = db.query_one("SELECT * FROM ops_log WHERE id=?", (op_id,))
    assert row["action"] == "power.kill"
    assert row["result"] == "ok"
    assert json.loads(row["detail"]) == {"code": 0, "response": {}}
    assert row["created_at"]
    db.close()


def test_log_op_detail_optional(tmp_path):
    db = make_db(tmp_path)
    op_id = models.log_op(db, server_id=None, action="snapshot.create", result="error")
    row = db.query_one("SELECT * FROM ops_log WHERE id=?", (op_id,))
    assert row["detail"] is None
    assert row["server_id"] is None
    db.close()
