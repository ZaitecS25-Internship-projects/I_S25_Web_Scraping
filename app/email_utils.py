from flask_mail import Message
from . import mail
from .db import get_users_db


def send_new_oposiciones_email(recipients, oposiciones):
    if not recipients or not oposiciones:
        return

    filas = []
    for o in oposiciones:
        titulo = o.get("titulo") or "(Sin título)"
        fecha = o.get("fecha") or ""
        url_html = o.get("url_html") or "#"
        url_pdf = o.get("url_pdf")
        dept = o.get("departamento") or ""
        pdf_html = f' | <a href="{url_pdf}">PDF</a>' if url_pdf else ""
        dept_html = f" — {dept}" if dept else ""
        filas.append(
            f'<li><strong>{titulo}</strong> — {fecha} — '
            f'<a href="{url_html}">HTML</a>{pdf_html}{dept_html}</li>'
        )

    lista_html = "".join(filas)
    html = (
        "<h3>Nuevas oposiciones publicadas</h3>"
        f"<p>Se han detectado {len(oposiciones)} nuevas oposiciones:</p>"
        f"<ul>{lista_html}</ul>"
        '<p style="font-size:12px;color:#666">'
        "Este es un mensaje automático, por favor no responda."
        "</p>"
    )

    subject = f"{len(oposiciones)} nuevas oposiciones publicadas"
    msg = Message(subject=subject, recipients=recipients, html=html)
    mail.send(msg)


def all_user_emails():
    db = get_users_db()
    return [r["email"] for r in db.execute("SELECT email FROM users").fetchall()]
