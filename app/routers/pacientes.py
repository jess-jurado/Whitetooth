from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime, date
from app.database import get_db_connection

router = APIRouter(prefix="/pacientes", tags=["pacientes"])

def calcular_edad(fecha_nacimiento):
    if not fecha_nacimiento:
        return None
    try:
        if isinstance(fecha_nacimiento, str):
            fn = datetime.strptime(fecha_nacimiento, "%Y-%m-%d").date()
        else:
            fn = fecha_nacimiento
        hoy = date.today()
        return hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    except Exception:
        return None

@router.get("", response_class=HTMLResponse)
def listar_pacientes(request: Request, q: str = "", estado: str = "alta", con_saldo: bool = False):
    conn = get_db_connection()
    
    query = """
        SELECT p.*,
            (SELECT COUNT(*) FROM tratamientos_paciente tp WHERE tp.paciente_id = p.id AND tp.estado = 'realizado') as total_tratamientos_realizados,
            COALESCE((SELECT SUM(tp.precio_final) FROM tratamientos_paciente tp WHERE tp.paciente_id = p.id AND tp.estado = 'realizado'), 0.0) as total_tratamientos_importe,
            COALESCE((SELECT SUM(c.importe) FROM cobros c WHERE c.paciente_id = p.id AND c.cobrado = 1), 0.0) as total_cobros_importe,
            (SELECT MAX(tp.fecha_realizacion) FROM tratamientos_paciente tp WHERE tp.paciente_id = p.id) as fecha_ultima_actuacion
        FROM pacientes p
        WHERE (p.estado = ? OR ? = 'todos')
    """
    params = [estado, estado]

    if q.strip():
        query += """ AND (
            p.nombre LIKE ? OR 
            p.apellidos LIKE ? OR 
            p.nif_cif LIKE ? OR 
            p.telefono_movil LIKE ? OR 
            p.numero_expediente = ?
        )"""
        search_term = f"%{q.strip()}%"
        exp_val = int(q.strip()) if q.strip().isdigit() else -1
        params.extend([search_term, search_term, search_term, search_term, exp_val])

    query += " ORDER BY p.apellidos, p.nombre"
    
    rows = conn.execute(query, params).fetchall()
    
    pacientes = []
    hoy = date.today()
    for row in rows:
        p = dict(row)
        p["edad"] = calcular_edad(p["fecha_nacimiento"])
        p["saldo"] = round(p["total_tratamientos_importe"] - p["total_cobros_importe"], 2)
        
        # Días sin actuaciones
        if p["fecha_ultima_actuacion"]:
            try:
                f_act = datetime.strptime(p["fecha_ultima_actuacion"][:10], "%Y-%m-%d").date()
                p["dias_sin_actuacion"] = (hoy - f_act).days
            except Exception:
                p["dias_sin_actuacion"] = "-"
        else:
            p["dias_sin_actuacion"] = "-"

        # Antigüedad en días
        if p["created_at"]:
            try:
                f_alta = datetime.strptime(p["created_at"][:10], "%Y-%m-%d").date()
                p["antiguedad_dias"] = (hoy - f_alta).days
            except Exception:
                p["antiguedad_dias"] = 0
        else:
            p["antiguedad_dias"] = 0

        if con_saldo and p["saldo"] <= 0:
            continue
            
        pacientes.append(p)

    conn.close()
    
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="pacientes.html", context={
        "pacientes": pacientes, 
        "q": q, 
        "estado": estado, 
        "con_saldo": con_saldo
    })

