import {useState} from 'react';
import type {Room} from './ClinicOperations';
import type {ScheduleSource} from './useAppointmentDrag';

export default function RescheduleForm({appointment, rooms, pending, error, save, close}: {
  appointment: ScheduleSource;
  rooms: Room[];
  pending: boolean;
  error: string;
  save: (appointment: ScheduleSource, startsAt: string, room: string) => Promise<boolean>;
  close: () => void;
}) {
  const [day, setDay] = useState(appointment.starts_at.slice(0, 10));
  const [hour, setHour] = useState(appointment.starts_at.slice(11, 16));
  const [room, setRoom] = useState(rooms.some(item => item.active && item.name === appointment.room)
    ? appointment.room : '');
  return <form className="appointment-reschedule" onSubmit={async event => {
    event.preventDefault();
    const time = hour === appointment.starts_at.slice(11, 16) ? appointment.starts_at.slice(11) : hour;
    if (await save(appointment, day + 'T' + time, room)) close();
  }}>
    <h3>Mover cita</h3>
    <div className="form-grid">
      <label>Nueva fecha<input autoFocus type="date" value={day} onChange={event => setDay(event.target.value)} required/></label>
      <label>Nueva hora<input type="time" value={hour} onChange={event => setHour(event.target.value)} required/></label>
    </div>
    <label>Gabinete de destino<select value={room} onChange={event => setRoom(event.target.value)} required>
      <option value="" disabled>Elige un gabinete activo</option>
      {rooms.filter(item => item.active).map(item => <option key={item.id}>{item.name}</option>)}
    </select></label>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="actions">
      <button type="button" className="secondary" onClick={close} disabled={pending}>Volver</button>
      <button type="submit" disabled={pending}>{pending ? 'Moviendo…' : 'Guardar cambio'}</button>
    </div>
  </form>;
}
