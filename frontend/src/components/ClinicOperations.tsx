import {useEffect, useState} from 'react';
import {Download, Plus} from 'lucide-react';

export type Room = {id: number; name: string; color: string; active: boolean};
type RoomForm = Omit<Room, 'id'>;
type CashPayment = {id: number; patient_id: number; patient: string; amount_cents: number; method: string; created_at: string};
export const paymentMethods = ['Tarjeta', 'Efectivo', 'Transferencia', 'Bizum', 'Financiación'];
const euros = new Intl.NumberFormat('es-ES', {style: 'currency', currency: 'EUR'});
const money = (cents: number) => euros.format(cents / 100);
const clock = new Intl.DateTimeFormat('es-ES', {timeZone: 'Europe/Madrid', hour: '2-digit', minute: '2-digit'});

export function RoomSettings({rooms, save, busy}: {
  rooms: Room[];
  save: (room: RoomForm, id?: number) => Promise<boolean>;
  busy: boolean;
}) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const current = rooms.find(room => room.id === editing);
  return <section className="panel">
    <div className="panel-heading">
      <h2>Gabinetes</h2>
      <button className="secondary" onClick={() => setEditing('new')}><Plus size={16}/> Nuevo gabinete</button>
    </div>
    <div className="table-scroll"><table>
      <thead><tr><th>Gabinete</th><th>Estado</th><th/></tr></thead>
      <tbody>{rooms.map(room => <tr key={room.id}>
        <td><span className="dot room-dot" style={{background: room.color}}/> {room.name}</td>
        <td>{room.active ? 'Activo' : 'Inactivo'}</td>
        <td><button className="text-button" onClick={() => setEditing(room.id)}>Editar {room.name}</button></td>
      </tr>)}</tbody>
    </table></div>
    {editing !== null && <form className="room-editor" key={editing} onSubmit={async event => {
      event.preventDefault();
      const fields = new FormData(event.currentTarget);
      const saved = await save({name: String(fields.get('name')), color: String(fields.get('color')), active: fields.has('active')}, current?.id);
      if (saved) setEditing(null);
    }}>
      <label>Nombre<input name="name" required minLength={2} maxLength={30} defaultValue={current?.name}/></label>
      <label>Color<input type="color" name="color" defaultValue={current?.color ?? '#39775e'}/></label>
      <label className="calendar-check"><input type="checkbox" name="active" defaultChecked={current?.active ?? true}/> Activo</label>
      <div className="actions">
        <button type="button" className="secondary" onClick={() => setEditing(null)}>Cancelar</button>
        <button disabled={busy}>Guardar gabinete</button>
      </div>
    </form>}
  </section>;
}

export function DailyCash({initialDay, request, openPatient}: {
  initialDay: string;
  request: (path: string) => Promise<CashPayment[]>;
  openPatient: (id: number) => void;
}) {
  const [day, setDay] = useState(initialDay);
  const [method, setMethod] = useState('');
  const [rows, setRows] = useState<CashPayment[]>([]);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    setPending(true);
    setError('');
    request('/cash?day=' + day).then(payments => {
      if (current) setRows(payments);
    }).catch(reason => {
      if (current) setError(reason.message);
    }).finally(() => {
      if (current) setPending(false);
    });
    return () => { current = false; };
  }, [day, request]);

  const visible = method ? rows.filter(payment => payment.method === method) : rows;
  const total = visible.reduce((sum, payment) => sum + payment.amount_cents, 0);
  return <section className="panel">
    <div className="panel-heading"><h2>Caja diaria</h2></div>
    <div className="cash-controls">
      <label>Fecha de caja<input type="date" value={day} onChange={event => event.target.value && setDay(event.target.value)}/></label>
      <label>Forma de pago<select value={method} onChange={event => setMethod(event.target.value)}>
        <option value="">Todas</option>
        {paymentMethods.map(option => <option key={option}>{option}</option>)}
      </select></label>
      {!pending && !error && <strong role="status">Total {money(total)}</strong>}
    </div>
    {pending ? <p className="cash-empty">Cargando cobros…</p> : error ? <div className="error" role="alert">{error}</div> : visible.length ?
      <div className="table-scroll"><table>
        <thead><tr><th>Hora</th><th>Paciente</th><th>Forma de pago</th><th>Importe</th></tr></thead>
        <tbody>{visible.map(payment => <tr key={payment.id}>
          <td>{clock.format(new Date(payment.created_at))}</td>
          <td><button className="text-button" onClick={() => openPatient(payment.patient_id)}>{payment.patient}</button></td>
          <td>{payment.method}</td><td>{money(payment.amount_cents)}</td>
        </tr>)}</tbody>
      </table></div> : <p className="cash-empty">Sin cobros para esta selección.</p>}
  </section>;
}

type BackupState = {
  enabled: boolean;
  at?: string;
  latest?: string | null;
  network_enabled?: boolean;
  network_synced?: boolean;
  error: string;
};

export function BackupPanel({download, request}: {
  download: () => Promise<void>;
  request: (path: string) => Promise<BackupState>;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<BackupState>();
  const [statusError, setStatusError] = useState('');

  useEffect(() => {
    let current = true;
    async function refresh() {
      try {
        const next = await request('/backups/status');
        if (current) {
          setStatus(next);
          setStatusError('');
        }
      } catch (reason) {
        if (current) setStatusError((reason as Error).message);
      }
    }
    void refresh();
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [request]);

  return <section className="panel">
    <div className="panel-heading">
      <div><h2>Copias de seguridad</h2><p>Base SQLite y documentos adjuntos.</p></div>
      <button disabled={pending} onClick={async () => {
        setPending(true);
        setError('');
        try { await download(); }
        catch (reason) { setError((reason as Error).message); }
        finally { setPending(false); }
      }}><Download size={16}/> {pending ? 'Preparando…' : 'Descargar copia'}</button>
    </div>
    <div className="backup-status">
      {status && <>
        <p>{status.enabled ? `Copia automática diaria · ${status.at} · Europe/Madrid` : 'Copia automática desactivada'}</p>
        {status.enabled && <p>{status.latest ? 'Última copia · ' + status.latest : 'Todavía no hay copias programadas.'}</p>}
        {status.network_enabled && <p>{status.network_synced ? 'Última copia replicada en red' : 'Copia en red pendiente'}</p>}
      </>}
      {(statusError || status?.error) && <p role="alert" className="error">{statusError || status?.error}</p>}
      {error && <p role="alert" className="error">{error}</p>}
    </div>
  </section>;
}
