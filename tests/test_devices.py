def _register(client):
    r = client.post("/devices/register")
    assert r.status_code == 201
    return r.json()  # {idDevice, code, device_token}


def test_full_pairing_flow(client, auth):
    headers, uid = auth()
    dev = _register(client)

    # before linking, the gadget can't get a token
    early = client.post(
        "/devices/auth",
        json={"idDevice": dev["idDevice"], "device_token": dev["device_token"]},
    )
    assert early.status_code == 425

    # user links it with the code
    link = client.post("/devices/link", json={"code": dev["code"], "name": "Living room"}, headers=headers)
    assert link.status_code == 200 and link.json()["linked"] is True

    # now the gadget exchanges its secret for an access token...
    r = client.post(
        "/devices/auth",
        json={"idDevice": dev["idDevice"], "device_token": dev["device_token"]},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    # ...and that token acts as the user across the API
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["idUser"] == uid


def test_link_unknown_code(client, auth):
    headers, _ = auth()
    assert client.post("/devices/link", json={"code": "NOPE1234"}, headers=headers).status_code == 404


def test_link_conflict_when_owned_by_another(client, auth):
    h1, _ = auth()
    h2, _ = auth()
    dev = _register(client)
    client.post("/devices/link", json={"code": dev["code"]}, headers=h1)
    assert client.post("/devices/link", json={"code": dev["code"]}, headers=h2).status_code == 409


def test_wrong_device_secret(client, auth):
    headers, _ = auth()
    dev = _register(client)
    client.post("/devices/link", json={"code": dev["code"]}, headers=headers)
    r = client.post("/devices/auth", json={"idDevice": dev["idDevice"], "device_token": "wrong"})
    assert r.status_code == 401


def test_list_and_unlink_revokes(client, auth):
    headers, _ = auth()
    dev = _register(client)
    client.post("/devices/link", json={"code": dev["code"]}, headers=headers)

    devices = client.get("/devices", headers=headers).json()
    assert [d["idDevice"] for d in devices] == [dev["idDevice"]]

    assert client.delete(f"/devices/{dev['idDevice']}", headers=headers).status_code == 204
    # gadget can no longer authenticate after being unlinked
    r = client.post(
        "/devices/auth",
        json={"idDevice": dev["idDevice"], "device_token": dev["device_token"]},
    )
    assert r.status_code == 401
    assert client.get("/devices", headers=headers).json() == []
