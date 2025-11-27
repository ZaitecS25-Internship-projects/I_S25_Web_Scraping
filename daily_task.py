import os
import time
from datetime import datetime
from app import create_app
from app.db import get_users_db, get_boe_db
from app.email_utils import send_new_oposiciones_email
from app.scraping.boe_scraper import sync_boe_hasta_hoy

# Creamos la app Flask para tener acceso a la base de datos y configuración
app = create_app()

# Buscamos oposiciones con la fecha de "HOY"
FECHA_BUSQUEDA = datetime.now().strftime("%Y%m%d") 

def job_diario():
    print(f"⏰ [ {datetime.now()} ] Iniciando tarea diaria...")
    
    with app.app_context():
        # 1. DESCARGA AUTOMÁTICA: Actualizamos la base de datos con el BOE de hoy
        print("🔄 Conectando con el BOE para descargar novedades...")
        try:
            nuevas = sync_boe_hasta_hoy()
            print(f"   ✅ Datos actualizados. {len(nuevas)} oposiciones nuevas encontradas.")
        except Exception as e:
            print(f"   ⚠️ Error al conectar con el BOE (se usará lo que haya en caché): {e}")

        # 2. GESTIÓN DE ENVÍO DE EMAILS
        users_db = get_users_db()
        boe_db = get_boe_db()

        # Buscar usuarios suscritos a la alerta diaria
        suscripciones = users_db.execute("SELECT * FROM suscripciones WHERE alerta_diaria = 1").fetchall()
        
        if not suscripciones:
            print("📭 Nadie tiene activadas las alertas diarias hoy.")
            return

        print(f"👥 Procesando {len(suscripciones)} usuarios suscritos...")

        for sub in suscripciones:
            user_id = sub['user_id']
            filtros_str = sub['departamento_filtro'] # Ej: "Sanidad,Hacienda" o "Todos"
            
            user = users_db.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user: continue
            email = user['email']
            
            # Construimos la consulta SQL base
            sql = "SELECT * FROM oposiciones WHERE fecha = ?"
            params = [FECHA_BUSQUEDA]

            # Lógica para filtrar por múltiples departamentos
            if filtros_str and filtros_str != "Todos":
                # Limpieza de seguridad (quita corchetes o comillas si quedaron de versiones viejas)
                clean_str = filtros_str.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
                lista_depts = [d.strip() for d in clean_str.split(',') if d.strip()]
                
                if lista_depts:
                    placeholders = ','.join(['?'] * len(lista_depts))
                    sql += f" AND departamento IN ({placeholders})"
                    params.extend(lista_depts)
            
            # Ejecutar búsqueda
            rows = boe_db.execute(sql, params).fetchall()
            oposiciones = [dict(row) for row in rows]

            # Enviar solo si hay resultados
            if oposiciones:
                print(f"  ✅ Enviando {len(oposiciones)} oposiciones a {email} (Filtros: {filtros_str})")
                try:
                    send_new_oposiciones_email([email], oposiciones)
                except Exception as e:
                    print(f"  ❌ Error enviando a {email}: {e}")
            else:
                print(f"  ℹ️ {email}: No hay novedades hoy para sus filtros.")

        print("🏁 Tarea finalizada con éxito.")

if __name__ == "__main__":
    job_diario()