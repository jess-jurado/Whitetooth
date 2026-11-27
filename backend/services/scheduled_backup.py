import asyncio
import hashlib
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from backend.database import STORAGE, engine
from backend.services.backup import snapshot

logger = logging.getLogger(__name__)
madrid = ZoneInfo('Europe/Madrid')


@dataclass(frozen=True)
class BackupSchedule:
    at: time
    directory: Path
    mirror: Optional[Path] = None


def configured_schedule():
    raw_time = os.getenv('DENTALIS_BACKUP_AT', '').strip()
    if not raw_time:
        return None
    at = datetime.strptime(raw_time, '%H:%M').time()
    if engine.dialect.name != 'sqlite' or not engine.url.database or engine.url.database == ':memory:':
        raise ValueError('Las copias programadas necesitan SQLite en disco')
    if os.name != 'posix':
        raise ValueError('Las copias programadas requieren macOS o Linux')
    mirror_value = os.getenv('DENTALIS_BACKUP_NETWORK_DIR', '').strip()
    mirror = Path(mirror_value).expanduser() if mirror_value else None
    directory = (STORAGE / 'backups').resolve()
    if mirror is not None and (not mirror.is_absolute() or mirror.resolve() == directory):
        raise ValueError('DENTALIS_BACKUP_NETWORK_DIR debe ser una carpeta absoluta distinta de los respaldos locales')
    return BackupSchedule(at, directory, mirror)


def replicate(source: Path, destination: Path):
    # A disconnected destination is reported instead of creating a new folder.
    with tempfile.NamedTemporaryFile(dir=destination, prefix='.dentalis-', delete=False) as temporary:
        draft = Path(temporary.name)
        try:
            with source.open('rb') as archive:
                shutil.copyfileobj(archive, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
            os.replace(draft, destination / source.name)
        finally:
            draft.unlink(missing_ok=True)


def mirror_marker(archive: Path, destination: Path):
    digest = hashlib.sha256(os.fsencode(destination)).hexdigest()[:16]
    return archive.with_name('.' + archive.stem + '-' + digest + '.copied')


def run_due_backup(schedule: BackupSchedule, now: datetime):
    from fcntl import LOCK_EX, LOCK_NB, flock

    local = now.astimezone(madrid)
    schedule.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (schedule.directory / '.daily.lock').open('a') as lock:
        try:
            flock(lock, LOCK_EX | LOCK_NB)
        except BlockingIOError:
            return

        archive = schedule.directory / f'dentalis-{local.date()}.zip'
        if local.time() >= schedule.at and not archive.exists():
            with tempfile.TemporaryDirectory(prefix='.draft-', dir=schedule.directory) as staging:
                packed = snapshot(Path(staging))
                os.chmod(packed, 0o600)
                os.replace(packed, archive)
            logger.info('Copia diaria creada: %s', archive.name)

        if schedule.mirror is not None:
            latest = latest_archive(schedule)
            if latest:
                marker = mirror_marker(latest, schedule.mirror)
                if not marker.exists():
                    replicate(latest, schedule.mirror)
                    marker.touch(mode=0o600)


def latest_archive(schedule: BackupSchedule):
    return max(schedule.directory.glob('dentalis-????-??-??.zip'), default=None)


def backup_status(schedule, config_error: str, last_error: str):
    if schedule is None:
        return {'enabled': False, 'error': config_error}
    latest = latest_archive(schedule)
    return {
        'enabled': True,
        'at': schedule.at.strftime('%H:%M'),
        'latest': latest.name if latest else None,
        'network_enabled': schedule.mirror is not None,
        'network_synced': bool(latest and schedule.mirror and mirror_marker(latest, schedule.mirror).exists()),
        'error': last_error,
    }


async def backup_loop(app, schedule: BackupSchedule):
    while True:
        try:
            await asyncio.to_thread(run_due_backup, schedule, datetime.now(madrid))
            app.state.backup_error = ''
        except Exception:
            app.state.backup_error = 'Fallo en el último intento de copia. Se reintentará en unos minutos.'
            logger.exception('Error en la copia programada de Dentalis')
        await asyncio.sleep(300)
