from flask import current_app
import sqlite3
from flask import g, current_app


# =========================
# BBDD BOE (solo oposiciones)
# =========================
def get_boe_db():
    db = getattr(g, "_boe_db", None)
    if db is None:
        db = g._boe_db = sqlite3.connect(current_app.config["BOE_DB_PATH"])
        db.row_factory = sqlite3.Row
    return db


def init_boe_db():
    db = get_boe_db()
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
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_oposiciones_fecha ON oposiciones(fecha)")
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_oposiciones_departamento ON oposiciones(departamento)")
    db.commit()


# =========================
# BBDD Usuarios
# =========================
def get_users_db():
    db = getattr(g, "_users_db", None)
    if db is None:
        db = g._users_db = sqlite3.connect(current_app.config["USERS_DB_PATH"])
        db.row_factory = sqlite3.Row
    return db


def init_users_db():
    db = get_users_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT,
            apellidos TEXT,
            age INTEGER,
            genero TEXT,
            telefono TEXT,
            foto_perfil TEXT,
            dni TEXT,
            fecha_nacimiento TEXT,
            nacionalidad TEXT,
            direccion TEXT,
            codigo_postal TEXT,
            ciudad TEXT,
            provincia TEXT,
            nivel_estudios TEXT,
            titulacion TEXT,
            situacion_laboral TEXT,
            idiomas TEXT,
            discapacidad INTEGER,
            porcentaje_discapacidad INTEGER
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
    db.execute("""
        CREATE TABLE IF NOT EXISTS favoritas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            oposicion_id INTEGER NOT NULL,
            fecha_favorito TEXT NOT NULL,
            UNIQUE(user_id, oposicion_id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS suscripciones (
            user_id INTEGER PRIMARY KEY,
            alerta_diaria INTEGER DEFAULT 0,
            alerta_favoritos INTEGER DEFAULT 0,
            departamento_filtro TEXT
        )
    """)
    db.commit()


def migrate_users_db():
    """Migración para agregar campos nuevos si no existen."""
    db = get_users_db()
    try:
        cursor = db.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]

        nuevas_columnas = [
            ("telefono", "TEXT"),
            ("foto_perfil", "TEXT"),
            ("dni", "TEXT"),
            ("fecha_nacimiento", "TEXT"),
            ("nacionalidad", "TEXT"),
            ("direccion", "TEXT"),
            ("codigo_postal", "TEXT"),
            ("ciudad", "TEXT"),
            ("provincia", "TEXT"),
            ("nivel_estudios", "TEXT"),
            ("titulacion", "TEXT"),
            ("situacion_laboral", "TEXT"),
            ("idiomas", "TEXT"),
            ("discapacidad", "INTEGER"),
            ("porcentaje_discapacidad", "INTEGER"),
        ]

        for columna, tipo in nuevas_columnas:
            if columna not in columns:
                db.execute(f"ALTER TABLE users ADD COLUMN {columna} {tipo}")
                print(f"✅ Columna '{columna}' agregada a la tabla users")

        db.commit()
        print("✅ Migración completada")
    except Exception as e:
        print(f"⚠️ Error en migración: {e}")


# =========================
# Cierre conexiones
# =========================


def teardown_appcontext(exception):
    boe_db = getattr(g, "_boe_db", None)
    if boe_db is not None:
        boe_db.close()

    users_db = getattr(g, "_users_db", None)
    if users_db is not None:
        users_db.close()
