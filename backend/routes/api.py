import os
import secrets
import shutil
import sqlite3
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import func, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend.database import get_db, STORAGE, engine
from backend.models.entities import User, LoginSession, Patient, Catalog, Budget, Treatment, ClinicalEntry, Appointment, Invoice, Payment, Document, Audit, Room
from backend.schemas import LoginIn, UserIn, PatientIn, CatalogIn, BudgetIn, TreatmentIn, StateIn, EntryIn, AppointmentIn, AppointmentReschedule, AppointmentState, PaymentIn, RoomIn, AcceptBudgetIn
from backend.services.security import current_user, require, audit, hash_password, verify_password, token_hash
from backend.services.pdf import budget_pdf
from backend.services.backup import snapshot
from backend.services.reminders import prepare_reminder
from backend.services.scheduled_backup import backup_status

router = APIRouter(prefix='/api')
login_attempts = defaultdict(list)

def obj(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns if c.name not in ('password','path')}

def get(db, model, id):
    result = db.get(model,id)
    if not result:
        raise HTTPException(404,'Registro no encontrado')
    return result

def clinical(user):
    require(user,'admin','clinico')

def lock(db, model, id):
    # Serialize aggregate changes in SQLite; row locks in PostgreSQL.
    db.execute(update(model).where(model.id==id).values(id=id))
    return get(db,model,id)

def treatment_rows(db,budget_id):
    return db.query(Treatment).filter_by(budget_id=budget_id).order_by(Treatment.id).all()

@router.post('/auth/login')
def login(data:LoginIn, request:Request, response:Response, db:Session=Depends(get_db)):
    key = request.client.host if request.client else 'local'
    now = time.time()
    login_attempts[key] = [t for t in login_attempts[key] if t > now-300]
    if len(login_attempts[key]) >= 10:
        raise HTTPException(429,'Demasiados intentos. Espera cinco minutos')
    login_attempts[key].append(now)
    user = db.query(User).filter_by(username=data.username).first()
    if not user or not user.active or not verify_password(data.password,user.password):
        raise HTTPException(401,'Usuario o contraseña incorrectos')
    login_attempts[key] = []
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(LoginSession(token=token_hash(token),csrf=csrf,user_id=user.id,expires=int(now)+28800))
    audit(db,user,'login','user',user.id)
    db.commit()
    response.set_cookie('dentalis_session',token,httponly=True,samesite='strict',secure=os.getenv('DENTALIS_SECURE_COOKIE')=='1',max_age=28800)
    return {'user':obj(user),'csrf':csrf}

@router.get('/auth/me')
def me(request:Request,user=Depends(current_user)):
    return {'user':obj(user),'csrf':request.state.session.csrf}

@router.post('/auth/logout')
def logout(request:Request,response:Response,user=Depends(current_user),db:Session=Depends(get_db)):
    db.delete(request.state.session)
    audit(db,user,'logout','user',user.id)
    db.commit()
    response.delete_cookie('dentalis_session')
    return {'ok':True}

@router.get('/users')
def users(user=Depends(current_user),db:Session=Depends(get_db)):
    return [obj(u) for u in db.query(User).order_by(User.id)]

@router.post('/users')
def add_user(data:UserIn,user=Depends(current_user),db:Session=Depends(get_db)):
    require(user,'admin')
    row = User(**data.model_dump(exclude={'password'}),password=hash_password(data.password))
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'El usuario ya existe')
    audit(db,user,'create','user',row.id,{'role':row.role})
    db.commit()
    return obj(row)

@router.get('/patients')
def patients(q:str='',user=Depends(current_user),db:Session=Depends(get_db)):
    rows = db.query(Patient).filter(Patient.name.ilike('%'+q[:150]+'%')).order_by(Patient.name).all()
    audit(db,user,'list','patient',0)
    db.commit()
    return [dict(obj(p),allergies=p.allergies if user.role!='recepcion' else '') for p in rows]

