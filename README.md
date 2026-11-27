# Dentalis · MVP local

Aplicación funcional de demostración para una clínica dental. Backend FastAPI + SQLAlchemy, React + TypeScript + Tailwind CSS y odontograma SVG. Solo datos ficticios. La versión anterior de `Nodule/dentalis` permanece intacta.

## Arrancar en macOS

Este checkout está en `/Users/jaimgregternerodorta/Documents/ChatGPT/Dentalis`; Git ya está inicializado en `main`. No es necesario crear otra copia en `~/Developer`.

```sh
cd /Users/jaimgregternerodorta/Documents/ChatGPT/Dentalis
./scripts/start.sh
```

Abre http://127.0.0.1:8000. En una instalación nueva el script pide la contraseña de `admin` (12 caracteres como mínimo) y carga cinco pacientes ficticios. En este entorno se ha creado una cuenta de demostración; la contraseña se entrega en el chat, no se guarda en el repositorio. Para detenerlo: Ctrl+C en la terminal del servidor.

Requisitos: Python 3.9 o posterior y Node 20.19+/22.12+. Verificado en Mac ARM64, Python 3.9.6 y Node 24.11.1. Se recomienda actualizar Python antes de preparar producción.

### Instalación manual y reproducible

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
npm --prefix frontend ci
npm --prefix frontend run build
# Primer arranque: definir una contraseña propia en DENTALIS_ADMIN_PASSWORD.
# DENTALIS_DEMO=1 carga los datos ficticios solamente si no existen usuarios.
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

En desarrollo, ejecutar también `npm --prefix frontend run dev`: Vite reenvía `/api` al backend en 8000. La versión compilada se sirve directamente desde FastAPI. API interactiva en `/docs`.

## Recorrido de demostración

1. Iniciar sesión y abrir Lucía Martín Demo en Pacientes.
2. Seleccionar varias piezas FDI y superficies en Odontograma. Registrar un diagnóstico independiente del plan de tratamiento.
3. Crear un presupuesto desde Presupuestos. Volver al odontograma, elegir piezas y añadir una línea de catálogo. El precio corresponde a toda la línea, no se multiplica por las piezas.
4. Pasar la línea por **Presupuestado → Aceptado → En curso → Realizado** desde Presupuestos. Comprobar los cambios en odontograma e historial. También se puede cancelar antes de realizar; los estados terminales no se reabren.
5. Descargar el presupuesto PDF. Las líneas canceladas se muestran pero no suman al total vigente.
6. Con todas las líneas realizadas o canceladas y al menos una realizada, emitir el documento interno de cobro. El presupuesto queda cerrado. En Cobros, registrar pagos parciales hasta liquidarlo.
7. Añadir una cita. Se impiden solapamientos de paciente, gabinete o profesional; se permiten citas adyacentes.
8. Subir un PDF, PNG o JPEG ficticio a Documentos y descargarlo con sesión clínica.
9. Crear usuarios de recepción y equipo clínico en Administración. Revisar auditoría de lecturas, exportaciones y cambios.

## Agenda visual

La agenda ofrece **Día, Semana, Mes y Selección**. En el calendario lateral se pueden marcar días sueltos; Mayús + clic marca un intervalo. Los campos Desde/Hasta permiten elegir hasta 31 días; la selección puede abarcar hasta 62 días naturales. Las columnas muestran únicamente los días seleccionados, con sus citas reales.

Los botones −/+ y el deslizador ajustan la altura de las horas (50–175 %). Al alejar desde el mínimo se pasa al mes; al acercar desde el mes se vuelve a la semana, y desde el máximo semanal se amplía al día. También se puede cambiar de vista directamente. Las cabeceras de día abren la vista diaria; Hoy y las flechas desplazan el periodo.

Al pulsar una franja libre se abre el alta de cita con fecha y hora precargadas. Al pulsar una cita se muestra su detalle, estado y acceso a la ficha. Los filtros permiten elegir gabinete e incluir canceladas. Las citas simultáneas ocupan columnas independientes y las que cruzan medianoche aparecen en ambos días. En pantallas estrechas, el calendario admite desplazamiento horizontal.

`GET /api/appointments?start=AAAA-MM-DD&end=AAAA-MM-DD` consulta un intervalo inclusivo de hasta 62 días; sigue disponible el parámetro `day` para un día. La interfaz descarta respuestas antiguas al cambiar rápidamente de periodo.

## Arquitectura

