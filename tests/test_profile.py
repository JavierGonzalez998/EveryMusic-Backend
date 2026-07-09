def test_update_name_and_nickname(client, auth):
    headers, _ = auth()
    r = client.patch("/users/me", json={"name": "New Name", "nickname": "nn"}, headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "New Name" and r.json()["nickname"] == "nn"


def test_change_email_conflict(client, auth):
    h1, _ = auth()
    h2, _ = auth()
    taken = client.get("/users/me", headers=h2).json()["email"]
    assert client.patch("/users/me", json={"email": taken}, headers=h1).status_code == 409


def test_change_email_ok(client, auth):
    headers, _ = auth()
    r = client.patch("/users/me", json={"email": "brand-new@test.co"}, headers=headers)
    assert r.status_code == 200 and r.json()["email"] == "brand-new@test.co"


def test_password_change_revokes_tokens(client, auth):
    headers, _ = auth()
    assert client.patch("/users/me", json={"password": "newsecret1"}, headers=headers).status_code == 200
    # old token no longer valid after password change
    assert client.get("/users/me", headers=headers).status_code == 401
