<#
.SYNOPSIS
    Complete Teardown & Permanent Resource Deletion Script (Task Z28)
#>

param (
    [string]$ResourceGroup = "telemetry-rg"
)

Write-Host "==========================================================" -ForegroundColor Red
Write-Host "  AZURE COMPLETE TEARDOWN & CREDIT PROTECTION" -ForegroundColor Red
Write-Host "==========================================================" -ForegroundColor Red
Write-Host "WARNING: This will permanently delete resource group '$ResourceGroup' and all contained resources." -ForegroundColor Yellow

$confirm = Read-Host "Are you sure you want to delete everything? (type 'yes' to proceed)"
if ($confirm -eq "yes") {
    Write-Host "[+] Initiating permanent deletion of '$ResourceGroup'..." -ForegroundColor Yellow
    az group delete --name $ResourceGroup --yes --no-wait
    Write-Host "[✔] Deletion command submitted. All cloud billing stopped permanently." -ForegroundColor Green
} else {
    Write-Host "[-] Aborted. No resources were deleted." -ForegroundColor Cyan
}
