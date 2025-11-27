# Script PowerShell para ejecutar el bot de Telegram en segundo plano
# Ejecutar: .\start_telegram_bot.ps1

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

Write-Host "🤖 Iniciando Bot de Telegram en segundo plano..." -ForegroundColor Green

# Activar entorno virtual y ejecutar bot
$process = Start-Process -FilePath ".\venv_new\Scripts\python.exe" `
    -ArgumentList "telegram_bot.py" `
    -WindowStyle Hidden `
    -PassThru

Write-Host "✅ Bot iniciado con PID: $($process.Id)" -ForegroundColor Green
Write-Host "📝 Para detener el bot, ejecuta: Stop-Process -Id $($process.Id)" -ForegroundColor Yellow

# Guardar PID en archivo para poder detenerlo después
$process.Id | Out-File -FilePath "telegram_bot.pid" -Encoding utf8

Write-Host "💡 Para detener el bot más tarde, ejecuta: .\stop_telegram_bot.ps1" -ForegroundColor Cyan
