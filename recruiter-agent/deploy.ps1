# =========================================================
# deploy.ps1 — Cloud Run Deployment Script (PWsh5 Safe)
# =========================================================

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "==================================================="
Write-Host "Deploying recruiter-agent to Cloud Run..."
Write-Host "==================================================="

# ==================================================
# Helper Functions
# ==================================================

function Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message"
    Write-Host ""
    exit 1
}

function CheckExit {
    param([string]$Step)
    if ($LASTEXITCODE -ne 0) {
        Fail "$Step failed (exit code $LASTEXITCODE)"
    }
}

# ==================================================
# Configuration
# ==================================================

# Defaults
$PROJECT = "recruiter-sergiu-260213"
$REGION  = "europe-west1"
$SERVICE = "recruiter-agent"
$REPO_NAME  = "recruiter-agent"
$IMAGE_NAME = "recruiter-agent"
$TAG = "latest"

# Environment overrides (PS5 compatible)
if ($env:GCP_PROJECT -and $env:GCP_PROJECT.Trim() -ne "") {
    $PROJECT = $env:GCP_PROJECT.Trim()
}
if ($env:GCP_REGION -and $env:GCP_REGION.Trim() -ne "") {
    $REGION = $env:GCP_REGION.Trim()
}
if ($env:CLOUD_RUN_SERVICE -and $env:CLOUD_RUN_SERVICE.Trim() -ne "") {
    $SERVICE = $env:CLOUD_RUN_SERVICE.Trim()
}
if ($env:IMAGE_TAG -and $env:IMAGE_TAG.Trim() -ne "") {
    $TAG = $env:IMAGE_TAG.Trim()
}

$AR_REPO = "$REGION-docker.pkg.dev/$PROJECT/$REPO_NAME/$IMAGE_NAME"
$IMAGE = "$AR_REPO" + ":" + "$TAG"

$PORT    = 8080
$MEMORY  = "1Gi"
$TIMEOUT = 300

Write-Host ""
Write-Host "--------- CONFIG ---------"
Write-Host "PROJECT : $PROJECT"
Write-Host "REGION  : $REGION"
Write-Host "SERVICE : $SERVICE"
Write-Host "IMAGE   : $IMAGE"
Write-Host "---------------------------"
Write-Host ""

# Validate
if (-not $PROJECT -or -not $REGION -or -not $SERVICE) {
    Fail "PROJECT, REGION, and SERVICE must be non-empty."
}

# ==================================================
# Preflight
# ==================================================

Write-Host "Checking required CLI tools..."
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) { Fail "gcloud not found." }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail "docker not found." }
Write-Host "OK"
Write-Host ""

Write-Host "Checking gcloud active project..."
$activeProject = (gcloud config get-value project 2>$null).Trim()
if (-not $activeProject) { Fail "No active gcloud project." }
Write-Host "Active project: $activeProject"
Write-Host ""

# ==================================================
# Docker Auth
# ==================================================

Write-Host "Configuring Docker authentication..."
gcloud auth configure-docker "$REGION-docker.pkg.dev"
CheckExit "Docker authentication"
Write-Host ""

# ==================================================
# Docker Build
# ==================================================

Write-Host "Building Docker image..."
Write-Host "docker build -t $IMAGE ."
docker build -t "$IMAGE" .
CheckExit "Docker build"
Write-Host ""

# ==================================================
# Docker Push
# ==================================================

Write-Host "Pushing image..."
Write-Host "docker push $IMAGE"
docker push "$IMAGE"
CheckExit "Docker push"
Write-Host ""

# ==================================================
# Deploy to Cloud Run
# ==================================================

Write-Host "Deploying to Cloud Run..."
gcloud run deploy $SERVICE `
    --image "$IMAGE" `
    --region "$REGION" `
    --platform managed `
    --allow-unauthenticated `
    --port $PORT `
    --memory $MEMORY `
    --timeout $TIMEOUT
CheckExit "Cloud Run deployment"

# ==================================================
# Done
# ==================================================

Write-Host ""
Write-Host "========================================="
Write-Host "Deployment complete!"
Write-Host "Service : $SERVICE"
Write-Host "Image   : $IMAGE"
Write-Host ""

Write-Host "Secure URL:"
$serviceUrl = gcloud run services describe $SERVICE --region $REGION --format="value(status.url)"
if ($LASTEXITCODE -eq 0 -and $serviceUrl) {
    Write-Host $serviceUrl
} else {
    Write-Host "(Could not retrieve URL)"
}
Write-Host "========================================="
