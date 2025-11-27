"""
Bot de Telegram para notificar nuevas oposiciones del BOE
Funcionalidades:
- /start - Inicia el bot y muestra comandos
- /nuevas - Muestra las oposiciones del día de hoy
- /departamento <nombre> - Muestra oposiciones de un departamento específico
- /buscar <texto> - Busca oposiciones por texto
- /suscribir - Activa notificaciones automáticas
- /desuscribir - Desactiva notificaciones
"""

import os
import sqlite3
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    logger.error("❌ ERROR: No se encontró TELEGRAM_BOT_TOKEN")
    logger.error("Por favor configura la variable de entorno o edita el archivo .env")
    exit(1)

DB_PATH = "oposiciones.db"
USERS_DB_PATH = "usuarios.db"


def get_boe_db():
    """Conecta a la base de datos de oposiciones"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_users_db():
    """Conecta a la base de datos de usuarios"""
    conn = sqlite3.connect(USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_telegram_db():
    """Inicializa tabla para suscriptores del bot de Telegram"""
    db = get_users_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS telegram_suscriptores (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            fecha_suscripcion TEXT,
            activo INTEGER DEFAULT 1,
            departamentos TEXT
        )
    """)
    db.commit()
    db.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start - Bienvenida y comandos disponibles"""
    mensaje = """
🎓 *Bot de Oposiciones BOE*

¡Bienvenido! Este bot te mantiene informado sobre las nuevas oposiciones publicadas en el BOE.

*Comandos disponibles:*
/nuevas - Ver oposiciones de hoy
/departamentos - Listar departamentos disponibles
/buscar <texto> - Buscar oposiciones
/suscribir - Activar notificaciones diarias
/desuscribir - Desactivar notificaciones
/ayuda - Mostrar esta ayuda

