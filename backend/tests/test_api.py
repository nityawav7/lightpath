from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_snapshot_shape(client: TestClient) -> None:
    data = client.get("/api/snapshot").json()
    assert len(data["nodes"]) == 14
    assert len(data["links"]) == 24
    assert all(len(link["channels"]) == data["num_channels"] for link in data["links"])


def test_service_lifecycle(client: TestClient) -> None:
    r = client.post(
        "/api/services",
        json={"src": "del", "dst": "bom", "rate_gbps": 400, "protection": "1+1"},
    )
    assert r.status_code == 201, r.text
    svc = r.json()
    assert svc["working"] and svc["protection_leg"]
    assert svc["modulation"].startswith("DP-16QAM")

    assert client.get(f"/api/services/{svc['id']}").status_code == 200
    assert client.delete(f"/api/services/{svc['id']}").status_code == 204
    assert client.get(f"/api/services/{svc['id']}").status_code == 404


def test_blocked_request_returns_409_with_reason(client: TestClient) -> None:
    r = client.post("/api/services", json={"src": "COK", "dst": "DEL", "rate_gbps": 400})
    assert r.status_code == 409
    assert "reach" in r.json()["detail"]


def test_invalid_request_returns_422(client: TestClient) -> None:
    r = client.post("/api/services", json={"src": "DEL", "dst": "BOM", "rate_gbps": 250})
    assert r.status_code == 422


def test_fail_and_repair_link(client: TestClient) -> None:
    client.post("/api/services", json={"src": "DEL", "dst": "JAI", "rate_gbps": 100})
    r = client.post("/api/links/DEL-JAI/fail")
    assert r.status_code == 200
    assert len(r.json()["restored"]) == 1
    assert client.post("/api/links/DEL-JAI/fail").status_code == 409
    assert client.post("/api/links/DEL-JAI/repair").status_code == 200


def test_compute_paths(client: TestClient) -> None:
    r = client.post("/api/paths/compute", json={"src": "COK", "dst": "DEL", "rate_gbps": 400})
    assert r.status_code == 200
    candidates = r.json()
    assert candidates and not any(c["feasible"] for c in candidates)


def test_alarm_ack(client: TestClient) -> None:
    client.post("/api/links/BOM-PNQ/fail")
    alarm = client.get("/api/snapshot").json()["alarms"][0]
    r = client.post(f"/api/alarms/{alarm['id']}/ack")
    assert r.status_code == 200 and r.json()["acknowledged"]
    assert client.post("/api/alarms/99999/ack").status_code == 404


def test_traffic_and_reset(client: TestClient) -> None:
    r = client.post("/api/simulate/traffic", json={"count": 30})
    body = r.json()
    assert body["provisioned"] + body["blocked"] == 30
    assert client.post("/api/reset").status_code == 204


def test_telemetry(client: TestClient) -> None:
    r = client.get("/api/links/DEL-JAI/telemetry")
    assert r.status_code == 200 and len(r.json()) >= 1
    assert client.get("/api/links/NOPE/telemetry").status_code == 404


def test_websocket_pushes_snapshot_on_change(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "snapshot"
        client.post("/api/services", json={"src": "DEL", "dst": "JAI", "rate_gbps": 100})
        msg = ws.receive_json()
        assert msg["data"]["version"] > first["data"]["version"]
        assert len(msg["data"]["services"]) == 1


def test_rate_limit() -> None:
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(seed_demo_services=False, rate_limit_per_minute=2))
    with TestClient(app) as c:
        assert c.post("/api/reset").status_code == 204
        assert c.post("/api/reset").status_code == 204
        r = c.post("/api/reset")
        assert r.status_code == 429 and "Retry-After" in r.headers
