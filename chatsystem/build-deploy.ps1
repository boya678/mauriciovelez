# ============================================================
# build-deploy.ps1  (chatsystem)
# Construye imagen multi-arch (amd64+arm64), la sube al ACR y despliega en K8s
#
# Uso:
#   .\build-deploy.ps1                  # build + push + deploy
#   .\build-deploy.ps1 -SkipBuild       # solo deploy (sin build/push)
#   .\build-deploy.ps1 -SkipDeploy      # solo build y push (sin kubectl)
#   .\build-deploy.ps1 -Tag v1.2.3      # tag personalizado
# ============================================================
param(
    [switch]$SkipBuild,
    [switch]$SkipDeploy,
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

# ── Configuración ─────────────────────────────────────────────
$REGISTRY        = "datara.azurecr.io"
$NAMESPACE       = "mauriciovelez"
$IMAGE           = "$REGISTRY/chatsystem-backend:$Tag"
$FRONTEND_IMAGE  = "$REGISTRY/chatsystem-frontend:$Tag"
$PLATFORMS       = "linux/amd64,linux/arm64"
$BUILDER_NAME    = "multiarch"
$ROOT            = $PSScriptRoot

# ── Helpers ───────────────────────────────────────────────────
function Write-Step([string]$msg) {
    Write-Host "`n▶  $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "✔  $msg" -ForegroundColor Green
}

# ── 1. Build + Push ───────────────────────────────────────────
if (-not $SkipBuild) {
    Write-Step "Configurando builder multi-arch: $BUILDER_NAME"
    docker buildx inspect $BUILDER_NAME 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        docker buildx create --name $BUILDER_NAME --use
    } else {
        docker buildx use $BUILDER_NAME
    }
    docker buildx inspect --bootstrap
    Write-OK "Builder listo"

    Write-Step "Build + Push  →  $IMAGE  [$PLATFORMS]"
    docker buildx build --platform $PLATFORMS --push -t $IMAGE "$ROOT\backend"
    Write-OK "Imagen publicada: $IMAGE"

    Write-Step "Build + Push  →  $FRONTEND_IMAGE  [$PLATFORMS]"
    docker buildx build --platform $PLATFORMS --push -t $FRONTEND_IMAGE "$ROOT\frontend"
    Write-OK "Imagen publicada: $FRONTEND_IMAGE"
}

if ($SkipDeploy) {
    Write-Host "`n-SkipDeploy activo — terminando sin aplicar manifests.`n" -ForegroundColor Yellow
    exit 0
}

# ── 2. Crear namespace (si no existe) ─────────────────────────
Write-Step "Asegurando namespace: $NAMESPACE"
kubectl get namespace $NAMESPACE 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    kubectl create namespace $NAMESPACE
    Write-OK "Namespace $NAMESPACE creado"
} else {
    Write-OK "Namespace $NAMESPACE ya existe"
}

# ── 3. Aplicar secret desde .env ──────────────────────────────
Write-Step "Aplicando secret chatsystem-secrets desde .env..."
$envFile = "$ROOT\backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "`n   ERROR: No se encontró $envFile" -ForegroundColor Red
    Write-Host "   Copia .env.example → .env y rellena los valores." -ForegroundColor Gray
    exit 1
}

kubectl create secret generic chatsystem-secrets `
    --namespace $NAMESPACE `
    --from-env-file="$envFile" `
    --dry-run=client -o yaml | kubectl apply -f -

Write-OK "Secret chatsystem-secrets actualizado"

# ── 4. Migraciones Alembic ────────────────────────────────────
Write-Step "Corriendo migraciones Alembic..."
$migPod = "alembic-migrate"
# Borrar pod previo si quedó de un deploy anterior
kubectl delete pod $migPod --namespace $NAMESPACE --ignore-not-found | Out-Null

$migManifest = @"
apiVersion: v1
kind: Pod
metadata:
  name: $migPod
  namespace: $NAMESPACE
spec:
  restartPolicy: Never
  containers:
    - name: alembic
      image: $IMAGE
      imagePullPolicy: Always
      command: ["python", "-m", "alembic", "upgrade", "head"]
      envFrom:
        - secretRef:
            name: chatsystem-secrets
"@
$migManifest | kubectl apply -f -

# Esperar a que termine (máx 2 minutos)
$deadline = (Get-Date).AddSeconds(120)
do {
    Start-Sleep -Seconds 3
    $phase = kubectl get pod $migPod -n $NAMESPACE -o jsonpath='{.status.phase}' 2>$null
} while ($phase -notin @("Succeeded","Failed") -and (Get-Date) -lt $deadline)

kubectl logs $migPod --namespace $NAMESPACE
if ($phase -ne "Succeeded") {
    Write-Host "`n   ERROR: Migraciones fallaron (phase=$phase). Abortando deploy." -ForegroundColor Red
    kubectl delete pod $migPod --namespace $NAMESPACE --ignore-not-found | Out-Null
    exit 1
}
kubectl delete pod $migPod --namespace $NAMESPACE --ignore-not-found | Out-Null
Write-OK "Migraciones aplicadas"

# ── 6. Aplicar manifests K8s ──────────────────────────────────
Write-Step "Aplicando manifests K8s..."
kubectl apply -f "$ROOT\backend\k8s\" --namespace $NAMESPACE
kubectl apply -f "$ROOT\frontend\k8s\" --namespace $NAMESPACE

# ── 7. Actualizar imagen en deployments ───────────────────────
Write-Step "Actualizando imagen en deployments..."
kubectl set image deployment/chatsystem-backend  backend=$IMAGE          --namespace $NAMESPACE
kubectl set image deployment/chatsystem-workers  workers=$IMAGE          --namespace $NAMESPACE
kubectl set image deployment/chatsystem-frontend frontend=$FRONTEND_IMAGE --namespace $NAMESPACE

# ── 6. Esperar rollout ────────────────────────────────────────
Write-Step "Esperando rollout backend..."
kubectl rollout restart deployment/chatsystem-backend --namespace $NAMESPACE

Write-Step "Esperando rollout workers..."
kubectl rollout restart deployment/chatsystem-workers --namespace $NAMESPACE

Write-Step "Esperando rollout frontend..."
kubectl rollout restart deployment/chatsystem-frontend --namespace $NAMESPACE

# ── 8. Estado final ───────────────────────────────────────────
Write-Step "Estado del namespace $NAMESPACE"
kubectl get all -n $NAMESPACE

Write-Host "`n🚀  Deploy chatsystem completado." -ForegroundColor Green
Write-Host "    Backend:  https://webhook.mauricioveleznumerologo.com" -ForegroundColor Green
Write-Host "    Frontend: https://chat.webhook.mauricioveleznumerologo.com`n" -ForegroundColor Green
