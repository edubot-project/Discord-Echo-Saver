"""
Tests manuales para los endpoints de chunkMessages.
Requiere que la API esté corriendo: uvicorn src.api.main:app --reload

Ejecutar: python3 -m test.api.v1.chunkMessages
"""

import requests

BASE_URL = "http://127.0.0.1:8000/chunkmessages"

# ID de canal de ejemplo — ajusta según tu entorno
CHANNEL_ID = 1311706520467144808


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_result(name: str, response: requests.Response):
    status = "OK" if response.status_code in (200, 202) else "FAIL"
    print(f"[{status}] {name}")
    print(f"       status_code : {response.status_code}")
    try:
        print(f"       body        : {response.json()}")
    except Exception:
        print(f"       body        : {response.text}")
    print()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_chunk_single_channel():
    """Chunkeniza solo el canal indicado — debe responder 202."""
    response = requests.post(
        f"{BASE_URL}/channel",
        json={"channel_id": CHANNEL_ID},
    )
    print_result("POST /chunkmessages/channel", response)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["channel_id"] == CHANNEL_ID


def test_chunk_channel_recursive():
    """Chunkeniza el canal y todos sus hijos — debe responder 202."""
    response = requests.post(
        f"{BASE_URL}/channel/recursive",
        json={"channel_id": CHANNEL_ID},
    )
    print_result("POST /chunkmessages/channel/recursive", response)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["channel_id"] == CHANNEL_ID


def test_chunk_single_channel_bad_body():
    """Body sin channel_id — FastAPI debe devolver 422."""
    response = requests.post(
        f"{BASE_URL}/channel",
        json={"wrong_field": CHANNEL_ID},
    )
    print_result("POST /chunkmessages/channel (body inválido)", response)
    assert response.status_code == 422


def test_chunk_channel_recursive_bad_body():
    """Body sin channel_id — FastAPI debe devolver 422."""
    response = requests.post(
        f"{BASE_URL}/channel/recursive",
        json={"wrong_field": CHANNEL_ID},
    )
    print_result("POST /chunkmessages/channel/recursive (body inválido)", response)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_chunk_single_channel()
    test_chunk_channel_recursive()
    test_chunk_single_channel_bad_body()
    test_chunk_channel_recursive_bad_body()
