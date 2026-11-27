import re
from urllib.parse import urlencode


def whatsapp_number(phone: str):
    value = re.sub(r'[\s().-]', '', phone)
    if re.fullmatch(r'[6789][0-9]{8}', value):
        return '34' + value
    if value.startswith('+'):
        value = value[1:]
    elif value.startswith('00'):
        value = value[2:]
    elif not re.fullmatch(r'34[6789][0-9]{8}', value):
        return None
    if re.fullmatch(r'[1-9][0-9]{7,14}', value):
        return value
    return None


def prepare_reminder(appointment, patient, clinic: str, enabled: bool):
    number = whatsapp_number(patient.phone or '')
    day = appointment.starts_at[:10].split('-')
    day_label = '/'.join(reversed(day))
    appointment_time = appointment.starts_at[11:16]
    message = (
        f'Hola. Te recordamos tu cita con {clinic} el {day_label} a las {appointment_time}. '
        '¿Puedes confirmar tu asistencia? Gracias.'
    )
    link = f'https://wa.me/{number}?' + urlencode({'text': message}) if enabled and number else None
    return {'phone': '+' + number if number else None, 'message': message, 'url': link, 'enabled': enabled}
