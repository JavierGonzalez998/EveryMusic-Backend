from models import File as FileModel
from models import Metadata


def _seed(db_session, uid, song, artist="", album=""):
    f = FileModel(ext="mp3", uploaded_by=uid)
    db_session.add(f)
    db_session.flush()
    db_session.add(Metadata(idFile=f.idFile, songName=song, songArtist=artist, albumName=album))
    db_session.commit()


def test_search_is_case_insensitive_and_scoped_to_user(client, auth, db_session):
    h1, u1 = auth()
    _, u2 = auth()
    _seed(db_session, u1, "Bohemian Rhapsody", "Queen", "A Night at the Opera")
    _seed(db_session, u2, "Queen intruder", "Other")  # belongs to another user

    res = client.get("/search", params={"q": "queen"}, headers=h1).json()
    assert [r["metadata"]["songName"] for r in res] == ["Bohemian Rhapsody"]


def test_search_matches_album_and_artist(client, auth, db_session):
    h1, u1 = auth()
    _seed(db_session, u1, "Imagine", "John Lennon", "Imagine")
    _seed(db_session, u1, "Yesterday", "The Beatles", "Help!")

    assert len(client.get("/search", params={"q": "lennon"}, headers=h1).json()) == 1
    assert len(client.get("/search", params={"q": "e"}, headers=h1).json()) == 2
