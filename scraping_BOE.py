"""scraping_boe.py

Aplicación Flask para Web Scraping del BOE (Boletín Oficial del Estado)
con sistema de usuarios (sign up / login) y notificación por email de
nuevas oposiciones detectadas.

Autor original: franSM, Cristóbal Delgado Romero
Ampliado con auth + email: 2025
"""

import os
import sqlite3
from datetime import datetime, timedelta

import requests
from flask import Flask, request, g, redirect, url_for, render_template, session, flash
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message

DB_PATH = 'oposiciones.db'
app = Flask(__name__)
app.secret_key = 'clave-secreta-para-flask-sessions-cambiar-en-produccion'

# === Configuración básica (lee de variables de entorno) ===
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'cambia-esto')
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'localhost')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', '25'))
app.config['MAIL_USE_TLS'] = bool(int(os.getenv('MAIL_USE_TLS', '0')))
app.config['MAIL_USE_SSL'] = bool(int(os.getenv('MAIL_USE_SSL', '0')))
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME'))

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
    except:
        return date_str

# --------------------
# Helpers DB
# --------------------

def get_db():
    try:
        # Intentar usar el contexto de Flask (para rutas web)
        db = getattr(g, '_database', None)
        if db is None:
            db = g._database = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
        return db
    except RuntimeError:
        # Si no hay contexto de Flask, crear conexión directamente
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        return db

@app.teardown_appcontext
def close_connection(_):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def extraer_provincia(texto):
    """Extrae el nombre de la provincia del texto usando palabras clave.
    
    Args:
        texto (str): Texto donde buscar la provincia (título, control, etc.)
        
    Returns:
        str: Nombre de la provincia encontrada o None
    """
    if not texto:
        return None
    
    # Lista de provincias españolas
    provincias = [
        'Álava', 'Albacete', 'Alicante', 'Almería', 'Asturias', 'Ávila',
        'Badajoz', 'Barcelona', 'Burgos', 'Cáceres', 'Cádiz', 'Cantabria',
        'Castellón', 'Ciudad Real', 'Córdoba', 'Cuenca', 'Girona', 'Granada',
        'Guadalajara', 'Guipúzcoa', 'Huelva', 'Huesca', 'Jaén', 'La Coruña',
        'La Rioja', 'Las Palmas', 'León', 'Lérida', 'Lugo', 'Madrid',
        'Málaga', 'Murcia', 'Navarra', 'Ourense', 'Palencia', 'Pontevedra',
        'Salamanca', 'Segovia', 'Sevilla', 'Soria', 'Tarragona', 'Teruel',
        'Toledo', 'Valencia', 'Valladolid', 'Vizcaya', 'Zamora', 'Zaragoza',
        'Ceuta', 'Melilla'
    ]
    
    texto_upper = texto.upper()
    
    for provincia in provincias:
        if provincia.upper() in texto_upper:
            return provincia
    
    return None


def init_db_for_db(db):
    """Inicializa la estructura de base de datos usando una conexión existente."""
    # Tabla oposiciones
    db.execute("""
        CREATE TABLE IF NOT EXISTS oposiciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificador TEXT NOT NULL,
            control TEXT,
            titulo TEXT,
            url_html TEXT UNIQUE,
            url_pdf TEXT,
            departamento TEXT,
            fecha TEXT,
            provincia TEXT
        )
    """)
    
    # Tabla usuarios
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Preferencias de usuario: departamentos seleccionados
    db.execute("""
        CREATE TABLE IF NOT EXISTS user_departamentos (
            user_id INTEGER NOT NULL,
            departamento TEXT NOT NULL,
            PRIMARY KEY (user_id, departamento)
        )
    """)
    
    # Migración: Añadir columna provincia si no existe
    try:
        db.execute('SELECT provincia FROM oposiciones LIMIT 1')
    except sqlite3.OperationalError:
        # La columna no existe, añadirla
        print("Añadiendo columna 'provincia' a la base de datos...")
        db.execute('ALTER TABLE oposiciones ADD COLUMN provincia TEXT')
        
        # Actualizar registros existentes con provincia extraída
        cursor = db.execute('SELECT id, titulo, control FROM oposiciones')
        rows = cursor.fetchall()
        for row in rows:
            provincia = extraer_provincia(row['titulo']) or extraer_provincia(row['control'])
            if provincia:
                db.execute('UPDATE oposiciones SET provincia = ? WHERE id = ?', (provincia, row['id']))
        print(f"Actualizado {len(rows)} registros con información de provincia.")
    
    db.commit()


