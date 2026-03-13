from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth
from app.routers import numerologia
from app.routers import admin_auth
from app.routers import admin_clientes
from app.routers import admin_usuarios
from app.routers import admin_audit

app = FastAPI(title="Mauricio Velez API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:4201"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(numerologia.router)
app.include_router(admin_auth.router)
app.include_router(admin_clientes.router)
app.include_router(admin_usuarios.router)
app.include_router(admin_audit.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}
