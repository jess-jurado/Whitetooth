import uvicorn
import socket
from app.config import SERVER_HOST, SERVER_PORT

def obtener_ip_local():
    """Detecta la IP local de la máquina en la red LAN para mostrarla al usuario."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No envía datos reales, solo determina la interfaz saliente
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

if __name__ == "__main__":
    local_ip = obtener_ip_local()
    print("=" * 65)
    print("🦷 WHITETOOTH - Sistema Integral de Gestión Clínica Dental")
    print("=" * 65)
    print(f"➜ Acceso local en este equipo (Torre 1): http://localhost:{SERVER_PORT}")
    print(f"➜ Acceso desde Torre 2 / Gabinete (Red LAN): http://{local_ip}:{SERVER_PORT}")
    print(f"➜ Base de datos SQLite: Segura y en caliente con respaldo diario")
    print("=" * 65)
    uvicorn.run("app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
