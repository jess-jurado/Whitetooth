from datetime import datetime, time
from urllib.parse import parse_qs, urlparse
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pytest
from backend.services.scheduled_backup import BackupSchedule, backup_status, run_due_backup


def test_whatsapp_draft_uses_current_schedule_and_demo_blocks_link(client, monkeypatch):
    appointment = client.post('/api/appointments', json={
        'patient_id': 1, 'professional_id': 1, 'starts_at': '2027-02-11T11:15',
        'duration': 30, 'room': 'Gabinete 1', 'reason': 'Motivo clínico ficticio',
    }).json()
    base = f"/api/appointments/{appointment['id']}"
    result = client.patch(base + '/schedule', json={
        'expected_start': appointment['starts_at'], 'expected_room': appointment['room'],
        'starts_at': '2027-03-11T12:30', 'room': 'Gabinete 1',
    })
    assert result.status_code == 200
    monkeypatch.setenv('DENTALIS_WHATSAPP_ENABLED', '1')
    monkeypatch.setenv('DENTALIS_CLINIC_NAME', 'Clínica Demo')
    response = client.post(base + '/whatsapp-draft')
    assert response.status_code == 200
    draft = response.json()
    assert draft['phone'].startswith('+34')
    assert 'Clínica Demo el 11/03/2027 a las 12:30' in draft['message']
    assert 'Motivo clínico' not in draft['message']
    assert draft['url'] is None

    monkeypatch.setenv('DENTALIS_DEMO', '0')
    enabled = client.post(base + '/whatsapp-draft').json()
    url = urlparse(enabled['url'])
    assert (url.scheme, url.netloc, url.path) == ('https', 'wa.me', '/' + draft['phone'][1:])
    assert parse_qs(url.query)['text'] == [draft['message']]
    assert client.patch(base, json={'status': 'Cancelada'}).status_code == 200
    assert client.post(base + '/whatsapp-draft').status_code == 409


def test_daily_backup_is_deduplicated_and_retries_mirror(client, tmp_path):
    local = tmp_path / 'daily'
    mirror = tmp_path / 'simulated-share'
    schedule = BackupSchedule(time(21), local, mirror)
    tz = ZoneInfo('Europe/Madrid')
    run_due_backup(schedule, datetime(2026, 11, 27, 20, 59, tzinfo=tz))
    assert not list(local.glob('*.zip'))
    with pytest.raises(FileNotFoundError):
        run_due_backup(schedule, datetime(2026, 11, 27, 21, tzinfo=tz))
    archive = local / 'dentalis-2026-11-27.zip'
    archived_bytes = archive.read_bytes()
    original_modified = archive.stat().st_mtime_ns
    with ZipFile(archive) as zipfile:
        assert zipfile.testzip() is None
        assert 'dentalis.db' in zipfile.namelist()
    assert not backup_status(schedule, '', '')['network_synced']
    mirror.mkdir()
    run_due_backup(schedule, datetime(2026, 11, 27, 21, 5, tzinfo=tz))
    assert archive.stat().st_mtime_ns == original_modified
    assert (mirror / archive.name).read_bytes() == archived_bytes
    assert backup_status(schedule, '', '')['network_synced']
    assert sorted(file.name for file in mirror.iterdir()) == [archive.name]
    assert client.get('/api/backups/status').json()['enabled'] is False
