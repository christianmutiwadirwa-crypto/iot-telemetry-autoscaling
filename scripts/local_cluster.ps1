<#
.SYNOPSIS
    Automated Local Kubernetes (kind) Cluster Setup & Rollout Script (Tasks L17-L22)
.DESCRIPTION
    Creates a 3-node local kind cluster, builds images, loads them into kind,
    installs metrics-server, and deploys the full telemetry pipeline with HPA.
#>

param (
    [string]$ClusterName = "telemetry-cluster"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  CITY SEISMIC TELEMETRY: LOCAL KUBERNETES ROLLOUT" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check if kind cluster already exists
$existingClusters = kind get clusters 2>$null
if ($existingClusters -contains $ClusterName) {
    Write-Host "[+] kind cluster '$ClusterName' is already running." -ForegroundColor Green
} else {
    Write-Host "[+] Creating 3-node kind cluster '$ClusterName'..." -ForegroundColor Yellow
    kind create cluster --config k8s/kind-config.yaml
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create kind cluster. Ensure Docker Desktop is running."
        exit 1
    }
}

# 2. Build local Docker images
Write-Host "`n[+] Building Ingest API and Processor Docker images..." -ForegroundColor Yellow
docker build -t ingest-api:latest services/ingest-api/
docker build -t processor:latest services/processor/

# 3. Load Docker images into kind nodes
Write-Host "`n[+] Loading images into kind cluster '$ClusterName'..." -ForegroundColor Yellow
kind load docker-image ingest-api:latest --name $ClusterName
kind load docker-image processor:latest --name $ClusterName

# 4. Install metrics-server for HPA (Task L22)
Write-Host "`n[+] Installing metrics-server for HPA..." -ForegroundColor Yellow
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch -n kube-system deployment/metrics-server --type='json' -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# 5. Deploy telemetry pipeline manifests
Write-Host "`n[+] Applying Kubernetes manifests (k8s/)..." -ForegroundColor Yellow
kubectl apply -k k8s/

# 6. Status Check
Write-Host "`n[+] Waiting for pods to become ready in 'telemetry' namespace..." -ForegroundColor Cyan
Start-Sleep -Seconds 5
kubectl get pods -n telemetry -o wide
kubectl get svc -n telemetry
kubectl get hpa -n telemetry

Write-Host "`n[✔] Cluster rollout complete!" -ForegroundColor Green
Write-Host "Ingest API: http://localhost:8000/healthz" -ForegroundColor Green
Write-Host "RabbitMQ Management: http://localhost:15672 (guest/guest)" -ForegroundColor Green
