from flask_mail import Message
from flask import url_for, render_template
from . import mail
from .db import get_users_db
from itsdangerous import URLSafeTimedSerializer
import os


def generate_reset_token(email):
    """Genera un token seguro para resetear contraseña"""
    serializer = URLSafeTimedSerializer(os.environ.get('SECRET_KEY', 'dev-secret-key'))
    return serializer.dumps(email, salt='password-reset-salt')


def verify_reset_token(token, expiration=3600):
    """Verifica el token y devuelve el email si es válido"""
    serializer = URLSafeTimedSerializer(os.environ.get('SECRET_KEY', 'dev-secret-key'))
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=expiration)
        return email
    except:
        return None


def send_password_reset_email(email, token):
    """Envía email con enlace para resetear contraseña"""
    reset_url = url_for('auth.reset_password', token=token, _external=True)
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #0d6efd;">Recuperación de Contraseña</h2>
        <p>Hola,</p>
        <p>Has solicitado restablecer tu contraseña en Oposiciones BOE.</p>
        <p>Haz clic en el siguiente botón para crear una nueva contraseña:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" 
               style="background-color: #0d6efd; color: white; padding: 12px 30px; 
                      text-decoration: none; border-radius: 5px; display: inline-block;">
                Restablecer Contraseña
            </a>
        </div>
        <p>O copia y pega este enlace en tu navegador:</p>
        <p style="word-break: break-all; color: #666;">{reset_url}</p>
        <p style="margin-top: 30px; font-size: 12px; color: #999;">
            Este enlace expirará en 1 hora por seguridad.<br>
            Si no solicitaste este cambio, puedes ignorar este correo.
        </p>
    </div>
    """
    
    msg = Message(
        subject="Recuperación de Contraseña - Oposiciones BOE",
        recipients=[email],
        html=html
    )
    mail.send(msg)


# 🔴 AQUÍ ESTÁ EL CAMBIO IMPORTANTE
def send_new_oposiciones_email(recipients, oposiciones):
    if not recipients or not oposiciones:
        return

    # Usamos la plantilla HTML en lugar de escribir el código aquí
    html_content = render_template('emails/nuevas_oposiciones.html', oposiciones=oposiciones)

    subject = f"📢 {len(oposiciones)} nuevas oposiciones encontradas"
    
    # Enviamos el mensaje (charset utf-8 importante para tildes)
    msg = Message(
        subject=subject, 
        recipients=recipients, 
        html=html_content,
        charset='utf-8'
    )
    mail.send(msg)


def all_user_emails():
    db = get_users_db()
    return [r["email"] for r in db.execute("SELECT email FROM users").fetchall()]