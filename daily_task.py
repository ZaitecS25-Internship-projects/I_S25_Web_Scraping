import os
import time
from datetime import datetime
from app import create_app
from app.db import get_users_db, get_boe_db
from app.email_utils import send_new_oposiciones_email
from app.scraping.boe_scraper import sync_boe_hasta_hoy

# Creamos la app Flask
app = create_app()

# Buscamos oposiciones con la fecha de "HOY"
FECHA_BUSQUEDA = datetime.now().strftime("%Y%m%d") 

def job_diario():
    print(f"⏰ [ {datetime.now()} ] Iniciando tarea diaria...")
    
    # Necesitamos el contexto de la aplicación
    with app.app_context():
        
        # 🔴 AÑADIDO: Contexto de Petición de Prueba
        # Esto permite usar 'render_template', 'url_for' y acceder a 'session' sin errores
        with app.test_request_context():
            
            # 1. DESCARGA AUTOMÁTICA
            print("🔄 Conectando con el BOE para descargar novedades...")
            try:
                nuevas = sync_boe_hasta_hoy()
                print(f"   ✅ Datos actualizados. {len(nuevas)} oposiciones nuevas encontradas.")
            except Exception as e:
                print(f"   ⚠️ Error al conectar con el BOE: {e}")

            # 2. GESTIÓN DE ENVÍO DE EMAILS
            users_db = get_users_db()
            boe_db = get_boe_db()

            suscripciones = users_db.execute("SELECT * FROM suscripciones WHERE alerta_diaria = 1").fetchall()
            
            if not suscripciones:
                print("📭 Nadie tiene activadas las alertas diarias hoy.")
                return

            print(f"👥 Procesando {len(suscripciones)} usuarios suscritos...")

            for sub in suscripciones:
                user_id = sub['user_id']
                filtros_str = sub['departamento_filtro']
                
                user = users_db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
                if not user: continue
                email = user['email']
                
                # Construimos la consulta
                sql = "SELECT * FROM oposiciones WHERE fecha = ?"
                params = [FECHA_BUSQUEDA]

                if filtros_str and filtros_str != "Todos":
                    clean_str = filtros_str.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
                    lista_depts = [d.strip() for d in clean_str.split(',') if d.strip()]
                    
                    if lista_depts:
                        placeholders = ','.join(['?'] * len(lista_depts))
                        sql += f" AND departamento IN ({placeholders})"
                        params.extend(lista_depts)
                
                rows = boe_db.execute(sql, params).fetchall()
                oposiciones = [dict(row) for row in rows]

                if oposiciones:
                    print(f"  ✅ Enviando {len(oposiciones)} oposiciones a {email} (Filtros: {filtros_str})")
                    try:
                        send_new_oposiciones_email([email], oposiciones)
                    except Exception as e:
                        # Imprimimos el error pero seguimos con el siguiente usuario
                        print(f"  ❌ Error enviando a {email}: {e}")
                else:
                    print(f"  ℹ️ {email}: No hay novedades hoy para sus filtros.")

            print("🏁 Tarea finalizada con éxito.")

if __name__ == "__main__":
    job_diario()