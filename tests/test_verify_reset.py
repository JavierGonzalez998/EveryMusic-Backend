def _token_from(body: str) -> str:
    return body.split("token=")[1].strip()


def test_email_verification_flow(client, auth, mailbox):
    headers, _ = auth()
    assert client.get("/users/me", headers=headers).json()["email_verified"] is False

    assert client.post("/auth/request-verify", headers=headers).status_code == 202
    token = _token_from(mailbox[-1])
    assert client.post("/auth/verify", json={"token": token}).status_code == 200
    assert client.get("/users/me", headers=headers).json()["email_verified"] is True


def test_password_reset_flow(client, mailbox):
    client.post(
        "/register",
        json={"name": "A", "nickname": "a", "email": "reset@test.co", "password": "secret123"},
    )
    old = client.post("/login", data={"username": "reset@test.co", "password": "secret123"}).json()

    r = client.post("/auth/request-password-reset", json={"email": "reset@test.co"})
    assert r.status_code == 202
    token = _token_from(mailbox[-1])

    assert client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brandnew1"}
    ).status_code == 204

    # old session revoked, old password rejected, new password works
    assert client.get("/users/me", headers={"Authorization": f"Bearer {old['access_token']}"}).status_code == 401
    assert client.post("/login", data={"username": "reset@test.co", "password": "secret123"}).status_code == 401
    assert client.post("/login", data={"username": "reset@test.co", "password": "brandnew1"}).status_code == 200


def test_reset_request_unknown_email_is_silent(client, mailbox):
    r = client.post("/auth/request-password-reset", json={"email": "ghost@test.co"})
    assert r.status_code == 202  # same response...
    assert mailbox == []  # ...but no email sent (no account enumeration)


def test_reset_token_cannot_be_reused(client, mailbox):
    client.post(
        "/register",
        json={"name": "A", "nickname": "a", "email": "reuse@test.co", "password": "secret123"},
    )
    client.post("/auth/request-password-reset", json={"email": "reuse@test.co"})
    token = _token_from(mailbox[-1])
    client.post("/auth/reset-password", json={"token": token, "new_password": "brandnew1"})
    # second use of the same token fails (token_version bumped)
    assert client.post(
        "/auth/reset-password", json={"token": token, "new_password": "another1"}
    ).status_code == 401
