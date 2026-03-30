$ErrorActionPreference = "SilentlyContinue"

$ContainerName = "finally"

Write-Host "Stopping FinAlly..."
docker rm -f $ContainerName
Write-Host "Data volume preserved."
