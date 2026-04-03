import requests

BASE_URL = "http://localhost:8000"

GUILD_ID_LIST = [772855809406271508, 1308885706621452369]
CHANNEL_ID_LIST = [1309953119366676510]


def test_update_channels():
    response = requests.post(
        f"{BASE_URL}/channels",
        json={"guild_id_list": GUILD_ID_LIST},
    )
    print(f"[POST /channels] {response.status_code} — {response.json()}")


def test_update_users():
    response = requests.post(
        f"{BASE_URL}/users",
        json={"guild_id_list": GUILD_ID_LIST},
    )
    print(f"[POST /users] {response.status_code} — {response.json()}")


def test_update_messages():
    response = requests.post(
        f"{BASE_URL}/messages",
        json={"channel_id_list": CHANNEL_ID_LIST},
    )
    print(f"[POST /messages] {response.status_code} — {response.json()}")


if __name__ == "__main__":
    #test_update_channels()
    #test_update_users()
    test_update_messages()


"""
python3 test/api/main.py


"""
