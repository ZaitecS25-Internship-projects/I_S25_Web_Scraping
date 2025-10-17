"""scraping_boe.py

Aplicación Flask para Web Scraping del BOE (Boletín Oficial del Estado)

Funcionalidades principales:
- Extrae oposiciones y concursos de la API oficial del BOE
- Almacena datos en base de datos SQLite local
- Interfaz web responsive con Bootstrap 5
- Organización por departamentos en vista de tarjetas
- Enlaces directos a documentos PDF oficiales
- Sistema de actualización manual de datos

Autor: Desarrollado por franSM, Cristóbal Delgado Romero.
Versión: 1.0
Fecha: 2025
"""

import sqlite3
from datetime import datetime, timedelta

import requests
from flask import Flask, request, g, redirect, url_for, render_template
from bs4 import BeautifulSoup

DB_PATH = 'oposiciones.db'
app = Flask(__name__)

# --------------------
# Jinja2 filters
# --------------------

@app.template_filter('format_date')
def format_date_filter(date_str):
    """Convierte fecha de formato YYYYMMDD a dd/mm/yyyy.
    
    Args:
        date_str (str): Fecha en formato YYYYMMDD (ej: '20251017')
        
    Returns:
        str: Fecha en formato dd/mm/yyyy (ej: '17/10/2025')
    """
    if not date_str or len(date_str) != 8:
        return date_str
    try:
        # Parsear YYYYMMDD
        year = date_str[0:4]
        month = date_str[4:6]
        day = date_str[6:8]
        return f"{day}/{month}/{year}"
    except:
        return date_str

# --------------------
# Database helpers
# --------------------


def get_db():
    """Obtiene conexión a la base de datos SQLite.
    
    Utiliza el patrón de Flask g para mantener una conexión por request.
    Configura row_factory para acceso por nombre de columna.
    
    Returns:
        sqlite3.Connection: Conexión a la base de datos con row_factory configurado
    """
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(_):
    """Cierra la conexión a la base de datos al finalizar la solicitud."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


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
    """
    db = get_db()
    db.execute('''
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
    ''')
    db.commit()


# --------------------
# Scraper BOE
# --------------------

def scrape_boe():
    """Extrae oposiciones del BOE y las almacena en SQLite.
    
    Proceso:
    1. Conecta a la API oficial del BOE con fecha actual
    2. Si no hay datos, retrocede hasta 7 días buscando información
    3. Parsea XML de la sección 2B (Oposiciones y Concursos)
    4. Extrae datos: identificador, título, control, URLs, departamento
    5. Guarda en base de datos evitando duplicados
    
    Returns:
        int: Número de registros nuevos insertados
        
    Raises:
        requests.RequestException: Error de conexión a la API
        sqlite3.Error: Error de base de datos
    """
    init_db()
    db = get_db()
    collected = 0

    # Construir URL con la fecha actual
    fecha = datetime.today()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/118.0.5993.118 Safari/537.36',
        'Accept': 'application/xml, text/xml, */*; q=0.01',
    }

    # Buscar hasta encontrar resultado en BOE si error 4xx hasta 7 días atrás.
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
        print(" No se encontró ningún BOE reciente.")
        return 0

    soup = BeautifulSoup(r.content, 'xml')

    # Buscar las entradas de tipo <item>
    seccion = soup.find("seccion", {"codigo": "2B"})
    if not seccion:
        print("No se encontró la sección 2B en el XML.")
        return 0

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

        try:
            db.execute('''
                INSERT INTO oposiciones (identificador, control, titulo, url_html, url_pdf, departamento, fecha)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (identificador, control, titulo, url_html, url_pdf, departamento, hoy))
            db.commit()
            collected += 1
        except sqlite3.IntegrityError:
            continue  # URL ya existe

    return collected
# --------------------
# Flask routes
# --------------------


@app.route('/')
def index():
    """Página principal - Lista de departamentos disponibles.
    
    Consulta todos los departamentos únicos que tienen oposiciones
    registradas y los muestra en formato de tarjetas.
    
    Returns:
        str: HTML renderizado con la lista de departamentos
    """
    init_db()
    db = get_db()
    deps = db.execute(
        'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL ORDER BY departamento'
    ).fetchall()
    return render_template('index.html', departamentos=deps)


@app.route('/departamento/<nombre>')
def mostrar_departamento(nombre):
    """Vista detallada de oposiciones por departamento.
    
    Args:
        nombre (str): Nombre del departamento a consultar
        
    Returns:
        str: HTML renderizado con tabla de oposiciones del departamento
    """
    init_db()
    db = get_db()

    cur = db.execute(
        'SELECT * FROM oposiciones WHERE departamento = ? ORDER BY id DESC',
        (nombre,)
    )
    rows = cur.fetchall()

    return render_template('tarjeta.html', departamento=nombre, rows=rows)


@app.route('/scrape')
def do_scrape():
    """Endpoint para actualizar datos del BOE.
    
    Ejecuta el proceso de web scraping para obtener las últimas
    oposiciones publicadas en el BOE y las almacena en la base de datos.
    
    Devuelve:
        werkzeug.wrappers.Response: Redirección a la página principal
    """
    init_db()
    scrape_boe()
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
