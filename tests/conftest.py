import os
import tempfile
import pytest
os.environ['DENTALIS_STORAGE']=tempfile.mkdtemp(prefix='dentalis-test-')
os.environ['DENTALIS_ADMIN_PASSWORD']='Pruebas-Dentalis-2026'
os.environ['DENTALIS_DEMO']='1'
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import Base, engine
from backend.routes.api import login_attempts

@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    login_attempts.clear()
    with TestClient(app) as c:
        result=c.post('/api/auth/login',json={'username':'admin','password':'Pruebas-Dentalis-2026'})
        assert result.status_code==200
        c.headers['X-CSRF-Token']=result.json()['csrf']
        yield c
