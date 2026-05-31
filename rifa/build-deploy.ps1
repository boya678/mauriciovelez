# ============================================================
# build-deploy.ps1 — Rifa
# Construye imagen multi-arch, la sube al ACR y despliega en K8s
#
# Uso desde la carpeta rifa/:
#   .\build-deploy.ps1              # build + push + deploy
#   .\build-deploy.ps1 -SkipDeploy # solo build y push
# ============================================================
param(
    [switch]$SkipDeploy,
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"

$REGISTRY     = "datara.azurecr.io"
$IMAGE        = "$REGISTRY/mauriciovelez-rifa:$Tag"
$NAMESPACE    = "mauriciovelez"
$PLATFORMS    = "linux/amd64,linux/arm64"
$BUILDER_NAME = "multiarch"

Write-Host ""
Write-Host "🎰  Build-Deploy — Rifa" -ForegroundColor Cyan
Write-Host "   Imagen  : $IMAGE"
Write-Host "   Namespace: $NAMESPACE"
Write-Host ""

# ── Asegurar builder multiarch ────────────────────────────────
$existing = docker buildx inspect $BUILDER_NAME 2>$null
if (-not $existing) {
    Write-Host "► Creando builder multiarch..." -ForegroundColor DarkGray
    docker buildx create --name $BUILDER_NAME --use | Out-Null
} else {
    docker buildx use $BUILDER_NAME | Out-Null
}

# ── Build y push ──────────────────────────────────────────────
Write-Host "► Construyendo imagen ($PLATFORMS)..." -ForegroundColor Yellow
docker buildx build --platform $PLATFORMS -t $IMAGE --push .
Write-Host "✔ Imagen publicada en ACR" -ForegroundColor Green

# ── Deploy K8s ────────────────────────────────────────────────
if (-not $SkipDeploy) {
    Write-Host "► Aplicando manifiestos K8s..." -ForegroundColor Yellow
    kubectl apply -f k8s/ -n $NAMESPACE

    Write-Host "► Reiniciando deployment..." -ForegroundColor Yellow
    kubectl rollout restart deployment/rifa -n $NAMESPACE

    Write-Host "► Esperando rollout..." -ForegroundColor Yellow
    kubectl rollout status deployment/rifa -n $NAMESPACE --timeout=90s

    Write-Host "✔ Deployment completado" -ForegroundColor Green
}

Write-Host ""
Write-Host "✅ ¡Listo! App disponible en: https://rifa.mauricioveleznumerologo.com" -ForegroundColor Green
Write-Host ""
