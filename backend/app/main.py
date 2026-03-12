from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth

app = FastAPI(title="Mauricio Velez API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
def health():
    return {"status": "ok"}
