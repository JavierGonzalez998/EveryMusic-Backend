import controller.files.router as fr


def test_upload_blocked_when_over_quota(client, auth, store, wav, monkeypatch):
    # Shrink the quota so two small uploads cross it.
    data = wav()
    monkeypatch.setattr(fr, "USER_QUOTA_BYTES", len(data) + 1)
    headers, _ = auth()

    assert client.post(
        "/files", files={"file": ("a.wav", data, "audio/wav")}, headers=headers
    ).status_code == 201
    # second upload would exceed the quota
    r = client.post("/files", files={"file": ("b.wav", data, "audio/wav")}, headers=headers)
    assert r.status_code == 413
    assert "quota" in r.json()["detail"].lower()


def test_quota_is_per_user(client, auth, store, wav, monkeypatch):
    data = wav()
    monkeypatch.setattr(fr, "USER_QUOTA_BYTES", len(data) + 1)
    h1, _ = auth()
    h2, _ = auth()
    client.post("/files", files={"file": ("a.wav", data, "audio/wav")}, headers=h1)
    # user 2 has their own quota, unaffected by user 1
    assert client.post(
        "/files", files={"file": ("a.wav", data, "audio/wav")}, headers=h2
    ).status_code == 201


def test_deleting_frees_quota(client, auth, store, wav, monkeypatch):
    data = wav()
    monkeypatch.setattr(fr, "USER_QUOTA_BYTES", len(data) + 1)
    headers, _ = auth()
    fid = client.post(
        "/files", files={"file": ("a.wav", data, "audio/wav")}, headers=headers
    ).json()["file"]["idFile"]
    assert client.post(
        "/files", files={"file": ("b.wav", data, "audio/wav")}, headers=headers
    ).status_code == 413
    client.delete(f"/files/{fid}", headers=headers)  # frees space
    assert client.post(
        "/files", files={"file": ("c.wav", data, "audio/wav")}, headers=headers
    ).status_code == 201
