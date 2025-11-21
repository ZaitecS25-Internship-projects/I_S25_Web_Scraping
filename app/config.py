import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "cambia-esto-en-produccion")

    # Rutas de las dos bases de datos
    USERS_DB_PATH = os.getenv("USERS_DB_PATH", "usuarios.db")
    BOE_DB_PATH = os.getenv("BOE_DB_PATH", "oposiciones.db")

    # Flask-Mail (idealmente todo por variables de entorno)
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = os.getenv(
        "MAIL_USERNAME", "notificaciones.scraper@gmail.com")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "sqoj zfue ovcf dlhz")
    MAIL_DEFAULT_SENDER = MAIL_USERNAME
