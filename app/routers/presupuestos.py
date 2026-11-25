from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime, date
from app.database import get_db_connection

router = APIRouter(prefix="/presupuestos", tags=["presupuestos"])

@router.get("", response_class=HTMLResponse)
def listar_presupuestos(request: Request, q: str = "", estado: str = "todos"):
    conn = get_db_connection()
    
    query = """
        SELECT pr.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, 
               p.nif_cif as paciente_nif, p.numero_expediente as paciente_expediente,
               u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM presupuestos pr
        JOIN pacientes p ON pr.paciente_id = p.id
        LEFT JOIN usuarios u ON pr.doctor_id = u.id
        WHERE (pr.estado = ? OR ? = 'todos')
    """
    params = [estado, estado]

    if q.strip():
        query += " AND (p.nombre LIKE ? OR p.apellidos LIKE ? OR p.nif_cif LIKE ? OR pr.numero_presupuesto = ?)"
        term = f"%{q.strip()}%"
        num = int(q.strip()) if q.strip().isdigit() else -1
        params.extend([term, term, term, num])

    query += " ORDER BY pr.anio DESC, pr.numero_presupuesto DESC"
    
    presupuestos = conn.execute(query, params).fetchall()
    pacientes = conn.execute("SELECT id, nombre, apellidos, numero_expediente FROM pacientes WHERE estado = 'alta' ORDER BY apellidos, nombre").fetchall()
    doctores = conn.execute("SELECT id, nombre, apellidos FROM usuarios WHERE activo = 1 ORDER BY nombre").fetchall()
    catalogo = conn.execute("SELECT * FROM catalogo_tratamientos WHERE activo = 1 ORDER BY categoria, nombre").fetchall()

    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="presupuestos.html", context={
        "presupuestos": presupuestos,
        "pacientes": pacientes,
        "doctores": doctores,
        "catalogo": catalogo,
        "q": q,
        "estado": estado
    })

@router.get("/{presupuesto_id}", response_class=HTMLResponse)
def ver_presupuesto(request: Request, presupuesto_id: int):
    conn = get_db_connection()
    
    pr = conn.execute("""
        SELECT pr.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, 
               p.nif_cif as paciente_nif, p.numero_expediente as paciente_expediente,
               p.telefono_movil as paciente_movil, p.direccion as paciente_direccion,
               u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM presupuestos pr
        JOIN pacientes p ON pr.paciente_id = p.id
        LEFT JOIN usuarios u ON pr.doctor_id = u.id
        WHERE pr.id = ?
    """, (presupuesto_id,)).fetchone()
    
    if not pr:
        conn.close()
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")
        
    lineas = conn.execute("""
        SELECT pl.*, ct.codigo as catalogo_codigo, ct.nombre as catalogo_nombre, ct.color as catalogo_color
        FROM presupuesto_lineas pl
        JOIN catalogo_tratamientos ct ON pl.tratamiento_catalogo_id = ct.id
        WHERE pl.presupuesto_id = ?
        ORDER BY pl.orden ASC, pl.id ASC
    """, (presupuesto_id,)).fetchall()

    clinica = conn.execute("SELECT * FROM clinica LIMIT 1;").fetchone()
    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="presupuesto_detalle.html", context={
        "pr": pr,
        "lineas": lineas,
        "clinica": clinica
    })

@router.post("/nuevo")
def crear_presupuesto(
    paciente_id: int = Form(...),
    doctor_id: int = Form(None),
    descripcion: str = Form("Presupuesto de Tratamiento Dental"),
    descuento_global: float = Form(0.0)
):
    conn = get_db_connection()
    current_year = date.today().year
    today_str = date.today().isoformat()

    # Next sequential budget number for this year
    max_num = conn.execute("SELECT MAX(numero_presupuesto) FROM presupuestos WHERE anio = ?", (current_year,)).fetchone()[0]
    next_num = (max_num or 300) + 1

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO presupuestos (
            paciente_id, numero_presupuesto, anio, fecha, descripcion,
            descuento_global_porcentaje, total_honorarios, total_descuento,
            total_presupuesto, total_aceptado, estado, doctor_id
        ) VALUES (?, ?, ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 'pendiente', ?);
    """, (
        paciente_id, next_num, current_year, today_str, descripcion,
        descuento_global, doctor_id
    ))
    nuevo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return RedirectResponse(url=f"/presupuestos/{nuevo_id}", status_code=303)

@router.post("/{presupuesto_id}/linea/nueva")
def agregar_linea_presupuesto(
    presupuesto_id: int,
    tratamiento_catalogo_id: int = Form(...),
    pieza_fdi: int = Form(None),
    caras: str = Form(None),
    descripcion_custom: str = Form(None),
    precio_unitario: float = Form(...),
    descuento_porcentaje: float = Form(0.0)
):
    conn = get_db_connection()
    
    # Check default description if custom is empty
    if not descripcion_custom:
        cat = conn.execute("SELECT nombre FROM catalogo_tratamientos WHERE id = ?", (tratamiento_catalogo_id,)).fetchone()
        descripcion_custom = cat["nombre"] if cat else "Tratamiento"

    importe = round(precio_unitario * (1.0 - (descuento_porcentaje or 0.0) / 100.0), 2)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO presupuesto_lineas (
            presupuesto_id, tratamiento_catalogo_id, pieza_fdi, caras,
            descripcion, precio_unitario, descuento_porcentaje, importe, aceptado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1);
    """, (
        presupuesto_id, tratamiento_catalogo_id, pieza_fdi, caras,
        descripcion_custom, precio_unitario, descuento_porcentaje, importe
    ))

    # Recalculate totals
    recalcular_totales_presupuesto(conn, presupuesto_id)
    
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/presupuestos/{presupuesto_id}", status_code=303)

