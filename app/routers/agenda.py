from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime, date, timedelta
import calendar
from app.database import get_db_connection

router = APIRouter(prefix="/agenda", tags=["agenda"])

MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

def generar_calendario_mes(year: int, month: int, dias_con_citas: set, fecha_seleccionada: str):
    """Genera la estructura de semanas y días para el mini-calendario."""
    cal = calendar.Calendar(firstweekday=0) # Lunes = 0
    dias_matriz = cal.monthdayscalendar(year, month)
    hoy_str = date.today().isoformat()

    semanas = []
    for week in dias_matriz:
        semana = []
        for day in week:
            if day == 0:
                semana.append(None)
            else:
                iso_fecha = f"{year:04d}-{month:02d}-{day:02d}"
                semana.append({
                    "dia": day,
                    "fecha": iso_fecha,
                    "es_hoy": iso_fecha == hoy_str,
                    "es_seleccionado": iso_fecha == fecha_seleccionada,
                    "tiene_citas": iso_fecha in dias_con_citas
                })
        semanas.append(semana)

    return {
        "year": year,
        "month": month,
        "nombre_mes": MESES_ES[month],
        "semanas": semanas
    }

@router.get("", response_class=HTMLResponse)
def vista_agenda(request: Request, fecha: str = None):
    conn = get_db_connection()
    
    fecha_seleccionada = fecha if fecha else date.today().isoformat()
    try:
        dt_sel = datetime.strptime(fecha_seleccionada, "%Y-%m-%d").date()
    except Exception:
        dt_sel = date.today()
        fecha_seleccionada = dt_sel.isoformat()

    # Gabinetes activos para la cuadrícula y todos para el modal de opciones
    gabinetes = conn.execute("SELECT * FROM gabinetes WHERE activo = 1 ORDER BY orden").fetchall()
    todos_gabinetes = conn.execute("SELECT * FROM gabinetes ORDER BY orden").fetchall()
    
    doctores = conn.execute("SELECT * FROM usuarios WHERE activo = 1 ORDER BY nombre").fetchall()
    pacientes = conn.execute("SELECT id, nombre, apellidos, telefono_movil, numero_expediente FROM pacientes WHERE estado = 'alta' ORDER BY apellidos, nombre").fetchall()
    
    # Query appointments for the selected date
    citas_rows = conn.execute("""
        SELECT c.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, p.telefono_movil as paciente_movil, p.numero_expediente,
               g.nombre as gabinete_nombre, g.color as gabinete_color,
               u.nombre || ' ' || u.apellidos as doctor_nombre, u.color_agenda as doctor_color,
               (SELECT COALESCE(SUM(tp.precio_final), 0) - COALESCE(SUM(cb.importe), 0) 
                FROM pacientes pc
                LEFT JOIN tratamientos_paciente tp ON tp.paciente_id = pc.id AND tp.estado = 'realizado'
                LEFT JOIN cobros cb ON cb.paciente_id = pc.id AND cb.cobrado = 1
                WHERE pc.id = c.paciente_id) as paciente_saldo
        FROM citas c
        JOIN pacientes p ON c.paciente_id = p.id
        JOIN gabinetes g ON c.gabinete_id = g.id
        LEFT JOIN usuarios u ON c.doctor_id = u.id
        WHERE date(c.fecha_hora_inicio) = ?
        ORDER BY c.fecha_hora_inicio ASC
    """, (fecha_seleccionada,)).fetchall()

    # Time slots for the daily grid (08:00 to 20:30 every 15 min)
    slots = []
    hora_inicio = datetime.strptime(f"{fecha_seleccionada} 08:00", "%Y-%m-%d %H:%M")
    hora_fin = datetime.strptime(f"{fecha_seleccionada} 20:30", "%Y-%m-%d %H:%M")
    curr = hora_inicio
    while curr <= hora_fin:
        slots.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=15)

    # Calculate status totals
    resumen_estados = {
        "programada": 0,
        "confirmada": 0,
        "en_espera": 0,
        "en_consulta": 0,
        "realizada": 0,
        "cancelada": 0,
        "no_asiste": 0,
    }
    for c in citas_rows:
        if c["estado"] in resumen_estados:
            resumen_estados[c["estado"]] += 1

    # Cálculo del Mes en Curso (Mes 1) y Mes Siguiente (Mes 2)
    m1_year = dt_sel.year
    m1_month = dt_sel.month
    if m1_month == 12:
        m2_year = m1_year + 1
        m2_month = 1
    else:
        m2_year = m1_year
        m2_month = m1_month + 1

    # Días con citas para mostrar indicadores en los mini-calendarios
    dias_citas_rows = conn.execute("""
        SELECT DISTINCT date(fecha_hora_inicio) as dia
        FROM citas
        WHERE date(fecha_hora_inicio) >= ? AND date(fecha_hora_inicio) <= ?
    """, (f"{m1_year:04d}-{m1_month:02d}-01", f"{m2_year:04d}-{m2_month:02d}-31")).fetchall()
    dias_con_citas = {r["dia"] for r in dias_citas_rows}

    cal_mes_actual = generar_calendario_mes(m1_year, m1_month, dias_con_citas, fecha_seleccionada)
    cal_mes_siguiente = generar_calendario_mes(m2_year, m2_month, dias_con_citas, fecha_seleccionada)

    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="agenda.html", context={
        "fecha": fecha_seleccionada,
        "gabinetes": gabinetes,
        "todos_gabinetes": todos_gabinetes,
        "doctores": doctores,
        "pacientes": pacientes,
        "citas": citas_rows,
        "slots": slots,
        "resumen_estados": resumen_estados,
        "cal_mes_actual": cal_mes_actual,
        "cal_mes_siguiente": cal_mes_siguiente
    })

