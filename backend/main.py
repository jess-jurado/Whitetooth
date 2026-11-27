from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.database import Base, engine, ROOT
from backend.routes.api import router
from backend.services.seed import seed, seed_rooms

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    seed()
    seed_rooms()
    yield

app=FastAPI(title='Dentalis',version='0.2.0',lifespan=lifespan)
@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control']='no-store'
    return response
app.include_router(router)
if (ROOT/'frontend/dist').exists():
    app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='frontend')
