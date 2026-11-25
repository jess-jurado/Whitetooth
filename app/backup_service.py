import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from app.config import DB_PATH, BACKUP_DIR, LAN_BACKUP_PATH, BACKUP_TIME, BACKUP_RETENTION_DAYS

def crear_copia_seguridad(tipo: str = "manual", ruta_red_lan: str = None) -> dict:
    """
    Realiza una copia de seguridad atómica en caliente utilizando VACUUM INTO de SQLite.
    Garantiza que la copia es 100% consistente sin bloquear a los usuarios.
    Copia adicionalmente el archivo resultante a la Torre 2 si hay ruta LAN configurada.
    """
    if not DB_PATH.exists():
        return {"success": False, "error": "La base de datos original no existe"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"whitetooth_backup_{timestamp}.db"
    ruta_destino_local = BACKUP_DIR / nombre_archivo

    # 1. Ejecutar SQLite VACUUM INTO
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(f"VACUUM INTO '{ruta_destino_local.as_posix()}';")
        conn.close()
    except Exception as e:
        return {"success": False, "error": f"Error al generar snapshot SQLite: {str(e)}"}

    tamano_bytes = ruta_destino_local.stat().st_size
    destino_lan_aplicado = None
    lan_exito = True
    lan_error_msg = ""

    # 2. Copia a Torre 2 (Red Local) si está configurada
    destino_lan = ruta_red_lan or LAN_BACKUP_PATH
    if destino_lan:
        try:
            lan_dir = Path(destino_lan)
            if lan_dir.exists() or destino_lan.startswith("\\\\"):
                lan_dest_file = lan_dir / nombre_archivo
                shutil.copy2(ruta_destino_local, lan_dest_file)
                destino_lan_aplicado = str(lan_dest_file)
        except Exception as e:
            lan_exito = False
            lan_error_msg = f"Error al transferir a Torre 2: {str(e)}"

    # 3. Registrar en la tabla de respaldos_log
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO respaldos_log (tipo, archivo_nombre, tamano_bytes, destino_local, destino_red_lan, estado, mensaje)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (
            tipo,
            nombre_archivo,
            tamano_bytes,
            str(ruta_destino_local),
            destino_lan_aplicado,
            "exito" if lan_exito else "aviso",
            "Copia local y LAN completada" if lan_exito else f"Copia local OK. Advertencia LAN: {lan_error_msg}"
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Aviso al guardar log de respaldo:", e)

    # 4. Rotación de copias antiguas locales
    limpiar_copias_antiguas()

    return {
        "success": True,
        "exitoso": True,
        "archivo": nombre_archivo,
        "tamano_mb": round(tamano_bytes / (1024 * 1024), 2),
        "ruta_local": str(ruta_destino_local),
        "ruta_lan": destino_lan_aplicado,
        "mensaje": "Copia de seguridad realizada con éxito." + (f" ({lan_error_msg})" if lan_error_msg else "")
    }

def limpiar_copias_antiguas():
    """Elimina copias locales más antiguas que los días de retención configurados."""
    try:
        limite = datetime.now() - timedelta(days=BACKUP_RETENTION_DAYS)
        for archivo in BACKUP_DIR.glob("whitetooth_backup_*.db"):
            if datetime.fromtimestamp(archivo.stat().st_mtime) < limite:
                archivo.unlink(missing_ok=True)
    except Exception as e:
        print("Error en limpieza de respaldos antiguos:", e)

def listar_copias_seguridad():
    """Devuelve la lista de copias locales disponibles ordenadas por fecha."""
    copias = []
    for archivo in sorted(BACKUP_DIR.glob("whitetooth_backup_*.db"), reverse=True):
        stat = archivo.stat()
        copias.append({
            "nombre": archivo.name,
            "tamano_mb": round(stat.st_size / (1024 * 1024), 2),
            "fecha": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "ruta": str(archivo)
        })
    return copias

def hilo_respaldo_diario():
    """Demostrador en segundo plano que ejecuta el respaldo diario automático."""
    while True:
        try:
            ahora = datetime.now()
            hora_actual = ahora.strftime("%H:%M")
            if hora_actual == BACKUP_TIME:
                print(f"[{datetime.now()}] Iniciando copia de seguridad programada diaria...")
                crear_copia_seguridad(tipo="automatico")
                time.sleep(70) # Esperar más de un minuto para no repetir el mismo minuto
            time.sleep(30)
        except Exception as e:
            print("Error en hilo de respaldo diario:", e)
            time.sleep(60)

def iniciar_servicio_respaldos():
    """Inicia el hilo demonio de respaldo automático."""
    t = threading.Thread(target=hilo_respaldo_diario, daemon=True)
    t.start()
