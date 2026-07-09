def _upload(client, headers, wav):
    return client.post(
        "/files", files={"file": ("s.wav", wav(), "audio/wav")}, headers=headers
    ).json()["file"]["idFile"]


def test_favorite_add_list_remove(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)

    assert client.post(f"/files/{fid}/favorite", headers=headers).status_code == 201
    favs = client.get("/favorites", headers=headers).json()
    assert [x["file"]["idFile"] for x in favs] == [fid]

    assert client.delete(f"/files/{fid}/favorite", headers=headers).status_code == 204
    assert client.get("/favorites", headers=headers).json() == []


def test_favorite_is_idempotent(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)
    client.post(f"/files/{fid}/favorite", headers=headers)
    client.post(f"/files/{fid}/favorite", headers=headers)
    assert len(client.get("/favorites", headers=headers).json()) == 1


def test_cannot_favorite_others_file(client, auth, store, wav):
    h1, _ = auth()
    h2, _ = auth()
    fid = _upload(client, h1, wav)
    assert client.post(f"/files/{fid}/favorite", headers=h2).status_code == 404


def test_deleting_file_clears_favorite(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)
    client.post(f"/files/{fid}/favorite", headers=headers)
    assert client.delete(f"/files/{fid}", headers=headers).status_code == 204
    assert client.get("/favorites", headers=headers).json() == []
