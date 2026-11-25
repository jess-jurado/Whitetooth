from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from datetime import date
from pathlib import Path

from app.config import BASE_DIR
from app.database import init_db, get_db_connection
from app.backup_service import iniciar_servicio_respaldos
from app.routers import (
    pacientes, agenda, odontograma, presupuestos,
    cobros, facturacion, whatsapp, respaldos
)

app = FastAPI(
    title="Whitetooth - Gestión Clínica Dental",
    description="Sistema moderno de gestión dental para sustitución de MN Program",
    version="1.0.0"
)

# Static and Templates
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

templates = Jinja2Templates(directory="app/templates")

# Include Routers
app.include_router(pacientes.router)
app.include_router(agenda.router)
app.include_router(odontograma.router)
app.include_router(presupuestos.router)
app.include_router(cobros.router)
app.include_router(facturacion.router)
app.include_router(whatsapp.router)
app.include_router(respaldos.router)

@app.on_event("startup")
def startup_event():
    init_db()
    iniciar_servicio_respaldos()
    print("Whitetooth iniciado correctamente. Base de datos SQLite lista.")

@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    conn = get_db_connection()
    today_str = date.today().isoformat()
    current_year = date.today().year

    # Citas hoy
    total_citas_hoy = conn.execute("""
        SELECT COUNT(*) FROM citas WHERE date(fecha_hora_inicio) = ?;
    """, (today_str,)).fetchone()[0]

    citas_hoy = conn.execute("""
        SELECT c.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, p.telefono_movil as paciente_movil,
               g.nombre as gabinete_nombre, g.color as gabinete_color,
               u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM citas c
        JOIN pacientes p ON c.paciente_id = p.id
        JOIN gabinetes g ON c.gabinete_id = g.id
        LEFT JOIN usuarios u ON c.doctor_id = u.id
        WHERE date(c.fecha_hora_inicio) = ?
        ORDER BY c.fecha_hora_inicio ASC
    """, (today_str,)).fetchall()

    # Pacientes en sala de espera
    en_espera_count = sum(1 for c in citas_hoy if c["estado"] == "en_espera")
    en_consulta_count = sum(1 for c in citas_hoy if c["estado"] == "en_consulta")

    # Cobros hoy desglosados
    cobros_hoy_rows = conn.execute("""
        SELECT forma_cobro, SUM(importe) as total 
        FROM cobros 
        WHERE fecha_cobro = ? AND cobrado = 1
        GROUP BY forma_cobro;
    """, (today_str,)).fetchall()

    cobros_desglose = {r["forma_cobro"]: r["total"] for r in cobros_hoy_rows}
    total_cobrado_hoy = sum(cobros_desglose.values())

    # Indicadores globales
    total_pacientes = conn.execute("SELECT COUNT(*) FROM pacientes WHERE estado = 'alta';").fetchone()[0]
    
    # Presupuestos pendientes del año
    presupuestos_pendientes = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(total_presupuesto), 0.0) 
        FROM presupuestos 
        WHERE anio = ? AND estado = 'pendiente';
    """, (current_year,)).fetchone()

    clinica = conn.execute("SELECT * FROM clinica LIMIT 1;").fetchone()

    conn.close()

    return templates.TemplateResponse(request=request, name="index.html", context={
        "clinica": clinica,
        "today_str": today_str,
        "total_citas_hoy": total_citas_hoy,
        "citas_hoy": citas_hoy,
        "en_espera_count": en_espera_count,
        "en_consulta_count": en_consulta_count,
        "cobros_desglose": cobros_desglose,
        "total_cobrado_hoy": round(total_cobrado_hoy, 2),
        "total_pacientes": total_pacientes,
        "num_presupuestos_pend": presupuestos_pendientes[0],
        "total_presupuestos_pend": round(presupuestos_pendientes[1], 2)
    })
