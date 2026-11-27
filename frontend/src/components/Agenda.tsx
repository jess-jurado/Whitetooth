import {useEffect,useMemo,useRef,useState,type DragEvent} from 'react';
import {CalendarDays,ChevronLeft,ChevronRight,Minus,Plus,X,ArrowRight,MessageCircle} from 'lucide-react';
import type {Room} from './ClinicOperations';
import RescheduleForm from './RescheduleForm';
import AppointmentReminder from './AppointmentReminder';
import {canMoveAppointment, useAppointmentDrag, type DropTarget, type ScheduleSource} from './useAppointmentDrag';
import './agenda.css';
type Appointment={id:number;patient_id:number;patient:string;professional:string;starts_at:string;ends_at:string;room:string;reason:string;status:string};
type View='Día'|'Semana'|'Mes'|'Selección';
const iso=(d:Date)=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const date=(s:string)=>new Date(s+'T12:00:00');
const add=(s:string,n:number)=>{const d=date(s);d.setDate(d.getDate()+n);return iso(d)};
const week=(s:string)=>add(s,-((date(s).getDay()+6)%7));
const days=(s:string,n:number)=>Array.from({length:n},(_,i)=>add(s,i));
const label=(s:string,options:Intl.DateTimeFormatOptions)=>date(s).toLocaleDateString('es-ES',options);
const monthStart=(s:string)=>s.slice(0,7)+'-01';
const shiftMonth=(s:string,n:number)=>{const d=date(monthStart(s));d.setMonth(d.getMonth()+n);return iso(d)};
const intersects=(a:Appointment,d:string)=>a.starts_at<add(d,1)+'T00:00:00'&&a.ends_at>d+'T00:00:00';
const minute=(s:string)=>Number(s.slice(11,13))*60+Number(s.slice(14,16));
const time=(n:number)=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
// Pack simultaneous appointments in separate lanes, retaining their actual duration.
function layout(rows:Appointment[],day:string){
 const sorted=rows.map(a=>({a,start:a.starts_at.slice(0,10)<day?0:minute(a.starts_at),end:a.ends_at.slice(0,10)>day?1440:minute(a.ends_at),lane:0,lanes:1})).sort((a,b)=>a.start-b.start||a.end-b.end);
 let group:typeof sorted=[],ends:number[]=[],until=-1;
 function finish(){group.forEach(a=>a.lanes=ends.length);group=[];ends=[]}
 for(const item of sorted){if(item.start>=until){finish();until=-1}let lane=ends.findIndex(end=>end<=item.start);if(lane<0)lane=ends.length;ends[lane]=item.end;item.lane=lane;group.push(item);until=Math.max(until,item.end)}finish();return sorted;
}
export default function Agenda({today,initialDay,revision,rooms,request,onCreate,onPatient,onChange,busy}:{today:string;initialDay:string;revision:unknown;rooms:Room[];request:(path:string,method?:string,data?:unknown)=>Promise<any>;onCreate:(start:string,room?:string)=>void;onPatient:(id:number)=>void;onChange:(id:number,status:string)=>Promise<boolean>;busy:boolean}){
 const [anchor,setAnchor]=useState(initialDay),[view,setView]=useState<View>('Semana'),[selected,setSelected]=useState([initialDay]),[month,setMonth]=useState(monthStart(initialDay)),[zoom,setZoom]=useState(64),[rows,setRows]=useState<Appointment[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState(''),[active,setActive]=useState<number|null>(null),[room,setRoom]=useState('Todos'),[cancelled,setCancelled]=useState(false),[rangeStart,setRangeStart]=useState(initialDay),[rangeEnd,setRangeEnd]=useState(initialDay);
 const [moving,setMoving]=useState(false);
 const moveInProgress=useRef(false);
 const [moveError,setMoveError]=useState('');
 const [moveNotice,setMoveNotice]=useState('');
 const [editingSchedule,setEditingSchedule]=useState(false);
 const [showReminder,setShowReminder]=useState(false);
 const [scheduleRevision,setScheduleRevision]=useState(0);
 const lastSelected=useRef(initialDay),scroll=useRef<HTMLDivElement>(null);
 const visible=useMemo(()=>view==='Mes'?days(week(monthStart(anchor)),42):view==='Semana'?days(week(anchor),7):view==='Día'?[anchor]:[...selected].sort(),[view,anchor,selected]);
 const start=visible[0],end=visible[visible.length-1];
 useEffect(()=>{let live=true;setLoading(true);setError('');setRows([]);request(`/appointments?start=${start}&end=${end}`).then(result=>{if(live)setRows(result)}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[start,end,revision,request]);
 const [bookedDays, setBookedDays] = useState<Set<string>>(new Set());
 const nextMonth = shiftMonth(month, 1);
 const nextMonthEnd = add(shiftMonth(month, 2), -1);
 useEffect(() => {
   let live = true;
   setBookedDays(new Set());
   request(`/appointments?start=${month}&end=${nextMonthEnd}`).then((appointments: Appointment[]) => {
     const marked = new Set<string>();
     for (const appointment of appointments) {
       if (appointment.status === 'Cancelada') continue;
       marked.add(appointment.starts_at.slice(0, 10));
       if (appointment.ends_at.slice(11) !== '00:00:00') marked.add(appointment.ends_at.slice(0, 10));
     }
     if (live) setBookedDays(marked);
   }).catch(() => { if (live) setBookedDays(new Set()); });
   return () => { live = false; };
 }, [month, nextMonthEnd, revision, scheduleRevision, request]);

 const filtered=rows.filter(a=>(room==='Todos'||a.room===room)&&(cancelled||a.status!=='Cancelada'));
 const dayRooms = rooms.filter(item => item.active || filtered.some(appointment => appointment.room === item.name && intersects(appointment, anchor)));
 const columns = view === 'Día' && room === 'Todos' && dayRooms.length
   ? dayRooms.map(item => ({day: anchor, room: item}))
   : visible.map(day => ({day, room: rooms.find(item => item.name === room)}));
 const slotMinutes = [0, 15, 30, 45];
 const relevant=filtered.filter(a=>visible.some(d=>intersects(a,d)));
 const early=Math.min(8,...relevant.map(a=>visible.some(d=>intersects(a,d)&&a.starts_at.slice(0,10)<d)?0:Math.floor(minute(a.starts_at)/60))),late=Math.max(20,...relevant.map(a=>a.ends_at.slice(0,10)!==a.starts_at.slice(0,10)?24:Math.ceil(minute(a.ends_at)/60)));
 const hours=Array.from({length:late-early},(_,i)=>early+i);
 const chosen=rows.find(a=>a.id===active);
 function focusDay(d:string){setAnchor(d);setSelected([d]);setMonth(monthStart(d));setRangeStart(d);setRangeEnd(d);lastSelected.current=d}
 function choose(d:string,range=false){let next=range?days(lastSelected.current<d?lastSelected.current:d,Math.round(Math.abs(date(d).getTime()-date(lastSelected.current).getTime())/86400000)+1):selected.includes(d)?selected.filter(x=>x!==d):[...selected,d];if(!next.length)next=[d];next.sort();if(next.length>31||Math.round((date(next[next.length-1]).getTime()-date(next[0]).getTime())/86400000)>61){setError('Selecciona hasta 31 días dentro de un intervalo de 62 días.');return}setError('');setSelected(next);setAnchor(d);setView('Selección');setRangeStart(next[0]);setRangeEnd(next[next.length-1]);if(!range)lastSelected.current=d}
 function changeView(v:View){setView(v);setActive(null)}
 function move(direction:number){if(view==='Mes'){const d=shiftMonth(anchor,direction);focusDay(d)}else if(view==='Selección'){const span=Math.round((date(end).getTime()-date(start).getTime())/86400000)+1;const next=selected.map(d=>add(d,direction*span));setSelected(next);setAnchor(next[0]);setMonth(monthStart(next[0]));setRangeStart(next[0]);setRangeEnd(next[next.length-1]);lastSelected.current=next[0]}else focusDay(add(anchor,direction*(view==='Semana'?7:1)))}
 function zoomStep(direction:number){if(direction>0){if(view==='Mes')changeView('Semana');else if(zoom<112)setZoom(zoom+16);else if(view!=='Día'){changeView('Día');setZoom(80)}}else{if(view==='Día'&&zoom<=48){changeView('Semana');setZoom(64)}else if(zoom>32)setZoom(zoom-16);else changeView('Mes')}}
 function openAppointment(appointment: Appointment) {
   setMoveError('');
   setEditingSchedule(false);
   setShowReminder(false);
   setActive(appointment.id);
 }

 async function reschedule(appointment: ScheduleSource, startsAt: string, destinationRoom: string) {
   if (moveInProgress.current || busy) return false;
   const normalizedStart = startsAt.length === 16 ? startsAt + ':00' : startsAt;
   if (normalizedStart === appointment.starts_at && destinationRoom === appointment.room) return true;
   moveInProgress.current = true;
   setMoving(true);
   setMoveError('');
   setMoveNotice('');
   try {
     const updated: Pick<Appointment,'starts_at'|'ends_at'|'room'> = await request(
       `/appointments/${appointment.id}/schedule`, 'PATCH',
       {starts_at: normalizedStart, room: destinationRoom, expected_start: appointment.starts_at, expected_room: appointment.room}
     );
     setRows(current => current.map(item => item.id === appointment.id ? {...item, ...updated} : item));
     setScheduleRevision(value => value + 1);
     const destinationDay = updated.starts_at.slice(0,10);
     if (!visible.includes(destinationDay)) {
       focusDay(destinationDay);
       changeView('Día');
     }
     if (room !== 'Todos' && room !== updated.room) setRoom('Todos');
     setMoveNotice(`Cita movida al ${label(destinationDay,{day:'numeric',month:'long',year:'numeric'})} a las ${updated.starts_at.slice(11,16)} · ${updated.room}`);
     return true;
   } catch (reason) {
     setMoveError((reason as Error).message);
     return false;
   } finally {
     moveInProgress.current = false;
     setMoving(false);
   }
 }

 const drag = useAppointmentDrag(reschedule);

 function timeDestination(event: DragEvent<HTMLElement>, day: string, columnRoom?: Room): DropTarget | undefined {
   if (columnRoom?.active === false) return;
   const offset = event.clientY - event.currentTarget.getBoundingClientRect().top;
   const quarter = Math.max(0, Math.min((late - early) * 4 - 1, Math.floor(offset / (zoom / 4))));
   return {day, room: columnRoom?.name, time: time(early * 60 + quarter * 15)};
 }

 const pickedDays = view === 'Selección' || view === 'Mes' ? selected : visible;
 return <div className="agenda-layout"><aside className="calendar-sidebar">
 <div className="mini-heading">
   <strong>Seleccionar días</strong>
   <div>
     <button className="icon" aria-label="Mes anterior del selector" onClick={() => setMonth(shiftMonth(month, -1))} {...drag.monthArrowProps(() => setMonth(value => shiftMonth(value, -1)))}><ChevronLeft size={16}/></button>
     <button className="icon" aria-label="Mes siguiente del selector" onClick={() => setMonth(shiftMonth(month, 1))} {...drag.monthArrowProps(() => setMonth(value => shiftMonth(value, 1)))}><ChevronRight size={16}/></button>
   </div>
 </div>
 {[month, nextMonth].map(shownMonth => <MiniMonth key={shownMonth} month={shownMonth} today={today} pickedDays={pickedDays} bookedDays={bookedDays} choose={choose} drag={drag}/>)}
 <p className="calendar-help">Pulsa días para añadirlos o quitarlos. <strong>Mayús + clic</strong> selecciona un intervalo.</p><form className="calendar-range" onSubmit={e=>{e.preventDefault();const count=Math.round((date(rangeEnd).getTime()-date(rangeStart).getTime())/86400000)+1;if(count<1||count>31){setError('El intervalo debe contener entre 1 y 31 días.');return}setSelected(days(rangeStart,count));setAnchor(rangeStart);setMonth(monthStart(rangeStart));lastSelected.current=rangeStart;setView('Selección');setError('')}}><label>Desde<input type="date" value={rangeStart} required onChange={e=>setRangeStart(e.target.value)}/></label><label>Hasta<input type="date" value={rangeEnd} required onChange={e=>setRangeEnd(e.target.value)}/></label><button className="secondary" type="submit">Mostrar intervalo</button></form><div className="calendar-filters"><label>Gabinete<select value={room} onChange={e=>setRoom(e.target.value)}><option>Todos</option>{rooms.map(item=><option key={item.id} value={item.name}>{item.name}{item.active?'':' (inactivo)'}</option>)}</select></label><label className="calendar-check"><input type="checkbox" checked={cancelled} onChange={e=>setCancelled(e.target.checked)}/> Mostrar canceladas</label></div><div className="calendar-key"><span><i className="dot done"/> Confirmada / completada</span><span><i className="dot planned"/> En espera</span></div></aside>
 <section className="calendar-main"><div className="calendar-toolbar"><div className="calendar-navigation"><button className="secondary" onClick={()=>{focusDay(today);if(view==='Selección')setView('Día')}}>Hoy</button><button className="icon" aria-label="Periodo anterior" onClick={()=>move(-1)}><ChevronLeft size={19}/></button><button className="icon" aria-label="Periodo siguiente" onClick={()=>move(1)}><ChevronRight size={19}/></button><h2>{view==='Mes'?label(anchor,{month:'long',year:'numeric'}):start===end?label(start,{day:'numeric',month:'long',year:'numeric'}):`${label(start,{day:'numeric',month:'short'})} – ${label(end,{day:'numeric',month:'short',year:'numeric'})}`}</h2></div><div className="calendar-views" aria-label="Vista del calendario">{(['Día','Semana','Mes','Selección'] as View[]).map(v=><button key={v} aria-pressed={view===v} className={view===v?'chosen':'secondary'} onClick={()=>changeView(v)}>{v}</button>)}</div></div><div className="calendar-subtoolbar"><span role="status">{loading?'Cargando citas…':`${relevant.length} citas · ${visible.length} días${view==='Selección'?' seleccionados':''}`}</span><div className="calendar-zoom"><button className="icon" aria-label="Alejar calendario" disabled={view==='Mes'} onClick={()=>zoomStep(-1)}><Minus size={17}/></button><label>Zoom horario<input aria-label="Zoom horario" type="range" min="32" max="112" step="16" disabled={view==='Mes'} value={zoom} onChange={e=>{const old=zoom,next=Number(e.target.value);if(scroll.current)scroll.current.scrollTop*=next/old;setZoom(next)}}/></label><button className="icon" aria-label="Acercar calendario" disabled={view==='Día'&&zoom===112} onClick={()=>zoomStep(1)}><Plus size={17}/></button><small>{view==='Mes'?'Vista general':Math.round(zoom/64*100)+'%'}</small></div></div>
 {error&&<div role="alert" className="error">{error}</div>}
 {moveError && !editingSchedule && <div role="alert" className="error">{moveError}</div>}
 <div className="calendar-move-status" role="status">{moving ? 'Moviendo cita…' : moveNotice}</div>
 {view === 'Mes' ? <div className="month-scroll">
   <div className="month-grid">
     <div className="month-weekdays">{['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'].map(day=><span key={day}>{day}</span>)}</div>
     {visible.map(day => {
       const dayAppointments = filtered.filter(appointment => intersects(appointment, day));
       const openDay = () => { focusDay(day); changeView('Día'); };
       const targeted = drag.target?.day === day;
       return <div key={day} className={`month-cell ${day.slice(0,7)!==anchor.slice(0,7)?'muted-month':''} ${targeted?'schedule-drop-day':''}`}
         {...drag.targetProps(() => ({day}))}>
         <button className={'month-day ' + (day===today?'today-number':'')} aria-label={'Abrir día ' + day} onClick={openDay}>{date(day).getDate()}</button>
         {dayAppointments.slice(0,3).map(appointment =>
           <button key={appointment.id}
             className={`month-event status-${appointment.status.replaceAll(' ','-')} ${drag.draggedId===appointment.id?'schedule-dragging':''}`}
             {...drag.sourceProps(appointment, moving || busy)}
             onClick={() => openAppointment(appointment)}
             title={`${appointment.starts_at.slice(11,16)} · ${appointment.patient} · ${appointment.reason}`}>
             <b>{appointment.starts_at.slice(11,16)}</b> {appointment.patient}
           </button>)}
         {dayAppointments.length > 3 && <button className="month-more" onClick={openDay}>+{dayAppointments.length - 3} más</button>}
       </div>;
     })}
   </div>
 </div>: <div className="time-scroll" ref={scroll}>
   <div className="time-grid" style={{minWidth: columns.length * (view === 'Día' ? 210 : 130) + 58}}>
     <div className="day-headings" style={{gridTemplateColumns: `58px repeat(${columns.length},minmax(0,1fr))`}}>
       <span className="timezone">Madrid</span>
       {columns.map(({day, room: columnRoom}) => {
         const count = filtered.filter(appointment => intersects(appointment, day) && (!columnRoom || appointment.room === columnRoom.name)).length;
         return <button key={day + (columnRoom?.id ?? '')}
           className={`${day === today ? 'today-heading' : ''} ${drag.target?.day === day && drag.target.room === columnRoom?.name && !drag.target.time ? 'schedule-drop-day' : ''}`}
           {...drag.targetProps(() => columnRoom?.active === false ? undefined : {day, room: columnRoom?.name})}
           onClick={() => {focusDay(day);changeView('Día')}} aria-label={`Ampliar día ${day}${columnRoom ? ', ' + columnRoom.name : ''}`}>
           <span>{label(day,{weekday:'short'})}</span><strong>{date(day).getDate()}</strong>
           {view === 'Día' && columnRoom && <small><i className="dot room-dot" style={{background: columnRoom.color}}/>{columnRoom.name}</small>}
           <small>{count} citas</small>
         </button>;
       })}
     </div>
     <div className="time-body" style={{gridTemplateColumns: `58px repeat(${columns.length},minmax(0,1fr))`, height: hours.length * zoom}}>
       <div className="hour-labels">{hours.map(hour => <span key={hour} style={{top:(hour-early)*zoom}}>{time(hour*60)}</span>)}</div>
       {columns.map(({day, room: columnRoom}) => {
         const columnRows = filtered.filter(appointment => intersects(appointment, day) && (!columnRoom || appointment.room === columnRoom.name));
         const target = drag.target;
         const highlightedTime = target?.day === day && target.room === columnRoom?.name ? target.time : undefined;
         return <div className="day-column" key={day + (columnRoom?.id ?? '')}
           {...drag.targetProps(event => timeDestination(event, day, columnRoom))}>
           {highlightedTime && <div className="schedule-drop-time" aria-hidden="true"
             style={{top:(minute(day + 'T' + highlightedTime)/60-early)*zoom,height:zoom/4}}>
             <span>{highlightedTime}</span>
           </div>}
           {hours.flatMap(hour => slotMinutes.map(minutes => {
             const slot = time(hour * 60 + minutes);
             return <button key={slot} className={'time-slot ' + (minutes ? 'half-hour' : '')}
               style={{top:(hour-early+minutes/60)*zoom, height:zoom/4}}
               aria-label={`Crear cita el ${day} a las ${slot}${columnRoom ? ', ' + columnRoom.name : ''}`}
               title={`Nueva cita · ${day} ${slot}`}
               disabled={columnRoom?.active === false} tabIndex={-1}
               onClick={() => onCreate(day + 'T' + slot, columnRoom?.name)}/>;
           }))}
           {layout(columnRows, day).map(({a, start: from, end: to, lane, lanes}) => {
             const color = rooms.find(item => item.name === a.room)?.color;
             const height = (to - from) / 60 * zoom;
             return <button key={a.id} className={`calendar-event status-${a.status.replaceAll(' ', '-')} ${drag.draggedId===a.id?'schedule-dragging':''}`}
               {...drag.sourceProps(a, moving || busy)}
               style={{top:(from/60-early)*zoom+1,height:Math.max(height-2,12),left:`calc(${lane/lanes*100}% + 3px)`,width:`calc(${100/lanes}% - 6px)`,borderLeftColor:color}}
               onClick={() => openAppointment(a)}
               aria-label={`${a.patient}, ${a.starts_at.slice(11,16)} a ${a.ends_at.slice(11,16)}, ${a.room}, ${a.status}`}
               title={`${a.patient} · ${a.starts_at.slice(11,16)} – ${a.ends_at.slice(11,16)} · ${a.room} · ${a.reason}`}>
               <strong>{a.starts_at.slice(11,16)} · {a.patient}</strong>
               {height >= 42 && <span>{a.reason}</span>}
               {height >= 60 && <small>{a.room} · {a.status}</small>}
             </button>;
           })}
         </div>;
       })}
     </div>
   </div>
 </div>}

 <div className="calendar-bottom"><CalendarDays size={15}/><span>{view==='Mes'
   ? 'Arrastra una cita a otro día para conservar su hora.'
   : 'Arrastra una cita a otra franja o a un día del calendario lateral.'}</span><span>Europe/Madrid</span></div></section>
 {chosen && <div className="modal-backdrop" onClick={event => {if(event.target===event.currentTarget && !moving)setActive(null)}}>
   <section className="modal appointment-detail" role="dialog" aria-modal="true" aria-labelledby="appointment-detail-title">
     <div className="modal-heading">
       <h2 id="appointment-detail-title">{chosen.patient}</h2>
       <button className="icon" aria-label="Cerrar detalle de cita" disabled={moving} onClick={()=>setActive(null)}><X size={20}/></button>
     </div>
     <div className="appointment-detail-body">
       {showReminder ? <AppointmentReminder id={chosen.id} request={request} close={()=>setShowReminder(false)}/> : editingSchedule ? <RescheduleForm
         appointment={chosen} rooms={rooms} pending={moving} error={moveError} save={reschedule}
         close={() => {setEditingSchedule(false);setMoveError('')}}/> : <>
         <span className={'badge state-'+chosen.status.replaceAll(' ','-')}>{chosen.status}</span>
         <h3>{chosen.reason}</h3>
         <p>{label(chosen.starts_at.slice(0,10),{weekday:'long',day:'numeric',month:'long'})}<br/>{chosen.starts_at.slice(11,16)} – {chosen.ends_at.slice(11,16)}</p>
         <dl><dt>Gabinete</dt><dd>{chosen.room}</dd><dt>Profesional</dt><dd>{chosen.professional}</dd></dl>
         {canMoveAppointment(chosen) && <>
           <label>Actualizar estado<select value="" disabled={busy} onChange={async event=>{if(await onChange(chosen.id,event.target.value))setActive(null)}}>
             <option value="">Selecciona el nuevo estado…</option>
             {(chosen.status==='Confirmada'?['En espera','Completada','Cancelada']:['Completada','Cancelada']).map(status=><option key={status}>{status}</option>)}
           </select></label>
           <button className="secondary" onClick={() => {setMoveError('');setEditingSchedule(true)}}>Mover cita</button>
           <button className="secondary" onClick={() => setShowReminder(true)}><MessageCircle size={16}/> Preparar WhatsApp</button>
         </>}
         <button onClick={()=>onPatient(chosen.patient_id)}>Abrir ficha del paciente <ArrowRight size={16}/></button>
       </>}
     </div>
   </section>
 </div>}
 </div>
}

function MiniMonth({month, today, pickedDays, bookedDays, choose, drag}: {
  month: string;
  today: string;
  pickedDays: string[];
  bookedDays: Set<string>;
  choose: (day: string, range: boolean) => void;
  drag: ReturnType<typeof useAppointmentDrag>;
}) {
  const offset = (date(month).getDay() + 6) % 7;
  const monthLength = date(add(shiftMonth(month, 1), -1)).getDate();
  return <div className="mini-calendar">
    <h3>{label(month, {month: 'long', year: 'numeric'})}</h3>
    <div className="mini-weekdays">{['L', 'M', 'X', 'J', 'V', 'S', 'D'].map(day => <span key={day}>{day}</span>)}</div>
    <div className="mini-days">
      {Array.from({length: offset}, (_, blank) => <span aria-hidden="true" key={blank}/>)}
      {days(month, monthLength).map(day => {
        const picked = pickedDays.includes(day);
        const booked = bookedDays.has(day);
        return <button key={day} aria-label={label(day, {day:'numeric',month:'long',year:'numeric'}) + (booked ? ' · Con citas' : '')}
          aria-pressed={picked} className={`${picked ? 'picked ' : ''}${day === today ? 'is-today ' : ''}${booked ? 'has-appointments' : ''} ${drag.target?.day === day && !drag.target.time ? 'schedule-drop-day' : ''}`}
          {...drag.targetProps(() => ({day}))} onClick={event => choose(day, event.shiftKey)}>{date(day).getDate()}</button>;
      })}
    </div>
  </div>;
}
