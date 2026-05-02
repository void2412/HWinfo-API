"""
Integration tests for FastAPI routes.
Mocks read_sensors() — no live HWInfo required.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from hwinfo.models import SensorReading

client = TestClient(app)


def _sensor(**overrides) -> SensorReading:
    defaults = dict(
        id=1, sensor_index=0, type="temperature", name="CPU Temp",
        unit="C", value=65.0, value_min=30.0, value_max=90.0, value_avg=60.0,
    )
    defaults.update(overrides)
    return SensorReading(**defaults)


# ── /health ────────────────────────────────────────────────────────────────────

def test_health_online():
    with patch("api.routes.read_sensors", return_value=[_sensor()]):
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "sensor_count": 1}


def test_health_offline():
    with patch("api.routes.read_sensors", return_value=None):
        r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "hwinfo_offline"


# ── /api/sensors ───────────────────────────────────────────────────────────────

def test_sensors_offline():
    with patch("api.routes.read_sensors", return_value=None):
        r = client.get("/api/sensors")
    assert r.status_code == 503
    assert "error" in r.json()


def test_sensors_returns_all():
    mock = [
        _sensor(id=1, type="temperature", name="CPU"),
        _sensor(id=2, type="fan", name="CPU Fan", unit="RPM", value=1200.0,
                value_min=800.0, value_max=2000.0, value_avg=1100.0),
    ]
    with patch("api.routes.read_sensors", return_value=mock):
        r = client.get("/api/sensors")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


def test_sensors_filter_by_type():
    mock = [
        _sensor(id=1, type="temperature"),
        _sensor(id=2, type="fan", unit="RPM", value=1200.0,
                value_min=800.0, value_max=2000.0, value_avg=1100.0),
    ]
    with patch("api.routes.read_sensors", return_value=mock):
        r = client.get("/api/sensors?type=temperature")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["type"] == "temperature"


def test_sensors_filter_case_insensitive():
    mock = [_sensor(type="fan", unit="RPM", value=1200.0,
                    value_min=800.0, value_max=2000.0, value_avg=1100.0)]
    with patch("api.routes.read_sensors", return_value=mock):
        r = client.get("/api/sensors?type=FAN")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_sensors_invalid_type_returns_400():
    with patch("api.routes.read_sensors", return_value=[_sensor()]):
        r = client.get("/api/sensors?type=unknown_xyz")
    assert r.status_code == 400
    body = r.json()
    assert "valid_types" in body


def test_sensors_empty_result_for_unmatched_filter():
    mock = [_sensor(type="temperature")]
    with patch("api.routes.read_sensors", return_value=mock):
        r = client.get("/api/sensors?type=fan")
    assert r.status_code == 200
    assert r.json() == []


# ── / dashboard ────────────────────────────────────────────────────────────────

def test_dashboard_online():
    with patch("main.read_sensors", return_value=[_sensor()]):
        r = client.get("/")
    assert r.status_code == 200
    assert "Online" in r.text
    assert "CPU Temp" in r.text


def test_dashboard_offline():
    with patch("main.read_sensors", return_value=None):
        r = client.get("/")
    assert r.status_code == 200
    assert "Offline" in r.text
    assert "HWInfo64 is not running" in r.text
    assert 'content="5"' in r.text  # meta-refresh present