def init_db():
    """Inicializa la estructura de base de datos.
    
    Crea la tabla 'oposiciones' con los siguientes campos:
    - id: Clave primaria autoincremental
    - identificador: ID único del BOE
    - control: Número de control
    - titulo: Título de la convocatoria
    - url_html: URL del documento HTML
    - url_pdf: URL del documento PDF (UNIQUE para evitar duplicados)
    - departamento: Entidad convocante
    - fecha: Fecha de publicación
    - provincia: Provincia extraída del título/control
    """
    db = get_db()
    init_db_for_db(db)

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
# Preferencias de usuario (departamentos)
# --------------------

def get_user_departamentos(user_id):
    db = get_db()
    rows = db.execute(
        "SELECT departamento FROM user_departamentos WHERE user_id = ? ORDER BY departamento",
        (user_id,)
    ).fetchall()
    return [r['departamento'] for r in rows]

def set_user_departamentos(user_id, departamentos):
    db = get_db()
    # Limpiar actuales
    db.execute("DELETE FROM user_departamentos WHERE user_id = ?", (user_id,))
    # Insertar nuevos
    if departamentos:
        db.executemany(
            "INSERT OR IGNORE INTO user_departamentos (user_id, departamento) VALUES (?, ?)",
            [(user_id, d) for d in departamentos]
        )
    db.commit()

# --------------------
# Email (Notificación de nuevas oposiciones)
# --------------------

