def test_public_playlist_readable_by_others(client, auth):
    owner, _ = auth()
    other, _ = auth()
    pid = client.post("/playlists", json={"name": "P"}, headers=owner).json()["idPlaylist"]

    # private by default -> others get 404
    assert client.get(f"/playlists/{pid}", headers=other).status_code == 404

    # make it public
    r = client.patch(f"/playlists/{pid}", json={"is_public": True}, headers=owner)
    assert r.status_code == 200 and r.json()["is_public"] is True

    # now readable by another user
    assert client.get(f"/playlists/{pid}", headers=other).status_code == 200


def test_only_owner_can_toggle_visibility(client, auth):
    owner, _ = auth()
    other, _ = auth()
    pid = client.post("/playlists", json={"name": "P"}, headers=owner).json()["idPlaylist"]
    assert client.patch(f"/playlists/{pid}", json={"is_public": True}, headers=other).status_code == 404
