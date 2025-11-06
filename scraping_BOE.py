"""scraping_boe.py

Aplicación Flask para Web Scraping del BOE (Boletín Oficial del Estado)
con sistema de usuarios (registrarse / iniciar sesión) y notificación por email de
nuevas oposiciones detectadas.
"""

import os
import re
import sqlite3
from datetime import datetime, timedelta

import requests
from flask import (
    Flask, request, g, redirect, url_for, render_template, session, flash, jsonify
)
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message

DB_PATH = os.getenv('DB_PATH', 'oposiciones.db')
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'cambia-esto-en-produccion')

# === Configuración de Flask-Mail (desde variables de entorno) ===
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'localhost')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '25'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', '0') == '1'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', '0') == '1'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME'))

mail = Mail(app)

# --------------------
# filtros Jinja2
# --------------------

@app.template_filter('format_date')
def format_date_filter(date_str):
    """Convierte YYYYMMDD a DD/MM/YYYY si corresponde."""
    if not date_str or len(date_str) != 8 or not date_str.isdigit():
        return date_str
    try:
        year = date_str[0:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{day}/{month}/{year}"
    except Exception:
        return date_str
    
from datetime import datetime, date

# Filtro Jinja: marca como recientes las oposiciones de los últimos x días
@app.template_filter('es_reciente')
def es_reciente(fecha_str, dias=0):
    """
    Devuelve True si la fecha de la oposición está dentro de los últimos `dias`.
    Usa formato 'YYYYMMDD' del BOE.
    """
    try:
        f = datetime.strptime(fecha_str, "%Y%m%d").date()
        return (date.today() - f).days <= dias
    except Exception:
        return False


# --------------------
# Helpers DB
# --------------------

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """Crea las tablas necesarias (idempotente).
    Incluye la columna 'provincia' desde el inicio.
    """
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS oposiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador TEXT,
            control TEXT,
            titulo TEXT,
            url_html TEXT UNIQUE,
            url_pdf TEXT,
            departamento TEXT,
            fecha TEXT,
            provincia TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS user_departamentos (
            user_id INTEGER NOT NULL,
            departamento TEXT NOT NULL,
            PRIMARY KEY (user_id, departamento),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS oposiciones_vistas (
            user_id INTEGER NOT NULL,
            oposicion_id INTEGER NOT NULL,
            fecha_vista TEXT NOT NULL,
            PRIMARY KEY (user_id, oposicion_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (oposicion_id) REFERENCES oposiciones(id) ON DELETE CASCADE
        )
    """)
    db.commit()

# --------------------
# Helpers Auth
# --------------------

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    row = db.execute("SELECT id, email FROM users WHERE id = ?", (uid,)).fetchone()
    return row


def login_required(fn):
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Inicia sesión para continuar.", "warning")
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def create_user(email, password):
    db = get_db()
    db.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email.lower(), generate_password_hash(password), datetime.utcnow().isoformat())
    )
    db.commit()


def find_user_by_email(email):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()

# --------------------
# Helpers Departamentos Usuario
# --------------------

def get_user_departamentos(user_id):
    """Obtiene la lista de departamentos seleccionados por el usuario."""
    db = get_db()
    rows = db.execute(
        "SELECT departamento FROM user_departamentos WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    return [row['departamento'] for row in rows]


def set_user_departamentos(user_id, departamentos):
    """Establece los departamentos seleccionados por el usuario.
    
    Args:
        user_id: ID del usuario
        departamentos: Lista de nombres de departamentos
    """
    db = get_db()
    # Eliminar selecciones anteriores
    db.execute("DELETE FROM user_departamentos WHERE user_id = ?", (user_id,))
    # Insertar nuevas selecciones
    for dep in departamentos:
        if dep:
            db.execute(
                "INSERT INTO user_departamentos (user_id, departamento) VALUES (?, ?)",
                (user_id, dep)
            )
    db.commit()


def get_all_departamentos():
    """Obtiene todos los departamentos únicos disponibles en la base de datos."""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL ORDER BY departamento"
    ).fetchall()
    return [row['departamento'] for row in rows]

# --------------------
# Helpers Oposiciones Vistas
# --------------------

def marcar_oposicion_vista(user_id, oposicion_id):
    """Marca una oposición como vista por el usuario."""
    db = get_db()
    try:
        db.execute(
            "INSERT OR REPLACE INTO oposiciones_vistas (user_id, oposicion_id, fecha_vista) VALUES (?, ?, ?)",
            (user_id, oposicion_id, datetime.utcnow().isoformat())
        )
        db.commit()
    except sqlite3.IntegrityError:
        # Ya existe, actualizar fecha
        db.execute(
            "UPDATE oposiciones_vistas SET fecha_vista = ? WHERE user_id = ? AND oposicion_id = ?",
            (datetime.utcnow().isoformat(), user_id, oposicion_id)
        )
        db.commit()


def get_oposiciones_vistas(user_id):
    """Obtiene el conjunto de IDs de oposiciones vistas por el usuario."""
    db = get_db()
    rows = db.execute(
        "SELECT oposicion_id FROM oposiciones_vistas WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    return {row['oposicion_id'] for row in rows}


def es_oposicion_vista(user_id, oposicion_id):
    """Verifica si una oposición ha sido vista por el usuario."""
    if not user_id:
        return False
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM oposiciones_vistas WHERE user_id = ? AND oposicion_id = ?",
        (user_id, oposicion_id)
    ).fetchone()
    return row is not None

def calcular_dias_habiles(num_dias=20):
    """
    Calcula las fechas de los últimos N días hábiles (excluyendo sábados y domingos).
    
    Args:
        num_dias: Número de días hábiles a calcular (por defecto 20)
    
    Returns:
        tuple: (fecha_desde, fecha_hasta) en formato YYYYMMDD
    """
    hoy = datetime.today().date()
    fecha_hasta = hoy.strftime('%Y%m%d')
    
    # Empezar desde hoy (o último viernes si es fin de semana)
    fecha_actual = hoy
    dias_habiles_encontrados = 0
    fecha_desde = None
    
    # Si hoy es fin de semana, no contar hoy y empezar desde el último viernes
    if fecha_actual.weekday() >= 5:  # 5=sábado, 6=domingo
        dias_retroceder = fecha_actual.weekday() - 4  # 1 si sábado, 2 si domingo
        fecha_actual -= timedelta(days=dias_retroceder)
    
    # Contar días hábiles retrocediendo hasta tener los N días
    while dias_habiles_encontrados < num_dias:
        # Verificar si es día hábil (lunes=0, domingo=6)
        if fecha_actual.weekday() < 5:  # 0-4 = lunes a viernes
            dias_habiles_encontrados += 1
            fecha_desde = fecha_actual  # Guardar el día más antiguo encontrado
            if dias_habiles_encontrados == num_dias:
                break
        fecha_actual -= timedelta(days=1)
        
        if (hoy - fecha_actual).days > 365:
            break
    
    if fecha_desde is None:
        fecha_desde = fecha_actual
    
    fecha_desde_str = fecha_desde.strftime('%Y%m%d')
    return fecha_desde_str, fecha_hasta

# --------------------
# Extraer provincia
# --------------------

def extraer_provincia(texto):
    """Intenta extraer la provincia de un texto con patrones comunes.
    Retorna el nombre de la provincia en mayúsculas o None.
    La heurística busca palabras en mayúscula con longitud razonable
    o coincidencias con una lista corta de provincias comunes.
    """
    if not texto:
        return None
    texto = re.sub(r"\s+", " ", texto).strip()

    # Lista abreviada y simple de provincias 
    provincias = [
        'Madrid', 'Barcelona', 'Valencia', 'Sevilla', 'Zaragoza', 'Málaga', 'Murcia',
        'Alicante', 'Córdoba', 'Granada', 'Burgos', 'Palencia', 'A Coruña', 'Cantabria',
    ]
    for p in provincias:
        if re.search(rf"\b{re.escape(p)}\b", texto, re.IGNORECASE):
            return p

    # Buscar palabra en mayúsculas (ej: 'SEVILLA') de longitud entre 4 y 15
    caps = re.findall(r"\b[A-ZÑ]{4,15}\b", texto)
    if caps:
        # Devolver la primera que parezca razonable
        return caps[0].capitalize()

    return None

# --------------------
# Email (Notificación)
# --------------------

def send_new_oposiciones_email(recipients, oposiciones):
    """Envía email HTML con la lista de nuevas oposiciones.
    """
    if not recipients or not oposiciones:
        return

    filas = []
    for o in oposiciones:
        titulo = o.get('titulo') or '(Sin título)'
        fecha = o.get('fecha') or ''
        url_html = o.get('url_html') or '#'
        url_pdf = o.get('url_pdf')
        dept = o.get('departamento') or ''
        pdf_html = f' | <a href="{url_pdf}">PDF</a>' if url_pdf else ''
        dept_html = f' — {dept}' if dept else ''
        filas.append(
            f'<li><strong>{titulo}</strong> — {fecha} — <a href="{url_html}">HTML</a>{pdf_html}{dept_html}</li>'
        )

    lista_html = ''.join(filas)
    html = (
        '<h3>Nuevas oposiciones publicadas</h3>'
        f'<p>Se han detectado {len(oposiciones)} nuevas oposiciones:</p>'
        f'<ul>{lista_html}</ul>'
        '<p style="font-size:12px;color:#666">Este es un mensaje automático, por favor no responda.</p>'
    )

    subject = f"{len(oposiciones)} nuevas oposiciones publicadas"
    msg = Message(subject=subject, recipients=recipients, html=html)
    mail.send(msg)


def all_user_emails():
    db = get_db()
    return [r['email'] for r in db.execute("SELECT email FROM users").fetchall()]

# --------------------
# Scraper BOE
# --------------------

def scrape_boe():
    """Busca en la API de datos abiertos del BOE y guarda nuevas oposiciones.

    Retorna:
        list[dict]: lista de oposiciones NUEVAS insertadas (cada item es un dict)
    """
    init_db()
    db = get_db()

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; scraping_boe/1.0)',
        'Accept': 'application/xml, text/xml, */*; q=0.01',
    }

    fecha = datetime.today()
    r = None
    hoy = None
    for _ in range(7):
        hoy = fecha.strftime('%Y%m%d')
        boe_url = f'https://www.boe.es/datosabiertos/api/boe/sumario/{hoy}'
        try:
            r = requests.get(boe_url, headers=headers, timeout=10)
            if r.status_code == 200 and r.content:
                break
        except requests.RequestException:
            pass
        fecha -= timedelta(days=1)
    else:
        return []

    # Intentar parsear XML
    try:
        soup = BeautifulSoup(r.content, 'lxml-xml')
    except Exception:
        soup = BeautifulSoup(r.content, 'xml')

    seccion = soup.find('seccion', {'codigo': '2B'})
    if not seccion:
        return []

    items = seccion.find_all('item')
    newly_inserted = []

    for item in items:
        identificador_tag = item.find('identificador')
        control_tag = item.find('control')
        titulo_tag = item.find('titulo')
        url_html_tag = item.find('url_html')
        url_pdf_tag = item.find('url_pdf')

        identificador = identificador_tag.text.strip() if identificador_tag else None
        control = control_tag.text.strip() if control_tag else None
        titulo = titulo_tag.text.strip() if titulo_tag else None
        url_html = url_html_tag.text.strip() if url_html_tag else None
        url_pdf = url_pdf_tag.text.strip() if url_pdf_tag else None

        dept_parent = item.find_parent('departamento')
        departamento = dept_parent.get('nombre') if dept_parent and dept_parent.has_attr('nombre') else None

        provincia = extraer_provincia(titulo) or extraer_provincia(control)

        try:
            db.execute('''
                INSERT INTO oposiciones (identificador, control, titulo, url_html, url_pdf, departamento, fecha, provincia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (identificador, control, titulo, url_html, url_pdf, departamento, hoy, provincia))
            db.commit()

            newly_inserted.append({
                'identificador': identificador,
                'control': control,
                'titulo': titulo,
                'url_html': url_html,
                'url_pdf': url_pdf,
                'departamento': departamento,
                'fecha': hoy,
                'provincia': provincia,
            })
        except sqlite3.IntegrityError:
            # duplicado por url_html (UNIQUE), ignorar
            continue

    return newly_inserted

# --------------------
# Rutas Flask
# --------------------

@app.route('/')
def index():
    init_db()
    db = get_db()

    user = current_user()
    
    # Si el usuario está logueado y tiene departamentos seleccionados, filtrar por últimos 20 días hábiles
    if user:
        user_deps = get_user_departamentos(user['id'])
        if user_deps:
            # Calcular últimos 20 días hábiles
            fecha_desde, fecha_hasta = calcular_dias_habiles(20)
            
            # Filtrar solo departamentos seleccionados por el usuario en los últimos 20 días hábiles
            placeholders = ','.join(['?'] * len(user_deps))
            query = f'''
                SELECT DISTINCT departamento FROM oposiciones 
                WHERE departamento IS NOT NULL 
                AND fecha >= ? 
                AND fecha <= ?
                AND departamento IN ({placeholders})
                ORDER BY departamento
            '''
            deps = db.execute(query, [fecha_desde, fecha_hasta] + user_deps).fetchall()
        else:
            # Usuario sin departamentos seleccionados, mostrar solo de hoy
            hoy = datetime.today().strftime('%Y%m%d')
            deps = db.execute(
                'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL AND fecha = ? ORDER BY departamento',
                (hoy,)
            ).fetchall()
    else:
        # Usuario no logueado, mostrar solo de hoy
        hoy = datetime.today().strftime('%Y%m%d')
        deps = db.execute(
            'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL AND fecha = ? ORDER BY departamento',
            (hoy,)
        ).fetchall()

    return render_template('index.html', departamentos=deps, user=user)



@app.route("/departamento/<nombre>")
def mostrar_departamento(nombre):
    db = get_db()
    user = current_user()

    # 🔹 Fecha actual para marcar las oposiciones nuevas
    hoy = datetime.today().strftime("%Y%m%d")

    busqueda = request.args.get("busqueda", "")
    provincia = request.args.get("provincia", "")
    fecha_desde = request.args.get("fecha_desde", "")
    fecha_hasta = request.args.get("fecha_hasta", "")
    page = int(request.args.get("page", 1))
    por_pagina = 10
    offset = (page - 1) * por_pagina

    sql = "SELECT * FROM oposiciones WHERE departamento = ?"
    params = [nombre]

    if busqueda:
        like = f"%{busqueda}%"
        sql += " AND (titulo LIKE ? OR identificador LIKE ? OR control LIKE ?)"
        params += [like, like, like]

    if fecha_desde:
        sql += " AND fecha >= ?"
        params.append(fecha_desde.replace("-", ""))

    if fecha_hasta:
        sql += " AND fecha <= ?"
        params.append(fecha_hasta.replace("-", ""))

    sql += " ORDER BY fecha DESC LIMIT ? OFFSET ?"
    params += [por_pagina, offset]

    rows = db.execute(sql, params).fetchall()

    # Obtener oposiciones vistas por el usuario
    oposiciones_vistas = set()
    if user:
        oposiciones_vistas = get_oposiciones_vistas(user['id'])

    total = db.execute(
        "SELECT COUNT(*) FROM oposiciones WHERE departamento = ?", (nombre,)
    ).fetchone()[0]
    total_pages = (total + por_pagina - 1) // por_pagina

    provincias = db.execute(
        "SELECT DISTINCT provincia FROM oposiciones WHERE provincia IS NOT NULL ORDER BY provincia"
    ).fetchall()

    return render_template(
        "tarjeta.html",
        departamento=nombre,
        rows=rows,
        page=page,
        total_pages=total_pages,
        provincias=provincias,
        busqueda=busqueda,
        provincia_filtro=provincia,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        hoy=hoy,
        user=user,
        oposiciones_vistas=oposiciones_vistas
    )




@app.route('/scrape')
def do_scrape():
    init_db()
    try:
        new_items = scrape_boe()
        if new_items:
            recipients = all_user_emails()
            try:
                if recipients:
                    send_new_oposiciones_email(recipients, new_items)
                flash(f"Se han insertado {len(new_items)} nuevas oposiciones.", "success")
            except Exception as e:
                flash(f"Se insertaron {len(new_items)} nuevas oposiciones, pero falló el envío de email: {e}", "warning")
        else:
            flash("No hay nuevas oposiciones hoy.", "info")
    except Exception as e:
        flash(f"Error al hacer scraping: {e}", "danger")
    return redirect(url_for('index'))


# --- Registro / Login ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    init_db()
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        if not email or not password:
            flash("Email y contraseña son obligatorios.", "danger")
            return render_template('register.html', user=current_user())
        if find_user_by_email(email):
            flash("Ese email ya está registrado.", "warning")
            return render_template('register.html', user=current_user())
        create_user(email, password)
        user = find_user_by_email(email)
        session['user_id'] = user['id']
        flash("Registro correcto. Sesion iniciada.", "success")
        return redirect(url_for('index'))
    return render_template('register.html', user=current_user())


@app.route('/login', methods=['GET', 'POST'])
def login():
    init_db()
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        user = find_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            flash("Credenciales inválidas.", "danger")
            return render_template('login.html', user=current_user())
        session['user_id'] = user['id']
        flash("Sesión iniciada.", "success")
        next_url = request.args.get('next') or url_for('index')
        return redirect(next_url)
    return render_template('login.html', user=current_user())


@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    flash("Sesión cerrada.", "info")
    return redirect(url_for('index'))


@app.route('/preferencias', methods=['GET', 'POST'])
@login_required
def preferencias():
    """Página para que el usuario seleccione sus departamentos favoritos."""
    user = current_user()
    
    if request.method == 'POST':
        # Obtener departamentos seleccionados del formulario
        departamentos_seleccionados = request.form.getlist('departamento')
        set_user_departamentos(user['id'], departamentos_seleccionados)
        flash(f"Se han guardado {len(departamentos_seleccionados)} departamentos seleccionados.", "success")
        return redirect(url_for('index'))
    
    # GET: mostrar formulario con checklist
    todos_departamentos = get_all_departamentos()
    departamentos_usuario = set(get_user_departamentos(user['id']))
    
    return render_template(
        'preferencias.html',
        user=user,
        todos_departamentos=todos_departamentos,
        departamentos_usuario=departamentos_usuario
    )


@app.route('/marcar_vista/<int:oposicion_id>', methods=['POST'])
@login_required
def marcar_vista(oposicion_id):
    """Marca una oposición como vista por el usuario actual."""
    user = current_user()
    if user:
        marcar_oposicion_vista(user['id'], oposicion_id)
        return jsonify({'status': 'ok'}), 200
    return jsonify({'status': 'error', 'message': 'Usuario no autenticado'}), 401


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
