from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime, date
from app.database import get_db_connection

router = APIRouter(prefix="/cobros", tags=["cobros"])

@router.get("", response_class=HTMLResponse)
def listar_cobros(request: Request, fecha_desde: str = None, fecha_hasta: str = None, forma_pago: str = "todas", q: str = ""):
    conn = get_db_connection()
    
    current_year = date.today().year
    desde = fecha_desde if fecha_desde else f"{current_year}-01-01"
    hasta = fecha_hasta if fecha_hasta else date.today().isoformat()

    query = """
        SELECT c.*, 
               p.nombre as paciente_nombre, p.apellidos as paciente_apellidos, p.numero_expediente, p.telefono_movil,
               f.numero_factura, f.serie as factura_serie, f.tipo_factura
        FROM cobros c
        JOIN pacientes p ON c.paciente_id = p.id
        LEFT JOIN facturas f ON c.factura_id = f.id
        WHERE c.fecha_cobro BETWEEN ? AND ?
    """
    params = [desde, hasta]

    if forma_pago != "todas":
        query += " AND c.forma_cobro = ?"
        params.append(forma_pago)

    if q.strip():
        query += " AND (p.nombre LIKE ? OR p.apellidos LIKE ? OR c.concepto LIKE ?)"
        term = f"%{q.strip()}%"
        params.extend([term, term, term])

    query += " ORDER BY c.fecha_cobro DESC, c.id DESC"
    
    cobros_rows = conn.execute(query, params).fetchall()

    # Arqueo / Totals by payment method
    totales_forma = conn.execute("""
        SELECT c.forma_cobro, SUM(c.importe) as total
        FROM cobros c
        WHERE c.fecha_cobro BETWEEN ? AND ? AND c.cobrado = 1
        GROUP BY c.forma_cobro
    """, (desde, hasta)).fetchall()

    total_general = sum(t["total"] for t in totales_forma)

    pacientes = conn.execute("SELECT id, nombre, apellidos, numero_expediente FROM pacientes WHERE estado = 'alta' ORDER BY apellidos, nombre").fetchall()
    
    conn.close()

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="cobros.html", context={
        "cobros": cobros_rows,
        "pacientes": pacientes,
        "fecha_desde": desde,
        "fecha_hasta": hasta,
        "forma_pago": forma_pago,
        "q": q,
        "totales_forma": totales_forma,
        "total_general": round(total_general, 2)
    })

@router.post("/nuevo")
def registrar_cobro(
    paciente_id: int = Form(...),
    fecha_cobro: str = Form(None),
    importe: float = Form(...),
    forma_cobro: str = Form(...),
    concepto: str = Form("A CUENTA"),
    cuenta_contable: str = Form("570-0000000"),
    importe_entregado: float = Form(None),
    factura_id: int = Form(None),
    generar_factura_directa: bool = Form(False)
):
    conn = get_db_connection()
    fecha_c = fecha_cobro if fecha_cobro else date.today().isoformat()
    
    # Calculate change
    importe_devuelto = None
    if importe_entregado is not None and importe_entregado >= importe:
        importe_devuelto = round(importe_entregado - importe, 2)

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cobros (
            paciente_id, factura_id, fecha_cobro, concepto, importe,
            forma_cobro, cuenta_contable, importe_entregado, importe_devuelto, cobrado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1);
    """, (
        paciente_id, factura_id, fecha_c, concepto, importe,
        forma_cobro, cuenta_contable, importe_entregado, importe_devuelto
    ))
    cobro_id = cursor.lastrowid

    # If user selected to generate invoice directly:
    if generar_factura_directa and not factura_id:
        current_year = date.today().year
        max_f = conn.execute("SELECT MAX(numero_factura) FROM facturas WHERE anio = ? AND serie = 'OFICIAL';", (current_year,)).fetchone()[0]
        next_f = (max_f or 400) + 1
        
        cursor.execute("""
            INSERT INTO facturas (
                paciente_id, serie, numero_factura, anio, fecha_factura,
                tipo_factura, base_imponible, porcentaje_iva, importe_iva, total_factura,
                forma_cobro_predeterminada, estado_pago
            ) VALUES (?, 'OFICIAL', ?, ?, ?, 'ordinaria', ?, 0.0, 0.0, ?, ?, 'cobrada');
        """, (paciente_id, next_f, current_year, fecha_c, importe, importe, forma_cobro))
        nueva_fac_id = cursor.lastrowid
        
        # Link invoice line and update collection with invoice id
        cursor.execute("""
            INSERT INTO factura_lineas (factura_id, concepto, cantidad, precio_unitario, descuento, total_linea)
            VALUES (?, ?, 1, ?, 0.0, ?);
        """, (nueva_fac_id, concepto, importe, importe))
        
        cursor.execute("UPDATE cobros SET factura_id = ? WHERE id = ?;", (nueva_fac_id, cobro_id))

    # History record
    cursor.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'actuacion_clinica', ?);
    """, (paciente_id, f"Cobro registrado: {importe:.2f} € mediante {forma_cobro} ({concepto})"))

    conn.commit()
    conn.close()
    
    return RedirectResponse(url=f"/pacientes/{paciente_id}#cobros", status_code=303)