@router.get("/{paciente_id}", response_class=HTMLResponse)
def detalle_paciente(request: Request, paciente_id: int):
    conn = get_db_connection()
    
    p_row = conn.execute("SELECT * FROM pacientes WHERE id = ?", (paciente_id,)).fetchone()
    if not p_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    paciente = dict(p_row)
    paciente["edad"] = calcular_edad(paciente["fecha_nacimiento"])
    
    # Financial summaries
    total_trat = conn.execute("""
        SELECT COALESCE(SUM(precio_final), 0.0) FROM tratamientos_paciente 
        WHERE paciente_id = ? AND estado = 'realizado'
    """, (paciente_id,)).fetchone()[0]
    
    total_cobrado = conn.execute("""
        SELECT COALESCE(SUM(importe), 0.0) FROM cobros 
        WHERE paciente_id = ? AND cobrado = 1
    """, (paciente_id,)).fetchone()[0]
    
    total_presupuestado = conn.execute("""
        SELECT COALESCE(SUM(total_presupuesto), 0.0) FROM presupuestos 
        WHERE paciente_id = ?
    """, (paciente_id,)).fetchone()[0]
    
    paciente["total_tratamientos"] = round(total_trat, 2)
    paciente["total_cobros"] = round(total_cobrado, 2)
    paciente["total_presupuestos"] = round(total_presupuestado, 2)
    paciente["saldo"] = round(total_trat - total_cobrado, 2)
    
    # Appointments
    citas = conn.execute("""
        SELECT c.*, g.nombre as gabinete_nombre, u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM citas c
        LEFT JOIN gabinetes g ON c.gabinete_id = g.id
        LEFT JOIN usuarios u ON c.doctor_id = u.id
        WHERE c.paciente_id = ?
        ORDER BY c.fecha_hora_inicio DESC
    """, (paciente_id,)).fetchall()

    # Budgets
    presupuestos = conn.execute("""
        SELECT pr.*, u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM presupuestos pr
        LEFT JOIN usuarios u ON pr.doctor_id = u.id
        WHERE pr.paciente_id = ?
        ORDER BY pr.fecha DESC, pr.numero_presupuesto DESC
    """, (paciente_id,)).fetchall()

    # Invoices
    facturas = conn.execute("""
        SELECT * FROM facturas 
        WHERE paciente_id = ?
        ORDER BY anio DESC, numero_factura DESC
    """, (paciente_id,)).fetchall()

    # Collections
    cobros = conn.execute("""
        SELECT c.*, u.nombre as usuario_nombre, f.numero_factura, f.serie as factura_serie
        FROM cobros c
        LEFT JOIN usuarios u ON c.usuario_id = u.id
        LEFT JOIN facturas f ON c.factura_id = f.id
        WHERE c.paciente_id = ?
        ORDER BY c.fecha_cobro DESC, c.id DESC
    """, (paciente_id,)).fetchall()

    # History notes
    historial = conn.execute("""
        SELECT h.*, u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM historial_clinico h
        LEFT JOIN usuarios u ON h.doctor_id = u.id
        WHERE h.paciente_id = ?
        ORDER BY h.fecha DESC
    """, (paciente_id,)).fetchall()

    # Lab Orders
    pedidos_lab = conn.execute("""
        SELECT * FROM pedidos_laboratorio
        WHERE paciente_id = ?
        ORDER BY fecha_envio DESC
    """, (paciente_id,)).fetchall()

    # Doctors and Cabinets for modals
    doctores = conn.execute("SELECT * FROM usuarios WHERE activo = 1 ORDER BY nombre").fetchall()
    gabinetes = conn.execute("SELECT * FROM gabinetes WHERE activo = 1 ORDER BY orden").fetchall()
    catalogo = conn.execute("SELECT * FROM catalogo_tratamientos WHERE activo = 1 ORDER BY categoria, nombre").fetchall()

    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="paciente_detalle.html", context={
        "p": paciente,
        "citas": citas,
        "presupuestos": presupuestos,
        "facturas": facturas,
        "cobros": cobros,
        "historial": historial,
        "pedidos_lab": pedidos_lab,
        "doctores": doctores,
        "gabinetes": gabinetes,
        "catalogo": catalogo
    })