_Datos actualizados del Boletín Oficial del Estado_
    """
    await update.message.reply_text(mensaje, parse_mode='Markdown')


async def nuevas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /nuevas - Muestra oposiciones del día"""
    db = get_boe_db()
    hoy = datetime.today().strftime("%Y%m%d")
    
    oposiciones = db.execute(
        "SELECT * FROM oposiciones WHERE fecha = ? ORDER BY departamento LIMIT 50",
        (hoy,)
    ).fetchall()
    
    db.close()
    
    if not oposiciones:
        await update.message.reply_text(
            "❌ No hay nuevas oposiciones publicadas hoy.",
            parse_mode='Markdown'
        )
        return
    
    # Agrupar por departamento
    departamentos = {}
    for op in oposiciones:
        dept = op['departamento']
        if dept not in departamentos:
            departamentos[dept] = []
        departamentos[dept].append(op)
    
    mensaje = f"📢 *Nuevas Oposiciones - {datetime.today().strftime('%d/%m/%Y')}*\n\n"
    
    for dept, ops in list(departamentos.items())[:10]:  # Límite de 10 departamentos
        mensaje += f"🏛️ *{dept}* ({len(ops)} oposiciones)\n"
        for op in ops[:3]:  # Max 3 por departamento
            titulo = op['titulo'][:100] + "..." if len(op['titulo']) > 100 else op['titulo']
            mensaje += f"  • {titulo}\n"
        if len(ops) > 3:
            mensaje += f"  _... y {len(ops) - 3} más_\n"
        mensaje += "\n"
    
    # Botones para ver más
    keyboard = [
        [InlineKeyboardButton("🔍 Ver por Departamento", callback_data="ver_departamentos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(mensaje, parse_mode='Markdown', reply_markup=reply_markup)


async def departamentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /departamentos - Lista todos los departamentos"""
    db = get_boe_db()
    hoy = datetime.today().strftime("%Y%m%d")
    
    deps = db.execute(
        """SELECT departamento, COUNT(*) as total 
           FROM oposiciones 
           WHERE fecha = ? AND departamento IS NOT NULL
           GROUP BY departamento 
           ORDER BY total DESC""",
        (hoy,)
    ).fetchall()
    
    db.close()
    
    if not deps:
        await update.message.reply_text("❌ No hay departamentos con oposiciones hoy.")
        return
    
    mensaje = "🏛️ *Departamentos con Oposiciones Hoy*\n\n"
    
    # Crear botones inline para cada departamento
    keyboard = []
    for i, dep in enumerate(deps[:20], 1):  # Máximo 20 departamentos
        nombre = dep['departamento']
        total = dep['total']
        # Acortar nombre si es muy largo
        nombre_corto = nombre[:30] + "..." if len(nombre) > 30 else nombre
        keyboard.append([InlineKeyboardButton(
            f"{nombre_corto} ({total})",
            callback_data=f"dept_{nombre}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    mensaje += f"_Toca un departamento para ver sus oposiciones_\n"
    mensaje += f"Total: {len(deps)} departamentos"
    
    await update.message.reply_text(mensaje, parse_mode='Markdown', reply_markup=reply_markup)


async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /buscar <texto> - Busca oposiciones"""
    if not context.args:
        await update.message.reply_text(
            "❌ Debes especificar qué buscar.\nEjemplo: `/buscar maestro`",
            parse_mode='Markdown'
        )
        return
    
    busqueda = " ".join(context.args)
    db = get_boe_db()
    desde = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")
    
    like = f"%{busqueda}%"
    oposiciones = db.execute(
        """SELECT * FROM oposiciones 
           WHERE fecha >= ? 
           AND (titulo LIKE ? OR identificador LIKE ? OR departamento LIKE ?)
           ORDER BY fecha DESC
           LIMIT 20""",
        (desde, like, like, like)
    ).fetchall()
    
    db.close()
    
    if not oposiciones:
        await update.message.reply_text(
            f"❌ No se encontraron oposiciones con: *{busqueda}*",
            parse_mode='Markdown'
        )
        return
    
    mensaje = f"🔍 *Resultados para:* {busqueda}\n"
    mensaje += f"_Se encontraron {len(oposiciones)} oposiciones_\n\n"
    
    for op in oposiciones[:10]:
        titulo = op['titulo'][:80] + "..." if len(op['titulo']) > 80 else op['titulo']
        fecha = datetime.strptime(op['fecha'], "%Y%m%d").strftime("%d/%m/%Y")
        dept = op['departamento'][:40] if op['departamento'] else "Sin departamento"
        
        mensaje += f"📄 *{titulo}*\n"
        mensaje += f"   🏛️ {dept}\n"
        mensaje += f"   📅 {fecha}\n"
        if op['url_html']:
            mensaje += f"   🔗 [Ver en BOE]({op['url_html']})\n"
        mensaje += "\n"
    
    if len(oposiciones) > 10:
        mensaje += f"_... y {len(oposiciones) - 10} más. Refina tu búsqueda._"
    
    await update.message.reply_text(mensaje, parse_mode='Markdown', disable_web_page_preview=True)


async def suscribir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /suscribir - Activa notificaciones diarias"""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "Anónimo"
    
    db = get_users_db()
    
    # Verificar si ya está suscrito
    existe = db.execute(
        "SELECT * FROM telegram_suscriptores WHERE chat_id = ?",
        (chat_id,)
    ).fetchone()
    
    if existe:
        db.execute(
            "UPDATE telegram_suscriptores SET activo = 1 WHERE chat_id = ?",
            (chat_id,)
        )
        mensaje = "✅ ¡Suscripción reactivada!\n\nRecibirás notificaciones diarias de nuevas oposiciones."
    else:
        db.execute(
            """INSERT INTO telegram_suscriptores (chat_id, username, fecha_suscripcion, activo)
               VALUES (?, ?, ?, 1)""",
            (chat_id, username, datetime.now().isoformat())
        )
        mensaje = "✅ ¡Suscripción exitosa!\n\nRecibirás notificaciones diarias de nuevas oposiciones."
    
    db.commit()
    db.close()
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')


async def desuscribir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /desuscribir - Desactiva notificaciones"""
    chat_id = update.effective_chat.id
    
    db = get_users_db()
    db.execute(
        "UPDATE telegram_suscriptores SET activo = 0 WHERE chat_id = ?",
        (chat_id,)
    )
    db.commit()
    db.close()
    
    mensaje = "❌ Suscripción desactivada.\n\nYa no recibirás notificaciones automáticas.\n\n"
    mensaje += "Puedes reactivarla en cualquier momento con /suscribir"
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los callbacks de botones inline"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "ver_departamentos":
        db = get_boe_db()
        hoy = datetime.today().strftime("%Y%m%d")
        
        deps = db.execute(
            """SELECT departamento, COUNT(*) as total 
               FROM oposiciones 
               WHERE fecha = ? AND departamento IS NOT NULL
               GROUP BY departamento 
               ORDER BY total DESC
               LIMIT 10""",
            (hoy,)
        ).fetchall()
        
        db.close()
        
        mensaje = "🏛️ *Top Departamentos Hoy*\n\n"
        for dep in deps:
            mensaje += f"• {dep['departamento']}: *{dep['total']}* oposiciones\n"
        
        await query.edit_message_text(mensaje, parse_mode='Markdown')
    
    elif data.startswith("dept_"):
        departamento = data[5:]  # Quitar "dept_"
        db = get_boe_db()
        hoy = datetime.today().strftime("%Y%m%d")
        
        oposiciones = db.execute(
            "SELECT * FROM oposiciones WHERE fecha = ? AND departamento = ? LIMIT 10",
            (hoy, departamento)
        ).fetchall()
        
        db.close()
        
        if not oposiciones:
            await query.edit_message_text(f"❌ No hay oposiciones para {departamento}")
            return
        
        mensaje = f"🏛️ *{departamento}*\n"
        mensaje += f"_Oposiciones del día: {len(oposiciones)}_\n\n"
        
        for op in oposiciones:
            titulo = op['titulo'][:100] + "..." if len(op['titulo']) > 100 else op['titulo']
            mensaje += f"📄 {titulo}\n"
            if op['url_html']:
                mensaje += f"   🔗 [Ver en BOE]({op['url_html']})\n"
            mensaje += "\n"
        
        await query.edit_message_text(mensaje, parse_mode='Markdown', disable_web_page_preview=True)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ayuda - Muestra ayuda"""
    await start(update, context)


async def enviar_resumen_diario(context: ContextTypes.DEFAULT_TYPE):
    """Envía resumen diario a todos los suscriptores activos"""
    db_users = get_users_db()
    suscriptores = db_users.execute(
        "SELECT chat_id FROM telegram_suscriptores WHERE activo = 1"
    ).fetchall()
    db_users.close()
    
    if not suscriptores:
        logger.info("No hay suscriptores activos")
        return
    
    # Obtener oposiciones del día
    db_boe = get_boe_db()
    hoy = datetime.today().strftime("%Y%m%d")
    
    oposiciones = db_boe.execute(
        "SELECT COUNT(*) as total FROM oposiciones WHERE fecha = ?",
        (hoy,)
    ).fetchone()
    
    departamentos = db_boe.execute(
        """SELECT departamento, COUNT(*) as total 
           FROM oposiciones 
           WHERE fecha = ? AND departamento IS NOT NULL
           GROUP BY departamento 
           ORDER BY total DESC
           LIMIT 5""",
        (hoy,)
    ).fetchall()
    
    db_boe.close()
    
    total = oposiciones['total']
    
    if total == 0:
        logger.info("No hay oposiciones nuevas hoy")
        return
    
    mensaje = f"🔔 *Resumen Diario - {datetime.today().strftime('%d/%m/%Y')}*\n\n"
    mensaje += f"📊 Total de oposiciones publicadas: *{total}*\n\n"
    mensaje += "🏛️ *Top Departamentos:*\n"
    
    for dep in departamentos:
        mensaje += f"• {dep['departamento']}: {dep['total']}\n"
    
    mensaje += "\n_Usa /nuevas para ver todas las oposiciones_"
    
    # Enviar a todos los suscriptores
    for suscriptor in suscriptores:
        try:
            await context.bot.send_message(
                chat_id=suscriptor['chat_id'],
                text=mensaje,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error enviando mensaje a {suscriptor['chat_id']}: {e}")


def main():
    """Función principal del bot"""
    # Inicializar base de datos
    init_telegram_db()
    
    # Crear aplicación
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Registrar comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("nuevas", nuevas))
    application.add_handler(CommandHandler("departamentos", departamentos))
    application.add_handler(CommandHandler("buscar", buscar))
    application.add_handler(CommandHandler("suscribir", suscribir))
    application.add_handler(CommandHandler("desuscribir", desuscribir))
    application.add_handler(CommandHandler("ayuda", ayuda))
    
    # Registrar callback de botones
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Programar envío diario a las 9:00 AM
    # application.job_queue.run_daily(
    #     enviar_resumen_diario,
    #     time=datetime.strptime("09:00", "%H:%M").time(),
    #     days=(0, 1, 2, 3, 4, 5, 6)  # Todos los días
    # )
    
    logger.info("Bot iniciado correctamente")
    print("🤖 Bot de Telegram en funcionamiento...")
    print("Presiona Ctrl+C para detener")
    
    # Iniciar bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
