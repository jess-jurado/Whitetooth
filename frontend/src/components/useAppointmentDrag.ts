import {useEffect, useRef, useState, type DragEvent} from 'react';

export type ScheduleSource = {id: number; starts_at: string; room: string; status: string};
export type DropTarget = {day: string; time?: string; room?: string};

export const canMoveAppointment = (appointment: ScheduleSource) =>
  appointment.status === 'Confirmada' || appointment.status === 'En espera';

export function useAppointmentDrag(
  move: (appointment: ScheduleSource, startsAt: string, room: string) => Promise<boolean>,
) {
  const source = useRef<ScheduleSource | null>(null);
  const monthTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const [draggedId, setDraggedId] = useState<number | null>(null);
  const [target, setTarget] = useState<DropTarget>();

  function stopMonthNavigation() {
    clearInterval(monthTimer.current);
    monthTimer.current = undefined;
  }

  useEffect(() => () => clearInterval(monthTimer.current), []);

  function finish() {
    stopMonthNavigation();
    source.current = null;
    setDraggedId(null);
    setTarget(undefined);
  }

  function sourceProps(appointment: ScheduleSource, disabled: boolean) {
    return {
      draggable: !disabled && canMoveAppointment(appointment),
      onDragStart(event: DragEvent<HTMLButtonElement>) {
        if (disabled || !canMoveAppointment(appointment)) {
          event.preventDefault();
          return;
        }
        source.current = appointment;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('application/x-dentalis-appointment', String(appointment.id));
        setDraggedId(appointment.id);
      },
      onDragEnd: finish,
    };
  }

  function targetProps(resolve: (event: DragEvent<HTMLElement>) => DropTarget | undefined) {
    return {
      onDragOver(event: DragEvent<HTMLElement>) {
        if (!source.current) return;
        const next = resolve(event);
        if (!next) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        setTarget(current => current?.day === next.day && current.time === next.time && current.room === next.room
          ? current : next);
      },
      onDragLeave(event: DragEvent<HTMLElement>) {
        if (!source.current || (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget))) return;
        // Capture the destination while React's event still has a currentTarget.
        const leaving = resolve(event);
        if (!leaving) return;
        setTarget(current => current?.day === leaving.day && current.room === leaving.room
          && Boolean(current.time) === Boolean(leaving.time) ? undefined : current);
      },
      onDrop(event: DragEvent<HTMLElement>) {
        const appointment = source.current;
        if (!appointment) return;
        const destination = resolve(event);
        if (!destination) return;
        event.preventDefault();
        finish();
        const time = destination.time ?? appointment.starts_at.slice(11);
        void move(appointment, destination.day + 'T' + time, destination.room ?? appointment.room);
      },
    };
  }

  function monthArrowProps(shift: () => void) {
    return {
      onDragOver(event: DragEvent<HTMLButtonElement>) {
        if (!source.current) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'none';
        if (monthTimer.current === undefined) monthTimer.current = setInterval(shift, 800);
      },
      onDragLeave: stopMonthNavigation,
      onDrop(event: DragEvent<HTMLButtonElement>) {
        if (!source.current) return;
        event.preventDefault();
        finish();
      },
    };
  }

  return {draggedId, target, sourceProps, targetProps, monthArrowProps};
}
