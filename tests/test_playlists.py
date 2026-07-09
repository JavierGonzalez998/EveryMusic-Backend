def _upload(client, headers, wav):
    return client.post(
        "/files", files={"file": ("s.wav", wav(), "audio/wav")}, headers=headers
    ).json()["file"]["idFile"]


def test_create_and_list(client, auth):
    headers, _ = auth()
    pid = client.post("/playlists", json={"name": "Rock"}, headers=headers).json()["idPlaylist"]
    listing = client.get("/playlists", headers=headers).json()
    assert [p["idPlaylist"] for p in listing] == [pid]


def test_add_files_orders_by_position(client, auth, store, wav):
    headers, _ = auth()
    ids = [_upload(client, headers, wav) for _ in range(3)]
    pid = client.post("/playlists", json={"name": "P"}, headers=headers).json()["idPlaylist"]
    r = client.post(f"/playlists/{pid}/files", json={"idFiles": ids}, headers=headers)
    assert r.status_code == 201 and r.json()["added"] == ids
    tracks = client.get(f"/playlists/{pid}", headers=headers).json()["tracks"]
    assert [t["position"] for t in tracks] == [1, 2, 3]
    assert [t["file"]["idFile"] for t in tracks] == ids


def test_add_duplicate_is_idempotent(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)
    pid = client.post("/playlists", json={"name": "P"}, headers=headers).json()["idPlaylist"]
    client.post(f"/playlists/{pid}/files", json={"idFiles": [fid]}, headers=headers)
    r = client.post(f"/playlists/{pid}/files", json={"idFiles": [fid]}, headers=headers)
    assert r.json()["added"] == [] and r.json()["skipped"] == [fid]


def test_cannot_add_others_file(client, auth, store, wav):
    h1, _ = auth()
    h2, _ = auth()
    fid = _upload(client, h1, wav)  # owned by user 1
    pid = client.post("/playlists", json={"name": "P"}, headers=h2).json()["idPlaylist"]
    r = client.post(f"/playlists/{pid}/files", json={"idFiles": [fid]}, headers=h2)
    assert r.status_code == 400


def test_remove_track(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)
    pid = client.post("/playlists", json={"name": "P"}, headers=headers).json()["idPlaylist"]
    client.post(f"/playlists/{pid}/files", json={"idFiles": [fid]}, headers=headers)
    assert client.delete(f"/playlists/{pid}/files/{fid}", headers=headers).status_code == 204
    assert client.get(f"/playlists/{pid}", headers=headers).json()["tracks"] == []


def test_rename_and_ownership(client, auth):
    h1, _ = auth()
    h2, _ = auth()
    pid = client.post("/playlists", json={"name": "Old"}, headers=h1).json()["idPlaylist"]
    r = client.patch(f"/playlists/{pid}", json={"name": "New"}, headers=h1)
    assert r.status_code == 200 and r.json()["name"] == "New"
    assert client.patch(f"/playlists/{pid}", json={"name": "X"}, headers=h2).status_code == 404


def test_delete_playlist(client, auth):
    headers, _ = auth()
    pid = client.post("/playlists", json={"name": "P"}, headers=headers).json()["idPlaylist"]
    assert client.delete(f"/playlists/{pid}", headers=headers).status_code == 204
    assert client.get(f"/playlists/{pid}", headers=headers).status_code == 404
