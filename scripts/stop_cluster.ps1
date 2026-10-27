<#
.SYNOPSIS
    Pauses or Resumes the Azure AKS Cluster to save credit (Task Z28)
#>

param (
    [string]$ResourceGroup = "telemetry-rg",
    [string]$ClusterName = "telemetry-aks",
    [ValidateSet("stop", "start")]
    [string]$Action = "stop"
)

Write-Host "[*] Executing 'az aks $Action' on cluster '$ClusterName' in '$ResourceGroup'..." -ForegroundColor Cyan

if ($Action -eq "stop") {
    az aks stop --resource-group $ResourceGroup --name $ClusterName
    Write-Host "[✔] Cluster stopped. VMs deallocated. Hourly compute charges are now $0.00." -ForegroundColor Green
} else {
    az aks start --resource-group $ResourceGroup --name $ClusterName
    Write-Host "[✔] Cluster resumed and ready for testing." -ForegroundColor Green
}
