from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime, date
from app.database import get_db_connection

router = APIRouter(prefix="/facturas", tags=["facturacion"])

@router.get("", response_class=HTMLResponse)
def listar_facturas(request: Request, anio: int = None, tipo: str = "todas", q: str = ""):
    conn = get_db_connection()
    current_year = anio or date.today().year

    query = """
        SELECT f.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, 
               p.nif_cif as paciente_nif, p.numero_expediente as paciente_expediente,
               rf.numero_factura as rectificada_numero, rf.serie as rectificada_serie
        FROM facturas f
        JOIN pacientes p ON f.paciente_id = p.id
        LEFT JOIN facturas rf ON f.factura_rectificada_id = rf.id
        WHERE f.anio = ?
    """
    params = [current_year]

    if tipo != "todas":
        query += " AND f.tipo_factura = ?"
        params.append(tipo)

    if q.strip():
        query += " AND (p.nombre LIKE ? OR p.apellidos LIKE ? OR p.nif_cif LIKE ? OR f.numero_factura = ?)"
        term = f"%{q.strip()}%"
        num = int(q.strip()) if q.strip().isdigit() else -1
        params.extend([term, term, term, num])

    query += " ORDER BY f.serie ASC, f.numero_factura DESC"
    
    facturas = conn.execute(query, params).fetchall()

    # Totals
    total_base = sum(f["base_imponible"] for f in facturas if f["tipo_factura"] == "ordinaria")
    total_abonos = sum(abs(f["base_imponible"]) for f in facturas if f["tipo_factura"] == "abono_rectificativa")
    total_neto = round(total_base - total_abonos, 2)

    pacientes = conn.execute("SELECT id, nombre, apellidos, nif_cif, numero_expediente FROM pacientes WHERE estado = 'alta' ORDER BY apellidos, nombre").fetchall()

    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="facturas.html", context={
        "facturas": facturas,
        "pacientes": pacientes,
        "anio_actual": current_year,
        "tipo": tipo,
        "q": q,
        "total_base": round(total_base, 2),
        "total_abonos": round(total_abonos, 2),
        "total_neto": total_neto
    })

@router.post("/nueva")
def crear_factura(
    paciente_id: int = Form(...),
    concepto: str = Form("Servicios Sanitarios Odontológicos"),
    importe: float = Form(...),
    forma_cobro: str = Form("Tarjeta"),
    fecha_factura: str = Form(None)
):
    conn = get_db_connection()
    current_year = date.today().year
    fecha_f = fecha_factura if fecha_factura else date.today().isoformat()

    # Get next sequential invoice number for 'OFICIAL'
    max_num = conn.execute("SELECT MAX(numero_factura) FROM facturas WHERE anio = ? AND serie = 'OFICIAL';", (current_year,)).fetchone()[0]
    next_num = (max_num or 400) + 1

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO facturas (
            paciente_id, serie, numero_factura, anio, fecha_factura,
            tipo_factura, base_imponible, porcentaje_iva, importe_iva, total_factura,
            forma_cobro_predeterminada, estado_pago, bloqueada
        ) VALUES (?, 'OFICIAL', ?, ?, ?, 'ordinaria', ?, 0.0, 0.0, ?, ?, 'cobrada', 1);
    """, (
        paciente_id, next_num, current_year, fecha_f, importe, importe, forma_cobro
    ))
    factura_id = cursor.lastrowid

    # Create line
    cursor.execute("""
        INSERT INTO factura_lineas (factura_id, concepto, cantidad, precio_unitario, descuento, total_linea)
        VALUES (?, ?, 1, ?, 0.0, ?);
    """, (factura_id, concepto, importe, importe))

    # Log in history
    cursor.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'actuacion_clinica', ?);
    """, (paciente_id, f"Emisión de Factura Oficial #{next_num}/{current_year} por importe de {importe:.2f} €"))

    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/facturas/{factura_id}/imprimir", status_code=303)

@router.post("/{factura_id}/abono")
def generar_factura_abono(
    factura_id: int,
    motivo: str = Form("Anulación de factura por rectificación o error administrativo")
):
    """
    Genera una Factura de Abono (Rectificativa) oficial referenciando la factura original.
    Cumple con el RD 1007/2023 y Ley Antifraude española (Veri*factu).
    """
    conn = get_db_connection()
    
    orig = conn.execute("SELECT * FROM facturas WHERE id = ?", (factura_id,)).fetchone()
    if not orig:
        conn.close()
        raise HTTPException(status_code=404, detail="Factura original no encontrada")

    current_year = date.today().year
    today_str = date.today().isoformat()

    # Next sequential abono number
    max_abono = conn.execute("SELECT MAX(numero_factura) FROM facturas WHERE anio = ? AND serie = 'ABONO';", (current_year,)).fetchone()[0]
    next_abono = (max_abono or 0) + 1

    importe_negativo = -abs(orig["total_factura"])

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO facturas (
            paciente_id, serie, numero_factura, anio, fecha_factura,
            tipo_factura, factura_rectificada_id, motivo_rectificacion,
            base_imponible, porcentaje_iva, importe_iva, total_factura,
            forma_cobro_predeterminada, estado_pago, bloqueada
        ) VALUES (?, 'ABONO', ?, ?, ?, 'abono_rectificativa', ?, ?, ?, 0.0, 0.0, ?, ?, 'cobrada', 1);
    """, (
        orig["paciente_id"], next_abono, current_year, today_str,
        factura_id, motivo, importe_negativo, importe_negativo, orig["forma_cobro_predeterminada"]
    ))
    abono_id = cursor.lastrowid

    # Line for the abono
    cursor.execute("""
        INSERT INTO factura_lineas (factura_id, concepto, cantidad, precio_unitario, descuento, total_linea)
        VALUES (?, ?, 1, ?, 0.0, ?);
    """, (abono_id, f"ABONO Factura Rectificada {orig['serie']} {orig['numero_factura']}/{orig['anio']} - {motivo}", importe_negativo, importe_negativo))

    # History record
    cursor.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'actuacion_clinica', ?);
    """, (orig["paciente_id"], f"Emitida Factura de Abono #{next_abono}/{current_year} rectificando factura {orig['serie']} {orig['numero_factura']}/{orig['anio']}. Motivo: {motivo}"))

    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/facturas/{abono_id}/imprimir", status_code=303)

@router.get("/{factura_id}/imprimir", response_class=HTMLResponse)
def imprimir_factura(request: Request, factura_id: int):
    conn = get_db_connection()
    
    fac = conn.execute("""
        SELECT f.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, 
               p.nif_cif as paciente_nif, p.direccion as paciente_direccion,
               p.codigo_postal as paciente_cp, p.poblacion as paciente_poblacion, p.provincia as paciente_provincia,
               p.numero_expediente as paciente_expediente,
               rf.numero_factura as rectificada_numero, rf.serie as rectificada_serie, rf.anio as rectificada_anio
        FROM facturas f
        JOIN pacientes p ON f.paciente_id = p.id
        LEFT JOIN facturas rf ON f.factura_rectificada_id = rf.id
        WHERE f.id = ?
    """, (factura_id,)).fetchone()
    
    if not fac:
        conn.close()
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    lineas = conn.execute("SELECT * FROM factura_lineas WHERE factura_id = ?", (factura_id,)).fetchall()
    clinica = conn.execute("SELECT * FROM clinica LIMIT 1;").fetchone()

    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="factura_detalle.html", context={
        "f": fac,
        "lineas": lineas,
        "clinica": clinica
    })
