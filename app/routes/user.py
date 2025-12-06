import os
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.scraping.boe_scraper import scrape_boe_ultimos_dias, sync_boe_hasta_hoy
from ..db import get_users_db, get_boe_db
from ..email_utils import send_new_oposiciones_email

user_bp = Blueprint("user", __name__)


# --- FUNCIONES AUXILIARES ---
def registrar_visita(user_id, oposicion_id):
    db = get_users_db()
    fecha = datetime.utcnow().isoformat()
    try:
        db.execute(
            "INSERT OR REPLACE INTO visitas (user_id, oposicion_id, fecha_visita) "
            "VALUES (?, ?, ?)",
            (user_id, oposicion_id, fecha),
        )
        db.commit()
    except Exception as e:
        print(f"Error al registrar visita: {e}")


def toggle_favorito(user_id, oposicion_id):
    db = get_users_db()
    fecha = datetime.utcnow().isoformat()
    try:
        cursor = db.execute(
            "DELETE FROM favoritas WHERE user_id = ? AND oposicion_id = ?",
            (user_id, oposicion_id),
        )
        if cursor.rowcount > 0:
            db.commit()
            return False
        db.execute(
            "INSERT INTO favoritas (user_id, oposicion_id, fecha_favorito) "
            "VALUES (?, ?, ?)",
            (user_id, oposicion_id, fecha),
        )
        db.commit()
        return True
    except Exception as e:
        print(f"Error al gestionar favorito: {e}")
        return False


# --- RUTAS ---

@user_bp.route("/user", methods=["GET", "POST"])
@login_required
def user_home():
    return render_template("user.html")


@user_bp.route("/user_oposiciones")
@login_required
def oposiciones_vigentes():
    boe_db = get_boe_db()
    users_db = get_users_db()
    user = current_user
    desde = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")

    page = int(request.args.get("page", 1))
    por_pagina = 10
    offset = (page - 1) * por_pagina

    raw_departamentos = request.args.getlist("departamentos")
    selected_departamentos = [d for d in raw_departamentos if d.strip()]

    busqueda = request.args.get("busqueda", "")
    provincia = request.args.get("provincia", "")
    fecha_desde = request.args.get("fecha_desde", "")
    fecha_hasta = request.args.get("fecha_hasta", "")
    orden = request.args.get("orden", "fecha_desc")

    sql_part = "FROM oposiciones WHERE fecha >= ?"
    params = [desde]

    if selected_departamentos:
        sql_part += " AND departamento IN ({})".format(
            ",".join(["?"] * len(selected_departamentos))
        )
        params.extend(selected_departamentos)

    if busqueda:
        like = f"%{busqueda}%"
        sql_part += " AND (titulo LIKE ? OR identificador LIKE ? OR control LIKE ?)"
        params += [like, like, like]

    if provincia:
        sql_part += " AND provincia = ?"
        params.append(provincia)

    if fecha_desde:
        sql_part += " AND fecha >= ?"
        params.append(fecha_desde.replace("-", ""))

    if fecha_hasta:
        sql_part += " AND fecha <= ?"
        params.append(fecha_hasta.replace("-", ""))

    total_query = f"SELECT COUNT(*) {sql_part}"
    total = boe_db.execute(total_query, params).fetchone()[0]
    total_pages = (total + por_pagina - 1) // por_pagina

    if orden == "fecha_asc":
        order_direction = "ASC"
    else:
        order_direction = "DESC"

    data_query = f"SELECT * {sql_part} ORDER BY fecha {order_direction} LIMIT ? OFFSET ?"
    data_params = params + [por_pagina, offset]
    oposiciones = boe_db.execute(data_query, data_params).fetchall()

    departamentos = boe_db.execute(
        """
        SELECT DISTINCT departamento 
        FROM oposiciones 
        WHERE fecha >= ? AND departamento IS NOT NULL 
        ORDER BY departamento
        """,
        (desde,),
    ).fetchall()

    provincias = boe_db.execute(
        "SELECT DISTINCT provincia FROM oposiciones "
        "WHERE provincia IS NOT NULL ORDER BY provincia"
    ).fetchall()

    visitadas = [
        row["oposicion_id"]
        for row in users_db.execute(
            "SELECT oposicion_id FROM visitas WHERE user_id = ?",
            (user.id,),
        ).fetchall()
    ]
    favoritas = [
        row["oposicion_id"]
        for row in users_db.execute(
            "SELECT oposicion_id FROM favoritas WHERE user_id = ?",
            (user.id,),
        ).fetchall()
    ]

    return render_template(
        "user_oposiciones.html",
        departamentos=departamentos,
        selected_departamentos=selected_departamentos,
        oposiciones=oposiciones,
        provincias=provincias,
        busqueda=busqueda,
        provincia_filtro=provincia,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        orden=orden,
        page=page,
        total_pages=total_pages,
        visitadas=visitadas,
        favoritas=favoritas,
        hoy=datetime.today().strftime("%Y%m%d"),
        titulo_pagina=f"📢 Oposiciones Vigentes de {user.name} {user.apellidos}",
        total=total
    )


