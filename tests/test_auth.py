def test_register_and_duplicate_email(client):
    body = {"name": "A", "nickname": "a", "email": "dup@test.co", "password": "secret123"}
    r = client.post("/register", json=body)
    assert r.status_code == 201
    assert "passwd" not in r.json()  # never leak the hash
    assert client.post("/register", json=body).status_code == 409


def test_login_returns_both_tokens_and_me(auth, client):
    headers, uid = auth()
    assert client.get("/users/me", headers=headers).json()["idUser"] == uid


def test_wrong_password(client):
    client.post(
        "/register",
        json={"name": "A", "nickname": "a", "email": "w@test.co", "password": "secret123"},
    )
    r = client.post("/login", data={"username": "w@test.co", "password": "nope"})
    assert r.status_code == 401


def test_refresh_flow(client):
    client.post(
        "/register",
        json={"name": "A", "nickname": "a", "email": "r@test.co", "password": "secret123"},
    )
    tok = client.post("/login", data={"username": "r@test.co", "password": "secret123"}).json()
    new = client.post("/refresh", json={"refresh_token": tok["refresh_token"]})
    assert new.status_code == 200
    access = new.json()["access_token"]
    assert client.get("/users/me", headers={"Authorization": f"Bearer {access}"}).status_code == 200
    # an access token is not a refresh token
    assert client.post("/refresh", json={"refresh_token": tok["access_token"]}).status_code == 401


def test_logout_revokes_all_tokens(client):
    client.post(
        "/register",
        json={"name": "A", "nickname": "a", "email": "lo@test.co", "password": "secret123"},
    )
    tok = client.post("/login", data={"username": "lo@test.co", "password": "secret123"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post("/logout", headers=h).status_code == 204
    assert client.get("/users/me", headers=h).status_code == 401
    assert client.post("/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_protected_requires_token(client):
    assert client.get("/users/me").status_code == 401
