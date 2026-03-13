# ============================================================
# build-deploy.ps1
# Construye imágenes multi-arch (amd64+arm64), las sube al ACR y despliega en K8s
#
# Uso:
#   .\build-deploy.ps1                  # build + push + deploy todo
#   .\build-deploy.ps1 -Target backend  # solo backend
#   .\build-deploy.ps1 -Target frontend # solo frontend
#   .\build-deploy.ps1 -Target admin    # solo admin
#   .\build-deploy.ps1 -SkipDeploy      # solo build y push (sin kubectl)
# ============================================================
param(
    [ValidateSet("backend", "frontend", "admin", "all")]
    [string]$Target = "all",
    [switch]$SkipDeploy,
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

# ── Configuración ─────────────────────────────────────────────
$REGISTRY       = "datara.azurecr.io"
$NAMESPACE      = "mauriciovelez"
$BACKEND_IMAGE  = "$REGISTRY/mauriciovelez-backend:$Tag"
$FRONTEND_IMAGE = "$REGISTRY/mauriciovelez-frontend:$Tag"
$ADMIN_IMAGE    = "$REGISTRY/mauriciovelez-admin:$Tag"
$PLATFORMS      = "linux/amd64,linux/arm64"
$BUILDER_NAME   = "multiarch"
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

# ── 2. Preparar builder multi-arch ────────────────────────────
Write-Step "Configurando builder multi-arch: $BUILDER_NAME"
$existsBuilder = docker buildx inspect $BUILDER_NAME 2>$null
if ($LASTEXITCODE -ne 0) {
    docker buildx create --name $BUILDER_NAME --use
} else {
    docker buildx use $BUILDER_NAME
}
docker buildx inspect --bootstrap
Write-OK "Builder $BUILDER_NAME listo"

# ── 3. Build + Push Backend ───────────────────────────────────
if ($Target -in "backend", "all") {
    Write-Step "Build + Push backend  →  $BACKEND_IMAGE  [$PLATFORMS]"
    docker buildx use $BUILDER_NAME
    docker buildx build --platform $PLATFORMS --push -t $BACKEND_IMAGE "$ROOT\backend"
    Write-OK "Backend image publicada"
}

# ── 4. Build + Push Frontend ──────────────────────────────────
if ($Target -in "frontend", "all") {
    Write-Step "Build + Push frontend  →  $FRONTEND_IMAGE  [$PLATFORMS]"
    docker buildx use $BUILDER_NAME
    docker buildx build --platform $PLATFORMS --push -t $FRONTEND_IMAGE "$ROOT\frontend"
    Write-OK "Frontend image publicada"
}

# ── 5. Build + Push Admin ─────────────────────────────────────
if ($Target -in "admin", "all") {
    Write-Step "Build + Push admin  →  $ADMIN_IMAGE  [$PLATFORMS]"
    docker buildx use $BUILDER_NAME
    docker buildx build --platform $PLATFORMS --push -t $ADMIN_IMAGE "$ROOT\admin"
    Write-OK "Admin image publicada"
}

if ($SkipDeploy) {
    Write-Host "`n-SkipDeploy activo — terminando sin aplicar manifests.`n" -ForegroundColor Yellow
    exit 0
}

# ── 6. Crear namespace (si no existe) ─────────────────────────
Write-Step "Asegurando namespace: $NAMESPACE"
kubectl get namespace $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    kubectl create namespace $NAMESPACE
    Write-OK "Namespace $NAMESPACE creado"
} else {
    Write-OK "Namespace $NAMESPACE ya existe"
}

# ── 7. Secrets (solo si no existen) ───────────────────────────
Write-Step "Verificando secret backend-secrets..."
$existsSecret = kubectl get secret backend-secrets -n $NAMESPACE 2>$null
if ($LASTEXITCODE -ne 0) {
    # Leer valores desde backend/.env
    $envFile = "$ROOT\backend\.env"
    if (-not (Test-Path $envFile)) {
        Write-Host "`n   ERROR: No se encontró $envFile" -ForegroundColor Red
        Write-Host "   Crea el archivo con las claves DATABASE_URL y JWT_SECRET_KEY" -ForegroundColor Gray
        exit 1
    }

    $dotenv = @{}
    Get-Content $envFile | Where-Object { $_ -match '^\s*[^#]\S+=.+' } | ForEach-Object {
        $parts = $_ -split '=', 2
        $dotenv[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
    }

    $dbUrl  = $dotenv['DATABASE_URL']
    $jwtKey = $dotenv['JWT_SECRET_KEY']

    if (-not $dbUrl -or -not $jwtKey) {
        Write-Host "`n   ERROR: $envFile debe contener DATABASE_URL y JWT_SECRET_KEY" -ForegroundColor Red
        exit 1
    }

    Write-Host "   Creando secret desde $envFile ..." -ForegroundColor Yellow
    kubectl create secret generic backend-secrets `
        --namespace $NAMESPACE `
        --from-literal=DATABASE_URL=$dbUrl `
        --from-literal=JWT_SECRET_KEY=$jwtKey
    Write-OK "Secret backend-secrets creado"
} else {
    Write-OK "Secret backend-secrets ya existe"
}

# ── 8. Aplicar manifests ──────────────────────────────────────
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

if ($Target -in "admin", "all") {
    Write-Step "Aplicando manifests admin..."
    kubectl apply -f "$ROOT\admin\k8s\" --namespace $NAMESPACE
    kubectl rollout restart deployment/admin --namespace $NAMESPACE
    Write-OK "Admin desplegado"
}

# ── 9. Verificar estado ───────────────────────────────────────
Write-Step "Estado del namespace $NAMESPACE"
kubectl get all -n $NAMESPACE

Write-Host "`n🚀  Deploy completado exitosamente.`n" -ForegroundColor Green
