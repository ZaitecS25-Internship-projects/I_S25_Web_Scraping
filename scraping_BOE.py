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
from flask import Flask, request, g, redirect, url_for, render_template, flash
from bs4 import BeautifulSoup

DB_PATH = 'oposiciones.db'
app = Flask(__name__)
app.secret_key = 'clave-secreta-para-flask-sessions-cambiar-en-produccion'

# --------------------
# filtros Jinja2 
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
# Ayudas con la bases de datos
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
    db.execute('''
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
    ''')
    
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
        tuple: (éxito: bool, mensaje: str, registros_nuevos: int)
        
    Raises:
        Exception: Captura y retorna cualquier error que ocurra
    """
    try:
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (identificador, control, titulo, url_html, url_pdf, departamento, hoy, provincia))
                db.commit()
                collected += 1
            except sqlite3.IntegrityError:
                continue  # URL ya existe

        if collected > 0:
            return (True, f"Se han añadido {collected} nuevas oposiciones.", collected)
        else:
            return (True, "No se encontraron nuevas oposiciones (todas ya estaban en la base de datos).", 0)
            
    except Exception as e:
        mensaje_error = f"Error inesperado: {str(e)}"
        print(f" {mensaje_error}")
        import traceback
        traceback.print_exc()
        return (False, mensaje_error, 0)
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
    """Vista detallada de oposiciones por departamento con filtros.
    
    Args:
        nombre (str): Nombre del departamento a consultar
        
    Query Parameters:
        busqueda (str): Texto para buscar en identificador, título, control o provincia
        provincia (str): Filtrar por provincia específica
        fecha_desde (str): Fecha desde en formato YYYY-MM-DD
        fecha_hasta (str): Fecha hasta en formato YYYY-MM-DD
        
    Returns:
        str: HTML renderizado con tabla de oposiciones del departamento filtradas
    """
    init_db()
    db = get_db()
    
    # Obtener parámetros de filtro de la URL
    texto_busqueda = request.args.get('busqueda', '').strip()
    provincia_filtro = request.args.get('provincia', '').strip()
    fecha_desde = request.args.get('fecha_desde', '').strip()
    fecha_hasta = request.args.get('fecha_hasta', '').strip()
    
    # Obtener lista de provincias disponibles para este departamento
    provincias_disponibles = db.execute(
        'SELECT DISTINCT provincia FROM oposiciones WHERE departamento = ? AND provincia IS NOT NULL ORDER BY provincia',
        [nombre]
    ).fetchall()
    
    # Construir consulta SQL dinámica
    query = 'SELECT * FROM oposiciones WHERE departamento = ?'
    params = [nombre]
    
    # Filtro por texto (busca en identificador, título, control y provincia)
    if texto_busqueda:
        query += ' AND (identificador LIKE ? OR titulo LIKE ? OR control LIKE ? OR provincia LIKE ?)'
        busqueda_param = f'%{texto_busqueda}%'
        params.extend([busqueda_param, busqueda_param, busqueda_param, busqueda_param])
    
    # Filtro por provincia específica
    if provincia_filtro:
        query += ' AND provincia = ?'
        params.append(provincia_filtro)
    
    # Filtro por fecha desde (convertir YYYY-MM-DD a YYYYMMDD)
    if fecha_desde:
        fecha_desde_formateada = fecha_desde.replace('-', '')
        query += ' AND fecha >= ?'
        params.append(fecha_desde_formateada)
    
    # Filtro por fecha hasta (convertir YYYY-MM-DD a YYYYMMDD)
    if fecha_hasta:
        fecha_hasta_formateada = fecha_hasta.replace('-', '')
        query += ' AND fecha <= ?'
        params.append(fecha_hasta_formateada)
    
    query += ' ORDER BY id DESC'
    
    # Ejecutar consulta con filtros
    cur = db.execute(query, params)
    rows = cur.fetchall()

    return render_template('tarjeta.html', 
                         departamento=nombre, 
                         rows=rows,
                         busqueda=texto_busqueda,
                         provincia_filtro=provincia_filtro,
                         provincias=provincias_disponibles,
                         fecha_desde=fecha_desde,
                         fecha_hasta=fecha_hasta)


@app.route('/scrape')
def do_scrape():
    """Endpoint para actualizar datos del BOE.
    
    Ejecuta el proceso de web scraping para obtener las últimas
    oposiciones publicadas en el BOE y las almacena en la base de datos.
    
    Devuelve:
        werkzeug.wrappers.Response: Redirección a la página principal
    """
    init_db()
    exito, mensaje, registros = scrape_boe()
    
    if exito:
        flash(mensaje, 'success')
    else:
        flash(mensaje, 'danger')
    
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
