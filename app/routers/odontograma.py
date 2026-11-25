from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from app.database import get_db_connection

router = APIRouter(prefix="/api/odontograma", tags=["odontograma"])

class TratamientoCreate(BaseModel):
    tratamiento_catalogo_id: int
    pieza_fdi: Optional[int] = None
    caras: Optional[str] = None
    estado: str = "previsto" # estado_anterior, previsto, realizado
    precio: Optional[float] = None
    descuento_porcentaje: Optional[float] = 0.0
    doctor_id: Optional[int] = None
    observaciones: Optional[str] = None

class EstadoUpdate(BaseModel):
    estado: str # estado_anterior, previsto, realizado, cancelado

@router.get("/{paciente_id}")
def obtener_odontograma_paciente(paciente_id: int):
    conn = get_db_connection()
    
    rows = conn.execute("""
        SELECT tp.*, 
               ct.codigo as catalogo_codigo, ct.nombre as tratamiento_nombre, 
               ct.categoria as tratamiento_categoria, ct.color as tratamiento_color,
               u.nombre || ' ' || u.apellidos as doctor_nombre
        FROM tratamientos_paciente tp
        JOIN catalogo_tratamientos ct ON tp.tratamiento_catalogo_id = ct.id
        LEFT JOIN usuarios u ON tp.doctor_id = u.id
        WHERE tp.paciente_id = ?
        ORDER BY tp.created_at DESC
    """, (paciente_id,)).fetchall()
    
    tratamientos = [dict(r) for r in rows]
    conn.close()
    return JSONResponse(tratamientos)

@router.post("/{paciente_id}/tratamiento")
def registrar_tratamiento(paciente_id: int, data: TratamientoCreate):
    conn = get_db_connection()
    
    # Get default price from catalog if not provided
    precio_base = data.precio
    if precio_base is None:
        cat = conn.execute("SELECT precio_base FROM catalogo_tratamientos WHERE id = ?", (data.tratamiento_catalogo_id,)).fetchone()
        if not cat:
            conn.close()
            raise HTTPException(status_code=404, detail="Tratamiento no encontrado en catálogo")
        precio_base = cat["precio_base"]

    precio_final = round(precio_base * (1.0 - (data.descuento_porcentaje or 0.0) / 100.0), 2)
    today_str = date.today().isoformat()
    fecha_realizacion = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if data.estado == "realizado" else None

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tratamientos_paciente (
            paciente_id, tratamiento_catalogo_id, pieza_fdi, caras, estado,
            precio_original, descuento_porcentaje, precio_final, doctor_id,
            fecha_prevista, fecha_realizacion, observaciones
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        paciente_id, data.tratamiento_catalogo_id, data.pieza_fdi, data.caras, data.estado,
        precio_base, data.descuento_porcentaje, precio_final, data.doctor_id,
        today_str if data.estado == "previsto" else None,
        fecha_realizacion, data.observaciones
    ))
    nuevo_id = cursor.lastrowid

    # If completed, log in clinical history
    if data.estado == "realizado":
        cat_nom = conn.execute("SELECT nombre FROM catalogo_tratamientos WHERE id = ?", (data.tratamiento_catalogo_id,)).fetchone()["nombre"]
        diente_txt = f" Pieza {data.pieza_fdi}" if data.pieza_fdi else ""
        caras_txt = f" ({data.caras})" if data.caras else ""
        conn.execute("""
            INSERT INTO historial_clinico (paciente_id, doctor_id, tipo_evento, descripcion)
            VALUES (?, ?, 'actuacion_clinica', ?);
        """, (paciente_id, data.doctor_id, f"Tratamiento realizado: {cat_nom}{diente_txt}{caras_txt}"))

    conn.commit()
    conn.close()
    return JSONResponse({"success": True, "id": nuevo_id})

@router.put("/tratamiento/{tratamiento_id}/estado")
def actualizar_estado_tratamiento(tratamiento_id: int, data: EstadoUpdate):
    conn = get_db_connection()
    
    fecha_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if data.estado == "realizado" else None
    
    conn.execute("""
        UPDATE tratamientos_paciente 
        SET estado = ?, 
            fecha_realizacion = COALESCE(fecha_realizacion, ?)
        WHERE id = ?;
    """, (data.estado, fecha_real, tratamiento_id))

    if data.estado == "realizado":
        row = conn.execute("""
            SELECT tp.paciente_id, tp.doctor_id, tp.pieza_fdi, tp.caras, ct.nombre 
            FROM tratamientos_paciente tp
            JOIN catalogo_tratamientos ct ON tp.tratamiento_catalogo_id = ct.id
            WHERE tp.id = ?
        """, (tratamiento_id,)).fetchone()
        if row:
            diente_txt = f" Pieza {row['pieza_fdi']}" if row['pieza_fdi'] else ""
            caras_txt = f" ({row['caras']})" if row['caras'] else ""
            conn.execute("""
                INSERT INTO historial_clinico (paciente_id, doctor_id, tipo_evento, descripcion)
                VALUES (?, ?, 'actuacion_clinica', ?);
            """, (row["paciente_id"], row["doctor_id"], f"Tratamiento completado: {row['nombre']}{diente_txt}{caras_txt}"))

    conn.commit()
    conn.close()
    return JSONResponse({"success": True})

@router.delete("/tratamiento/{tratamiento_id}")
def eliminar_tratamiento(tratamiento_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM tratamientos_paciente WHERE id = ?;", (tratamiento_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"success": True})
