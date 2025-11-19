"""scraping_boe.py

Aplicación Flask para Web Scraping del BOE (Boletín Oficial del Estado)
con sistema de usuarios (sign up / login) y notificación por email de
nuevas oposiciones detectadas.

Autor original: franSM, Cristóbal Delgado Romero
Ampliado con auth + email: 2025
"""

from datetime import datetime, date
from datetime import datetime, date
import os
import re
import sqlite3
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from flask import ( # type: ignore
    Flask, request, g, redirect, url_for, render_template, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
from flask_mail import Mail, Message # type: ignore
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required, current_user
)


# --- Flask + DB en instance/ ---
app = Flask(__name__, instance_relative_config=True)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, "oposiciones.db")

app.secret_key = os.getenv('SECRET_KEY', 'clave-secreta-para-flask-sessions-cambiar-en-produccion')



class User(UserMixin):
    def __init__(self, id, email, name, apellidos, age, genero):
        self.id = id
        self.email = email
        self.name = name
        self.apellidos = apellidos
        self.age = age
        self.genero = genero


    @staticmethod
    def get(user_id):
        db = get_db()
        row = db.execute(
            
            "SELECT id, email, name, apellidos, age, genero FROM users WHERE id = ?", (user_id,)
    ).fetchone()

        if row:
            return User(row["id"], row["email"], row["name"], row["apellidos"], row["age"], row["genero"]
    )
        return None


@login_manager.user_loader # type: ignore
def load_user(user_id):
    return User.get(user_id)


# === Configuración de Flask-Mail (desde variables de entorno) ===
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'localhost')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '25'))
app.config['MAIL_USE_TLS'] = bool(int(os.getenv('MAIL_USE_TLS', '0')))
app.config['MAIL_USE_SSL'] = bool(int(os.getenv('MAIL_USE_SSL', '0')))
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv(
    'MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME'))

mail = Mail(app)

# --------------------
# filtros Jinja2
# --------------------


@app.template_filter('format_date')
def format_date_filter(date_str):
    if not date_str or len(date_str) != 8:
        return date_str
    try:
        year = date_str[0:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{day}/{month}/{year}"
    except Exception:
        return date_str


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
def close_connection(_):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def ensure_schema():
    """Crea tablas si no existen y añade columna 'provincia' si falta (no rompe merges previos)."""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS oposiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador TEXT NOT NULL,
            control TEXT,
            titulo TEXT,
            url_html TEXT UNIQUE,
            url_pdf TEXT,
            departamento TEXT,
            fecha TEXT
        )
    """)
    cols = [r[1] for r in db.execute("PRAGMA table_info(oposiciones)").fetchall()]
    if 'provincia' not in cols:
        db.execute("ALTER TABLE oposiciones ADD COLUMN provincia TEXT")
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT,
            apellidos TEXT,
            age INTEGER,
            genero TEXT
        )
    """)
    db.commit()

def init_db():
    ensure_schema()

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


def create_user(email, password, name, apellidos, age, genero):
    db = get_db()
    password_hash = generate_password_hash(password)
    db.execute(
        "INSERT INTO users (email, password_hash, name, apellidos, age, genero) VALUES (?, ?, ?, ?, ?, ?)",
        (email.lower(), password_hash, name, apellidos, age, genero)
    )
    db.commit()

def find_user_by_email(email):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()

# --------------------
# Email (Notificación de nuevas oposiciones)
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
    if not recipients or not oposiciones:
        return

    filas = []
    for o in oposiciones:
        titulo = o.get("titulo") or "(Sin título)"
        fecha = o.get("fecha") or ""
        url_html = o.get("url_html") or "#"
        url_pdf = o.get("url_pdf")
        dept = o.get("departamento") or ""
        pdf_html = f' | <a href="{url_pdf}">PDF</a>' if url_pdf else ""
        dept_html = f" — {dept}" if dept else ""
        filas.append(
            f'<li><strong>{titulo}</strong> — {fecha} — '
            f'<a href="{url_html}">HTML</a>{pdf_html}{dept_html}</li>'
        )
    html = (
        "<h3>Nuevas oposiciones publicadas</h3>"
        f"<p>Se han detectado {len(oposiciones)} nuevas oposiciones:</p>"
        f"<ul>{''.join(filas)}</ul>"
        '<p style="font-size:12px;color:#666">Este es un mensaje automático, por favor no responda.</p>'
    )

    subject = f"{len(oposiciones)} nuevas oposiciones publicadas"
    msg = Message(subject=subject, recipients=recipients, html=html)
    mail.send(msg)

def all_user_emails():
    db = get_db()
    return [r['email'] for r in db.execute("SELECT email FROM users").fetchall()]

