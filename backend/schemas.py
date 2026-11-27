from datetime import date, datetime
from typing import List, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

class UserIn(Strict):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=256)
    role: Literal['admin', 'clinico', 'recepcion']

class PatientIn(Strict):
    name: str = Field(min_length=2, max_length=150)
    birth_date: date
    phone: str = Field(default='', max_length=40)
    email: str = Field(default='', max_length=150)
    allergies: str = Field(default='', max_length=2000)
    @field_validator('birth_date')
    @classmethod
    def past(cls, value):
        if value > date.today():
            raise ValueError('La fecha de nacimiento no puede ser futura')
        return value

class CatalogIn(Strict):
    name: str = Field(min_length=2, max_length=150)
    category: str = Field(min_length=2, max_length=60)
    price_cents: int = Field(ge=0, le=10000000)

class BudgetIn(Strict):
    title: str = Field(min_length=2, max_length=150)

class DentalSelection(Strict):
    teeth: List[int] = Field(default_factory=list, max_length=52)
    surfaces: List[Literal['M','D','V','L','O','I']] = Field(default_factory=list, max_length=6)
    @field_validator('teeth')
    @classmethod
    def fdi(cls, value):
        if any(not (1 <= n//10 <= 4 and 1 <= n%10 <= 8 or 5 <= n//10 <= 8 and 1 <= n%10 <= 5) for n in value):
            raise ValueError('Pieza FDI no válida')
        return sorted(set(value))

class TreatmentIn(DentalSelection):
    catalog_id: int
    price_cents: int = Field(ge=0, le=10000000)
    notes: str = Field(default='', max_length=2000)

class StateIn(Strict):
    status: Literal['Presupuestado','Aceptado','En curso','Realizado','Cancelado']
    version: int = Field(ge=1)

class EntryIn(DentalSelection):
    kind: Literal['Diagnóstico','Nota']
    text: str = Field(min_length=2, max_length=5000)

class AppointmentIn(Strict):
    patient_id: int
    professional_id: int
    starts_at: datetime
    duration: int = Field(ge=15, le=240)
    room: Literal['Gabinete 1','Gabinete 2','Gabinete 3']
    reason: str = Field(min_length=2, max_length=200)
    @field_validator('starts_at')
    @classmethod
    def local_time(cls, value):
        if value.tzinfo is not None:
            raise ValueError('Usa hora local Europe/Madrid sin zona')
        return value

class AppointmentState(Strict):
    status: Literal['Confirmada','En espera','Completada','Cancelada']

class PaymentIn(Strict):
    amount_cents: int = Field(gt=0, le=10000000)
    method: Literal['Tarjeta','Efectivo','Transferencia']
    reference: str = Field(min_length=8, max_length=80)
