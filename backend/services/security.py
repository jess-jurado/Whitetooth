import hashlib
import hmac
import secrets
import time
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.entities import User, LoginSession, Audit

def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return salt + ':' + digest

def verify_password(password, stored):
    salt, digest = stored.split(':')
    return hmac.compare_digest(digest, hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex())

def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

def current_user(request: Request, db: Session = Depends(get_db)):
    session = db.get(LoginSession, token_hash(request.cookies.get('dentalis_session', '')))
    if not session or session.expires < time.time():
        raise HTTPException(401, 'Inicia sesión para continuar')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, 'Cuenta desactivada')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf):
        raise HTTPException(403, 'Sesión de formulario no válida')
    request.state.session = session
    return user

def require(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, 'Tu rol no permite esta operación')

def audit(db, user, action, entity, entity_id, details=None):
    db.add(Audit(user_id=user.id, action=action, entity=entity, entity_id=entity_id, details=details or {}))