- `backend/database.py`: motor SQLAlchemy, sesión por petición, claves foráneas SQLite activas.
- `backend/models/entities.py`: usuarios, sesiones, pacientes, catálogo, presupuestos, líneas de tratamiento, entradas clínicas, citas, documentos internos de cobro, pagos, documentos y auditoría.
- `backend/schemas.py`: validación de entradas, importes enteros en céntimos, fechas, FDI permanente y temporal, superficies M/D/V/L/O/I.
- `backend/routes/api.py`: endpoints autenticados, permisos y transacciones.
- `backend/services/security.py`: PBKDF2-SHA256, sesiones opacas cuyo identificador se guarda hasheado, CSRF, control de roles.
- `backend/services/pdf.py`: presupuesto PDF con tablas paginadas.
- `backend/services/seed.py`: carga inicial explícita e idempotente.
- `frontend/src/main.tsx`: interfaz React, formularios, navegación, SVG interactivo y consumo de API.
- `frontend/src/style.css`: estilos y Tailwind; diseño adaptable.
- `storage/`: SQLite y documentos privados; excluidos de Git y fuera del directorio público.

**Una única fuente de tratamientos:** cada línea pertenece a un presupuesto y conserva sus piezas, superficies, precio, nombre del tratamiento en ese momento y estado. Odontograma y presupuesto leen las mismas líneas; el historial consulta los eventos de esas líneas. Los diagnósticos son entradas clínicas separadas y no se eliminan al completar un tratamiento. Sin registro no significa pieza sana. Si hay varias intervenciones sobre la misma superficie, se colorea la última línea registrada y se muestran marcadores de los estados presentes; el detalle debajo conserva todos los tratamientos. No sustituye una representación clínica validada.

**Consistencia:** versión de tratamiento para evitar actualizaciones obsoletas; transacciones serializadas por presupuesto/factura y bloqueo de agenda; referencia única de pago para reintentos idempotentes; no se permite sobrepago. La interfaz genera una referencia por envío y bloquea el botón mientras guarda.

**Fechas:** citas en hora local Europe/Madrid (sin zona en DB); eventos y auditoría UTC. El despliegue debe usar la zona de la clínica para sus métricas diarias. No incluye todavía gestión de clínicas en distintas zonas horarias.

### Roles

| Acción | Administrador | Clínico | Recepción |
|---|---|---|---|
| Pacientes, citas y cobros | Sí | Sí | Sí |
| Diagnósticos, historial, documentos y PDF clínico | Sí | Sí | No |
| Crear planes y cambiar tratamientos | Sí | Sí | No |
| Gestionar catálogo y crear usuarios | Sí | No | No |
| Consultar auditoría | Sí | No | No |

Sesión HTTP-only, SameSite Strict, caducidad de 8 horas, CSRF para escrituras, respuestas API no almacenables en caché, CSP, protección contra encuadre y límites de archivo. El límite de login es de 10 intentos/5 minutos por IP y proceso. Los archivos se descargan como adjuntos y usan nombres internos aleatorios. Las entradas clínicas y eventos no tienen endpoints de edición o borrado.

## Pruebas

```sh
.venv/bin/python -m pytest -q
npm --prefix frontend run build
```

La suite usa su propia base temporal y cubre flujo clínico y persistencia, estados y versiones, permisos y CSRF, validación FDI, conflictos de agenda, PDF/documentos, cierre económico, idempotencia y sobrepagos concurrentes. No toca la base demo.

## PostgreSQL y evolución

Configurar `DATABASE_URL=postgresql+psycopg://usuario:clave@host/dentalis` y opcionalmente `DENTALIS_STORAGE` antes de arrancar. Los modelos utilizan tipos portables de SQLAlchemy; se incluye el controlador psycopg. PostgreSQL **no se ha probado en este entorno**. No se copian automáticamente los datos de SQLite. Actualmente el esquema inicial se crea con `create_all`; incorporar migraciones versionadas antes de modificar una base existente o desplegar producción.

## Límites del MVP y siguientes entregas

- **Facturación:** documentos internos de demostración, sin emisión de facturas fiscales ni integración tributaria. Faltan series fiscales, impuestos y rectificaciones.
- **Seguridad de producción:** faltan recuperación/cambio de contraseña, MFA, administración de bajas, rate limiting compartido, cifrado de datos y copias, recuperación probada, auditoría protegida frente a administradores de la BD, antivirus y revisión independiente.
- **Clínica:** falta validación profesional del odontograma, correcciones con contrapartida, estados diagnósticos y evolución avanzada, consentimientos firmados y permisos por centro.
- **Agenda:** permite crear y cambiar estado; reprogramar requiere cancelar y crear una nueva cita.
- **Interfaz:** formularios funcionales; quedan pruebas exhaustivas de accesibilidad, foco de modales y escenarios de red inestable.
- Sin multiclínica, migración desde MNprogram ni despliegue externo. No se ha enviado nada a Jesús ni a GitHub.

No usar datos sanitarios reales ni exponer a internet esta demo. El salto a producto comercial requiere completar estos puntos, validar los flujos con la clínica y revisar requisitos legales aplicables. Para HTTPS futuro activar `DENTALIS_SECURE_COOKIE=1`; en localhost HTTP debe permanecer desactivado.
