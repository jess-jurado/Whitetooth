from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
import urllib.parse
from app.database import get_db_connection

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

PLANTILLAS = {
    "recordatorio_cita": "Hola {nombre}, le recordamos su cita en {clinica} programada para el {fecha} a las {hora} con el/la Dr/a. {doctor}. Rogamos confirme su asistencia respondiendo a este mensaje. ¡Muchas gracias!",
    "postoperatorio": "Hola {nombre}, desde {clinica} queremos saber cómo se encuentra tras su tratamiento de hoy. Recuerde no ingerir alimentos muy calientes y seguir la pauta médica indicada.",
    "recall_revision": "Hola {nombre}, ha transcurrido el tiempo recomendado desde su última visita en {clinica}. Le aconsejamos agendar su revisión periódica para mantener su salud bucodental impecable. ¿Desea que le reservemos un hueco esta semana?",
    "presupuesto_listo": "Hola {nombre}, ya tiene disponible en {clinica} su plan de tratamiento y presupuesto personalizado. Quedamos a su disposición para resolver cualquier duda."
}

@router.post("/generar-enlace")
def generar_enlace_whatsapp(
    paciente_id: int = Form(...),
    tipo_plantilla: str = Form("recordatorio_cita"),
    fecha: str = Form(""),
    hora: str = Form(""),
    doctor: str = Form(""),
    cita_id: int = Form(None)
):
    conn = get_db_connection()
    paciente = conn.execute("SELECT * FROM pacientes WHERE id = ?", (paciente_id,)).fetchone()
    if not paciente:
        conn.close()
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    clinica = conn.execute("SELECT nombre_comercial FROM clinica LIMIT 1;").fetchone()["nombre_comercial"]

    # Format Spanish phone number
    movil = paciente["telefono_movil"].replace(" ", "").replace("-", "")
    if not movil.startswith("34") and len(movil) == 9:
        movil = "34" + movil

    plantilla = PLANTILLAS.get(tipo_plantilla, PLANTILLAS["recordatorio_cita"])
    texto = plantilla.format(
        nombre=f"{paciente['nombre']} {paciente['apellidos']}",
        clinica=clinica,
        fecha=fecha,
        hora=hora,
        doctor=doctor or "de nuestro equipo"
    )

    url_whatsapp = f"https://wa.me/{movil}?text={urllib.parse.quote(texto)}"

    # Record in history and update appointment flag
    conn.execute("""
        INSERT INTO historial_clinico (paciente_id, tipo_evento, descripcion)
        VALUES (?, 'comunicacion_whatsapp', ?);
    """, (paciente_id, f"WhatsApp ({tipo_plantilla}): {texto}"))

    if cita_id:
        conn.execute("UPDATE citas SET recordatorio_whatsapp_enviado = 1 WHERE id = ?;", (cita_id,))

    conn.commit()
    conn.close()

    return JSONResponse({
        "success": True,
        "url": url_whatsapp,
        "texto": texto,
        "telefono": movil
    })
