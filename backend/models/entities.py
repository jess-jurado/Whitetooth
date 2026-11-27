from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON, Boolean
from backend.database import Base

def now():
    return datetime.utcnow().isoformat(timespec='seconds') + 'Z'

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    username = Column(String(80), unique=True, nullable=False)
    password = Column(Text, nullable=False)
    role = Column(String(30), nullable=False)
    active = Column(Boolean, default=True, nullable=False)

class LoginSession(Base):
    __tablename__ = 'sessions'
    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    csrf = Column(String(80), nullable=False)
    expires = Column(Integer, nullable=False)

class Patient(Base):
    __tablename__ = 'patients'
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    birth_date = Column(String(10), nullable=False)
    phone = Column(String(40), default='')
    email = Column(String(150), default='')
    allergies = Column(Text, default='')
    created_at = Column(String(30), default=now)

class Catalog(Base):
    __tablename__ = 'catalog'
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    category = Column(String(60), nullable=False)
    price_cents = Column(Integer, nullable=False)

class Budget(Base):
    __tablename__ = 'budgets'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False)
    title = Column(String(150), nullable=False)
    created_at = Column(String(30), default=now)

class Treatment(Base):
    __tablename__ = 'treatments'
    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey('budgets.id'), nullable=False)
    catalog_id = Column(Integer, ForeignKey('catalog.id'), nullable=False)
    name = Column(String(150), nullable=False)
    teeth = Column(JSON, nullable=False)
    surfaces = Column(JSON, nullable=False)
    price_cents = Column(Integer, nullable=False)
    notes = Column(Text, default='')
    status = Column(String(30), default='Presupuestado', nullable=False)
    version = Column(Integer, default=1, nullable=False)

class ClinicalEntry(Base):
    __tablename__ = 'clinical_entries'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    kind = Column(String(30), nullable=False)
    text = Column(Text, nullable=False)
    teeth = Column(JSON, default=list)
    surfaces = Column(JSON, default=list)
    created_at = Column(String(30), default=now)

class Room(Base):
    __tablename__ = 'rooms'
    id = Column(Integer, primary_key=True)
    name = Column(String(30), unique=True, nullable=False)
    color = Column(String(7), nullable=False)
    active = Column(Boolean, default=True, nullable=False)

class Appointment(Base):
    __tablename__ = 'appointments'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False)
    professional_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    starts_at = Column(String(19), nullable=False)
    ends_at = Column(String(19), nullable=False)
    room = Column(String(30), nullable=False)
    reason = Column(String(200), nullable=False)
    status = Column(String(30), default='Confirmada', nullable=False)

class Invoice(Base):
    __tablename__ = 'invoices'
    id = Column(Integer, primary_key=True)
    budget_id = Column(Integer, ForeignKey('budgets.id'), unique=True, nullable=False)
    total_cents = Column(Integer, nullable=False)
    created_at = Column(String(30), default=now)

class Payment(Base):
    __tablename__ = 'payments'
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('invoices.id'), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    method = Column(String(30), nullable=False)
    reference = Column(String(80), unique=True, nullable=False)
    created_at = Column(String(30), default=now)

class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey('patients.id'), nullable=False)
    name = Column(String(200), nullable=False)
    path = Column(String(80), nullable=False)
    media_type = Column(String(80), nullable=False)
    created_at = Column(String(30), default=now)

class Audit(Base):
    __tablename__ = 'audit'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    action = Column(String(100), nullable=False)
    entity = Column(String(60), nullable=False)
    entity_id = Column(Integer, nullable=False)
    details = Column(JSON, default=dict)
    created_at = Column(String(30), default=now)
