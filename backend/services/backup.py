import re
import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from backend.database import STORAGE, engine


def snapshot(directory: Path) -> Path:
    database = directory / 'dentalis.db'
    source_uri = Path(engine.url.database).resolve().as_uri() + '?mode=ro'
    source = sqlite3.connect(source_uri, uri=True)
    copy = sqlite3.connect(database)
    try:
        source.backup(copy)
        attachments = copy.execute('SELECT path FROM documents ORDER BY id').fetchall()
        copy.execute('PRAGMA secure_delete=ON')
        copy.execute('DELETE FROM sessions')
        copy.commit()
    finally:
        copy.close()
        source.close()

    # Uploads are immutable and written before their database record is committed.
    archive = directory / 'dentalis.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
        bundle.write(database, 'dentalis.db')
        for (name,) in attachments:
            if not re.fullmatch('[0-9a-f]{48}', name):
                raise ValueError('Nombre de documento no válido')
            bundle.write(STORAGE / name, f'documents/{name}')
    return archive
