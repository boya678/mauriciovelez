# ChatSystem — Plataforma de atención al cliente por WhatsApp

Sistema multi-tenant de chat que integra WhatsApp (Meta Cloud API), un agente de IA con LangGraph, asignación automática de conversaciones a agentes humanos y un panel de administración en tiempo real.

---

## Índice

1. [Arquitectura](#arquitectura)
2. [Flujo de mensajes](#flujo-de-mensajes)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Variables de entorno](#variables-de-entorno)
5. [Desarrollo local](#desarrollo-local)
6. [Migraciones de base de datos](#migraciones-de-base-de-datos)
7. [Despliegue en Kubernetes](#despliegue-en-kubernetes)
8. [API — Endpoints principales](#api--endpoints-principales)
9. [WebSocket](#websocket)
10. [Frontend](#frontend)

---

## Arquitectura

```
WhatsApp Cloud API
        │  webhook POST /api/v1/webhook
        ▼
┌─────────────────────────────────────────────────────┐
│                   FastAPI (backend)                  │
│                                                     │
│  /api/v1/webhook  →  Redis Stream: inbound_messages │
│  /api/v1/conversations  (REST)                      │
│  /api/v1/agents         (REST)                      │
│  /ws/{tenant}/{agent}   (WebSocket)                 │
└───────────────┬─────────────────────────────────────┘
                │
        Redis Streams
        │              │              │              │
        ▼              ▼              ▼              ▼
  MessageIngestion  AIWorker   AssignmentWorker  OutgoingWorker
  (parse & store)  (LangGraph) (human handoff)  (send to WA)
                                                      │
                                              WhatsApp Cloud API
                                              POST /messages
```

### Componentes principales

| Componente | Tecnología | Función |
|---|---|---|
| **API** | FastAPI + Uvicorn | REST + WebSocket |
| **Base de datos** | PostgreSQL 16 (asyncpg) | Persistencia multi-tenant |
| **Cola de mensajes** | Redis 7 Streams | Pipeline asíncrono entre workers |
| **IA** | LangGraph + Azure OpenAI (GPT-4o) | Respuestas automáticas |
| **Workers** | asyncio tasks internas | Procesamiento de mensajes en background |
| **Frontend** | Angular 17 (standalone) | Panel web para agentes |

---

## Flujo de mensajes

```
1. WhatsApp envía webhook  →  POST /api/v1/webhook
2. Webhook publica en     →  Redis Stream: inbound_messages
3. MessageIngestion lee   →  Guarda mensaje en PostgreSQL, crea conversación si es nueva
4. AIWorker analiza       →  LangGraph decide responder o escalar a humano
   ├── Si puede responder →  OutgoingWorker → WhatsApp API
   └── Si escala        →  AssignmentWorker cambia estado a waiting_human
5. Agente toma conversación  →  POST /conversations/{id}/take
6. Agente envía mensajes     →  POST /conversations/{id}/send → OutgoingWorker → WhatsApp
7. Agente cierra             →  POST /conversations/{id}/close
8. Toda acción notifica      →  WebSocket broadcast al tenant
```

### Estados de conversación

```
new → bot_active → waiting_human → human_active → closed
```

| Estado | Descripción |
|---|---|
| `new` | Recién creada, sin procesar |
| `bot_active` | IA respondiendo |
| `waiting_human` | IA escaló; esperando agente disponible |
| `human_active` | Asignada a un agente humano |
| `closed` | Finalizada |

---

## Estructura del proyecto

```
chatsystem/
├── backend/
│   ├── app/
│   │   ├── main.py                  # Entry point FastAPI + lifespan
│   │   ├── core/
│   │   │   ├── config.py            # Settings (pydantic-settings)
│   │   │   └── security.py          # JWT + bcrypt
│   │   ├── api/
│   │   │   ├── webhook.py           # POST /api/v1/webhook (WhatsApp)
│   │   │   ├── conversations.py     # CRUD conversaciones
│   │   │   ├── agents.py            # Login, perfil, CRUD agentes
│   │   │   ├── tenants.py           # Gestión de tenants
│   │   │   └── ws.py                # WebSocket /ws/{tenant}/{agent}
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── schemas/                 # Pydantic schemas (request/response)
│   │   ├── services/                # Lógica de negocio
│   │   ├── redis/
│   │   │   ├── client.py            # Conexión global Redis
│   │   │   └── streams.py           # Publish/consume helpers
│   │   ├── workers/
│   │   │   ├── runner.py            # Lanza todos los workers
│   │   │   ├── message_ingestion.py # Ingiere mensajes entrantes
│   │   │   ├── ai_worker.py         # LangGraph pipeline
│   │   │   ├── assignment_worker.py # Escalado a humano
│   │   │   └── outgoing_worker.py   # Envío a WhatsApp API
│   │   └── websocket/
│   │       └── manager.py           # Broadcast por tenant
│   ├── alembic/                     # Migraciones de BD
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/app/
│   │   ├── core/
│   │   │   ├── models/              # TypeScript interfaces
│   │   │   ├── services/            # HTTP + WebSocket services
│   │   │   ├── interceptors/        # Auth JWT interceptor
│   │   │   └── guards/              # authGuard, adminGuard
│   │   └── features/
│   │       ├── auth/login/          # Pantalla de login
│   │       ├── layout/              # Shell con sidebar
│   │       ├── agent/
│   │       │   ├── inbox/           # Bandeja split-panel
│   │       │   └── chat/            # Panel de mensajes
│   │       └── admin/
│   │           ├── dashboard/       # Stats + agentes online
│   │           └── agents/          # CRUD agentes
│   ├── Dockerfile
│   └── k8s/
├── docker-compose.yml               # Entorno local completo
└── build-deploy.ps1                 # Build multi-arch + deploy K8s
```

---

## Variables de entorno

Crea `backend/.env` copiando el siguiente template:

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://chatsystem:chatsystem@localhost:5432/chatsystem

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
SECRET_KEY=cambia_esto_por_un_secreto_largo_y_aleatorio
ACCESS_TOKEN_EXPIRE_MINUTES=480

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://tu-recurso.openai.azure.com/
AZURE_OPENAI_API_KEY=TU_API_KEY
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-01

# WhatsApp Meta Cloud API
WHATSAPP_VERIFY_TOKEN=token_que_usas_en_meta_dashboard
WHATSAPP_TOKEN=Bearer token del sistema de WhatsApp
WHATSAPP_PHONE_ID=ID_del_numero_en_Meta

# Configuración opcional de IA
AI_MAX_TURNS=10
AI_CONFIDENCE_THRESHOLD=0.6
```

> **Nunca** subas `.env` al repositorio. Está en `.gitignore`.

---

## Desarrollo local

### Requisitos

- Docker Desktop
- Python 3.11+
- Node.js 20+

### 1. Levantar infraestructura

```bash
cd chatsystem
docker compose up postgres redis -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Migraciones
alembic upgrade head

# Servidor de desarrollo
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm start
# Abre http://localhost:4200
```

### 4. Stack completo con Docker Compose

```bash
docker compose up --build
# Backend:  http://localhost:8000
# Docs API: http://localhost:8000/docs
```

---

## Migraciones de base de datos

```bash
# Aplicar todas las migraciones pendientes
alembic upgrade head

# Crear una nueva migración (autogenerada)
alembic revision --autogenerate -m "descripcion"

# Revertir última migración
alembic downgrade -1
```

---

## Despliegue en Kubernetes

### Pre-requisitos

- AKS cluster activo
- `kubectl` configurado (`az aks get-credentials ...`)
- ACR: `datara.azurecr.io`
- `docker buildx` con builder multi-arch

### Script de deploy

```powershell
# Construye imágenes multi-arch (amd64 + arm64), las sube al ACR y despliega
.\build-deploy.ps1

# Solo hacer build y push, sin desplegar
.\build-deploy.ps1 -SkipDeploy

# Solo desplegar (reusar imágenes ya publicadas)
.\build-deploy.ps1 -SkipBuild

# Tag personalizado
.\build-deploy.ps1 -Tag v1.2.0
```

### URLs en producción

| Servicio | URL |
|---|---|
| Backend API | `https://webhook.mauricioveleznumerologo.com` |
| Panel de agentes | `https://chat.webhook.mauricioveleznumerologo.com` |
| Webhook WhatsApp | `https://webhook.mauricioveleznumerologo.com/api/v1/webhook` |

### Manifests K8s

Cada componente tiene su propio directorio `k8s/` con `deployment.yaml`, `service.yaml` e `ingress.yaml`. El Ingress usa cert-manager con Let's Encrypt para TLS automático.

---

## API — Endpoints principales

### Autenticación

```
POST /api/v1/agents/login
  Headers: X-Tenant-ID: {slug}
  Body: { email, password }
  Response: { access_token, token_type }
```

Todos los demás endpoints requieren:
```
Authorization: Bearer {token}
X-Tenant-ID: {slug}
```

### Conversaciones

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/conversations` | Listar (filtro: `?status=waiting_human`) |
| `GET` | `/api/v1/conversations/{id}` | Detalle con mensajes |
| `POST` | `/api/v1/conversations/{id}/take` | Asignar al agente autenticado |
| `POST` | `/api/v1/conversations/{id}/close` | Cerrar conversación |
| `POST` | `/api/v1/conversations/{id}/send` | Enviar mensaje como agente |

### Agentes

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/v1/agents/me` | Perfil propio |
| `PUT` | `/api/v1/agents/me/status` | Cambiar estado (online/offline) |
| `POST` | `/api/v1/agents/heartbeat` | Mantener presencia |
| `GET` | `/api/v1/agents` | Listar todos (admin) |
| `POST` | `/api/v1/agents` | Crear agente (admin) |
| `PUT` | `/api/v1/agents/{id}` | Editar agente (admin) |
| `DELETE` | `/api/v1/agents/{id}` | Eliminar agente (admin) |

### Webhook WhatsApp

```
GET  /api/v1/webhook   →  Verificación Meta (hub.challenge)
POST /api/v1/webhook   →  Recepción de mensajes entrantes
```

La documentación interactiva completa está disponible en `/docs` (Swagger UI).

---

## WebSocket

### Conexión

```
wss://webhook.mauricioveleznumerologo.com/ws/{tenantSlug}/{agentId}?token={JWT}
```

### Eventos del servidor → cliente

```jsonc
// Nuevo mensaje en una conversación
{ "type": "new_message", "conversation_id": "...", "message": { ... } }

// Conversación asignada / reasignada
{ "type": "conversation_assigned", "conversation_id": "..." }

// Conversación cerrada
{ "type": "conversation_closed", "conversation_id": "..." }

// Respuesta al ping del cliente
{ "type": "pong" }
```

### Mensajes del cliente → servidor

```jsonc
// Keepalive (el frontend envía cada 10s)
{ "type": "ping" }
```

---

## Frontend

### Rutas

| Ruta | Componente | Acceso |
|---|---|---|
| `/login` | LoginComponent | Público |
| `/inbox` | InboxComponent | Agentes autenticados |
| `/admin/dashboard` | DashboardComponent | Solo admin/superadmin |
| `/admin/agents` | AgentsMgmtComponent | Solo admin/superadmin |

### Roles de agente

| Rol | Permisos |
|---|---|
| `agent` | Ver bandeja, tomar y atender conversaciones |
| `admin` | Todo lo anterior + dashboard + gestión de agentes |
| `superadmin` | Igual que admin (con capacidad de gestión cross-tenant) |

### Tecnologías

- Angular 17 — standalone components, signals, functional guards
- Sin librerías de UI externas — diseño propio en SCSS
- WebSocket con reconexión automática y heartbeat
- JWT almacenado en `localStorage` (`cs_token`, `cs_tenant`)
