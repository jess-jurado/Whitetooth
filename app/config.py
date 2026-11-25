import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "whitetooth.db"
BACKUP_DIR = DATA_DIR / "backups"
UPLOADS_DIR = DATA_DIR / "uploads"

# Ensure runtime directories exist
DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

# Server network settings
SERVER_HOST = os.getenv("WHITETOOTH_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("WHITETOOTH_PORT", "8000"))

# Clinic settings
CLINICA_DEFAULT = {
    "nombre_comercial": "Clínica Dental Whitetooth",
    "nombre_fiscal": "Whitetooth Odontología Integral S.L.",
    "cif_nif": "B-99887766",
    "direccion": "Calle Mayor 14, 1º B",
    "codigo_postal": "29001",
    "ciudad": "Málaga",
    "provincia": "Málaga",
    "telefono": "952 12 34 56",
    "email": "contacto@clinicawhitetooth.es",
    "texto_legal_factura": "Actividad sanitaria de odontología exenta de IVA según el Art. 20.Uno.3º de la Ley 37/1992 del IVA.",
    "texto_legal_rgpd": "En cumplimiento del RGPD (UE) 2016/679 y la LOPD-GDD 3/2018, sus datos de salud serán tratados con la exclusiva finalidad de prestarle asistencia bucodental.",
    "serie_factura": "OFICIAL",
    "serie_abono": "ABONO",
}

# Automated Backup Settings
BACKUP_TIME = os.getenv("BACKUP_TIME", "21:00")
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
LAN_BACKUP_PATH = os.getenv("LAN_BACKUP_PATH", "") # e.g. \\TORRE2\backups_whitetooth or /Volumes/Torre2/backups
