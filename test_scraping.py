"""
Script para probar la función de scraping del BOE de forma independiente
"""

import os
import re
import sqlite3
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

DB_PATH = 'oposiciones.db'


def extraer_provincia(texto):
    if not texto:
        return None
    texto = re.sub(r"\s+", " ", texto).strip()

    provincias = [
        'Madrid', 'Barcelona', 'Valencia', 'Sevilla', 'Zaragoza', 'Málaga', 'Murcia',
        'Alicante', 'Córdoba', 'Granada', 'Burgos', 'Palencia', 'A Coruña', 'Cantabria',
    ]
    for p in provincias:
        if re.search(rf"\b{re.escape(p)}\b", texto, re.IGNORECASE):
            return p

    caps = re.findall(r"\b[A-ZÑ]{4,15}\b", texto)
    if caps:
        return caps[0].capitalize()
    return None


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
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
    db.commit()
    return db


def scrape_boe():
    db = init_db()

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; scraping_boe/1.0)',
        'Accept': 'application/xml, text/xml, */*; q=0.01',
    }

    fecha = datetime.today()
    r = None
    hoy = None
    for i in range(7):
        hoy = fecha.strftime('%Y%m%d')
        boe_url = f'https://www.boe.es/datosabiertos/api/boe/sumario/{hoy}'
        print(f"Intentando scraping para fecha: {hoy} ({fecha.strftime('%d/%m/%Y')})")
        try:
            r = requests.get(boe_url, headers=headers, timeout=10)
            print(f"  Status code: {r.status_code}")
            if r.status_code == 200 and r.content:
                print(f"  ✓ Datos encontrados para {hoy}")
                break
            else:
                print(f"  × No hay datos para {hoy}")
        except requests.RequestException as e:
            print(f"  × Error de conexión: {e}")
        fecha -= timedelta(days=1)
    else:
        print("❌ No se pudieron obtener datos de los últimos 7 días")
        db.close()
        return []

    try:
        soup = BeautifulSoup(r.content, 'lxml-xml')
    except Exception:
        soup = BeautifulSoup(r.content, 'xml')

    seccion = soup.find('seccion', {'codigo': '2B'})
    if not seccion:
        print(f"❌ No se encontró la sección 2B (oposiciones) en el BOE del {hoy}")
        db.close()
        return []

    items = seccion.find_all('item')
    print(f"\n📋 Se encontraron {len(items)} items en la sección 2B")
    newly_inserted = []

    for idx, item in enumerate(items, 1):
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
        departamento = (
            dept_parent.get('nombre')
            if dept_parent and dept_parent.has_attr('nombre')
            else None
        )

        provincia = extraer_provincia(titulo) or extraer_provincia(control)

        try:
            cursor = db.execute(
                '''
                INSERT INTO oposiciones (
                    identificador, control, titulo, url_html, url_pdf,
                    departamento, fecha, provincia
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (identificador, control, titulo, url_html, url_pdf,
                 departamento, hoy, provincia)
            )
            db.commit()

            print(f"  {idx}. ✓ Nueva oposición: {titulo[:50]}...")
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
            print(f"  {idx}. - Ya existe: {titulo[:50]}...")
            continue

    db.close()
    return newly_inserted


if __name__ == '__main__':
    print("=" * 70)
    print("INICIANDO SCRAPING DEL BOE")
    print("=" * 70)
    
    nuevas = scrape_boe()
    
    print("\n" + "=" * 70)
    print(f"RESULTADO: {len(nuevas)} nuevas oposiciones agregadas a la base de datos")
    print("=" * 70)
    
    if nuevas:
        print("\nResumen de nuevas oposiciones:")
        for i, op in enumerate(nuevas[:5], 1):  # Mostrar solo las primeras 5
            print(f"\n{i}. {op['titulo']}")
            print(f"   Departamento: {op['departamento']}")
            print(f"   Provincia: {op['provincia']}")
            print(f"   URL: {op['url_html']}")
        
        if len(nuevas) > 5:
            print(f"\n... y {len(nuevas) - 5} más")
