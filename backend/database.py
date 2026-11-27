import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
STORAGE = Path(os.getenv('DENTALIS_STORAGE', str(ROOT / 'storage')))
STORAGE.mkdir(parents=True, exist_ok=True)
URL = os.getenv('DATABASE_URL', 'sqlite:///' + str(STORAGE / 'dentalis.db'))
engine = create_engine(URL, connect_args={'check_same_thread': False} if URL.startswith('sqlite') else {})
if URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_settings(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

def get_db():
    with SessionLocal() as db:
        yield db
