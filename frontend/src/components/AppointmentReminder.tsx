import {useEffect, useState} from 'react';
import {ExternalLink} from 'lucide-react';

type Draft = {phone: string | null; message: string; url: string | null; enabled: boolean};

export default function AppointmentReminder({id, request, close}: {
  id: number;
  request: (path: string, method: string) => Promise<Draft>;
  close: () => void;
}) {
  const [draft, setDraft] = useState<Draft>();
  const [error, setError] = useState('');
  const [copyFeedback, setCopyFeedback] = useState('');

  useEffect(() => {
    let current = true;
    request(`/appointments/${id}/whatsapp-draft`, 'POST').then(result => {
      if (current) setDraft(result);
    }).catch(reason => {
      if (current) setError((reason as Error).message);
    });
    return () => { current = false; };
  }, [id, request]);

  return <div className="appointment-reminder">
    <h3>Recordatorio de cita</h3>
    {error ? <p className="error" role="alert">{error}</p> : draft ? <>
      <p>{draft.phone ? 'Teléfono · ' + draft.phone : 'Añade un teléfono válido en la ficha del paciente.'}</p>
      <label>Mensaje preparado<textarea value={draft.message} readOnly rows={4}/></label>
      <p>{draft.enabled ? 'Revisa el mensaje y envíalo desde WhatsApp.' : 'La apertura de WhatsApp está desactivada en esta instalación.'}</p>
    </> : <p role="status">Preparando el recordatorio…</p>}
    <div className="actions">
      <button type="button" className="secondary" onClick={close}>Volver</button>
      {draft && <button className="secondary" type="button" onClick={async () => {
        try {
          await navigator.clipboard.writeText(draft.message);
          setCopyFeedback('Mensaje copiado.');
        } catch {
          setCopyFeedback('Selecciona el texto para copiarlo.');
        }
      }}>Copiar mensaje</button>}
      {draft?.url && <a className="button" href={draft.url} target="_blank" rel="noopener noreferrer">
        Abrir WhatsApp <ExternalLink size={14}/>
      </a>}
    </div>
    {copyFeedback && <p role="status">{copyFeedback}</p>}
  </div>;
}
