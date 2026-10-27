<#
.SYNOPSIS
    Automated Azure AKS Deployment Script (Tasks Z4, Z22, Z23)
.DESCRIPTION
    Provisions a 2-node Standard_B2s AKS cluster strictly respecting the 4 vCPU student limit,
    attaches kubectl, installs metrics-server, and applies all telemetry manifests.
#>

param (
    [string]$ResourceGroup = "telemetry-rg",
    [string]$ClusterName = "telemetry-aks",
    [string]$Location = "eastus",
    [string]$VmSize = "Standard_B2s",
    [int]$NodeCount = 2
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  CITY SEISMIC TELEMETRY: AZURE AKS CLOUD DEPLOYMENT" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Verify Azure CLI Login
$account = az account show 2>$null
if (-not $account) {
    Write-Host "[!] Azure CLI not logged in. Initiating az login..." -ForegroundColor Yellow
    az login
}

Write-Host "[+] Target Region: $Location | VM Size: $VmSize | Nodes: $NodeCount" -ForegroundColor Green

# 2. Create Resource Group if not exists
Write-Host "`n[+] Checking Resource Group '$ResourceGroup'..." -ForegroundColor Yellow
az group create --name $ResourceGroup --location $Location --output table

# 3. Create AKS Cluster
Write-Host "`n[+] Provisioning AKS cluster '$ClusterName'..." -ForegroundColor Yellow
az aks create `
    --resource-group $ResourceGroup `
    --name $ClusterName `
    --node-count $NodeCount `
    --node-vm-size $VmSize `
    --os-disk-size-gb 32 `
    --generate-ssh-keys `
    --tier free `
    --output table

if ($LASTEXITCODE -ne 0) {
    Write-Error "AKS provisioning failed. Please check your regional quota."
    exit 1
}

# 4. Attach kubectl Context
Write-Host "`n[+] Fetching cluster credentials into local kubectl..." -ForegroundColor Yellow
az aks get-credentials --resource-group $ResourceGroup --name $ClusterName --overwrite-existing

# 5. Install Metrics Server (for HPA)
Write-Host "`n[+] Installing Metrics Server for HPA Autoscaling..." -ForegroundColor Yellow
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# 6. Apply Telemetry Pipeline Manifests
Write-Host "`n[+] Deploying Telemetry manifests (k8s/)..." -ForegroundColor Yellow
kubectl apply -k k8s/

# 7. Check Cluster Status
Write-Host "`n[+] Waiting for public load balancer IP..." -ForegroundColor Cyan
Start-Sleep -Seconds 10
kubectl get nodes -o wide
kubectl get pods -n telemetry
kubectl get svc -n telemetry

Write-Host "`n[✔] Azure AKS deployment initiated successfully!" -ForegroundColor Green
Write-Host "Use 'kubectl get svc -n telemetry ingest-api-service --watch' to get the public IP." -ForegroundColor Green
Write-Host "To pause the cluster and save credit: az aks stop --resource-group $ResourceGroup --name $ClusterName" -ForegroundColor Yellow
