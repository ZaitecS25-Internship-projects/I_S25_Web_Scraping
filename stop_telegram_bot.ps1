# Script PowerShell para detener el bot de Telegram
# Ejecutar: .\stop_telegram_bot.ps1

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

if (Test-Path "telegram_bot.pid") {
    $pid = Get-Content "telegram_bot.pid"
    
    try {
        Stop-Process -Id $pid -Force
        Write-Host "✅ Bot detenido correctamente (PID: $pid)" -ForegroundColor Green
        Remove-Item "telegram_bot.pid"
    }
    catch {
        Write-Host "❌ No se pudo detener el proceso. Puede que ya esté cerrado." -ForegroundColor Red
        Remove-Item "telegram_bot.pid" -ErrorAction SilentlyContinue
    }
}
else {
    Write-Host "⚠️  No se encontró el archivo PID. El bot puede no estar ejecutándose." -ForegroundColor Yellow
    Write-Host "💡 Detén manualmente con: Get-Process python | Where-Object {$_.Path -like '*telegram_bot*'} | Stop-Process" -ForegroundColor Cyan
}