# --------------------
# Utilidades: detectar provincia
# --------------------
_PROVINCIAS = {
    "A CORUÑA","ALAVA","ARABA","ALBACETE","ALICANTE","ALMERIA","ASTURIAS","AVILA","BADAJOZ","BARCELONA",
    "BIZKAIA","VIZCAYA","BURGOS","CACERES","CADIZ","CANTABRIA","CASTELLON","CIUDAD REAL","CORDOBA","CUENCA",
    "GIPUZKOA","GUIPUZCOA","GIRONA","GERONA","GRANADA","GUADALAJARA","HUELVA","HUESCA","ILLES BALEARS","BALEARES",
    "JAEN","LA RIOJA","LAS PALMAS","LEON","LLEIDA","LERIDA","LUGO","MADRID","MALAGA","MURCIA","NAVARRA",
    "OURENSE","PALENCIA","PONTEVEDRA","SALAMANCA","SANTA CRUZ DE TENERIFE","SEGOVIA","SEVILLA","SORIA","TARRAGONA",
    "TERUEL","TOLEDO","VALENCIA","VALLADOLID","ZAMORA","ZARAGOZA","CEUTA","MELILLA"
}
def extraer_provincia(texto: str | None) -> str | None:
    if not texto:
        return None
    t = re.sub(r'[\W_]+', ' ', texto.upper())
    for prov in _PROVINCIAS:
        if re.search(rf'(^|\s){re.escape(prov)}(\s|$)', t):
            return prov.title()
    return None

