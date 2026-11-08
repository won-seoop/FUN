import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def wait_job(client, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get("/observation/status").json()
        if st["status"] != "running":
            return st
        time.sleep(0.1)
    raise TimeoutError


def wait_idle(client):
    for _ in range(100):
        if not client.get("/telescope/position").json()["slewing"]:
            return
        time.sleep(0.05)


def test_frontend_and_health(client):
    assert client.get("/health").status_code == 200
    r = client.get("/")
    assert r.status_code == 200 and "Space Telescope" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_requires_connection(client):
    client.post("/telescope/disconnect")
    assert client.get("/telescope/position").status_code == 409
    assert client.post("/telescope/move", json={"ra": 1, "dec": 2}).status_code == 409


def test_telescope_control(client):
    r = client.post("/telescope/connect", json={"mode": "sim"})
    assert r.status_code == 200 and r.json()["connected"]
    assert client.post("/telescope/move", json={"ra": 30, "dec": 0}).status_code == 422
    r = client.post("/telescope/move", json={"target": "Vega"})
    assert r.status_code == 200
    wait_idle(client)
    pos = client.get("/telescope/position").json()
    assert pos["ra"] == pytest.approx(18.6156, abs=1e-6)
    assert client.post("/telescope/stop").status_code == 200
    assert client.post("/telescope/move", json={"target": "Nope"}).status_code == 400


def test_capture_analyze_and_images(client):
    client.post("/telescope/connect", json={"mode": "sim"})
    client.post("/telescope/move", json={"target": "Sirius"})
    wait_idle(client)
    meta = client.post("/camera/capture", json={"exposure": 1.0}).json()
    assert meta["analysis"]["star_count"] > 5
    assert meta["analysis"]["solve"]["success"]
    assert client.get(f"/images/{meta['id']}/png").headers["content-type"] == "image/png"
    assert client.get(f"/images/{meta['id']}/fits").status_code == 200
    assert client.post(f"/vision/analyze/{meta['id']}").status_code == 200
    meta2 = client.post("/camera/capture", json={"exposure": 1.0, "analyze": False}).json()
    tr = client.post("/vision/track", json={"image_a": meta["id"], "image_b": meta2["id"]}).json()
    assert tr["distance"] < 2
    assert any(m["id"] == meta["id"] for m in client.get("/images").json())
    assert client.get("/images/nope").status_code == 404


def test_auto_correction(client):
    client.post("/telescope/connect", json={"mode": "sim"})
    r = client.post("/correction/run", json={"target": "Altair", "exposure": 1.0})
    assert r.status_code == 200
    st = wait_job(client)
    assert st["status"] == "done", st
    res = st["results"][0]
    assert res["success"] and res["final_error_arcsec"] <= res["tolerance_arcsec"]
    assert res["iterations"][0]["error_arcsec"] > res["final_error_arcsec"]


def test_auto_observation_and_logs(client):
    client.post("/telescope/connect", json={"mode": "sim"})
    r = client.post("/observation/start",
                    json={"targets": ["Rigel", "Deneb"], "exposure": 1, "final_exposure": 2})
    assert r.status_code == 200
    assert client.post("/observation/start", json={"targets": ["Vega"]}).status_code == 409
    st = wait_job(client)
    assert st["status"] == "done", st
    assert [x["target"] for x in st["results"]] == ["Rigel", "Deneb"]
    assert all(x["observation_image_id"] for x in st["results"])
    logs = client.get("/logs").json()
    assert any("자동 관측 완료" in entry["message"] for entry in logs)
