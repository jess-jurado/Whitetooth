import sqlite3
from datetime import datetime, date
from app.config import DB_PATH, CLINICA_DEFAULT

def get_db_connection():
    """Returns a SQLite connection with WAL mode and Row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

def init_db():
    """Initializes all database tables and seed data if not present."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- 1. Clínica
    CREATE TABLE IF NOT EXISTS clinica (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre_comercial TEXT NOT NULL,
        nombre_fiscal TEXT NOT NULL,
        cif_nif TEXT NOT NULL,
        direccion TEXT,
        codigo_postal TEXT,
        ciudad TEXT,
        provincia TEXT,
        telefono TEXT,
        email TEXT,
        texto_legal_factura TEXT,
        texto_legal_rgpd TEXT,
        serie_factura TEXT DEFAULT 'OFICIAL',
        serie_abono TEXT DEFAULT 'ABONO',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 2. Usuarios / Profesionales
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        apellidos TEXT NOT NULL,
        email TEXT,
        telefono TEXT,
        rol TEXT NOT NULL CHECK(rol IN ('administrador', 'doctor', 'higienista', 'recepcion')),
        numero_colegiado TEXT,
        color_agenda TEXT DEFAULT '#3B82F6',
        activo INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 3. Gabinetes / Despachos
    CREATE TABLE IF NOT EXISTS gabinetes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        color TEXT DEFAULT '#10B981',
        orden INTEGER DEFAULT 0,
        activo INTEGER DEFAULT 1
    );

    -- 4. Pacientes
    CREATE TABLE IF NOT EXISTS pacientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_expediente INTEGER UNIQUE,
        nombre TEXT NOT NULL,
        apellidos TEXT NOT NULL,
        nif_cif TEXT,
        fecha_nacimiento DATE,
        telefono_fijo TEXT,
        telefono_movil TEXT NOT NULL,
        email TEXT,
        direccion TEXT,
        codigo_postal TEXT,
        poblacion TEXT,
        provincia TEXT,
        tipo_paciente TEXT DEFAULT 'general' CHECK(tipo_paciente IN ('general', 'aseguradora', 'infantil', 'vip')),
        aseguradora_nombre TEXT,
        numero_poliza TEXT,
        alergias TEXT,
        antecedentes_medicos TEXT,
        consentimiento_rgpd_firmado INTEGER DEFAULT 0,
        fecha_consentimiento_rgpd TIMESTAMP,
        estado TEXT DEFAULT 'alta' CHECK(estado IN ('alta', 'baja')),
        motivo_consulta TEXT,
        notas_administrativas TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 5. Citas / Agenda
    CREATE TABLE IF NOT EXISTS citas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        gabinete_id INTEGER NOT NULL REFERENCES gabinetes(id),
        doctor_id INTEGER REFERENCES usuarios(id),
        fecha_hora_inicio TIMESTAMP NOT NULL,
        fecha_hora_fin TIMESTAMP NOT NULL,
        motivo TEXT,
        estado TEXT DEFAULT 'programada' CHECK(estado IN ('programada', 'confirmada', 'en_espera', 'en_consulta', 'realizada', 'cancelada', 'no_asiste')),
        color TEXT,
        recordatorio_whatsapp_enviado INTEGER DEFAULT 0,
        notas TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 6. Catálogo de Tratamientos
    CREATE TABLE IF NOT EXISTS catalogo_tratamientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        nombre TEXT NOT NULL,
        categoria TEXT NOT NULL,
        precio_base REAL NOT NULL DEFAULT 0.0,
        requiere_diente INTEGER DEFAULT 1,
        requiere_cara INTEGER DEFAULT 0,
        color TEXT DEFAULT '#3B82F6',
        icono TEXT,
        activo INTEGER DEFAULT 1
    );

    -- 7. Tratamientos de Paciente / Odontograma
    CREATE TABLE IF NOT EXISTS tratamientos_paciente (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        tratamiento_catalogo_id INTEGER NOT NULL REFERENCES catalogo_tratamientos(id),
        pieza_fdi INTEGER,
        caras TEXT, -- Ej: 'V', 'M,O', 'V,D,O'
        estado TEXT DEFAULT 'previsto' CHECK(estado IN ('estado_anterior', 'previsto', 'realizado', 'cancelado')),
        precio_original REAL NOT NULL,
        descuento_porcentaje REAL DEFAULT 0.0,
        precio_final REAL NOT NULL,
        doctor_id INTEGER REFERENCES usuarios(id),
        cita_id INTEGER REFERENCES citas(id),
        fecha_prevista DATE,
        fecha_realizacion TIMESTAMP,
        factura_id INTEGER REFERENCES facturas(id),
        observaciones TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 8. Presupuestos
    CREATE TABLE IF NOT EXISTS presupuestos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        numero_presupuesto INTEGER NOT NULL,
        anio INTEGER NOT NULL,
        fecha DATE NOT NULL,
        descripcion TEXT,
        descuento_global_porcentaje REAL DEFAULT 0.0,
        total_honorarios REAL DEFAULT 0.0,
        total_descuento REAL DEFAULT 0.0,
        total_presupuesto REAL DEFAULT 0.0,
        total_aceptado REAL DEFAULT 0.0,
        estado TEXT DEFAULT 'pendiente' CHECK(estado IN ('pendiente', 'aceptado_total', 'aceptado_parcial', 'rechazado')),
        doctor_id INTEGER REFERENCES usuarios(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 9. Líneas de Presupuesto
    CREATE TABLE IF NOT EXISTS presupuesto_lineas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        presupuesto_id INTEGER NOT NULL REFERENCES presupuestos(id) ON DELETE CASCADE,
        tratamiento_catalogo_id INTEGER NOT NULL REFERENCES catalogo_tratamientos(id),
        pieza_fdi INTEGER,
        caras TEXT,
        descripcion TEXT NOT NULL,
        precio_unitario REAL NOT NULL,
        descuento_porcentaje REAL DEFAULT 0.0,
        importe REAL NOT NULL,
        aceptado INTEGER DEFAULT 0,
        orden INTEGER DEFAULT 0
    );

    -- 10. Facturas Oficiales y de Abono
    CREATE TABLE IF NOT EXISTS facturas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
        serie TEXT NOT NULL DEFAULT 'OFICIAL',
        numero_factura INTEGER NOT NULL,
        anio INTEGER NOT NULL,
        fecha_factura DATE NOT NULL,
        tipo_factura TEXT DEFAULT 'ordinaria' CHECK(tipo_factura IN ('ordinaria', 'abono_rectificativa')),
        factura_rectificada_id INTEGER REFERENCES facturas(id),
        motivo_rectificacion TEXT,
        base_imponible REAL NOT NULL,
        porcentaje_iva REAL DEFAULT 0.0,
        importe_iva REAL DEFAULT 0.0,
        total_factura REAL NOT NULL,
        forma_cobro_predeterminada TEXT DEFAULT 'Tarjeta',
        estado_pago TEXT DEFAULT 'cobrada' CHECK(estado_pago IN ('cobrada', 'pendiente_parcial', 'impagada')),
        bloqueada INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(serie, numero_factura, anio)
    );

    -- 11. Líneas de Factura
    CREATE TABLE IF NOT EXISTS factura_lineas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        factura_id INTEGER NOT NULL REFERENCES facturas(id) ON DELETE RESTRICT,
        tratamiento_paciente_id INTEGER REFERENCES tratamientos_paciente(id),
        concepto TEXT NOT NULL,
        pieza_fdi INTEGER,
        cantidad INTEGER DEFAULT 1,
        precio_unitario REAL NOT NULL,
        descuento REAL DEFAULT 0.0,
        total_linea REAL NOT NULL
    );

    -- 12. Cobros / Flujo de Caja
    CREATE TABLE IF NOT EXISTS cobros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id),
        factura_id INTEGER REFERENCES facturas(id),
        fecha_cobro DATE NOT NULL,
        concepto TEXT NOT NULL,
        importe REAL NOT NULL,
        forma_cobro TEXT NOT NULL CHECK(forma_cobro IN ('Efectivo', 'Tarjeta', 'Bizum', 'Transferencia', 'Financiado', 'Cheque', 'Pagaré', 'Recibo')),
        cuenta_contable TEXT DEFAULT '570-0000000',
        importe_entregado REAL,
        importe_devuelto REAL,
        cobrado INTEGER DEFAULT 1,
        usuario_id INTEGER REFERENCES usuarios(id),
        observaciones TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 13. Historial Clínico
    CREATE TABLE IF NOT EXISTS historial_clinico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        doctor_id INTEGER REFERENCES usuarios(id),
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tipo_evento TEXT NOT NULL CHECK(tipo_evento IN ('actuacion_clinica', 'comunicacion_whatsapp', 'llamada', 'consentimiento_firmado', 'receta', 'incidencia')),
        descripcion TEXT NOT NULL,
        adjunto_url TEXT
    );

    -- 14. Pedidos a Laboratorio Protésico
    CREATE TABLE IF NOT EXISTS pedidos_laboratorio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paciente_id INTEGER NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
        laboratorio_nombre TEXT NOT NULL,
        tipo_trabajo TEXT NOT NULL,
        color_guia TEXT,
        fecha_envio DATE NOT NULL,
        fecha_prevista_entrega DATE,
        fecha_recepcion_real DATE,
        coste REAL DEFAULT 0.0,
        estado TEXT DEFAULT 'enviado' CHECK(estado IN ('enviado', 'recibido', 'probado_en_boca', 'ajustes_necesarios', 'colocado')),
        observaciones TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 15. Configuración y Log de Respaldos
    CREATE TABLE IF NOT EXISTS respaldos_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tipo TEXT NOT NULL CHECK(tipo IN ('automatico', 'manual')),
        archivo_nombre TEXT NOT NULL,
        tamano_bytes INTEGER,
        destino_local TEXT,
        destino_red_lan TEXT,
        estado TEXT DEFAULT 'exito' CHECK(estado IN ('exito', 'error')),
        mensaje TEXT
    );

    -- Índices para máximo rendimiento
    CREATE INDEX IF NOT EXISTS idx_pacientes_movil ON pacientes(telefono_movil);
    CREATE INDEX IF NOT EXISTS idx_pacientes_expediente ON pacientes(numero_expediente);
    CREATE INDEX IF NOT EXISTS idx_citas_inicio ON citas(fecha_hora_inicio);
    CREATE INDEX IF NOT EXISTS idx_citas_gabinete ON citas(gabinete_id, fecha_hora_inicio);
    CREATE INDEX IF NOT EXISTS idx_tratamientos_paciente ON tratamientos_paciente(paciente_id);
    CREATE INDEX IF NOT EXISTS idx_cobros_paciente ON cobros(paciente_id);
    CREATE INDEX IF NOT EXISTS idx_cobros_fecha ON cobros(fecha_cobro);
    CREATE INDEX IF NOT EXISTS idx_facturas_paciente ON facturas(paciente_id);
    CREATE INDEX IF NOT EXISTS idx_facturas_numero ON facturas(serie, anio, numero_factura);
    """)

    # Seed initial data if empty
    cursor.execute("SELECT COUNT(*) FROM clinica;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO clinica (nombre_comercial, nombre_fiscal, cif_nif, direccion, codigo_postal, ciudad, provincia, telefono, email, texto_legal_factura, texto_legal_rgpd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            CLINICA_DEFAULT["nombre_comercial"],
            CLINICA_DEFAULT["nombre_fiscal"],
            CLINICA_DEFAULT["cif_nif"],
            CLINICA_DEFAULT["direccion"],
            CLINICA_DEFAULT["codigo_postal"],
            CLINICA_DEFAULT["ciudad"],
            CLINICA_DEFAULT["provincia"],
            CLINICA_DEFAULT["telefono"],
            CLINICA_DEFAULT["email"],
            CLINICA_DEFAULT["texto_legal_factura"],
            CLINICA_DEFAULT["texto_legal_rgpd"]
        ))

    # Seed professionals
    cursor.execute("SELECT COUNT(*) FROM usuarios;")
    if cursor.fetchone()[0] == 0:
        usuarios_seed = [
            ("Alejandro", "Soler García", "a.soler@clinicawhitetooth.es", "600112233", "doctor", "29004521", "#3B82F6"),
            ("Carmen", "Navarro Rios", "c.navarro@clinicawhitetooth.es", "600223344", "doctor", "29004899", "#8B5CF6"),
            ("Marta", "Gómez Pérez", "marta@clinicawhitetooth.es", "600334455", "recepcion", None, "#10B981"),
        ]
        cursor.executemany("""
            INSERT INTO usuarios (nombre, apellidos, email, telefono, rol, numero_colegiado, color_agenda)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, usuarios_seed)

    # Seed cabinets (1 activo por defecto, ampliable en opciones)
    cursor.execute("SELECT COUNT(*) FROM gabinetes;")
    if cursor.fetchone()[0] == 0:
        gabinetes_seed = [
            ("GABINETE 1 (Principal)", "#0284C7", 1, 1),
            ("GABINETE 2", "#8B5CF6", 2, 0),
            ("GABINETE 3", "#10B981", 3, 0),
        ]
        cursor.executemany("""
            INSERT INTO gabinetes (nombre, color, orden, activo)
            VALUES (?, ?, ?, ?);
        """, gabinetes_seed)

    # Seed treatment catalog
    cursor.execute("SELECT COUNT(*) FROM catalogo_tratamientos;")
    if cursor.fetchone()[0] == 0:
        tratamientos_seed = [
            ("OBT1", "Obturación simple (1 cara)", "conservadora", 45.0, 1, 1, "#3B82F6", "tooth"),
            ("OBT2", "Obturación compuesta (2 caras)", "conservadora", 55.0, 1, 1, "#2563EB", "tooth"),
            ("OBTC", "Obturación compleja (>2 caras / reconstrucción)", "conservadora", 70.0, 1, 1, "#1D4ED8", "tooth"),
            ("ENDO1", "Endodoncia unirradicular", "endodoncia", 120.0, 1, 0, "#F59E0B", "activity"),
            ("ENDO2", "Endodoncia multirradicular", "endodoncia", 160.0, 1, 0, "#D97706", "activity"),
            ("COR-POR", "Corona porcelana / zirconio", "protesis", 280.0, 1, 0, "#EC4899", "shield"),
            ("EXO-SIM", "Extracción simple", "cirugia", 40.0, 1, 0, "#EF4444", "trash-2"),
            ("EXO-QUI", "Extracción quirúrgica / cordal", "cirugia", 90.0, 1, 0, "#DC2626", "trash-2"),
            ("IMP-TIT", "Implante titanio alta gama", "implantes", 650.0, 1, 0, "#6366F1", "anchor"),
            ("PRO-ACR", "Prótesis acrílica de 1 a 4 piezas", "protesis", 410.0, 0, 0, "#8B5CF6", "layers"),
            ("LIM-TAR", "Tartrectomía / Limpieza bucal", "prevencion", 35.0, 0, 0, "#10B981", "sparkles"),
            ("BLANQ", "Blanqueamiento dental clínica + férulas", "estetica", 250.0, 0, 0, "#14B8A6", "sun"),
            ("FER-DES", "Férula de descarga tipo Michigan", "conservadora", 180.0, 0, 0, "#64748B", "smile"),
        ]
        cursor.executemany("""
            INSERT INTO catalogo_tratamientos (codigo, nombre, categoria, precio_base, requiere_diente, requiere_cara, color, icono)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, tratamientos_seed)

    # Seed sample patients (extracted from the clinic photos)
    cursor.execute("SELECT COUNT(*) FROM pacientes;")
    if cursor.fetchone()[0] == 0:
        pacientes_seed = [
            (1767, "JOSEFA", "RODRIGUEZ MORENO", "50031047-K", "1968-05-14", "952123456", "625342048", "josefa.rm@gmail.com", "Calle Larios 12, 3º", "29005", "Málaga", "Málaga", "general", None, None, "Alergia a la penicilina", "Hipertensión controlada", 1, "2024-02-10 10:00:00", "alta", "Revisión general y prótesis", "Paciente puntual"),
            (2045, "JOSE CARLOS", "DEL POZO MARTIN", "24891574-P", "1982-11-20", "952987654", "611223344", "jcpozo@gmail.com", "Av. Andalucía 45", "29007", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-05-18 11:30:00", "alta", "Molestia en molar inferior", None),
            (1158, "EVA CRISTINA", "JAVIER REMES", "76754460-X", "1990-03-08", None, "622334455", "evajavier@hotmail.com", "Calle Granada 8", "29015", "Málaga", "Málaga", "general", None, None, "Alergia al látex", None, 1, "2023-09-01 09:15:00", "alta", "Limpieza anual", None),
            (2281, "HECTOR", "SAVINI", "Z-3127648-K", "1975-07-29", None, "633445566", "hsavini@outlook.com", "Paseo Marítimo 30", "29016", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-01-15 16:00:00", "alta", "Presupuesto implante", None),
            (1593, "LUIS", "VALERO AGUAYO", "25952795-D", "1988-12-05", "952554433", "644556677", "lvalero@gmail.com", "Calle Victoria 19", "29012", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-06-22 12:00:00", "alta", "Dolor al masticar", None),
            (174, "ALVARO", "TAMAYO", "25665831-Q", "1960-09-15", None, "655667788", "atamayo@yahoo.es", "Calle Carretería 5", "29008", "Málaga", "Málaga", "general", None, None, None, "Diabetes tipo 2", 1, "2022-04-10 10:00:00", "alta", "Corona en premolar", None),
            (2084, "TOMAS", "PEREZ ATIENZA", "74985995-L", "1995-04-12", None, "666778899", "tomas.perez@gmail.com", "Calle Marmoles 22", "29007", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-03-05 17:00:00", "alta", "Empaste caído", None),
            (1820, "ANTONIA ANA", "ALARCON JIMENEZ", "24832507-M", "1971-08-25", "952332211", "677889900", "antonia.alarcon@gmail.com", "Calle Hilera 14", "29007", "Málaga", "Málaga", "general", None, None, None, None, 1, "2023-11-12 18:00:00", "alta", "Revisión periódica", None),
            (2054, "M CARMEN", "TOLEDO GARCIA", "08916171-Z", "1965-02-18", None, "688990011", "mctoledo@gmail.com", "Av. Aurora 10", "29002", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-02-28 11:00:00", "alta", "Endodoncia", None),
            (724, "SARA", "OREJUELA LOPEZ", "77183846-D", "1983-06-30", "952778899", "699001122", "sara.orejuela@gmail.com", "Calle Álamos 11", "29012", "Málaga", "Málaga", "general", None, None, None, None, 1, "2021-10-04 16:30:00", "alta", "Blanqueamiento", None),
            (1843, "RAMON", "CHECA GEA", "25323550-K", "1979-01-14", None, "610112233", "rcheca@gmail.com", "Calle Nueva 2", "29005", "Málaga", "Málaga", "general", None, None, None, None, 1, "2023-12-01 10:30:00", "alta", "Reconstrucción", None),
            (427, "ALVARO", "LOPEZ DE CASAS", "26808600-F", "1955-10-09", "952445566", "620223344", "alopezcasas@gmail.com", "Paseo de Reding 4", "29016", "Málaga", "Málaga", "general", None, None, None, None, 1, "2020-05-15 12:30:00", "alta", "Implantes", None),
            (2244, "REMEDIOS", "GARCIA SEGOVIA", "25034029-R", "1973-04-03", None, "630334455", "remedios.garcia@gmail.com", "Calle San Juan 7", "29005", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-04-12 17:30:00", "alta", "Prótesis", None),
            (167, "JOSE LUIS", "MATEOS", "24700380-J", "1963-07-22", None, "640445566", "jlmateos@gmail.com", "Calle Companía 15", "29008", "Málaga", "Málaga", "general", None, None, None, None, 1, "2019-08-20 18:30:00", "alta", "Revisión", None),
            (2285, "ANTONIO", "MORENO MARTINEZ", "25112233-A", "1986-09-11", None, "650556677", "amoreno@gmail.com", "Calle Cuarteles 18", "29002", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-07-01 09:30:00", "alta", "Limpieza", None),
            (285, "GLORIA", "CASTILLO ROMERO", "25071062-G", "1969-12-19", "952667788", "660667788", "gcastillo@gmail.com", "Calle Salitre 21", "29002", "Málaga", "Málaga", "general", None, None, None, None, 1, "2021-03-10 11:30:00", "alta", "Férula", None),
            (2286, "CRISTINA", "MARTIN GONZALEZ", "07154835-H", "1992-05-24", None, "670778899", "cmarting@gmail.com", "Calle Cisneros 6", "29005", "Málaga", "Málaga", "general", None, None, None, None, 1, "2024-08-14 16:00:00", "alta", "Caries", None),
            (1108, "SONIA", "RIVERA FRANQUELO", "74826096-N", "1980-02-14", None, "680889900", "srivera@gmail.com", "Av. Carlos Haya 33", "29010", "Málaga", "Málaga", "general", None, None, None, None, 1, "2023-05-09 10:00:00", "alta", "Ortodoncia", None),
            (1449, "M ANGELES", "GONZALEZ ZAMBRANA", "24811223-K", "1977-10-30", "952889900", "690990011", "magz@gmail.com", "Calle Beatas 20", "29008", "Málaga", "Málaga", "general", None, None, None, None, 1, "2023-01-20 17:00:00", "alta", "Tratamiento completo", None),
            (1862, "RAFAEL", "LOPEZ ROBLES", "24829616-J", "1967-08-16", "952112244", "601112233", "rlopezrobles@gmail.com", "Calle Camas 3", "29005", "Málaga", "Málaga", "general", None, None, None, None, 1, "2023-04-18 12:00:00", "alta", "Cirugía", None),
        ]
        cursor.executemany("""
            INSERT INTO pacientes (numero_expediente, nombre, apellidos, nif_cif, fecha_nacimiento, telefono_fijo, telefono_movil, email, direccion, codigo_postal, poblacion, provincia, tipo_paciente, aseguradora_nombre, numero_poliza, alergias, antecedentes_medicos, consentimiento_rgpd_firmado, fecha_consentimiento_rgpd, estado, motivo_consulta, notas_administrativas)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, pacientes_seed)

    # Seed sample treatments, appointments, budgets and billing for Josefa Rodriguez Moreno (patient_id=1)
    cursor.execute("SELECT COUNT(*) FROM presupuestos;")
    if cursor.fetchone()[0] == 0:
        today_str = date.today().isoformat()
        current_year = date.today().year

        # Presupuesto 320 for Josefa Rodriguez Moreno
        cursor.execute("""
            INSERT INTO presupuestos (paciente_id, numero_presupuesto, anio, fecha, descripcion, total_honorarios, total_descuento, total_presupuesto, total_aceptado, estado, doctor_id)
            VALUES (1, 320, ?, ?, 'Presupuesto Prótesis Acrílica 1 a 4 piezas', 410.0, 0.0, 410.0, 410.0, 'aceptado_total', 1);
        """, (current_year, today_str))
        presupuesto_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO presupuesto_lineas (presupuesto_id, tratamiento_catalogo_id, pieza_fdi, caras, descripcion, precio_unitario, descuento_porcentaje, importe, aceptado, orden)
            VALUES (?, 10, NULL, NULL, 'PROTESIS ACRILICO DE 1 A 4 PIEZAS', 410.0, 0.0, 410.0, 1, 1);
        """, (presupuesto_id,))

        # Treatment planned for Josefa
        cursor.execute("""
            INSERT INTO tratamientos_paciente (paciente_id, tratamiento_catalogo_id, pieza_fdi, caras, estado, precio_original, descuento_porcentaje, precio_final, doctor_id, fecha_prevista, observaciones)
            VALUES (1, 10, NULL, NULL, 'previsto', 410.0, 0.0, 410.0, 1, ?, 'Aceptado de Presupuesto 320');
        """, (today_str,))

        # Sample treatments for Odontogram of Josefa
        cursor.execute("""
            INSERT INTO tratamientos_paciente (paciente_id, tratamiento_catalogo_id, pieza_fdi, caras, estado, precio_original, descuento_porcentaje, precio_final, doctor_id, fecha_realizacion, observaciones)
            VALUES 
            (1, 2, 37, 'O,D', 'realizado', 55.0, 0.0, 55.0, 1, ?, 'Obturación compuesta terminada'),
            (1, 1, 12, 'D', 'realizado', 45.0, 0.0, 45.0, 1, ?, 'Obturación simple'),
            (1, 11, NULL, NULL, 'realizado', 35.0, 0.0, 35.0, 1, ?, 'Tartrectomía anual');
        """, (today_str, today_str, today_str))

        # Sample Invoice 438
        cursor.execute("""
            INSERT INTO facturas (paciente_id, serie, numero_factura, anio, fecha_factura, tipo_factura, base_imponible, porcentaje_iva, importe_iva, total_factura, forma_cobro_predeterminada, estado_pago)
            VALUES (20, 'OFICIAL', 438, ?, ?, 'ordinaria', 1000.0, 0.0, 0.0, 1000.0, 'Transferencia', 'cobrada');
        """, (current_year, today_str))
        factura_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO factura_lineas (factura_id, concepto, cantidad, precio_unitario, descuento, total_linea)
            VALUES (?, 'Tratamiento Quirúrgico e Implantes', 1, 1000.0, 0.0, 1000.0);
        """, (factura_id,))

        cursor.execute("""
            INSERT INTO cobros (paciente_id, factura_id, fecha_cobro, concepto, importe, forma_cobro, cuenta_contable, cobrado, usuario_id)
            VALUES (20, ?, ?, 'A CUENTA - Factura Oficial 438', 1000.0, 'Transferencia', '572-0000000', 1, 1);
        """, (factura_id, today_str))

        # Sample Appointments for today in the cabinets
        cursor.execute("""
            INSERT INTO citas (paciente_id, gabinete_id, doctor_id, fecha_hora_inicio, fecha_hora_fin, motivo, estado, color)
            VALUES 
            (1, 1, 1, ? || ' 09:30:00', ? || ' 10:15:00', 'Prótesis acrílica toma de medidas', 'confirmada', '#3B82F6'),
            (2, 1, 1, ? || ' 10:30:00', ? || ' 11:15:00', 'Obturación molar 46', 'en_espera', '#10B981'),
            (3, 2, 2, ? || ' 10:00:00', ? || ' 10:45:00', 'Sutura y revisión implante', 'confirmada', '#8B5CF6'),
            (4, 2, 2, ? || ' 11:30:00', ? || ' 12:30:00', 'Colocación corona zirconio', 'programada', '#8B5CF6'),
            (5, 3, 3, ? || ' 09:00:00', ? || ' 09:45:00', 'Limpieza bucal y fluorización', 'realizada', '#F59E0B');
        """, (today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str, today_str))

        # Sample clinical history notes
        cursor.execute("""
            INSERT INTO historial_clinico (paciente_id, doctor_id, tipo_evento, descripcion)
            VALUES 
            (1, 1, 'actuacion_clinica', 'Paciente acude para revisión. Se observa necesidad de reposición protésica en arcada superior. Se realiza presupuesto 320.'),
            (1, 1, 'comunicacion_whatsapp', 'Recordatorio de cita enviado al móvil 625342048 para el día de hoy.');
        """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
