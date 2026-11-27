from concurrent.futures import ThreadPoolExecutor
from backend.database import SessionLocal
from backend.models.entities import Treatment

def create_line(c):
    b=c.post('/api/patients/1/budgets',json={'title':'Plan de prueba'}).json()
    r=c.post(f"/api/budgets/{b['id']}/lines",json={'catalog_id':1,'teeth':[16,26],'surfaces':['O','M'],'price_cents':17000,'notes':'Dos piezas, precio total de línea'})
    assert r.status_code==200
    return b,r.json()

def advance(c,line):
    for state in ['Aceptado','En curso','Realizado']:
        r=c.patch(f"/api/treatments/{line['id']}/status",json={'status':state,'version':line['version']})
        assert r.status_code==200
        line=r.json()
    return line

def test_complete_clinical_flow_and_persistence(client):
    c=client
    p=c.post('/api/patients',json={'name':'Paciente Prueba','birth_date':'1990-03-20','allergies':'Dato ficticio'})
    assert p.status_code==200
    entry=c.post('/api/patients/1/entries',json={'kind':'Diagnóstico','text':'Caries de prueba','teeth':[16],'surfaces':['O']})
    assert entry.status_code==200
    b,line=create_line(c)
    assert c.patch(f"/api/treatments/{line['id']}/status",json={'status':'Realizado','version':1}).status_code==409
    advance(c,line)
    with SessionLocal() as db:
        saved=db.get(Treatment,line['id'])
        assert saved.status=='Realizado' and saved.teeth==[16,26]
    detail=c.get('/api/patients/1').json()
    assert next(x for x in detail['budgets'] if x['id']==b['id'])['lines'][0]['status']=='Realizado'
    history=c.get('/api/patients/1/history').json()
    assert any(x['details'].get('to')=='Realizado' for x in history)
    invoice=c.post(f"/api/budgets/{b['id']}/invoice").json()
    assert invoice['total_cents']==17000
    url=f"/api/invoices/{invoice['id']}/payments"
    payment={'amount_cents':7000,'method':'Tarjeta','reference':'test-payment-001'}
    first=c.post(url,json=payment)
    assert first.status_code==200
    assert c.post(url,json=payment).json()['id']==first.json()['id']
    assert c.post(url,json={**payment,'reference':'test-payment-002','amount_cents':10001}).status_code==409
    assert c.post(url,json={**payment,'reference':'test-payment-003','amount_cents':10000}).status_code==200
    assert c.post(f"/api/budgets/{b['id']}/lines",json={'catalog_id':1,'teeth':[16],'price_cents':100}).status_code==409
    assert c.post(f"/api/budgets/{b['id']}/invoice").status_code==409
    assert c.get('/api/dashboard').json()['pending']==0

def test_auth_csrf_and_roles(client):
    c=client
    assert c.post('/api/users',json={'name':'Recepción Demo','username':'recepcion','password':'Password-Demo-123','role':'recepcion'}).status_code==200
    c.headers.pop('X-CSRF-Token')
    assert c.post('/api/patients',json={'name':'Demo Uno','birth_date':'2000-01-01'}).status_code==403
    login=c.post('/api/auth/login',json={'username':'recepcion','password':'Password-Demo-123'}).json()
    c.headers['X-CSRF-Token']=login['csrf']
    assert c.get('/api/audit').status_code==403
    assert c.post('/api/patients/1/entries',json={'kind':'Nota','text':'test'}).status_code==403
    assert c.get('/api/budgets/1/pdf').status_code==403
    d=c.get('/api/patients/1').json()
    assert d['entries']==[] and d['documents']==[] and d['patient']['allergies']==''
    assert d['budgets'][0]['lines'][0]['teeth']==[]
    assert c.post('/api/auth/logout').status_code==200
    assert c.get('/api/patients').status_code==401

def test_fdi_validation_and_concurrency(client):
    b,line=create_line(client)
    for tooth in [0,19,49,56,89,99]:
        assert client.post(f"/api/budgets/{b['id']}/lines",json={'catalog_id':1,'teeth':[tooth],'price_cents':100}).status_code==422
    assert client.post(f"/api/budgets/{b['id']}/lines",json={'catalog_id':1,'teeth':[55,85],'surfaces':['BAD'],'price_cents':100}).status_code==422
    assert client.patch(f"/api/treatments/{line['id']}/status",json={'status':'Aceptado','version':1}).status_code==200
    assert client.patch(f"/api/treatments/{line['id']}/status",json={'status':'Cancelado','version':1}).status_code==409

