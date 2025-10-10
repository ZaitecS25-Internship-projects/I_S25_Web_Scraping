"""scraping_boe.py

Aplicación Flask que:
- Raspa oposiciones del BOE usando requests + BeautifulSoup
- Guarda resultados en SQLite
- Muestra tabla con Bootstrap en plantilla externa (/templates/index.html)
- Permite búsqueda por texto y filtrado
"""

import sqlite3
from datetime import datetime, timedelta

import requests
from flask import Flask, request, g, redirect, url_for, render_template
from bs4 import BeautifulSoup

DB_PATH = 'oposiciones.db'
app = Flask(__name__)  # Cambiar nombre

# --------------------
# Database helpers
# --------------------


def get_db():
    """Devuelve la conexión a la base de datos SQLite."""
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
    """Inicializa la tabla de oposiciones si no existe."""
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
    """"Raspa TODAS las oposiciones del BOE y las guarda en SQLite"""
    init_db()
    db = get_db()
    collected = 0

    # Construir URL con la fecha actual
    fecha = datetime.today()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/118.0.5993.118 Safari/537.3',
        'Accept': 'application/xml, text/xml, */*; q=0.01',
    }

    # Buscar hasta encontrar resultado en BOE si error 4xx hasta 7 días atrás.
    for _ in range(7):
        hoy = fecha.strftime('%Y%m%d')
        boe_url = f'https://www.boe.es/datosabiertos/api/boe/sumario/{hoy}'
        try:
            r = requests.get(boe_url, headers=headers, timeout=10)
            if r.status_code == 200:
                print(f"✅ BOE encontrado {boe_url}")
                break
            print(f"❌ No disponible para {hoy}. Probando día anterior.")
        except requests.RequestException as e:
            print(f"❌ Error al obtener {boe_url}: {e}")

        fecha -= timedelta(days=1)  # Retroceder un día si falla.
    else:
        print("❌ No se encontró ningún BOE reciente.")
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
    """Muestra la tabla de oposiciones, con búsqueda y filtro."""
    init_db()
    db = get_db()

    q = request.args.get('q', '').strip()
    departamento = request.args.get('departamento', '').strip()

    params = []
    where = []
    sql = 'SELECT * FROM oposiciones'

    if q:
        likeq = f'%{q}%'
        where.append(
            "(identificador LIKE ? OR control LIKE ? OR titulo LIKE ?)")
        params.extend([likeq, likeq, likeq])

    if departamento:
        where.append("departamento = ?")
        params.append(departamento)

    if where:
        sql += ' WHERE ' + ' AND '.join(where)

    sql += ' ORDER BY id DESC'

    cur = db.execute(sql, params)
    rows = cur.fetchall()

    # Obtener lista de departamentos para el filtro
    deps = db.execute(
        'SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL ORDER BY departamento'
    ).fetchall()

    return render_template('index.html', rows=rows, q=q, departamento=departamento, departamentos=deps)


@app.route('/scrape')
def do_scrape():
    """Ejecuta el scraper y redirige a la página principal."""
    init_db()
    scrape_boe()
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
