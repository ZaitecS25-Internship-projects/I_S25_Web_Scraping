from datetime import datetime
import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from ..db import get_users_db
from ..models import User
from ..email_utils import send_password_reset_email, generate_reset_token, verify_reset_token

auth_bp = Blueprint("auth", __name__)


def create_user(
    email,
    password,
    name,
    apellidos,
    age,
    genero,
    telefono=None,
    dni=None,
    fecha_nacimiento=None,
    nacionalidad=None,
    nivel_estudios=None,
    titulacion=None,
    situacion_laboral=None,
    discapacidad=0,
    porcentaje_discapacidad=0,
):
    db = get_users_db()
    password_hash = generate_password_hash(password)
    db.execute(
        """
        INSERT INTO users (email, password_hash, name, apellidos, age, genero, telefono, dni,
                          fecha_nacimiento, nacionalidad, nivel_estudios, titulacion, situacion_laboral,
                          discapacidad, porcentaje_discapacidad) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            email.lower(),
            password_hash,
            name,
            apellidos,
            age,
            genero,
            telefono,
            dni,
            fecha_nacimiento,
            nacionalidad,
            nivel_estudios,
            titulacion,
            situacion_laboral,
            discapacidad,
            porcentaje_discapacidad,
        ),
    )
    db.commit()


def find_user_by_email(email):
    db = get_users_db()
    return db.execute(
        "SELECT * FROM users WHERE email = ?",
        (email.lower(),),
    ).fetchone()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = find_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            flash("Credenciales inválidas.", "danger")
            return redirect(url_for("auth.login"))
        login_user(
            User(
                user["id"],
                user["email"],
                user["name"],
                user["apellidos"],
                user["age"],
                user["genero"],
                user["telefono"],
                user["foto_perfil"],
                user["dni"],
                user["fecha_nacimiento"],
                user["nacionalidad"],
                user["direccion"],
                user["codigo_postal"],
                user["ciudad"],
                user["provincia"],
                user["nivel_estudios"],
                user["titulacion"],
                user["situacion_laboral"],
                user["idiomas"],
                user["discapacidad"],
                user["porcentaje_discapacidad"],
            )
        )
        flash("Sesión iniciada.", "success")
        next_url = request.args.get("next") or url_for("main.index")
        return redirect(next_url)
    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        name = (request.form.get("nombre") or "").strip()
        apellidos = (request.form.get("apellidos") or "").strip()
        age = (request.form.get("edad") or "")
        genero = (request.form.get("genero") or "").strip()

        dni = (request.form.get("dni") or "").strip()
        fecha_nacimiento = (request.form.get("fecha_nacimiento") or "").strip()
        nacionalidad = (request.form.get("nacionalidad") or "").strip()
        nivel_estudios = (request.form.get("nivel_estudios") or "").strip()
        situacion_laboral = (request.form.get(
            "situacion_laboral") or "").strip()

        telefono = (request.form.get("telefono") or "").strip() or None
        titulacion = (request.form.get("titulacion") or "").strip() or None
        discapacidad = 1 if request.form.get("discapacidad") == "si" else 0
        porcentaje_discapacidad = int(
            request.form.get("porcentaje_discapacidad", 0) or 0
        )

        if genero == "Otro":
            otro_genero = request.form.get("otro_genero", "").strip()
            if otro_genero:
                genero = otro_genero

        if not all(
            [
                email,
                password,
                name,
                apellidos,
                age,
                nivel_estudios,
            ]
        ):
            flash("¡Rellena todos los campos obligatorios!", "danger")
            return render_template("register.html", user=current_user)

        if find_user_by_email(email):
            flash("Ese email ya está registrado.", "warning")
            return render_template("register.html", user=current_user)

        create_user(
            email,
            password,
            name,
            apellidos,
            age,
            genero,
            telefono,
            nivel_estudios,
            titulacion,
        )

        user = find_user_by_email(email)

        foto_perfil = None
        if "foto_perfil" in request.files:
            file = request.files["foto_perfil"]
            if file and file.filename:
                allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
                filename = file.filename.lower()
                if "." in filename and filename.rsplit(".", 1)[1] in allowed_extensions:
                    filename = secure_filename(
                        f"user_{user['id']}_{int(datetime.now().timestamp())}."
                        f"{filename.rsplit('.', 1)[1]}"
                    )
                    upload_folder = current_app.config["UPLOAD_FOLDER"]
                    filepath = os.path.join(upload_folder, filename)
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                    file.save(filepath)
                    foto_perfil = f"/static/uploads/profiles/{filename}"

                    db = get_users_db()
                    db.execute(
                        "UPDATE users SET foto_perfil = ? WHERE id = ?",
                        (foto_perfil, user["id"]),
                    )
                    db.commit()

        user = find_user_by_email(email)
        login_user(
            User(
                user["id"],
                user["email"],
                user["name"],
                user["apellidos"],
                user["age"],
                user["genero"],
                user["telefono"],
                user["foto_perfil"],
                user["nivel_estudios"],
                user["titulacion"],
            )
        )
        flash("Registro correcto. Sesión iniciada.", "success")
        return redirect(url_for("main.index"))
    return render_template("register.html")


@auth_bp.route("/change_password", methods=["POST"])
@login_required
def change_password():
    db = get_users_db()
    user_id = current_user.id

    current_password = request.form.get("current_password")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")

    if not current_password or not new_password or not confirm_password:
        flash("Por favor, rellena todos los campos.", "danger")
        return redirect(url_for("user.configuracion_cuenta"))

    if new_password != confirm_password:
        flash("Las nuevas contraseñas no coinciden.", "danger")
        return redirect(url_for("user.configuracion_cuenta"))

    row = db.execute(
        "SELECT password_hash FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        flash("Usuario no encontrado.", "danger")
        return redirect(url_for("main.index"))

    stored_hash = row["password_hash"]

    if not check_password_hash(stored_hash, current_password):
        flash("La contraseña actual es incorrecta.", "danger")
        return redirect(url_for("user.configuracion_cuenta"))

    new_hash = generate_password_hash(new_password)
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (new_hash, user_id))
    db.commit()

    flash("¡Contraseña actualizada correctamente!", "success")
    return redirect(url_for("user.configuracion_cuenta"))


@auth_bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """Solicitud de recuperación de contraseña"""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        
        if not email:
            flash("Por favor, introduce tu correo electrónico.", "danger")
            return redirect(url_for("auth.forgot_password"))
        
        user = find_user_by_email(email)
        
        if user:
            token = generate_reset_token(email)
            try:
                send_password_reset_email(email, token)
                flash("Se ha enviado un correo con instrucciones para restablecer tu contraseña.", "success")
            except Exception as e:
                flash("Error al enviar el correo. Por favor, inténtalo más tarde.", "danger")
        else:
            # Por seguridad, mostramos el mismo mensaje aunque el email no exista
            flash("Se ha enviado un correo con instrucciones para restablecer tu contraseña.", "success")
        
        return redirect(url_for("auth.login"))
    
    return render_template("forgot_password.html")


@auth_bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Formulario para establecer nueva contraseña usando el token"""
    email = verify_reset_token(token)
    
    if not email:
        flash("El enlace de recuperación es inválido o ha expirado.", "danger")
        return redirect(url_for("auth.forgot_password"))
    
    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        if not new_password or not confirm_password:
            flash("Por favor, rellena todos los campos.", "danger")
            return redirect(url_for("auth.reset_password", token=token))
        
        if len(new_password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "danger")
            return redirect(url_for("auth.reset_password", token=token))
        
        if new_password != confirm_password:
            flash("Las contraseñas no coinciden.", "danger")
            return redirect(url_for("auth.reset_password", token=token))
        
        # Actualizar contraseña
        db = get_users_db()
        new_hash = generate_password_hash(new_password)
        db.execute(
            "UPDATE users SET password_hash = ? WHERE email = ?",
            (new_hash, email)
        )
        db.commit()
        
        flash("¡Contraseña restablecida correctamente! Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))
    
    return render_template("reset_password.html", token=token, email=email)
