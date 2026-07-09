import controller.files.router as fr


def _upload(client, headers, wav, name="s.wav"):
    return client.post(
        "/files", files={"file": (name, wav(), "audio/wav")}, headers=headers
    ).json()["file"]["idFile"]


def test_no_cover_by_default(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)
    assert client.get(f"/files/{fid}/cover", headers=headers).status_code == 404


def test_cover_extracted_and_served(client, auth, store, wav, monkeypatch):
    # Fake embedded art so we don't need a real tagged file.
    monkeypatch.setattr(fr, "_extract_cover", lambda data: (b"IMG", "image/jpeg"))
    headers, uid = auth()
    r = client.post("/files", files={"file": ("s.wav", wav(), "audio/wav")}, headers=headers)
    fid = r.json()["file"]["idFile"]
    assert r.json()["file"]["has_cover"] is True
    assert f"{uid}/{fid}.cover" in store
    cov = client.get(f"/files/{fid}/cover", headers=headers)
    assert cov.status_code == 200 and cov.json()["url"].endswith(".cover")


def test_cover_removed_on_delete(client, auth, store, wav, monkeypatch):
    monkeypatch.setattr(fr, "_extract_cover", lambda data: (b"IMG", "image/jpeg"))
    headers, uid = auth()
    fid = client.post(
        "/files", files={"file": ("s.wav", wav(), "audio/wav")}, headers=headers
    ).json()["file"]["idFile"]
    assert f"{uid}/{fid}.cover" in store
    client.delete(f"/files/{fid}", headers=headers)
    assert f"{uid}/{fid}.cover" not in store  # audio + cover both gone
    assert len(store) == 0


def test_play_is_recorded_in_history(client, auth, store, wav):
    headers, _ = auth()
    f1 = _upload(client, headers, wav)
    f2 = _upload(client, headers, wav)
    client.get(f"/files/{f1}/play", headers=headers)
    client.get(f"/files/{f2}/play", headers=headers)
    hist = client.get("/history", headers=headers).json()
    assert len(hist) == 2
    assert {h["file"]["idFile"] for h in hist} == {f1, f2}
    assert all("played_at" in h for h in hist)


def test_history_cleared_on_file_delete(client, auth, store, wav):
    headers, _ = auth()
    fid = _upload(client, headers, wav)
    client.get(f"/files/{fid}/play", headers=headers)
    client.delete(f"/files/{fid}", headers=headers)
    assert client.get("/history", headers=headers).json() == []
