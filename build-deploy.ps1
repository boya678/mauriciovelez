# ============================================================
# build-deploy.ps1
# Construye imágenes Docker, las sube al ACR y despliega en K8s
#
# Uso:
#   .\build-deploy.ps1                  # build + push + deploy todo
#   .\build-deploy.ps1 -Target backend  # solo backend
#   .\build-deploy.ps1 -Target frontend # solo frontend
#   .\build-deploy.ps1 -SkipDeploy      # solo build y push (sin kubectl)
# ============================================================
param(
    [ValidateSet("backend", "frontend", "all")]
    [string]$Target = "all",
    [switch]$SkipDeploy,
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

# ── Configuración ─────────────────────────────────────────────
$REGISTRY  = "datara.azurecr.io"
$NAMESPACE = "apuestas"
$BACKEND_IMAGE  = "$REGISTRY/mauriciovelez-backend:$Tag"
$FRONTEND_IMAGE = "$REGISTRY/mauriciovelez-frontend:$Tag"
$ROOT = $PSScriptRoot

# ── Helpers ───────────────────────────────────────────────────
function Write-Step([string]$msg) {
    Write-Host "`n▶  $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "✔  $msg" -ForegroundColor Green
}

# ── 1. Login al ACR ───────────────────────────────────────────
Write-Step "Login en Azure Container Registry: $REGISTRY"
az acr login --name ($REGISTRY -split '\.')[0]
Write-OK "Login OK"

# ── 2. Build + Push Backend ───────────────────────────────────
if ($Target -in "backend", "all") {
    Write-Step "Build backend  →  $BACKEND_IMAGE"
    docker build -t $BACKEND_IMAGE "$ROOT\backend"
    Write-Step "Push backend   →  $BACKEND_IMAGE"
    docker push $BACKEND_IMAGE
    Write-OK "Backend image publicada"
}

# ── 3. Build + Push Frontend ──────────────────────────────────
if ($Target -in "frontend", "all") {
    Write-Step "Build frontend  →  $FRONTEND_IMAGE"
    docker build -t $FRONTEND_IMAGE "$ROOT\frontend"
    Write-Step "Push frontend   →  $FRONTEND_IMAGE"
    docker push $FRONTEND_IMAGE
    Write-OK "Frontend image publicada"
}

if ($SkipDeploy) {
    Write-Host "`n-SkipDeploy activo — terminando sin aplicar manifests.`n" -ForegroundColor Yellow
    exit 0
}

# ── 4. Crear namespace (si no existe) ─────────────────────────
Write-Step "Asegurando namespace: $NAMESPACE"
kubectl get namespace $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    kubectl create namespace $NAMESPACE
    Write-OK "Namespace $NAMESPACE creado"
} else {
    Write-OK "Namespace $NAMESPACE ya existe"
}

# ── 5. Secrets (solo si no existen) ───────────────────────────
# NOTA: edita las variables de entorno antes de correr esto por primera vez
Write-Step "Verificando secret backend-secrets..."
$existsSecret = kubectl get secret backend-secrets -n $NAMESPACE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Secret no encontrado. Creando desde variables de entorno..." -ForegroundColor Yellow
    Write-Host "   Asegúrate de exportar DB_URL y JWT_KEY antes de correr este script." -ForegroundColor Yellow

    if (-not $env:DB_URL -or -not $env:JWT_KEY) {
        Write-Host "`n   ERROR: Debes definir las variables de entorno DB_URL y JWT_KEY" -ForegroundColor Red
        Write-Host "   Ejemplo:" -ForegroundColor Gray
        Write-Host '   $env:DB_URL = "postgresql://usuario:pass@host:5432/portal"' -ForegroundColor Gray
        Write-Host '   $env:JWT_KEY = "tu_secret_aqui"' -ForegroundColor Gray
        exit 1
    }

    kubectl create secret generic backend-secrets `
        --namespace $NAMESPACE `
        --from-literal=DATABASE_URL=$env:DB_URL `
        --from-literal=JWT_SECRET_KEY=$env:JWT_KEY
    Write-OK "Secret backend-secrets creado"
} else {
    Write-OK "Secret backend-secrets ya existe"
}

# ── 6. Secret de pull del ACR ─────────────────────────────────
Write-Step "Verificando secret acr-secret..."
$existsAcr = kubectl get secret acr-secret -n $NAMESPACE 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Creando acr-secret desde credenciales ACR..." -ForegroundColor Yellow

    $acrName = ($REGISTRY -split '\.')[0]
    $acrCreds = az acr credential show --name $acrName | ConvertFrom-Json
    $acrUser  = $acrCreds.username
    $acrPass  = $acrCreds.passwords[0].value

    kubectl create secret docker-registry acr-secret `
        --namespace $NAMESPACE `
        --docker-server=$REGISTRY `
        --docker-username=$acrUser `
        --docker-password=$acrPass
    Write-OK "acr-secret creado"
} else {
    Write-OK "acr-secret ya existe"
}

# ── 7. Aplicar manifests ──────────────────────────────────────
if ($Target -in "backend", "all") {
    Write-Step "Aplicando manifests backend..."
    kubectl apply -f "$ROOT\backend\k8s\" --namespace $NAMESPACE
    kubectl rollout restart deployment/backend --namespace $NAMESPACE
    Write-OK "Backend desplegado"
}

if ($Target -in "frontend", "all") {
    Write-Step "Aplicando manifests frontend..."
    kubectl apply -f "$ROOT\frontend\k8s\" --namespace $NAMESPACE
    kubectl rollout restart deployment/frontend --namespace $NAMESPACE
    Write-OK "Frontend desplegado"
}

# ── 8. Verificar estado ───────────────────────────────────────
Write-Step "Estado del namespace $NAMESPACE"
kubectl get all -n $NAMESPACE

Write-Host "`n🚀  Deploy completado exitosamente.`n" -ForegroundColor Green
