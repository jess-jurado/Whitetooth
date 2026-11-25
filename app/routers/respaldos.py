from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from pathlib import Path
from app.config import BACKUP_DIR, LAN_BACKUP_PATH, BACKUP_TIME, DB_PATH
from app.backup_service import crear_copia_seguridad, listar_copias_seguridad
from app.database import get_db_connection

router = APIRouter(prefix="/respaldos", tags=["respaldos"])

@router.get("", response_class=HTMLResponse)
def panel_respaldos(request: Request):
    conn = get_db_connection()
    logs = conn.execute("SELECT * FROM respaldos_log ORDER BY fecha_hora DESC LIMIT 20;").fetchall()
    conn.close()

    copias = listar_copias_seguridad()
    db_size_mb = round(DB_PATH.stat().st_size / (1024 * 1024), 2) if DB_PATH.exists() else 0

    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(request=request, name="respaldos.html", context={
        "logs": logs,
        "copias": copias,
        "db_size_mb": db_size_mb,
        "lan_backup_path": LAN_BACKUP_PATH,
        "backup_time": BACKUP_TIME
    })

@router.post("/ejecutar-manual")
def ejecutar_respaldo_manual():
    resultado = crear_copia_seguridad(tipo="manual")
    return JSONResponse(resultado)

@router.get("/descargar/{nombre_archivo}")
def descargar_copia(nombre_archivo: str):
    ruta = BACKUP_DIR / nombre_archivo
    if not ruta.exists() or not ruta.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path=str(ruta), filename=nombre_archivo, media_type="application/octet-stream")