def send_new_oposiciones_email(recipients, oposiciones):
    """
    Envía un email HTML a todos los 'recipients' con el listado de nuevas oposiciones.
    """
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
    lista_html = "".join(filas)
    html = (
        "<h3>Nuevas oposiciones publicadas</h3>"
        f"<p>Se han detectado {len(oposiciones)} nuevas oposiciones:</p>"
        f"<ul>{lista_html}</ul>"
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

def es_dia_habil(fecha):
    """Determina si una fecha es un día hábil (lunes a viernes, excluyendo festivos).
    
    Args:
        fecha: datetime object
        
    Returns:
        bool: True si es día hábil, False si no
    """
    return fecha.weekday() < 5  # 0=Lunes, 6=Domingo

def calcular_ultimos_dias_habiles(dias=20):
    """Calcula los últimos N días hábiles.
    
    Args:
        dias: Número de días hábiles a contar
        
    Returns:
        tuple: (fecha_inicio, fecha_fin) ambas como string YYYYMMDD
    """
    fecha_fin = datetime.today()
    fecha_inicio = fecha_fin
    dias_habiles_contados = 0
    
    while dias_habiles_contados < dias:
        if es_dia_habil(fecha_inicio):
            dias_habiles_contados += 1
        if dias_habiles_contados < dias:
            fecha_inicio -= timedelta(days=1)
    
    return fecha_inicio.strftime('%Y%m%d'), fecha_fin.strftime('%Y%m%d')

def scrape_boe():
    """Extrae oposiciones del BOE y las almacena en SQLite.
    
    Proceso:
    1. Conecta a la API oficial del BOE con fecha actual
    2. Si no hay datos, retrocede hasta 7 días buscando información
    3. Parsea XML de la sección 2B (Oposiciones y Concursos)
    4. Extrae datos: identificador, título, control, URLs, departamento
    5. Guarda en base de datos evitando duplicados
    
    Returns:
        tuple: (éxito: bool, mensaje: str, registros_nuevos: int)
        
    Raises:
        Exception: Captura y retorna cualquier error que ocurra
    """
    try:
        # Inicializar la base de datos antes de usarla
        db = get_db()
        init_db_for_db(db)
        collected = 0
        # Detectar si la conexión es standalone (no gestionada por Flask)
        try:
            getattr(g, '_database')  # Si esto no falla, Flask gestiona la conexión
            is_standalone_db = False
        except RuntimeError:
            is_standalone_db = True

        # Construir URL con la fecha actual
        fecha = datetime.today()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/118.0.5993.118 Safari/537.36',
            'Accept': 'application/xml, text/xml, */*; q=0.01',
        }

        # Buscar hasta encontrar resultado en BOE si da error hasta 7 días atrás.
        r = None
        for _ in range(7):
            hoy = fecha.strftime('%Y%m%d')
            boe_url = f'https://www.boe.es/datosabiertos/api/boe/sumario/{hoy}'
            try:
                r = requests.get(boe_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    print(f" BOE encontrado {boe_url}")
                    break
                print(f" No disponible para {hoy}. Probando día anterior.")
            except requests.RequestException as e:
                print(f" Error al obtener {boe_url}: {e}")

            fecha -= timedelta(days=1)  # Retroceder un día si falla.
        else:
            mensaje = "No se encontró ningún BOE reciente en los últimos 7 días."
            print(f" {mensaje}")
            return (False, mensaje, 0)

        if not r or r.status_code != 200:
            return (False, "No se pudo conectar con el BOE.", 0)

        # Parsear XML con lxml
        try:
            soup = BeautifulSoup(r.content, 'lxml-xml')
        except Exception as e:
            # Intentar con html.parser como fallback
            try:
                soup = BeautifulSoup(r.content, 'html.parser')
                print("Advertencia: usando html.parser en lugar de lxml")
            except Exception as e2:
                return (False, f"Error al parsear XML: {str(e)}. SOLUCIÓN: 1) Cierra Flask (Ctrl+C), 2) Ejecuta 'pip install lxml', 3) Reinicia Flask con 'python scraping_BOE.py'", 0)

        # Buscar las entradas de tipo <item>
        seccion = soup.find("seccion", {"codigo": "2B"})
        if not seccion:
            mensaje = "No se encontró la sección 2B (Oposiciones y Concursos) en el BOE."
            print(mensaje)
            return (True, mensaje, 0)

        items = seccion.find_all("item")

        for item in items:
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

            # Buscar el departamento padre
            dept_parent = item.find_parent("departamento")
            departamento = dept_parent.get(
                'nombre') if dept_parent and dept_parent.has_attr('nombre') else None
            
            # Extraer provincia del título o control
            provincia = extraer_provincia(titulo) or extraer_provincia(control)

            try:
                db.execute('''
                    INSERT INTO oposiciones (identificador, control, titulo, url_html, url_pdf, departamento, fecha, provincia)
                    VALUES ( ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (identificador, control, titulo, url_html, url_pdf, departamento, hoy, provincia))
                db.commit()
                collected += 1
            except sqlite3.IntegrityError:
                continue  # URL ya existe

        if collected > 0:
            result = (True, f"Se han añadido {collected} nuevas oposiciones.", collected)
        else:
            result = (True, "No se encontraron nuevas oposiciones (todas ya estaban en la base de datos).", 0)
        
        # Cerrar conexión si no está gestionada por Flask
        try:
            if is_standalone_db:
                db.close()
        except:
            pass
        return result
            
    except Exception as e:
        mensaje_error = f"Error inesperado: {str(e)}"
        print(f" {mensaje_error}")
        import traceback
        traceback.print_exc()
        # Asegurar que la conexión se cierre en caso de error
        try:
            if 'is_standalone_db' in locals() and is_standalone_db and db:
                db.close()
        except:
            pass
        return (False, mensaje_error, 0)

# --------------------
# Rutas Flask
# --------------------

@app.route('/')
def index():
    init_db()
    db = get_db()
    
    # Calcular rango de últimos 20 días hábiles
    fecha_inicio, fecha_fin = calcular_ultimos_dias_habiles(20)
    
    # Departamentos base con filtro de fechas
    base_query = (
        'SELECT DISTINCT o.departamento FROM oposiciones o '
        'WHERE o.departamento IS NOT NULL '
        'AND o.fecha >= ? AND o.fecha <= ?'
    )
    params = [fecha_inicio, fecha_fin]
    
    user_row = current_user()
    if user_row:
        seleccionados = get_user_departamentos(user_row['id'])
        if seleccionados:
            placeholders = ','.join(['?'] * len(seleccionados))
            base_query += f' AND o.departamento IN ({placeholders})'
            params.extend(seleccionados)
    
    base_query += ' ORDER BY o.departamento'
    deps = db.execute(base_query, params).fetchall()
    return render_template('index.html', departamentos=deps, user=user_row)

@app.route('/departamento/<nombre>')
def mostrar_departamento(nombre):
    
    init_db()
    db = get_db()
    
    # Obtener parámetros de filtro de la URL
    texto_busqueda = request.args.get('busqueda', '').strip()
    provincia_filtro = request.args.get('provincia', '').strip()
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    page = request.args.get('page', 1, type=int)
    
    # Configuración de paginación
    per_page = 20
    offset = (page - 1) * per_page
    
    # Si el usuario tiene preferencias y este departamento no está incluido, mostrar vacío con aviso
    user_row = current_user()
    if user_row:
        seleccionados = get_user_departamentos(user_row['id'])
        if seleccionados and nombre not in seleccionados:
            flash("Este departamento no está entre tus seleccionados.", "info")
            return render_template('tarjeta.html', 
                                 departamento=nombre, 
                                 rows=[],
                                 busqueda=texto_busqueda,
                                 provincia_filtro=provincia_filtro,
                                 provincias=[],
                                 fecha_desde=fecha_desde,
                                 fecha_hasta=fecha_hasta,
                                 page=1,
                                 total_pages=1,
                                 total_count=0,
                                 per_page=20)

    # Calcular rango de últimos 20 días hábiles
    fecha_inicio, fecha_fin = calcular_ultimos_dias_habiles(20)
    
    # Obtener lista de provincias disponibles para este departamento (solo últimos 20 días hábiles)
    provincias_disponibles = db.execute(
        'SELECT DISTINCT provincia FROM oposiciones WHERE departamento = ? AND provincia IS NOT NULL AND fecha >= ? AND fecha <= ? ORDER BY provincia',
        [nombre, fecha_inicio, fecha_fin]
    ).fetchall()
    
    # Construir consulta SQL para contar total (solo últimos 20 días hábiles)
    count_query = 'SELECT COUNT(*) as total FROM oposiciones WHERE departamento = ? AND fecha >= ? AND fecha <= ?'
    count_params = [nombre, fecha_inicio, fecha_fin]
    
    # Aplicar filtros a la consulta de conteo
    if texto_busqueda:
        count_query += ' AND (identificador LIKE ? OR titulo LIKE ? OR control LIKE ? OR provincia LIKE ?)'
        busqueda_param = f'%{texto_busqueda}%'
        count_params.extend([busqueda_param, busqueda_param, busqueda_param, busqueda_param])
    
    if provincia_filtro:
        count_query += ' AND provincia = ?'
        count_params.append(provincia_filtro)
    
    if fecha_desde:
        fecha_desde_formateada = fecha_desde.replace('-', '')
        count_query += ' AND fecha >= ?'
        count_params.append(fecha_desde_formateada)
    
    if fecha_hasta:
        fecha_hasta_formateada = fecha_hasta.replace('-', '')
        count_query += ' AND fecha <= ?'
        count_params.append(fecha_hasta_formateada)
    
    # Obtener total de registros
    total_count = db.execute(count_query, count_params).fetchone()['total']
    
    # Construir consulta SQL para datos con paginación (solo últimos 20 días hábiles)
    query = 'SELECT * FROM oposiciones WHERE departamento = ? AND fecha >= ? AND fecha <= ?'
    params = [nombre, fecha_inicio, fecha_fin]
    
    # Aplicar filtros
    if texto_busqueda:
        query += ' AND (identificador LIKE ? OR titulo LIKE ? OR control LIKE ? OR provincia LIKE ?)'
        busqueda_param = f'%{texto_busqueda}%'
        params.extend([busqueda_param, busqueda_param, busqueda_param, busqueda_param])
    
    if provincia_filtro:
        query += ' AND provincia = ?'
        params.append(provincia_filtro)
    
    if fecha_desde:
        fecha_desde_formateada = fecha_desde.replace('-', '')
        query += ' AND fecha >= ?'
        params.append(fecha_desde_formateada)
    
    if fecha_hasta:
        fecha_hasta_formateada = fecha_hasta.replace('-', '')
        query += ' AND fecha <= ?'
        params.append(fecha_hasta_formateada)
    
    query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    params.extend([per_page, offset])
    
    # Ejecutar consulta con filtros y paginación
    cur = db.execute(query, params)
    rows = cur.fetchall()
    
    # Calcular total de páginas
    total_pages = (total_count + per_page - 1) // per_page

    return render_template('tarjeta.html', 
                         departamento=nombre, 
                         rows=rows,
                         busqueda=texto_busqueda,
                         provincia_filtro=provincia_filtro,
                         provincias=provincias_disponibles,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta,
                         page=page,
                         total_pages=total_pages,
                         total_count=total_count,
                         per_page=per_page)

@app.route('/scrape')
def do_scrape():
    init_db()
    exito, mensaje, registros = scrape_boe()
    
    if exito:
        flash(mensaje, 'success')
    else:
        flash(mensaje, 'danger')
    
    return redirect(url_for('index'))

# --- Registro / Login ---

@app.route('/preferencias', methods=['GET', 'POST'])
def preferencias():
    init_db()
    user_row = current_user()
    if not user_row:
        flash('Inicia sesión para gestionar tus preferencias.', 'warning')
        return redirect(url_for('login', next=url_for('preferencias')))

    db = get_db()
    # Lista completa de departamentos disponibles
    deps_all = db.execute(
        'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL ORDER BY departamento'
    ).fetchall()
    seleccionados = set(get_user_departamentos(user_row['id']))

    if request.method == 'POST':
        seleccion = request.form.getlist('departamentos')
        set_user_departamentos(user_row['id'], seleccion)
        flash('Preferencias guardadas.', 'success')
        return redirect(url_for('index'))

    return render_template('preferencias.html', departamentos=deps_all, seleccionados=seleccionados, user=user_row)

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

if __name__ == '__main__':
    import sys
    import socket
    import traceback
    
    # Verificar que el puerto 5000 esté disponible
    def verificar_puerto(port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result != 0
    
    # Verificar dependencias críticas
    try:
        import flask
        import requests
        import bs4
        print("[OK] Dependencias verificadas correctamente")
    except ImportError as e:
        print(f"[ERROR] Falta instalar dependencia: {e}")
        print("[TIP] Ejecuta: pip install -r requirements.txt")
        sys.exit(1)
    
    # Verificar puerto
    if not verificar_puerto(5000):
        print("[ADVERTENCIA] El puerto 5000 esta ocupado")
        print("[TIP] Cierra otras aplicaciones que usen el puerto 5000 o cambia el puerto en el codigo")
    
    # Inicializar la base de datos antes de iniciar el servidor
    try:
        with app.app_context():
            init_db()
        print("[OK] Base de datos inicializada correctamente")
    except Exception as e:
        print(f"[ADVERTENCIA] Al inicializar base de datos: {e}")
        print("[TIP] Continuando de todas formas...")
    
    # Mostrar información del servidor
    print("\n" + "="*50)
    print("INICIANDO SERVIDOR FLASK...")
    print("="*50)
    print("Accede a la aplicacion en: http://localhost:5000")
    print("O desde otro dispositivo: http://0.0.0.0:5000")
    print("Presiona Ctrl+C para detener el servidor")
    print("="*50 + "\n")
    
    # Iniciar el servidor Flask
    try:
        app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
    except OSError as e:
        if "Address already in use" in str(e) or "address is already in use" in str(e):
            print(f"\n\n[ERROR] El puerto 5000 ya esta en uso")
            print("[TIP] Soluciones:")
            print("   1. Cierra otras aplicaciones que usen el puerto 5000")
            print("   2. Cambia el puerto en la linea 'app.run(..., port=XXXX)'")
            print("   3. En Windows: netstat -ano | findstr :5000 (para ver que proceso usa el puerto)")
        else:
            print(f"\n\n[ERROR] Error al iniciar el servidor: {e}")
    except KeyboardInterrupt:
        print("\n\n[INFO] Servidor detenido por el usuario")
    except Exception as e:
        print(f"\n\n[ERROR] Error inesperado al iniciar el servidor: {e}")
        traceback.print_exc()


