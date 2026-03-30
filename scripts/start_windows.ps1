$ErrorActionPreference = "Stop"

$ContainerName = "finally"
$ImageName = "finally"

Write-Host "Building FinAlly..."
docker build -t $ImageName .

Write-Host "Stopping any existing container..."
docker rm -f $ContainerName 2>$null

Write-Host "Starting FinAlly..."
docker run -d `
  --name $ContainerName `
  -p 8000:8000 `
  -v finally-data:/app/db `
  --env-file .env `
  $ImageName

Write-Host ""
Write-Host "FinAlly is running at http://localhost:8000"

Start-Sleep -Seconds 2
Start-Process "http://localhost:8000"
