$root = $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\api'; .\run.ps1" -WindowStyle Normal
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\web'; if (-not (Test-Path node_modules)) { npm install }; npm run dev" -WindowStyle Normal
Start-Sleep -Seconds 8
Start-Process "http://localhost:3000"
