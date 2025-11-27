# 🚀 Inicio Automático del Bot de Telegram

## Opción 1: Script PowerShell (Recomendado para Windows)

### Iniciar el bot en segundo plano:
```powershell
.\start_telegram_bot.ps1
```

### Detener el bot:
```powershell
.\stop_telegram_bot.ps1
```

### Verificar si está corriendo:
```powershell
Get-Process python | Where-Object {$_.CommandLine -like "*telegram_bot*"}
```

---

## Opción 2: Inicio Automático con Windows (Tarea Programada)

### Configurar inicio automático al encender el PC:

1. **Crear acceso directo del script:**
   - Click derecho en `start_telegram_bot.bat` → Crear acceso directo
   - Mover el acceso directo a: `C:\Users\TU_USUARIO\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`

2. **O usar el Programador de Tareas:**
   ```powershell
   # Abrir Programador de Tareas
   taskschd.msc
   ```
   - Crear Tarea Básica → Nombre: "Bot Telegram Oposiciones"
   - Desencadenador: "Al iniciar el equipo"
   - Acción: Iniciar programa
   - Programa: `C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping\venv_new\Scripts\python.exe`
   - Argumentos: `telegram_bot.py`
   - Directorio: `C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping`
   - ✅ Marcar "Ejecutar aunque el usuario no haya iniciado sesión"

---

## Opción 3: Servicio de Windows con NSSM

### Instalar NSSM (Non-Sucking Service Manager):

1. **Descargar NSSM:**
   - https://nssm.cc/download
   - Extraer `nssm.exe` a una carpeta en PATH o al proyecto

2. **Instalar como servicio:**
   ```powershell
   # Abrir PowerShell como Administrador
   cd "C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping"
   
   # Instalar servicio
   nssm install TelegramBotOposiciones "C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping\venv_new\Scripts\python.exe" "telegram_bot.py"
   
   # Configurar directorio de trabajo
   nssm set TelegramBotOposiciones AppDirectory "C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping"
   
   # Iniciar servicio
   nssm start TelegramBotOposiciones
   ```

3. **Gestionar el servicio:**
   ```powershell
   # Ver estado
   nssm status TelegramBotOposiciones
   
   # Detener
   nssm stop TelegramBotOposiciones
   
   # Reiniciar
   nssm restart TelegramBotOposiciones
   
   # Desinstalar
   nssm remove TelegramBotOposiciones confirm
   ```

---

## Opción 4: Ejecutar con pythonw (Sin ventana)

Crear archivo `start_bot_hidden.vbs`:

```vbs
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping && venv_new\Scripts\pythonw.exe telegram_bot.py", 0, False
Set WshShell = Nothing
```

Doble click en este archivo para ejecutar el bot sin ventana.

---

## Opción 5: Webhook en Servidor (Producción)

Para un despliegue profesional, usa webhook en lugar de polling:

### Modificar `telegram_bot.py`:

```python
# En lugar de application.run_polling()
application.run_webhook(
    listen="0.0.0.0",
    port=8443,
    url_path="telegram_webhook",
    webhook_url=f"https://tu-dominio.com/telegram_webhook"
)
```

Requiere:
- Servidor con IP pública o dominio
- Certificado SSL (Let's Encrypt)
- Puerto 8443, 443, 80 o 88

---

## Verificar que el bot está corriendo

### PowerShell:
```powershell
# Ver todos los procesos Python
Get-Process python

# Ver solo el bot
Get-Process python | Where-Object {$_.Path -like '*telegram_bot*'}

# Ver logs en tiempo real (si guardas logs)
Get-Content -Path "telegram_bot.log" -Wait -Tail 50
```

### Comando de red:
```powershell
# Ver conexiones activas del bot
netstat -ano | findstr "443"
```

---

## Logs y Monitoreo

### Guardar logs en archivo:

Modificar en `telegram_bot.py`:

```python
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('telegram_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
```

---

## Solución de Problemas

### El bot no inicia:
```powershell
# Verificar token
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('TELEGRAM_BOT_TOKEN'))"

# Verificar dependencias
pip list | findstr telegram
```

### El bot se cierra solo:
- Revisar `telegram_bot.log`
- Verificar que no haya otro proceso usando el mismo token
- Comprobar conexión a internet

### Reiniciar el bot automáticamente si falla:

En el Programador de Tareas:
- Pestaña "Configuración"
- ✅ "Si la tarea falla, reiniciar cada: 1 minuto"
- ✅ "Intentar reiniciar hasta: 3 veces"

---

## Recomendación Final

Para desarrollo: **Usar `start_telegram_bot.ps1`**
Para producción: **Usar NSSM o Tarea Programada de Windows**

El bot estará siempre activo y responderá a `/start` sin necesidad de ejecutar nada manualmente.