@router.post("/{presupuesto_id}/aceptar")
def aceptar_presupuesto(presupuesto_id: int):
    """
    Marca el presupuesto como aceptado y transfiere automáticamente todas sus líneas
    a 'tratamientos_paciente' con estado 'previsto' para agendarlas y verlas en el odontograma.
    """
    conn = get_db_connection()
    
    pr = conn.execute("SELECT * FROM presupuestos WHERE id = ?", (presupuesto_id,)).fetchone()
    if not pr:
        conn.close()
        raise HTTPException(status_code=404, detail="Presupuesto no encontrado")

    lineas = conn.execute("""
        SELECT * FROM presupuesto_lineas WHERE presupuesto_id = ?
    """, (presupuesto_id,)).fetchall()

    today_str = date.today().isoformat()
    cursor = conn.cursor()

    for l in lineas:
        # Mark line as accepted
        cursor.execute("UPDATE presupuesto_lineas SET aceptado = 1 WHERE id = ?", (l["id"],))

        # Add to patient active planned treatments
        cursor.execute("""
            INSERT INTO tratamientos_paciente (
                paciente_id, tratamiento_catalogo_id, pieza_fdi, caras, estado,
                precio_original, descuento_porcentaje, precio_final, doctor_id,
                fecha_prevista, observaciones
            ) VALUES (?, ?, ?, ?, 'previsto', ?, ?, ?, ?, ?, ?);
        """, (
            pr["paciente_id"], l["tratamiento_catalogo_id"], l["pieza_fdi"], l["caras"],
            l["precio_unitario"], l["descuento_porcentaje"], l["importe"], pr["doctor_id"],
            today_str, f"Derivado de Presupuesto #{pr['numero_presupuesto']}"
        ))

    # Update budget header
    cursor.execute("""
        UPDATE presupuestos 
        SET estado = 'aceptado_total', total_aceptado = total_presupuesto
        WHERE id = ?;
    """, (presupuesto_id,))

    # Log in history
    cursor.execute("""
        INSERT INTO historial_clinico (paciente_id, doctor_id, tipo_evento, descripcion)
        VALUES (?, ?, 'actuacion_clinica', ?);
    """, (pr["paciente_id"], pr["doctor_id"], f"Aceptación de Presupuesto #{pr['numero_presupuesto']} por importe de {pr['total_presupuesto']} €"))

    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/presupuestos/{presupuesto_id}", status_code=303)

@router.delete("/{presupuesto_id}/linea/{linea_id}")
def eliminar_linea_presupuesto(presupuesto_id: int, linea_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM presupuesto_lineas WHERE id = ? AND presupuesto_id = ?;", (linea_id, presupuesto_id))
    recalcular_totales_presupuesto(conn, presupuesto_id)
    conn.commit()
    conn.close()
    return JSONResponse({"success": True})

def recalcular_totales_presupuesto(conn, presupuesto_id: int):
    rows = conn.execute("""
        SELECT precio_unitario, descuento_porcentaje, importe, aceptado 
        FROM presupuesto_lineas 
        WHERE presupuesto_id = ?;
    """, (presupuesto_id,)).fetchall()
    
    total_honorarios = sum(r["precio_unitario"] for r in rows)
    total_presupuesto = sum(r["importe"] for r in rows)
    total_descuento = round(total_honorarios - total_presupuesto, 2)
    total_aceptado = sum(r["importe"] for r in rows if r["aceptado"] == 1)

    conn.execute("""
        UPDATE presupuestos SET
            total_honorarios = ?,
            total_descuento = ?,
            total_presupuesto = ?,
            total_aceptado = ?
        WHERE id = ?;
    """, (total_honorarios, total_descuento, total_presupuesto, total_aceptado, presupuesto_id))
