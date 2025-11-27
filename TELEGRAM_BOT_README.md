# 🤖 Bot de Telegram para Oposiciones BOE

Bot de Telegram que notifica sobre nuevas oposiciones publicadas en el BOE.

## 📋 Funcionalidades

### Comandos Disponibles

- `/start` - Inicia el bot y muestra la lista de comandos
- `/nuevas` - Muestra las oposiciones publicadas hoy
- `/departamentos` - Lista todos los departamentos con oposiciones
- `/buscar <texto>` - Busca oposiciones por palabra clave
- `/suscribir` - Activa notificaciones diarias automáticas
- `/desuscribir` - Desactiva las notificaciones
- `/ayuda` - Muestra la ayuda

### Características

✅ Listado de oposiciones del día agrupadas por departamento  
✅ Búsqueda por texto en títulos y departamentos  
✅ Botones interactivos para navegar por departamentos  
✅ Enlaces directos al BOE  
✅ Sistema de suscripciones con notificaciones diarias  
✅ Base de datos SQLite para gestionar suscriptores  

## 🚀 Instalación

### 1. Instalar dependencias

```bash
pip install python-telegram-bot
```

O actualizar el `requirements.txt`:

```bash
echo "python-telegram-bot==20.7" >> requirements.txt
pip install -r requirements.txt
```

### 2. Crear Bot en Telegram

1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot`
3. Sigue las instrucciones:
   - Nombre del bot: `Oposiciones BOE Bot`
   - Username: `oposiciones_boe_bot` (debe terminar en `bot`)
4. Guarda el **TOKEN** que te proporciona

### 3. Configurar Variables de Entorno

Crea un archivo `.env` (o añade al existente):

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 4. Inicializar Base de Datos

El bot creará automáticamente la tabla `telegram_suscriptores` en `usuarios.db`.

## 🎯 Uso

### Ejecutar el Bot

```bash
python telegram_bot.py
```

O en Windows PowerShell:

```powershell
& .\venv_new\Scripts\python.exe telegram_bot.py
```

### Usar el Bot

1. Abre Telegram y busca tu bot por su username
2. Envía `/start` para comenzar
3. Usa los comandos disponibles

## 📊 Ejemplos de Uso

### Ver Oposiciones de Hoy
```
/nuevas
```

### Buscar Oposiciones
```
/buscar maestro
/buscar administrativo
/buscar enfermero
```

### Activar Notificaciones Diarias
```
/suscribir
```

## 🔧 Configuración Avanzada

### Cambiar Hora de Notificaciones

En `telegram_bot.py`, modifica esta línea:

```python
application.job_queue.run_daily(
    enviar_resumen_diario,
    time=datetime.strptime("09:00", "%H:%M").time(),  # Cambia "09:00"
    days=(0, 1, 2, 3, 4, 5, 6)
)
```

### Personalizar Límites

```python
# Número máximo de oposiciones a mostrar
LIMIT_OPOSICIONES = 50

# Departamentos en resumen
LIMIT_DEPARTAMENTOS = 10

# Resultados de búsqueda
LIMIT_BUSQUEDA = 20
```

## 📁 Estructura de Base de Datos

El bot crea la tabla `telegram_suscriptores`:

```sql
CREATE TABLE telegram_suscriptores (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    fecha_suscripcion TEXT,
    activo INTEGER DEFAULT 1,
    departamentos TEXT
);
```

## 🔐 Seguridad

⚠️ **IMPORTANTE:**
- Nunca compartas tu TOKEN del bot
- Añade `.env` al `.gitignore`
- No subas el token a repositorios públicos

## 🐛 Troubleshooting

### Error: "Invalid token"
- Verifica que el token en `.env` sea correcto
- Asegúrate de usar el formato: `TELEGRAM_BOT_TOKEN=tu_token`

### Error: "No module named 'telegram'"
```bash
pip install python-telegram-bot
```

### El bot no responde
- Verifica que el bot esté ejecutándose
- Comprueba los logs en la consola
- Reinicia el bot con Ctrl+C y vuelve a ejecutar

### Base de datos bloqueada
- Cierra otras conexiones a `usuarios.db`
- Reinicia el bot

## 🚀 Despliegue en Producción

### Opción 1: Servidor Linux con systemd

Crear `/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=Bot Telegram Oposiciones BOE
After=network.target

[Service]
Type=simple
User=tu_usuario
WorkingDirectory=/ruta/al/proyecto
Environment="TELEGRAM_BOT_TOKEN=tu_token"
ExecStart=/ruta/al/proyecto/venv_new/bin/python telegram_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Activar:
```bash
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
sudo systemctl status telegram-bot
```

### Opción 2: Docker

Crear `Dockerfile.telegram`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY telegram_bot.py .
COPY oposiciones.db .
COPY usuarios.db .

CMD ["python", "telegram_bot.py"]
```

Ejecutar:
```bash
docker build -f Dockerfile.telegram -t telegram-bot .
docker run -d --name telegram-bot -e TELEGRAM_BOT_TOKEN=tu_token telegram-bot
```

### Opción 3: Heroku / Railway / Render

1. Añade `Procfile`:
```
bot: python telegram_bot.py
```

2. Configura la variable de entorno `TELEGRAM_BOT_TOKEN`

3. Despliega

## 📈 Mejoras Futuras

- [ ] Filtros personalizados por departamento
- [ ] Búsqueda por provincia
- [ ] Notificaciones instantáneas (webhook)
- [ ] Estadísticas de uso del bot
- [ ] Exportar oposiciones a PDF
- [ ] Integración con calendario
- [ ] Bot en múltiples idiomas

## 📞 Soporte

Para problemas o sugerencias:
1. Revisa los logs del bot
2. Verifica la configuración
3. Consulta la documentación de [python-telegram-bot](https://docs.python-telegram-bot.org/)

## 📄 Licencia

Mismo que el proyecto principal.
