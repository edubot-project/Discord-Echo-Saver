"""
Tests manuales para los endpoints de fetchDiscordApi.
Requiere que la API esté corriendo: uvicorn src.api.main:app --reload

Ejecutar: python3 -m test.api.v1.fetchDiscordApi
"""

import requests

BASE_URL = "http://127.0.0.1:8000/fetchdiscord"

# IDs de ejemplo — ajusta según tu entorno
GUILD_IDS = [772855809406271508, 1308885706621452369]
CHANNEL_IDS = [1311706520467144808]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_result(name: str, response: requests.Response):
    status = "OK" if response.status_code == 202 else "FAIL"
    print(f"[{status}] {name}")
    print(f"       status_code : {response.status_code}")
    print(f"       body        : {response.json()}")
    print()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_update_channels():
    response = requests.post(
        f"{BASE_URL}/channels",
        json={"guild_id_list": GUILD_IDS},
    )
    print_result("POST /fetchdiscord/channels", response)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["guild_id_list"] == GUILD_IDS


def test_update_users():
    response = requests.post(
        f"{BASE_URL}/users",
        json={"guild_id_list": GUILD_IDS},
    )
    print_result("POST /fetchdiscord/users", response)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["guild_id_list"] == GUILD_IDS


def test_update_messages():
    response = requests.post(
        f"{BASE_URL}/messages",
        json={"channel_id_list": CHANNEL_IDS},
    )
    print_result("POST /fetchdiscord/messages", response)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["channel_id_list"] == CHANNEL_IDS


def test_update_channels_empty_list():
    """Lista vacía — debe aceptarse igual (202) y no hacer nada en background."""
    response = requests.post(
        f"{BASE_URL}/channels",
        json={"guild_id_list": []},
    )
    print_result("POST /fetchdiscord/channels (lista vacía)", response)
    assert response.status_code == 202


def test_update_channels_bad_body():
    """Body incorrecto — FastAPI debe devolver 422."""
    response = requests.post(
        f"{BASE_URL}/channels",
        json={"wrong_field": GUILD_IDS},
    )
    print_result("POST /fetchdiscord/channels (body inválido)", response)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_update_messages()