def scrape_boe():
    """
    Devuelve lista de oposiciones NUEVAS insertadas (para email).
    No rompe datos ya existentes (evita duplicados por url_html).
    """
    init_db()
    db = get_db()

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/xml, text/xml, */*; q=0.01',
    }

    fecha = datetime.today()
    r = None
    hoy_str = None

    for _ in range(7):
        hoy_str = fecha.strftime('%Y%m%d')
        boe_url = f'https://www.boe.es/datosabiertos/api/boe/sumario/{hoy_str}'
        try:
            r = requests.get(boe_url, headers=headers, timeout=10)
            if r.status_code == 200 and r.content:
                break
        except requests.RequestException:
            pass
        fecha -= timedelta(days=1)
    else:
        return []

    try:
        soup = BeautifulSoup(r.content, 'lxml-xml')
    except Exception:
        soup = BeautifulSoup(r.content, 'html.parser')

    seccion = soup.find("seccion", {"codigo": "2B"})
    if not seccion:
        return []

    newly_inserted = []
    for item in seccion.find_all("item"):
        identificador_tag = item.find("identificador")
        control_tag = item.find("control")
        titulo_tag = item.find("titulo")
        url_html_tag = item.find("url_html")
        url_pdf_tag = item.find("url_pdf")

        identificador = identificador_tag.text.strip() if identificador_tag else None
        control = control_tag.text.strip() if control_tag else None
        titulo = titulo_tag.text.strip() if titulo_tag else None
        url_html = url_html_tag.text.strip() if url_html_tag else None
        url_pdf = url_pdf_tag.text.strip() if url_pdf_tag else None

        dept_parent = item.find_parent('departamento')
        departamento = dept_parent.get(
            'nombre') if dept_parent and dept_parent.has_attr('nombre') else None

        provincia = extraer_provincia(titulo) or extraer_provincia(control)

        try:
            db.execute(
                "INSERT INTO oposiciones (identificador, control, titulo, url_html, url_pdf, departamento, fecha, provincia) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (identificador, control, titulo, url_html, url_pdf, departamento, hoy_str, provincia)
            )
            db.commit()
            newly_inserted.append({
                "identificador": identificador,
                "control": control,
                "titulo": titulo,
                "url_html": url_html,
                "url_pdf": url_pdf,
                "departamento": departamento,
                "fecha": hoy_str,
                "provincia": provincia
            })
        except sqlite3.IntegrityError:
            # duplicado por url_html -> ignorar
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
    deps = db.execute(
        'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL ORDER BY departamento'
    ).fetchall()
    return render_template('index.html', departamentos=deps, user=current_user())

    return render_template('index.html', departamentos=deps, user=current_user)


@app.route("/departamento/<nombre>")
def mostrar_departamento(nombre):
    init_db()
    db = get_db()

    texto_busqueda = (request.args.get('busqueda') or '').strip()
    provincia_filtro = (request.args.get('provincia') or '').strip()
    fecha_desde = (request.args.get('fecha_desde') or '').strip()
    fecha_hasta = (request.args.get('fecha_hasta') or '').strip()

    provincias_disponibles = db.execute(
        'SELECT DISTINCT provincia FROM oposiciones WHERE departamento = ? AND provincia IS NOT NULL ORDER BY provincia',
        [nombre]
    ).fetchall()

    query = 'SELECT * FROM oposiciones WHERE departamento = ?'
    params = [nombre]

    if texto_busqueda:
        query += ' AND (identificador LIKE ? OR titulo LIKE ? OR control LIKE ? OR provincia LIKE ?)'
        like = f'%{texto_busqueda}%'
        params.extend([like, like, like, like])

        visitadas = [
            row["oposicion_id"]
            for row in db.execute(
                "SELECT oposicion_id FROM visitas WHERE user_id = ?", (
                    user.id,)
            ).fetchall()
        ]

    return render_template(
        'tarjeta.html',
        departamento=nombre,
        rows=rows,
        busqueda=texto_busqueda,
        provincia_filtro=provincia_filtro,
        provincias=provincias_disponibles,
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
        flash("Registro correcto. Sesión iniciada.", "success")
        return redirect(url_for('index'))
    return render_template('register.html', user=current_user())

@app.route('/login', methods=['GET', 'POST'])
def login():
    init_db()
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = (request.form.get('password') or '')
        user = find_user_by_email(email)
        if not user or not check_password_hash(user['password_hash'], password):
            flash("Credenciales inválidas.", "danger")
            return redirect(url_for('login'))  # 🔹 redirect limpio
        login_user(User(user["id"], user["email"], user["name"]))
        flash("Sesión iniciada.", "success")
        next_url = request.args.get('next') or url_for('index')
        return redirect(next_url)
    return render_template('login.html', user=current_user)


@app.route('/logout')
@login_required
def logout():
    session.pop('user_id', None)
    flash("Sesión cerrada.", "info")
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    init_db()
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = (request.form.get('password') or '')
        name = (request.form.get('nombre') or '')
        apellidos = (request.form.get('apellidos') or '')
        age = (request.form.get ('edad') or '')
        genero = (request.form.get('genero') or '')
        if not email or not password or not name or not apellidos or not age or not genero:
            flash("¡Rellena todos los campos!", "danger")
            return render_template('register.html', user=current_user)
        if find_user_by_email(email):
            flash("Ese email ya está registrado.", "warning")
            return render_template('register.html', user=current_user)
        create_user(email, password, name, apellidos, age, genero)
        user = find_user_by_email(email)
        login_user(User(user["id"], user["email"], user["name"], user["apellidos"], user["age"], user["genero"]))
        flash("Registro correcto. Sesión iniciada.", "success")
        return redirect(url_for('index'))
    return render_template('register.html', user=current_user)


@app.route("/user", methods=["GET", "POST"])
@login_required
def user():
    return render_template("user.html", user=current_user)
@app.route("/user_oposiciones")
@login_required
def oposiciones_vigentes():
    db = get_db()
    desde = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")

    # 🔹 Obtener todos los departamentos con oposiciones recientes
    departamentos = db.execute('''
        SELECT DISTINCT departamento 
        FROM oposiciones 
        WHERE fecha >= ? AND departamento IS NOT NULL 
        ORDER BY departamento
    ''', (desde,)).fetchall()

    # --- Filtros ---
    selected_departamentos = request.args.getlist("departamentos")
    busqueda = request.args.get("busqueda", "")
    provincia = request.args.get("provincia", "")
    fecha_desde = request.args.get("fecha_desde", "")
    fecha_hasta = request.args.get("fecha_hasta", "")

    sql = "SELECT * FROM oposiciones WHERE fecha >= ?"
    params = [desde]

    if selected_departamentos:
        sql += " AND departamento IN ({})".format(
            ",".join(["?"] * len(selected_departamentos)))
        params.extend(selected_departamentos)

    if busqueda:
        like = f"%{busqueda}%"
        sql += " AND (titulo LIKE ? OR identificador LIKE ? OR control LIKE ?)"
        params += [like, like, like]

    if provincia:
        sql += " AND provincia = ?"
        params.append(provincia)

    if fecha_desde:
        sql += " AND fecha >= ?"
        params.append(fecha_desde.replace("-", ""))

    if fecha_hasta:
        sql += " AND fecha <= ?"
        params.append(fecha_hasta.replace("-", ""))

    sql += " ORDER BY fecha DESC"
    oposiciones = db.execute(sql, params).fetchall()

    provincias = db.execute(
        "SELECT DISTINCT provincia FROM oposiciones WHERE provincia IS NOT NULL ORDER BY provincia"
    ).fetchall()

    return render_template(
        "user_oposiciones.html",
        user=current_user,
        departamentos=departamentos,
        selected_departamentos=selected_departamentos,
        oposiciones=oposiciones,
        provincias=provincias,
        busqueda=busqueda,
        provincia_filtro=provincia,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


@app.route("/user_alertas")
@login_required
def newsletter_prefs():
    """Sección para gestionar alertas por correo / newsletter."""
    # En el futuro: formulario para suscribirse a departamentos concretos.
    return render_template("user_newsletter.html", user=current_user)


@app.route("/user_configuracion")
@login_required
def configuracion_cuenta():
    """Panel de configuración de perfil del usuario."""
    # En el futuro: formularios de perfil, seguridad, etc.
    return render_template("user_configuracion.html", user=current_user)


@app.route("/marcar_visitada/<int:oposicion_id>", methods=["POST"])
@login_required
def marcar_visitada(oposicion_id):
    user = current_user
    print(
        f"🟢 Registro de visita recibido: user={user['id']}, oposicion_id={oposicion_id}")
    registrar_visita(user["id"], oposicion_id)
    return jsonify({"ok": True})


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
