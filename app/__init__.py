import os
from flask import Flask, session, request, redirect, url_for
from flask_mail import Mail
from flask_login import LoginManager, current_user

from .config import Config
from .db import init_boe_db, init_users_db, migrate_users_db

mail = Mail()
login_manager = LoginManager()


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "..", "static"),
    )
    app.config.from_object(Config)

    # Inicializar extensiones
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Crear directorio para fotos de perfil
    upload_folder = os.path.join(app.static_folder, "uploads", "profiles")
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder

    # Inicializar BBDD
    with app.app_context():
        init_boe_db()
        init_users_db()
        migrate_users_db()

    from .db import teardown_appcontext

    app.teardown_appcontext(teardown_appcontext)

    # ==== Tema claro / oscuro ====
    @app.before_request
    def ensure_theme():
        if "theme" not in session:
            session["theme"] = "light"

    @app.route("/toggle_theme")
    def toggle_theme():
        current = session.get("theme", "light")
        session["theme"] = "dark" if current == "light" else "light"
        return redirect(request.referrer or url_for("main.index"))

    # ==== Context processors ====
    @app.context_processor
    def inject_theme():
        return {"theme": session.get("theme", "light")}

    @app.context_processor
    def inject_user():
        return {"user": current_user}

    # ==== Filtros Jinja ====
    from datetime import datetime, date

    @app.template_filter("format_date")
    def format_date_filter(date_str):
        if not date_str or len(date_str) != 8 or not date_str.isdigit():
            return date_str
        try:
            year = date_str[0:4]
            month = date_str[4:6]
            day = date_str[6:8]
            return f"{day}/{month}/{year}"
        except Exception:
            return date_str

    @app.template_filter("es_reciente")
    def es_reciente(fecha_str, dias=0):
        try:
            f = datetime.strptime(fecha_str, "%Y%m%d").date()
            return (date.today() - f).days <= dias
        except Exception:
            return False

    @app.template_filter("resaltar_titulo")
    def resaltar_titulo(titulo):
        """Resalta palabras clave importantes en el título de las oposiciones"""
        import re

        if not titulo:
            return titulo

        # Palabras clave a resaltar
        palabras_clave = [
            r"\bconvocatoria\b",
            r"\boposiciones?\b",
            r"\bplazas?\b",
            r"\bacceso\b",
            r"\bproceso selectivo\b",
            r"\bfuncionarios?\b",
            r"\bcuerpo\b",
            r"\bescala\b",
            r"\bgrupo [A-C][12]?\b",
            r"\bturnos?\b",
            r"\blibre\b",
            r"\bpromoci[oó]n interna\b",
            r"\bdiscapacidad\b",
            r"\breserva\b",
            r"\bnombramientos?\b",
            r"\bceses?\b",
            r"\bampliac[ió]n\b",
            r"\bmodificac[ió]n\b",
            r"\banulaci[oó]n\b",
            r"\bcorrecc[ió]n\b",
            r"\bpresentac[ió]n\b",
            r"\badmisi[oó]n\b",
            r"\bexclusi[oó]n\b",
            r"\blista[s]?\b",
            r"\bsolicitantes?\b",
            r"\badmitidos?\b",
            r"\bexcluidos?\b",
            r"\btribunal\b",
            r"\bcalificac[ió]n\b",
            r"\bpruebas?\b",
            r"\bejercicio[s]?\b",
            r"\bexamen\b",
            r"\bresultados?\b",
            r"\bpuntuac[ió]n\b",
            r"\badjudicac[ió]n\b",
            r"\bdestinos?\b",
            r"\btraslados?\b",
            r"\bayuntamiento?\b"
        ]

        # Reemplazar cada palabra clave con versión en negrita
        resultado = titulo
        for patron in palabras_clave:
            resultado = re.sub(
                patron,
                lambda m: f'<strong>{m.group()}</strong>',
                resultado,
                flags=re.IGNORECASE,
            )

        return resultado

    # Registrar blueprints
    from .routes.main import main_bp
    from .routes.auth import auth_bp
    from .routes.user import user_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)

    return app