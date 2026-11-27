import os
from datetime import date
from backend.database import SessionLocal
from backend.models.entities import User, Patient, Catalog, Budget, Treatment, ClinicalEntry, Appointment
from backend.services.security import hash_password

def seed():
    with SessionLocal() as db:
        if db.query(User).first():
            return
        password = os.getenv('DENTALIS_ADMIN_PASSWORD', '')
        if len(password) < 12:
            raise RuntimeError('Define DENTALIS_ADMIN_PASSWORD con al menos 12 caracteres para el primer arranque')
        admin = User(name='Administración', username='admin', role='admin', password=hash_password(password))
        db.add(admin)
        db.flush()
        if os.getenv('DENTALIS_DEMO') == '1':
            people = [('Lucía Martín Demo','1991-04-18','Sin alergias conocidas'),('Carlos Vega Demo','1985-09-02','Penicilina (dato ficticio)'),('Elena Ruiz Demo','1978-12-15',''),('Mateo Torres Demo','2016-06-23',''),('Sofía Navarro Demo','1994-03-08','')]
            patients = [Patient(name=n,birth_date=b,phone='600 000 000',email='demo@example.invalid',allergies=a) for n,b,a in people]
            catalog = [Catalog(name=n,category=c,price_cents=p) for n,c,p in [('Obturación de composite','Conservadora',8500),('Higiene bucodental','Prevención',6000),('Endodoncia multirradicular','Endodoncia',24000),('Corona de zirconio','Prótesis',42000),('Extracción simple','Cirugía',9000),('Revisión y diagnóstico','Prevención',3500)]]
            db.add_all(patients + catalog)
            db.flush()
            b = Budget(patient_id=patients[0].id,title='Plan de salud oral · noviembre')
            db.add(b)
            db.flush()
            db.add_all([Treatment(budget_id=b.id,catalog_id=catalog[0].id,name=catalog[0].name,teeth=[16],surfaces=['O'],price_cents=8500,status='Aceptado',notes='Restauración oclusal'),Treatment(budget_id=b.id,catalog_id=catalog[1].id,name=catalog[1].name,teeth=[],surfaces=[],price_cents=6000,status='Realizado',notes='Tratamiento general')])
            db.add(ClinicalEntry(patient_id=patients[0].id,author_id=admin.id,kind='Diagnóstico',text='Lesión de caries oclusal en 16. Caso ficticio para demostración.',teeth=[16],surfaces=['O']))
            for i, p in enumerate(patients):
                hour = 9 + i
                db.add(Appointment(patient_id=p.id, professional_id=admin.id, starts_at=f'{date.today()}T{hour:02d}:00:00',ends_at=f'{date.today()}T{hour:02d}:45:00',room='Gabinete 1',reason=['Revisión inicial','Higiene bucodental','Revisión de prótesis','Odontopediatría','Obturación'][i]))
        db.commit()
