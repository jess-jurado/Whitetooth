import sys
import os

# Si se ejecuta con el Python del sistema (ej. Python 3.9 de macOS),
# conmutar automáticamente al entorno virtual del proyecto donde están instaladas las dependencias
script_dir = os.path.dirname(os.path.abspath(__file__))
venv_python = os.path.join(script_dir, "venv", "bin", "python3")
if os.path.exists(venv_python):
    if os.path.realpath(sys.executable) != os.path.realpath(venv_python):
        os.execv(venv_python, [venv_python] + sys.argv)

import uvicorn
import socket
import webbrowser
import threading
import time
from app.config import SERVER_HOST, SERVER_PORT

def obtener_ip_local():
    """Detecta la IP local de la máquina en la red LAN para mostrarla al usuario."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def buscar_puerto_disponible(puerto_inicial=8000):
    """Verifica si el puerto inicial está libre. Si está ocupado, busca el siguiente disponible."""
    for port in range(puerto_inicial, puerto_inicial + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', port))
                return port
            except OSError:
                continue
    return puerto_inicial

def abrir_navegador_auto(url):
    """Abre automáticamente la ventana del navegador web con Whitetooth."""
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass

if __name__ == "__main__":
    local_ip = obtener_ip_local()
    puerto = buscar_puerto_disponible(SERVER_PORT)

    url_local = f"http://localhost:{puerto}"
    url_lan = f"http://{local_ip}:{puerto}"

    print("=" * 68)
    print("🦷 WHITETOOTH - Sistema Integral de Gestión Clínica Dental")
    print("=" * 68)
    if puerto != SERVER_PORT:
        print(f"ℹ️  El puerto {SERVER_PORT} estaba en uso. Usando puerto alternativo {puerto}.")
    print(f"➜ Abriendo interfaz gráfica en: {url_local}")
    print(f"➜ Acceso desde Torre 2 / Gabinete (Red LAN): {url_lan}")
    print(f"➜ Base de datos SQLite: Segura y en caliente con respaldo diario")
    print("=" * 68)
    print("Presiona Ctrl+C en cualquier momento para detener el servidor.\n")

    # Iniciar apertura automática del navegador en segundo plano
    threading.Thread(target=abrir_navegador_auto, args=[url_local], daemon=True).start()

    # Ejecutar servidor FastAPI
    uvicorn.run("app.main:app", host=SERVER_HOST, port=puerto, reload=False)