def test_appointment_conflict_and_cancellation(client):
    assert client.post('/api/rooms', json={'name': 'Gabinete 2', 'color': '#39775e'}).status_code == 200
    a={'patient_id':1,'professional_id':1,'starts_at':'2026-12-01T09:00','duration':60,'room':'Gabinete 1','reason':'Revisión demo'}
    r=client.post('/api/appointments',json=a)
    assert r.status_code==200
    assert client.post('/api/appointments',json={**a,'starts_at':'2026-12-01T09:30','room':'Gabinete 2'}).status_code==409
    assert client.post('/api/appointments',json={**a,'starts_at':'2026-12-01T10:00'}).status_code==200
    assert client.patch(f"/api/appointments/{r.json()['id']}",json={'status':'Cancelada'}).status_code==200
    assert client.post('/api/appointments',json=a).status_code==200
    assert client.patch(f"/api/appointments/{r.json()['id']}",json={'status':'Confirmada'}).status_code==409

def test_documents_and_pdf(client):
    r=client.get('/api/budgets/1/pdf')
    assert r.status_code==200 and r.content.startswith(b'%PDF-')
    upload=client.post('/api/patients/1/documents',files={'file':('demo.pdf',r.content,'application/pdf')})
    assert upload.status_code==200 and 'path' not in upload.json()
    assert client.get(f"/api/documents/{upload.json()['id']}/download").content==r.content
    assert client.post('/api/patients/1/documents',files={'file':('fake.pdf',b'<script>bad</script>','application/pdf')}).status_code==422
    assert client.post('/api/patients/1/documents',files={'file':('huge.pdf',b'%PDF-'+b'x'*(10*1024*1024),'application/pdf')}).status_code==413

def test_parallel_payment_cannot_overcharge(client):
    b,line=create_line(client);advance(client,line)
    invoice=client.post(f"/api/budgets/{b['id']}/invoice").json()
    def pay(ref):
        return client.post(f"/api/invoices/{invoice['id']}/payments",json={'amount_cents':12000,'method':'Tarjeta','reference':ref}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        codes=list(executor.map(pay,['parallel-001','parallel-002']))
    assert sorted(codes)==[200,409]

def test_cancellation_and_early_invoice(client):
    b,line=create_line(client)
    assert client.post(f"/api/budgets/{b['id']}/invoice").status_code==409
    assert client.patch(f"/api/treatments/{line['id']}/status",json={'status':'Cancelado','version':1}).status_code==200
    assert client.post(f"/api/budgets/{b['id']}/invoice").status_code==409

def test_validation_and_audit(client):
    assert client.post('/api/patients',json={'name':'Future Demo','birth_date':'2099-01-01'}).status_code==422
    assert client.get('/api/patients/9999').status_code==404
    client.get('/api/patients/1')
    rows=client.get('/api/audit').json()
    assert any(a['action']=='read' and a['entity']=='patient' for a in rows)
    assert all('password' not in u for u in client.get('/api/users').json())

def test_calendar_date_range_includes_all_selected_days(client):
    a={'patient_id':1,'professional_id':1,'starts_at':'2026-12-01T09:00','duration':30,'room':'Gabinete 1','reason':'Calendario demo'}
    for start in ['2026-11-30T23:45','2026-12-01T09:00','2026-12-03T10:00','2026-12-04T00:00']:
        assert client.post('/api/appointments',json={**a,'starts_at':start}).status_code==200
    r=client.get('/api/appointments?start=2026-12-01&end=2026-12-03')
    assert r.status_code==200
    assert [a['starts_at'] for a in r.json()]==['2026-11-30T23:45:00','2026-12-01T09:00:00','2026-12-03T10:00:00']
    assert len(client.get('/api/appointments?day=2026-12-03').json())==1
    for query in ['start=2026-12-03&end=2026-12-01','start=2026-01-01&end=2026-12-31','start=2026-12-01','day=2026-12-01&start=2026-12-01&end=2026-12-02','start=not-a-date&end=2026-12-01']:
        assert client.get('/api/appointments?'+query).status_code==422