@router.post("/citas/nueva")
def crear_cita(
    paciente_id: int = Form(...),
    gabinete_id: int = Form(...),
    doctor_id: int = Form(None),
    fecha: str = Form(...),
    hora_inicio: str = Form(...),
    duracion_minutos: int = Form(30),
    motivo: str = Form(...),
    color: str = Form(None),
    notas: str = Form(None)
):
    conn = get_db_connection()
    
    inicio_dt = datetime.strptime(f"{fecha} {hora_inicio}", "%Y-%m-%d %H:%M")
    fin_dt = inicio_dt + timedelta(minutes=duracion_minutos)
    
    conn.execute("""
        INSERT INTO citas (
            paciente_id, gabinete_id, doctor_id, fecha_hora_inicio, fecha_hora_fin, motivo, color, notas
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        paciente_id, gabinete_id, doctor_id,
        inicio_dt.strftime("%Y-%m-%d %H:%M:%S"),
        fin_dt.strftime("%Y-%m-%d %H:%M:%S"),
        motivo, color, notas
    ))
    conn.commit()
    conn.close()
    
    return RedirectResponse(url=f"/agenda?fecha={fecha}", status_code=303)

@router.post("/citas/{cita_id}/estado")
def cambiar_estado_cita(cita_id: int, estado: str = Form(...)):
    conn = get_db_connection()
    conn.execute("UPDATE citas SET estado = ? WHERE id = ?;", (estado, cita_id))
    
    if estado == "realizada":
        cita = conn.execute("SELECT paciente_id, motivo FROM citas WHERE id = ?", (cita_id,)).fetchone()
        if cita:
            conn.execute("""
                INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
                VALUES (?, 'actuacion_clinica', ?);
            """, (cita["paciente_id"], f"Cita completada: {cita['motivo']}"))

    conn.commit()
    conn.close()
    return JSONResponse({"success": True})

@router.post("/citas/{cita_id}/recall")
def crear_recall(cita_id: int, meses: int = Form(6)):
    """Programa una cita de revisión (Recall) futura a 6 o 12 meses."""
    conn = get_db_connection()
    cita = conn.execute("SELECT * FROM citas WHERE id = ?", (cita_id,)).fetchone()
    if not cita:
        conn.close()
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    f_inicio = datetime.strptime(cita["fecha_hora_inicio"], "%Y-%m-%d %H:%M:%S")
    dias_aprox = meses * 30
    nueva_fecha_inicio = f_inicio + timedelta(days=dias_aprox)
    nueva_fecha_fin = nueva_fecha_inicio + timedelta(minutes=30)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO citas (paciente_id, gabinete_id, doctor_id, fecha_hora_inicio, fecha_hora_fin, motivo, estado, color, notas)
        VALUES (?, ?, ?, ?, ?, ?, 'programada', '#10B981', ?);
    """, (
        cita["paciente_id"], cita["gabinete_id"], cita["doctor_id"],
        nueva_fecha_inicio.strftime("%Y-%m-%d %H:%M:%S"),
        nueva_fecha_fin.strftime("%Y-%m-%d %H:%M:%S"),
        f"Revisión periódica ({meses} meses)",
        f"Recall programado automáticamente tras la cita #{cita_id}"
    ))
    conn.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'actuacion_clinica', ?);
    """, (cita["paciente_id"], f"Programado Recall de revisión para {nueva_fecha_inicio.strftime('%d/%m/%Y')}"))
    conn.commit()
    conn.close()
    return JSONResponse({"success": True, "nueva_fecha": nueva_fecha_inicio.strftime("%Y-%m-%d")})

@router.delete("/citas/{cita_id}")
def eliminar_cita(cita_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM citas WHERE id = ?;", (cita_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"success": True})

# --- GESTIÓN DINÁMICA DE GABINETES (OPCIONES) ---

@router.post("/gabinetes/nuevo")
def crear_gabinete(
    nombre: str = Form(...),
    color: str = Form("#0284C7"),
    fecha_redireccion: str = Form(None)
):
    conn = get_db_connection()
    max_orden = conn.execute("SELECT COALESCE(MAX(orden), 0) FROM gabinetes;").fetchone()[0]
    next_orden = max_orden + 1
    
    conn.execute("""
        INSERT INTO gabinetes (nombre, color, orden, activo)
        VALUES (?, ?, ?, 1);
    """, (nombre.strip(), color.strip(), next_orden))
    conn.commit()
    conn.close()
    
    red_url = f"/agenda?fecha={fecha_redireccion}" if fecha_redireccion else "/agenda"
    return RedirectResponse(url=red_url, status_code=303)

@router.post("/gabinetes/{gabinete_id}/toggle")
def alternar_estado_gabinete(gabinete_id: int, fecha_redireccion: str = Form(None)):
    conn = get_db_connection()
    gab = conn.execute("SELECT activo FROM gabinetes WHERE id = ?", (gabinete_id,)).fetchone()
    if not gab:
        conn.close()
        raise HTTPException(status_code=404, detail="Gabinete no encontrado")
    
    nuevo_estado = 0 if gab["activo"] == 1 else 1
    
    # Prevenir desactivar todos los gabinetes (al menos 1 debe quedar activo)
    if nuevo_estado == 0:
        total_activos = conn.execute("SELECT COUNT(*) FROM gabinetes WHERE activo = 1;").fetchone()[0]
        if total_activos <= 1:
            conn.close()
            raise HTTPException(status_code=400, detail="Debe haber al menos 1 gabinete activo en la clínica.")
    
    conn.execute("UPDATE gabinetes SET activo = ? WHERE id = ?;", (nuevo_estado, gabinete_id))
    conn.commit()
    conn.close()
    
    red_url = f"/agenda?fecha={fecha_redireccion}" if fecha_redireccion else "/agenda"
    return RedirectResponse(url=red_url, status_code=303)

@router.post("/gabinetes/{gabinete_id}/editar")
def editar_gabinete(
    gabinete_id: int,
    nombre: str = Form(...),
    color: str = Form(...),
    fecha_redireccion: str = Form(None)
):
    conn = get_db_connection()
    conn.execute("UPDATE gabinetes SET nombre = ?, color = ? WHERE id = ?;", (nombre.strip(), color.strip(), gabinete_id))
    conn.commit()
    conn.close()
    
    red_url = f"/agenda?fecha={fecha_redireccion}" if fecha_redireccion else "/agenda"
    return RedirectResponse(url=red_url, status_code=303)
