from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth
from app.routers import numerologia
from app.routers import admin_auth
from app.routers import admin_clientes
from app.routers import admin_usuarios
from app.routers import admin_audit
from app.routers import admin_historico
from app.routers import admin_suscripciones
from app.routers import admin_loterias
from app.routers import admin_dashboard
from app.routers import admin_banners
from app.routers import admin_contactos
from app.routers import banners
from app.core import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="Mauricio Velez API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(numerologia.router)
app.include_router(admin_auth.router)
app.include_router(admin_clientes.router)
app.include_router(admin_usuarios.router)
app.include_router(admin_audit.router)
app.include_router(admin_historico.router)
app.include_router(admin_suscripciones.router)
app.include_router(admin_loterias.router)
app.include_router(admin_dashboard.router)
app.include_router(admin_banners.router)
app.include_router(admin_contactos.router)
app.include_router(banners.router)


@app.get("/health")
def health():
    return {"status": "ok"}
