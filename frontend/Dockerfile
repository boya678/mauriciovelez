# ── Stage 1: build Angular ────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Instalar dependencias (cacheable)
COPY package*.json ./
RUN npm ci --silent

# Compilar en modo producción
COPY . .
RUN npm run build -- --configuration production

# ── Stage 2: nginx para servir el SPA ────────────────────────
FROM nginx:1.27-alpine

# Configuración de nginx para SPA (maneja rutas de Angular)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar artefactos del build
COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
