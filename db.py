from sqlmodel import Session, create_engine

from config import settings

url = settings.mysql_url
# SQLAlchemy needs an explicit driver dialect; hosted URLs often ship as plain mysql://
if url.startswith("mysql://"):
    url = "mysql+pymysql://" + url[len("mysql://"):]

engine = create_engine(url, pool_pre_ping=True)


def get_session():
    with Session(engine) as session:
        yield session
