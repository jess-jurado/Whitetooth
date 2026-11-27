from concurrent.futures import ThreadPoolExecutor


def book(client, starts_at, room='Gabinete 1', patient_id=1, professional_id=1):
    response = client.post('/api/appointments', json={
        'patient_id': patient_id, 'professional_id': professional_id, 'starts_at': starts_at,
        'duration': 45, 'room': room, 'reason': 'Cita ficticia de reprogramación',
    })
    assert response.status_code == 200
    return response.json()


def move(client, appointment, starts_at, room=None):
    return client.patch(f"/api/appointments/{appointment['id']}/schedule", json={
        'expected_start': appointment['starts_at'],
        'expected_room': appointment['room'],
        'starts_at': starts_at,
        'room': room or appointment['room'],
    })


def test_move_between_months_retains_identity_duration_and_history(client):
    assert client.post('/api/rooms', json={'name': 'Gabinete 2', 'color': '#39775e'}).status_code == 200
    appointment = book(client, '2027-02-11T11:15')
    response = move(client, appointment, '2027-04-01T23:45', 'Gabinete 2')
    assert response.status_code == 200
    updated = response.json()
    assert updated == {**appointment, 'starts_at': '2027-04-01T23:45:00',
                       'ends_at': '2027-04-02T00:30:00', 'room': 'Gabinete 2'}
    for day in ['2027-04-01', '2027-04-02']:
        assert [row['id'] for row in client.get('/api/appointments', params={'day': day}).json()] == [appointment['id']]
    assert client.get('/api/appointments?day=2027-02-11').json() == []
    history = client.get('/api/audit').json()
    event = next(item for item in history if item['action'] == 'reschedule')
    assert event['entity_id'] == appointment['id']
    assert event['details']['previous']['starts_at'] == appointment['starts_at']
    assert event['details']['current']['room'] == updated['room']


def test_conflict_leaves_original_booking_and_cancellation_frees_slot(client):
    blocker = book(client, '2027-04-10T10:00', patient_id=2)
    appointment = book(client, '2027-04-09T10:00')
    assert move(client, appointment, '2027-04-10T10:15').status_code == 409
    assert client.get('/api/appointments?day=2027-04-09').json()[0]['starts_at'] == appointment['starts_at']
    assert client.patch(f"/api/appointments/{blocker['id']}", json={'status': 'Cancelada'}).status_code == 200
    assert move(client, blocker, '2027-04-14T10:00').status_code == 409
    assert move(client, appointment, '2027-04-10T10:15').status_code == 200


def test_parallel_moves_cannot_overwrite_a_newer_schedule(client):
    appointment = book(client, '2027-04-09T10:00')
    destinations = ['2027-04-12T10:00', '2027-04-13T10:00']
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda destination: move(client, appointment, destination), destinations))
    assert sorted(response.status_code for response in responses) == [200, 409]
    winning = next(response.json() for response in responses if response.status_code == 200)
    assert move(client, winning, '2027-04-14T10:00', 'Gabinete inexistente').status_code == 422
