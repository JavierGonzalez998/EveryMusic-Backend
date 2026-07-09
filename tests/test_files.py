def _upload(client, headers, wav, name="song.wav"):
    return client.post(
        "/files", files={"file": (name, wav(), "audio/wav")}, headers=headers
    )


def test_upload_and_list(client, auth, store, wav):
    headers, _ = auth()
    r = _upload(client, headers, wav)
    assert r.status_code == 201
    fid = r.json()["file"]["idFile"]
    assert len(store) == 1  # object landed in the (fake) bucket
    listing = client.get("/files", headers=headers).json()
    assert [x["file"]["idFile"] for x in listing] == [fid]


def test_upload_rejects_bad_extension(client, auth, store):
    headers, _ = auth()
    r = client.post("/files", files={"file": ("a.txt", b"hi", "text/plain")}, headers=headers)
    assert r.status_code == 400
    assert not store


def test_upload_rejects_non_audio(client, auth, store):
    headers, _ = auth()
    r = client.post("/files", files={"file": ("a.wav", b"not audio", "audio/wav")}, headers=headers)
    assert r.status_code == 400


def test_upload_rejects_oversized(client, auth, store, monkeypatch):
    import controller.files.router as fr

    monkeypatch.setattr(fr, "MAX_UPLOAD_BYTES", 100)
    headers, _ = auth()
    r = client.post("/files", files={"file": ("a.wav", b"x" * 500, "audio/wav")}, headers=headers)
    assert r.status_code == 413


def test_get_file_ownership(client, auth, store, wav):
    h1, _ = auth()
    h2, _ = auth()
    fid = _upload(client, h1, wav).json()["file"]["idFile"]
    assert client.get(f"/files/{fid}", headers=h1).status_code == 200
    assert client.get(f"/files/{fid}", headers=h2).status_code == 404


def test_play_returns_url(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav).json()["file"]["idFile"]
    r = client.get(f"/files/{fid}/play", headers=headers)
    assert r.status_code == 200 and r.json()["url"].startswith("https://fake/")


def test_delete_cleans_bucket_and_cascades(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav).json()["file"]["idFile"]
    pl = client.post("/playlists", json={"name": "P"}, headers=headers).json()["idPlaylist"]
    client.post(f"/playlists/{pl}/files", json={"idFiles": [fid]}, headers=headers)
    assert len(store) == 1

    assert client.delete(f"/files/{fid}", headers=headers).status_code == 204
    assert len(store) == 0  # object removed from bucket
    assert client.get(f"/files/{fid}", headers=headers).status_code == 404
    # playlist no longer lists the deleted track
    assert client.get(f"/playlists/{pl}", headers=headers).json()["tracks"] == []
