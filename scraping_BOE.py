"""scraping_boe.py

Aplicación Flask para Web Scraping del BOE (Boletín Oficial del Estado)
con sistema de usuarios (sign up / login) y notificación por email de
nuevas oposiciones detectadas.

Autor original: franSM, Cristóbal Delgado Romero
Ampliado con auth + email: 2025
"""

import os
import re
import sqlite3
from datetime import datetime, timedelta

import requests
from flask import (
    Flask, request, g, redirect, url_for, render_template, session, flash
)
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from flask import jsonify

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

# 🟡 Filtro Jinja: marca como recientes las oposiciones de los últimos x días
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
        CREATE TABLE IF NOT EXISTS visitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            oposicion_id INTEGER NOT NULL,
            fecha_visita TEXT NOT NULL,
            UNIQUE(user_id, oposicion_id)
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

    # Lista abreviada y simple de provincias (puede ampliarse)
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
# Registrar oposiciones vistas
# --------------------
# 🆕 Función para registrar una visita
def registrar_visita(user_id, oposicion_id):
    db = get_db()
    fecha = datetime.utcnow().isoformat()
    try:
        db.execute(
            "INSERT OR REPLACE INTO visitas (user_id, oposicion_id, fecha_visita) VALUES (?, ?, ?)",
            (user_id, oposicion_id, fecha)
        )
        db.commit()
    except Exception as e:
        print(f"Error al registrar visita: {e}")


# --------------------
# Rutas Flask
# --------------------

@app.route('/')
def index():
    init_db()
    db = get_db()

    # Fecha de hoy en formato YYYYMMDD
    hoy = datetime.today().strftime('%Y%m%d')

    # Departamentos con oposiciones publicadas hoy
    deps = db.execute(
        'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL AND fecha = ? ORDER BY departamento',
        (hoy,)
    ).fetchall()

    return render_template('index.html', departamentos=deps, user=current_user())



@app.route("/departamento/<nombre>")
def mostrar_departamento(nombre):
    db = get_db()

    # 🔹 Fecha actual para marcar las oposiciones nuevas
    hoy = datetime.today().strftime("%Y%m%d")

    user = current_user()
    user_id = user["id"] if user else None

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

    total = db.execute(
        "SELECT COUNT(*) FROM oposiciones WHERE departamento = ?", (nombre,)
    ).fetchone()[0]
    total_pages = (total + por_pagina - 1) // por_pagina

    provincias = db.execute(
        "SELECT DISTINCT provincia FROM oposiciones WHERE provincia IS NOT NULL ORDER BY provincia"
    ).fetchall()

    # 🔵 Obtener las oposiciones visitadas por el usuario actual
    visitadas = []
    user = current_user()
    if user:
        db.execute("""
            CREATE TABLE IF NOT EXISTS visitas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                oposicion_id INTEGER,
                fecha_visita TEXT,
                UNIQUE(user_id, oposicion_id)
            )
        """)
        db.commit()

        visitadas = [
            row["oposicion_id"]
            for row in db.execute(
                "SELECT oposicion_id FROM visitas WHERE user_id = ?", (user["id"],)
            ).fetchall()
        ]


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
        visitadas=visitadas,
        user=user,  
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


@app.route("/marcar_visitada/<int:oposicion_id>", methods=["POST"])
@login_required
def marcar_visitada(oposicion_id):
    user = current_user()
    print(f"🟢 Registro de visita recibido: user={user['id']}, oposicion_id={oposicion_id}")
    registrar_visita(user["id"], oposicion_id)
    return jsonify({"ok": True})


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