@user_bp.route("/user_alertas", methods=["GET", "POST"])
@login_required
def newsletter_prefs():
    boe_db = get_boe_db()
    users_db = get_users_db()
    user_id = current_user.id

    if request.method == "POST":
        alerta_diaria = 1 if request.form.get("alerta_diaria") else 0
        # 🔴 ELIMINADO: ya no capturamos alerta_favoritos del formulario

        # Capturar lista múltiple de departamentos
        seleccionados = request.form.getlist("departamentos")
        
        if "Todos" in seleccionados or not seleccionados:
            dept_string = "Todos"
        else:
            dept_string = ",".join(seleccionados)

        # 🔴 ACTUALIZADO: La SQL ya no guarda alerta_favoritos explícitamente
        # (Se usará el valor por defecto de la tabla, que es 0)
        users_db.execute(
            """
            INSERT OR REPLACE INTO suscripciones (user_id, alerta_diaria, departamento_filtro)
            VALUES (?, ?, ?)
        """,
            (user_id, alerta_diaria, dept_string),
        )
        users_db.commit()
        flash("¡Preferencias de alertas actualizadas!", "success")
        return redirect(url_for("user.newsletter_prefs"))

    prefs = users_db.execute(
        "SELECT * FROM suscripciones WHERE user_id = ?", (user_id,)
    ).fetchone()

    if not prefs:
        prefs = {
            "alerta_diaria": 0,
            "departamento_filtro": "Todos",
        }

    dept_rows = boe_db.execute(
        "SELECT DISTINCT departamento FROM oposiciones WHERE departamento IS NOT NULL ORDER BY departamento"
    ).fetchall()
    departamentos = [d["departamento"] for d in dept_rows]

    return render_template(
        "user_newsletter.html",
        user=current_user,
        prefs=prefs,
        departamentos=departamentos,
    )


@user_bp.route("/user_configuracion")
@login_required
def configuracion_cuenta():
    return render_template("user_configuracion.html")