@router.post('/patients')
def add_patient(data:PatientIn,user=Depends(current_user),db:Session=Depends(get_db)):
    if user.role=='recepcion' and data.allergies:
        raise HTTPException(403,'Solo el equipo clínico puede registrar alergias')
    row=Patient(**data.model_dump(mode='json'))
    db.add(row)
    db.flush()
    audit(db,user,'create','patient',row.id)
    db.commit()
    return obj(row)

@router.put('/patients/{id}')
def edit_patient(id:int,data:PatientIn,user=Depends(current_user),db:Session=Depends(get_db)):
    row=get(db,Patient,id)
    for k,v in data.model_dump(mode='json').items():
        if k=='allergies' and user.role=='recepcion':
            continue
        setattr(row,k,v)
    audit(db,user,'update','patient',id)
    db.commit()
    return dict(obj(row),allergies=row.allergies if user.role!='recepcion' else '')

@router.get('/patients/{id}')
def patient_detail(id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    patient=get(db,Patient,id)
    budgets=db.query(Budget).filter_by(patient_id=id).order_by(Budget.id.desc()).all()
    result={'patient':obj(patient),'budgets':[dict(obj(b),lines=[obj(t) for t in treatment_rows(db,b.id)]) for b in budgets]}
    result['entries']=[dict(obj(e),author=get(db,User,e.author_id).name) for e in db.query(ClinicalEntry).filter_by(patient_id=id).order_by(ClinicalEntry.id.desc())] if user.role!='recepcion' else []
    result['documents']=[obj(d) for d in db.query(Document).filter_by(patient_id=id)] if user.role!='recepcion' else []
    invoices=db.query(Invoice).join(Budget).filter(Budget.patient_id==id).all()
    result['invoices']=[dict(obj(i),payments=[obj(p) for p in db.query(Payment).filter_by(invoice_id=i.id)]) for i in invoices]
    if user.role=='recepcion':
        result['patient']['allergies']=''
        for b in result['budgets']:
            for line in b['lines']:
                line['notes']=''; line['teeth']=[]; line['surfaces']=[]
    audit(db,user,'read','patient',id)
    db.commit()
    return result

@router.get('/catalog')
def catalog(user=Depends(current_user),db:Session=Depends(get_db)):
    return [obj(c) for c in db.query(Catalog).order_by(Catalog.category,Catalog.name)]

@router.post('/catalog')
def add_catalog(data:CatalogIn,user=Depends(current_user),db:Session=Depends(get_db)):
    require(user,'admin')
    row=Catalog(**data.model_dump()); db.add(row); db.flush()
    audit(db,user,'create','catalog',row.id); db.commit()
    return obj(row)

@router.post('/patients/{id}/budgets')
def add_budget(id:int,data:BudgetIn,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user); get(db,Patient,id)
    row=Budget(patient_id=id,**data.model_dump()); db.add(row); db.flush()
    audit(db,user,'create','budget',row.id); db.commit()
    return obj(row)

@router.post('/budgets/{id}/lines')
def add_line(id:int,data:TreatmentIn,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user); lock(db,Budget,id)
    if db.query(Invoice).filter_by(budget_id=id).first():
        raise HTTPException(409,'El presupuesto facturado está cerrado')
    catalog=get(db,Catalog,data.catalog_id)
    row=Treatment(budget_id=id,name=catalog.name,**data.model_dump()); db.add(row); db.flush()
    audit(db,user,'create','treatment',row.id); db.commit()
    return obj(row)

@router.post('/budgets/{id}/accept')
def accept_budget(id: int, data: AcceptBudgetIn, user=Depends(current_user), db: Session=Depends(get_db)):
    clinical(user)
    lock(db, Budget, id)
    if db.query(Invoice).filter_by(budget_id=id).first():
        raise HTTPException(409, 'El presupuesto facturado está cerrado')
    pending = [line for line in treatment_rows(db, id) if line.status == 'Presupuestado']
    if {line.id: line.version for line in pending} != data.versions:
        raise HTTPException(409, 'El presupuesto cambió. Vuelve a abrir la ficha y revisa las líneas pendientes')
    for line in pending:
        set_treatment_status(db, user, line, 'Aceptado')
    db.commit()
    return {'accepted': len(pending)}


def set_treatment_status(db, user, line, status):
    previous = line.status
    line.status = status
    line.version += 1
    audit(db, user, 'status', 'treatment', line.id, {'from': previous, 'to': status})


@router.patch('/treatments/{id}/status')
def change_status(id:int,data:StateIn,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user)
    row=get(db,Treatment,id); lock(db,Budget,row.budget_id); db.refresh(row)
    if db.query(Invoice).filter_by(budget_id=row.budget_id).first():
        raise HTTPException(409,'El presupuesto facturado está cerrado')
    if row.version!=data.version:
        raise HTTPException(409,'Otro usuario ha modificado el tratamiento. Recarga la ficha')
    transitions={'Presupuestado':['Aceptado','Cancelado'],'Aceptado':['En curso','Cancelado'],'En curso':['Realizado','Cancelado'],'Realizado':[],'Cancelado':[]}
    if data.status not in transitions[row.status]:
        raise HTTPException(409,'Transición de estado no permitida')
    set_treatment_status(db, user, row, data.status)
    # History references the treatment; no duplicated clinical treatment record.
    db.commit(); return obj(row)

@router.post('/patients/{id}/entries')
def add_entry(id:int,data:EntryIn,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user); get(db,Patient,id)
    row=ClinicalEntry(patient_id=id,author_id=user.id,**data.model_dump()); db.add(row); db.flush()
    audit(db,user,'create','clinical_entry',row.id); db.commit()
    return obj(row)

@router.get('/patients/{id}/history')
def history(id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user); get(db,Patient,id)
    ids=[t.id for t in db.query(Treatment).join(Budget).filter(Budget.patient_id==id)]
    rows=db.query(Audit).filter(Audit.entity=='treatment',Audit.entity_id.in_(ids)).order_by(Audit.id.desc()).all()
    audit(db,user,'read_history','patient',id); db.commit()
    return [dict(obj(a),treatment=get(db,Treatment,a.entity_id).name,author=get(db,User,a.user_id).name) for a in rows]

@router.get('/budgets/{id}/pdf')
def pdf(id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user)
    b=get(db,Budget,id)
    content=budget_pdf(b,get(db,Patient,b.patient_id),treatment_rows(db,id))
    audit(db,user,'export','budget',id); db.commit()
    return Response(content,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="presupuesto-{id}.pdf"'})

@router.post('/budgets/{id}/invoice')
def invoice(id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    lock(db,Budget,id)
    if db.query(Invoice).filter_by(budget_id=id).first():
        raise HTTPException(409,'Ya existe un documento de cobro')
    lines=treatment_rows(db,id)
    if not lines or any(t.status not in ('Realizado','Cancelado') for t in lines) or not any(t.status=='Realizado' for t in lines):
        raise HTTPException(409,'Completa los tratamientos antes de emitir el documento de cobro')
    row=Invoice(budget_id=id,total_cents=sum(t.price_cents for t in lines if t.status=='Realizado'))
    db.add(row); db.flush(); audit(db,user,'issue_demo_invoice','invoice',row.id); db.commit()
    return obj(row)

@router.post('/invoices/{id}/payments')
def payment(id:int,data:PaymentIn,user=Depends(current_user),db:Session=Depends(get_db)):
    invoice=lock(db,Invoice,id)
    existing=db.query(Payment).filter_by(reference=data.reference).first()
    if existing:
        if existing.invoice_id==id and existing.amount_cents==data.amount_cents and existing.method==data.method:
            return obj(existing)
        raise HTTPException(409,'La referencia ya corresponde a otro cobro')
    paid=sum(p.amount_cents for p in db.query(Payment).filter_by(invoice_id=id))
    if paid+data.amount_cents>invoice.total_cents:
        raise HTTPException(409,'El cobro supera el saldo pendiente')
    row=Payment(invoice_id=id,**data.model_dump()); db.add(row); db.flush()
    audit(db,user,'create','payment',row.id); db.commit(); return obj(row)

@router.get('/cash')
def daily_cash(day: date, user=Depends(current_user), db: Session=Depends(get_db)):
    madrid = ZoneInfo('Europe/Madrid')
    start = datetime(day.year, day.month, day.day, tzinfo=madrid)
    end = start + timedelta(days=1)
    lower, upper = (moment.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') for moment in (start, end))
    rows = (db.query(Payment, Patient.id, Patient.name)
            .join(Invoice, Payment.invoice_id == Invoice.id)
            .join(Budget, Invoice.budget_id == Budget.id)
            .join(Patient, Budget.patient_id == Patient.id)
            .filter(Payment.created_at >= lower, Payment.created_at < upper)
            .order_by(Payment.created_at.desc(), Payment.id.desc()))
    return [dict(obj(payment), patient_id=patient_id, patient=name) for payment, patient_id, name in rows]


def lock_agenda(db):
    # Room edits and bookings use the same lock, including across different rooms.
    first = db.query(User.id).order_by(User.id).first()
    lock(db, User, first.id)


@router.get('/rooms')
def list_rooms(user=Depends(current_user), db: Session=Depends(get_db)):
    return [obj(room) for room in db.query(Room).order_by(Room.id)]


def save_room(db, user, data, room=None):
    name_in_use = db.query(Room).filter(func.lower(Room.name) == data.name.lower())
    if room is not None:
        name_in_use = name_in_use.filter(Room.id != room.id)
    if name_in_use.first():
        raise HTTPException(409, 'Ya existe un gabinete con ese nombre')
    if room is None:
        room = Room(name=data.name, color=data.color)
        db.add(room)
        action = 'create'
    else:
        action = 'update'
        if room.active and not data.active and db.query(Room).filter_by(active=True).count() == 1:
            raise HTTPException(409, 'Mantén al menos un gabinete activo')
        if room.name != data.name:
            db.execute(update(Appointment).where(Appointment.room == room.name).values(room=data.name))
    previous_name = room.name
    room.name = data.name
    room.color = data.color
    room.active = data.active
    db.flush()
    audit(db, user, action, 'room', room.id, {'previous_name': previous_name, 'name': room.name, 'active': room.active})
    db.commit()
    return obj(room)


@router.post('/rooms')
def create_room(data: RoomIn, user=Depends(current_user), db: Session=Depends(get_db)):
    require(user, 'admin')
    lock_agenda(db)
    return save_room(db, user, data)


@router.put('/rooms/{id}')
def update_room(id: int, data: RoomIn, user=Depends(current_user), db: Session=Depends(get_db)):
    require(user, 'admin')
    lock_agenda(db)
    return save_room(db, user, data, get(db, Room, id))


@router.get('/backups/status')
def scheduled_backup_status(request: Request, user=Depends(current_user)):
    require(user, 'admin')
    state = request.app.state
    return backup_status(state.backup_schedule, state.backup_config_error, state.backup_error)


@router.post('/backups')
def create_backup(user=Depends(current_user), db: Session=Depends(get_db)):
    require(user, 'admin')
    if engine.dialect.name != 'sqlite' or not engine.url.database or engine.url.database == ':memory:':
        raise HTTPException(409, 'La copia local está disponible para SQLite en disco')
    # Release the authentication read transaction before taking the snapshot.
    audit(db, user, 'export', 'backup', 0)
    db.commit()
    directory = Path(tempfile.mkdtemp(prefix='dentalis-backup-', dir=STORAGE))
    try:
        archive = snapshot(directory)
    except (OSError, sqlite3.Error, ValueError):
        shutil.rmtree(directory, ignore_errors=True)
        raise HTTPException(500, 'No se pudo completar la copia de seguridad')
    return FileResponse(archive, media_type='application/zip', filename=f'dentalis-copia-{date.today()}.zip',
                        background=BackgroundTask(shutil.rmtree, directory, ignore_errors=True))


@router.get('/appointments')
def appointments(day:Optional[date]=None,start:Optional[date]=None,end:Optional[date]=None,user=Depends(current_user),db:Session=Depends(get_db)):
    if day is not None:
        if start is not None or end is not None:
            raise HTTPException(422,'Usa un día o un intervalo, no ambos')
        start=end=day
    if start is None or end is None or end < start or (end-start).days > 61:
        raise HTTPException(422,'Selecciona un intervalo válido de hasta 62 días')
    rows=db.query(Appointment).filter(Appointment.starts_at < str(end+timedelta(days=1)),Appointment.ends_at > str(start)+'T00:00:00').order_by(Appointment.starts_at,Appointment.id)
    return [dict(obj(a),patient=get(db,Patient,a.patient_id).name,professional=get(db,User,a.professional_id).name) for a in rows]

def check_appointment_slot(db, starts_at, ends_at, room, patient_id, professional_id, excluded_id=None):
    if not db.query(Room).filter_by(name=room, active=True).first():
        raise HTTPException(422, 'Selecciona un gabinete activo')
    professional = get(db, User, professional_id)
    if professional.role not in ('admin', 'clinico') or not professional.active:
        raise HTTPException(422, 'Profesional no válido')

    collisions = db.query(Appointment).filter(
        Appointment.status != 'Cancelada',
        Appointment.starts_at < ends_at,
        Appointment.ends_at > starts_at,
        (Appointment.professional_id == professional_id)
        | (Appointment.room == room)
        | (Appointment.patient_id == patient_id),
    )
    if excluded_id is not None:
        collisions = collisions.filter(Appointment.id != excluded_id)
    if collisions.first():
        raise HTTPException(409, 'Horario ocupado para el paciente, profesional o gabinete')


def appointment_period(start, duration):
    try:
        end = start + duration
    except OverflowError:
        raise HTTPException(422, 'La cita debe terminar en una fecha válida')
    return start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds')


@router.post('/appointments')
def add_appointment(data: AppointmentIn, user=Depends(current_user), db: Session=Depends(get_db)):
    get(db, Patient, data.patient_id)
    lock_agenda(db)
    start, end = appointment_period(data.starts_at, timedelta(minutes=data.duration))
    check_appointment_slot(db, start, end, data.room, data.patient_id, data.professional_id)
    row = Appointment(**data.model_dump(exclude={'duration', 'starts_at'}), starts_at=start, ends_at=end)
    db.add(row)
    db.flush()
    audit(db, user, 'create', 'appointment', row.id)
    db.commit()
    return obj(row)


@router.post('/appointments/{id}/whatsapp-draft')
def appointment_whatsapp_draft(id: int, user=Depends(current_user), db: Session=Depends(get_db)):
    appointment = get(db, Appointment, id)
    if appointment.status not in ('Confirmada', 'En espera'):
        raise HTTPException(409, 'Esta cita ya no admite recordatorios')
    patient = get(db, Patient, appointment.patient_id)
    enabled = os.getenv('DENTALIS_WHATSAPP_ENABLED') == '1' and os.getenv('DENTALIS_DEMO') != '1'
    clinic = os.getenv('DENTALIS_CLINIC_NAME', '').strip() or 'tu clínica'
    result = prepare_reminder(appointment, patient, clinic, enabled)
    audit(db, user, 'prepare_whatsapp_draft', 'appointment', id)
    db.commit()
    return result


@router.patch('/appointments/{id}/schedule')
def reschedule_appointment(id: int, data: AppointmentReschedule, user=Depends(current_user), db: Session=Depends(get_db)):
    lock_agenda(db)
    row = get(db, Appointment, id)
    if row.status not in ('Confirmada', 'En espera'):
        raise HTTPException(409, 'Solo se pueden mover citas confirmadas o en espera')
    if (row.starts_at, row.room) != (data.expected_start, data.expected_room):
        raise HTTPException(409, 'La cita ya cambió de horario o gabinete. Vuelve a seleccionarla tras actualizar la agenda')

    old_start = datetime.fromisoformat(row.starts_at)
    duration = datetime.fromisoformat(row.ends_at) - old_start
    start, end = appointment_period(data.starts_at, duration)
    if (row.starts_at, row.room) == (start, data.room):
        return obj(row)
    check_appointment_slot(db, start, end, data.room, row.patient_id, row.professional_id, excluded_id=row.id)

    previous = {'starts_at': row.starts_at, 'ends_at': row.ends_at, 'room': row.room}
    row.starts_at, row.ends_at, row.room = start, end, data.room
    current = {'starts_at': start, 'ends_at': end, 'room': data.room}
    audit(db, user, 'reschedule', 'appointment', id, {'previous': previous, 'current': current})
    db.commit()
    return obj(row)


@router.patch('/appointments/{id}')
def appointment_status(id:int,data:AppointmentState,user=Depends(current_user),db:Session=Depends(get_db)):
    lock_agenda(db)
    row=get(db,Appointment,id)
    transitions={'Confirmada':['En espera','Completada','Cancelada'],'En espera':['Completada','Cancelada'],'Completada':[],'Cancelada':[]}
    if data.status not in transitions[row.status]:
        raise HTTPException(409,'Cambio de cita no permitido')
    row.status=data.status; audit(db,user,'status','appointment',id,{'to':row.status}); db.commit(); return obj(row)


@router.post('/patients/{id}/documents')
async def upload(id:int,file:UploadFile=File(...),user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user); get(db,Patient,id)
    content=await file.read(10*1024*1024+1)
    if not content or len(content)>10*1024*1024:
        raise HTTPException(413,'El archivo debe ocupar entre 1 byte y 10 MB')
    media='application/pdf' if content.startswith(b'%PDF-') else 'image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if content.startswith(b'\xff\xd8\xff') else None
    if not media:
        raise HTTPException(422,'Admite PDF, PNG y JPEG')
    name=Path(file.filename or 'documento').name[:200]
    path=secrets.token_hex(24)
    (STORAGE/path).write_bytes(content)
    row=Document(patient_id=id,name=name,path=path,media_type=media); db.add(row)
    try:
        db.flush(); audit(db,user,'upload','document',row.id); db.commit()
    except Exception:
        (STORAGE/path).unlink(missing_ok=True)
        raise
    return obj(row)

@router.get('/documents/{id}/download')
def download(id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    clinical(user); row=get(db,Document,id)
    audit(db,user,'download','document',id); db.commit()
    return FileResponse(STORAGE/row.path,media_type=row.media_type,filename=row.name)

@router.get('/audit')
def audit_log(user=Depends(current_user),db:Session=Depends(get_db)):
    require(user,'admin')
    return [dict(obj(a),author=get(db,User,a.user_id).name) for a in db.query(Audit).order_by(Audit.id.desc()).limit(200)]

@router.get('/dashboard')
def dashboard(user=Depends(current_user),db:Session=Depends(get_db)):
    invoices=db.query(Invoice).all(); payments=db.query(Payment).all()
    return {'patients':db.query(Patient).count(),'appointments':db.query(Appointment).filter(Appointment.starts_at.startswith(str(date.today())),Appointment.status!='Cancelada').count(),'planned':db.query(Treatment).filter(Treatment.status.in_(['Aceptado','En curso'])).count(),'collected':sum(p.amount_cents for p in payments),'pending':sum(i.total_cents for i in invoices)-sum(p.amount_cents for p in payments)}