@router.post("/nuevo")
def crear_paciente(
    nombre: str = Form(...),
    apellidos: str = Form(...),
    telefono_movil: str = Form(...),
    nif_cif: str = Form(None),
    fecha_nacimiento: str = Form(None),
    telefono_fijo: str = Form(None),
    email: str = Form(None),
    direccion: str = Form(None),
    codigo_postal: str = Form(None),
    poblacion: str = Form(None),
    provincia: str = Form(None),
    tipo_paciente: str = Form("general"),
    alergias: str = Form(None),
    antecedentes_medicos: str = Form(None),
    motivo_consulta: str = Form(None),
    notas_administrativas: str = Form(None)
):
    conn = get_db_connection()
    
    # Auto-generate next expediente number
    max_exp = conn.execute("SELECT MAX(numero_expediente) FROM pacientes;").fetchone()[0]
    next_exp = (max_exp or 100) + 1

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pacientes (
            numero_expediente, nombre, apellidos, nif_cif, fecha_nacimiento,
            telefono_fijo, telefono_movil, email, direccion, codigo_postal,
            poblacion, provincia, tipo_paciente, alergias, antecedentes_medicos,
            motivo_consulta, notas_administrativas
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        next_exp, nombre.strip().upper(), apellidos.strip().upper(), nif_cif.strip().upper() if nif_cif else None,
        fecha_nacimiento if fecha_nacimiento else None, telefono_fijo, telefono_movil.strip(), email,
        direccion, codigo_postal, poblacion, provincia, tipo_paciente,
        alergias, antecedentes_medicos, motivo_consulta, notas_administrativas
    ))
    nuevo_id = cursor.lastrowid
    
    # Add initial history event
    conn.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'actuacion_clinica', 'Alta de nuevo paciente en el sistema.');
    """, (nuevo_id,))
    
    conn.commit()
    conn.close()
    
    return RedirectResponse(url=f"/pacientes/{nuevo_id}", status_code=303)

@router.post("/{paciente_id}/actualizar")
def actualizar_paciente(
    paciente_id: int,
    nombre: str = Form(...),
    apellidos: str = Form(...),
    telefono_movil: str = Form(...),
    nif_cif: str = Form(None),
    fecha_nacimiento: str = Form(None),
    telefono_fijo: str = Form(None),
    email: str = Form(None),
    direccion: str = Form(None),
    codigo_postal: str = Form(None),
    poblacion: str = Form(None),
    provincia: str = Form(None),
    tipo_paciente: str = Form("general"),
    alergias: str = Form(None),
    antecedentes_medicos: str = Form(None),
    motivo_consulta: str = Form(None),
    notas_administrativas: str = Form(None),
    estado: str = Form("alta")
):
    conn = get_db_connection()
    conn.execute("""
        UPDATE pacientes SET
            nombre = ?, apellidos = ?, nif_cif = ?, fecha_nacimiento = ?,
            telefono_fijo = ?, telefono_movil = ?, email = ?, direccion = ?,
            codigo_postal = ?, poblacion = ?, provincia = ?, tipo_paciente = ?,
            alergias = ?, antecedentes_medicos = ?, motivo_consulta = ?,
            notas_administrativas = ?, estado = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?;
    """, (
        nombre.strip().upper(), apellidos.strip().upper(), nif_cif.strip().upper() if nif_cif else None,
        fecha_nacimiento if fecha_nacimiento else None, telefono_fijo, telefono_movil.strip(), email,
        direccion, codigo_postal, poblacion, provincia, tipo_paciente,
        alergias, antecedentes_medicos, motivo_consulta, notas_administrativas, estado, paciente_id
    ))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/pacientes/{paciente_id}", status_code=303)

@router.post("/{paciente_id}/consentimiento-rgpd")
def firmar_rgpd(paciente_id: int):
    conn = get_db_connection()
    conn.execute("""
        UPDATE pacientes SET
            consentimiento_rgpd_firmado = 1,
            fecha_consentimiento_rgpd = CURRENT_TIMESTAMP
        WHERE id = ?;
    """, (paciente_id,))
    conn.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'consentimiento_firmado', 'Consentimiento informado RGPD / LOPD-GDD firmado y registrado.');
    """, (paciente_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"success": True})

@router.post("/{paciente_id}/nueva-nota")
def agregar_nota_historial(
    paciente_id: int,
    descripcion: str = Form(...),
    doctor_id: int = Form(None)
):
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO historial_clinico (paciente_id, doctor_id, tipo_evento, descripcion)
        VALUES (?, ?, 'actuacion_clinica', ?);
    """, (paciente_id, doctor_id, descripcion.strip()))
    conn.commit()
    conn.close()
    return JSONResponse({"success": True})