@user_bp.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    db = get_users_db()
    user = current_user

    name = request.form.get("name", "").strip()
    apellidos = request.form.get("apellidos", "").strip()
    telefono = request.form.get("telefono", "").strip()
    genero = request.form.get("genero", "").strip()

    dni = request.form.get("dni", "").strip()
    fecha_nacimiento = request.form.get("fecha_nacimiento", "").strip()
    nacionalidad = request.form.get("nacionalidad", "").strip()
    direccion = request.form.get("direccion", "").strip()
    codigo_postal = request.form.get("codigo_postal", "").strip()
    ciudad = request.form.get("ciudad", "").strip()
    provincia = request.form.get("provincia", "").strip()
    nivel_estudios = request.form.get("nivel_estudios", "").strip()
    titulacion = request.form.get("titulacion", "").strip()
    situacion_laboral = request.form.get("situacion_laboral", "").strip()

    idiomas_seleccionados = request.form.getlist("idiomas")
    otros_idiomas = request.form.get("otros_idiomas", "").strip()
    if otros_idiomas:
        idiomas_seleccionados.append(otros_idiomas)
    idiomas = ", ".join(idiomas_seleccionados) if idiomas_seleccionados else ""

    discapacidad = 1 if request.form.get("discapacidad") == "si" else 0
    porcentaje_discapacidad = int(
        request.form.get("porcentaje_discapacidad", 0) or 0
    )

    if genero == "Otro":
        otro_genero = request.form.get("otro_genero", "").strip()
        if otro_genero:
            genero = otro_genero

    foto_perfil = user.foto_perfil
    
    if "foto_perfil" in request.files:
        file = request.files["foto_perfil"]
        if file and file.filename:
            allowed_extensions = {"png", "jpg", "jpeg", "gif", "webp"}
            filename = file.filename.lower()
            if "." in filename and filename.rsplit(".", 1)[1] in allowed_extensions:
                
                filename = secure_filename(
                    f"user_{user.id}_{int(datetime.now().timestamp())}."
                    f"{filename.rsplit('.', 1)[1]}"
                )
                upload_folder = current_app.config["UPLOAD_FOLDER"]
                filepath = os.path.join(upload_folder, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                file.save(filepath)
                foto_perfil = f"/static/uploads/profiles/{filename}"

    db.execute(
        """
        UPDATE users 
        SET name = ?, apellidos = ?, telefono = ?, foto_perfil = ?, genero = ?,
            dni = ?, fecha_nacimiento = ?, nacionalidad = ?, direccion = ?, codigo_postal = ?,
            ciudad = ?, provincia = ?, nivel_estudios = ?, titulacion = ?, situacion_laboral = ?,
            idiomas = ?, discapacidad = ?, porcentaje_discapacidad = ?
        WHERE id = ?
    """,
        (
            name, apellidos, telefono, foto_perfil, genero,
            dni, fecha_nacimiento, nacionalidad, direccion, codigo_postal,
            ciudad, provincia, nivel_estudios, titulacion, situacion_laboral,
            idiomas, discapacidad, porcentaje_discapacidad,
            user.id,
        ),
    )
    db.commit()

    flash("Perfil actualizado correctamente", "success")
    return redirect(url_for("user.configuracion_cuenta"))


@user_bp.route("/marcar_visitada/<int:oposicion_id>", methods=["POST"])
@login_required
def marcar_visitada(oposicion_id):
    user_id = current_user.id
    registrar_visita(user_id, oposicion_id)
    return jsonify({"ok": True})


@user_bp.route("/toggle_favorito/<int:oposicion_id>", methods=["POST"])
@login_required
def toggle_favorito_route(oposicion_id):
    user = current_user
    is_favorite = toggle_favorito(user.id, oposicion_id)
    return jsonify({"ok": True, "is_favorite": is_favorite})


@user_bp.route("/user_favoritas")
@login_required
def oposiciones_favoritas():
    boe_db = get_boe_db()
    users_db = get_users_db()
    user = current_user

    # Filtros para la vista de favoritas
    desde = (datetime.today() - timedelta(days=30)).strftime("%Y%m%d")
    departamentos = boe_db.execute(
        "SELECT DISTINCT departamento FROM oposiciones WHERE fecha >= ? AND departamento IS NOT NULL ORDER BY departamento",
        (desde,),
    ).fetchall()
    provincias = boe_db.execute(
        "SELECT DISTINCT provincia FROM oposiciones WHERE provincia IS NOT NULL ORDER BY provincia"
    ).fetchall()

    fav_rows = users_db.execute(
        "SELECT oposicion_id, fecha_favorito FROM favoritas WHERE user_id = ?",
        (user.id,),
    ).fetchall()

    if not fav_rows:
        return render_template(
            "user_oposiciones.html",
            oposiciones=[],
            departamentos=departamentos,
            selected_departamentos=[],
            provincias=provincias,
            busqueda="",
            provincia_filtro="",
            fecha_desde="",
            fecha_hasta="",
            visitadas=[],
            favoritas=[],
            hoy=datetime.now().strftime("%Y-%m-%d"),
            total=0,
            page=1,
            total_pages=1,
            orden="desc",
            titulo_pagina=f"⭐ Oposiciones Favoritas de {user.name} {user.apellidos}",
        )

    opos_ids = [row["oposicion_id"] for row in fav_rows]
    placeholders = ",".join("?" * len(opos_ids))

    oposiciones = boe_db.execute(
        f"SELECT * FROM oposiciones WHERE id IN ({placeholders})",
        opos_ids,
    ).fetchall()

    fecha_por_id = {row["oposicion_id"]: row["fecha_favorito"] for row in fav_rows}

    oposiciones_ordenadas = sorted(
        oposiciones,
        key=lambda o: fecha_por_id.get(o["id"], ""),
        reverse=True,
    )

    visitadas = [
        row["oposicion_id"]
        for row in users_db.execute(
            "SELECT oposicion_id FROM visitas WHERE user_id = ?",
            (user.id,),
        ).fetchall()
    ]

    return render_template(
        "user_oposiciones.html",
        oposiciones=oposiciones_ordenadas,
        departamentos=departamentos,
        selected_departamentos=[],
        provincias=provincias,
        busqueda="",
        provincia_filtro="",
        fecha_desde="",
        fecha_hasta="",
        visitadas=visitadas,
        favoritas=[o["id"] for o in oposiciones_ordenadas],
        hoy=datetime.now().strftime("%Y-%m-%d"),
        total=len(oposiciones_ordenadas),
        page=1,
        total_pages=1,
        orden="desc",
        titulo_pagina=f"⭐ Oposiciones Favoritas de {user.name} {user.apellidos}",
    )


@user_bp.route("/enviar_resumen_ahora", methods=["POST"])
@login_required
def enviar_resumen_ahora():
    boe_db = get_boe_db()
    users_db = get_users_db()
    user = current_user

    prefs = users_db.execute(
        "SELECT * FROM suscripciones WHERE user_id = ?", (user.id,)
    ).fetchone()

    dept_filter_str = (
        prefs["departamento_filtro"]
        if prefs and prefs["departamento_filtro"]
        else "Todos"
    )

    fecha_busqueda = datetime.now().strftime("%Y%m%d")
    
    sql = "SELECT * FROM oposiciones WHERE fecha >= ?"
    params = [fecha_busqueda]

    # Lógica de limpieza y múltiples departamentos
    if dept_filter_str and dept_filter_str != "Todos":
        clean_str = dept_filter_str.replace("[", "").replace("]", "").replace("'", "").replace('"', "")
        lista_depts = [d.strip() for d in clean_str.split(',') if d.strip()]
        
        if lista_depts:
            placeholders = ','.join(['?'] * len(lista_depts))
            sql += f" AND departamento IN ({placeholders})"
            params.extend(lista_depts)

    sql += " ORDER BY fecha DESC LIMIT 200"
    rows = boe_db.execute(sql, params).fetchall()

    oposiciones = [dict(row) for row in rows]

    if oposiciones:
        try:
            send_new_oposiciones_email([user.email], oposiciones)
            flash(
                f"✅ Email enviado correctamente a {user.email} con {len(oposiciones)} oposiciones recientes.",
                "success",
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            flash(f"❌ Error al enviar email: {e}", "danger")
    else:
        flash(f"⚠️ No se encontraron oposiciones publicadas hoy para: {dept_filter_str}", "warning")

    return redirect(url_for("user.newsletter_prefs"))