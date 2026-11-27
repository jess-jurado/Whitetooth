from io import BytesIO
from pathlib import Path
import sqlite3
from zipfile import ZipFile

from backend.database import SessionLocal
from backend.models.entities import Appointment, Room
from backend.services.seed import seed_rooms


def test_rooms_upgrade_and_rename_keep_appointments(client):
    with SessionLocal() as db:
        db.query(Room).delete()
        db.add(Appointment(patient_id=1, professional_id=1, starts_at='2027-04-06T08:00:00',
                           ends_at='2027-04-06T08:30:00', room='Gabinete anterior', reason='Cita de prueba'))
        db.commit()

    seed_rooms()
    rooms = {room['name']: room for room in client.get('/api/rooms').json()}
    assert rooms.keys() == {'Gabinete 1', 'Gabinete anterior'}
    previous_room = rooms['Gabinete anterior']
    url = f"/api/rooms/{previous_room['id']}"
    renamed = {'name': 'Gabinete Norte', 'color': '#0284c7', 'active': False}
    assert client.put(url, json=renamed).status_code == 200
    assert client.get('/api/appointments?day=2027-04-06').json()[0]['room'] == 'Gabinete Norte'
    assert client.post('/api/appointments', json={'patient_id': 1, 'professional_id': 1, 'starts_at': '2027-04-06T09:15',
                       'duration': 30, 'room': 'Gabinete Norte', 'reason': 'Revisión demo'}).status_code == 422
    assert client.put(f"/api/rooms/{rooms['Gabinete 1']['id']}", json={**renamed, 'name': 'Gabinete 1'}).status_code == 409


def test_accept_budget_atomically_updates_only_matching_pending_lines(client):
    budget = client.post('/api/patients/1/budgets', json={'title': 'Plan demo'}).json()
    url = f"/api/budgets/{budget['id']}"
    lines = [client.post(url + '/lines', json={'catalog_id': 1, 'teeth': [16], 'price_cents': 2500}).json() for _ in range(3)]
    cancelled = lines.pop()
    assert client.patch(f"/api/treatments/{cancelled['id']}/status",
                        json={'status': 'Cancelado', 'version': cancelled['version']}).status_code == 200
    versions = {str(line['id']): line['version'] for line in lines}
    assert client.post(url + '/accept', json={'versions': {str(lines[0]['id']): 1}}).status_code == 409
    assert client.post(url + '/accept', json={'versions': versions}).json() == {'accepted': 2}
    assert client.post(url + '/accept', json={'versions': versions}).status_code == 409
    details = client.get('/api/patients/1').json()
    saved = next(item for item in details['budgets'] if item['id'] == budget['id'])['lines']
    assert [(line['status'], line['version']) for line in saved] == [('Aceptado', 2), ('Aceptado', 2), ('Cancelado', 2)]
    history = client.get('/api/patients/1/history').json()
    assert {event['entity_id'] for event in history if event['details'].get('to') == 'Aceptado'} == {line['id'] for line in lines}


def test_cash_uses_madrid_day_boundaries(client):
    from backend.models.entities import Invoice, Payment
    with SessionLocal() as db:
        invoice = Invoice(budget_id=1, total_cents=15000)
        db.add(invoice)
        db.flush()
        db.add_all(Payment(invoice_id=invoice.id, amount_cents=1000, method='Bizum', reference=f'cash-demo-{index}', created_at=instant)
                   for index, instant in enumerate(['2026-03-28T22:59:59Z', '2026-03-28T23:00:00Z',
                                                  '2026-03-29T21:59:59Z', '2026-03-29T22:00:00Z']))
        db.commit()
    rows = client.get('/api/cash?day=2026-03-29').json()
    assert [row['reference'] for row in rows] == ['cash-demo-2', 'cash-demo-1']
    assert {row['patient_id'] for row in rows} == {1}


def test_backup_contains_restorable_database_and_documents(client, tmp_path: Path):
    document = client.get('/api/budgets/1/pdf').content
    assert client.post('/api/patients/1/documents', files={'file': ('demo.pdf', document, 'application/pdf')}).status_code == 200
    result = client.post('/api/backups')
    assert result.status_code == 200
    assert result.headers['cache-control'] == 'no-store'
    with ZipFile(BytesIO(result.content)) as backup:
        restored = tmp_path / 'restored.db'
        restored.write_bytes(backup.read('dentalis.db'))
        connection = sqlite3.connect(restored)
        try:
            assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
            assert connection.execute('SELECT COUNT(*) FROM sessions').fetchone() == (0,)
            name = connection.execute('SELECT path FROM documents').fetchone()[0]
            assert backup.read('documents/' + name) == document
        finally:
            connection.close()
    assert client.get('/api/auth/me').status_code == 200
    assert client.post('/api/users', json={'name': 'Recepción Demo', 'username': 'recepcion',
                                         'password': 'Pruebas-Dentalis-2026', 'role': 'recepcion'}).status_code == 200
    login = client.post('/api/auth/login', json={'username': 'recepcion', 'password': 'Pruebas-Dentalis-2026'}).json()
    client.headers['X-CSRF-Token'] = login['csrf']
    assert client.post('/api/backups').status_code == 403
    assert client.post('/api/rooms', json={'name': 'Gabinete 2', 'color': '#39775e'}).status_code == 403
    assert client.post('/api/budgets/1/accept', json={'versions': {'1': 1}}).status_code == 403
