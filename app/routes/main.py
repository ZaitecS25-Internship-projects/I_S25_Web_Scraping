from datetime import datetime
from flask import Blueprint, render_template, flash, redirect, url_for, request
from flask_login import current_user, login_required

from ..db import get_boe_db, get_users_db
from ..scraping.boe_scraper import (
    scrape_boe_dia,
    scrape_boe_ultimos_dias,
    sync_boe_hasta_hoy,
)

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    try:
        # Sincronizar la BBDD con los días faltantes hasta hoy.
        # Si la tabla está vacía, `sync_boe_hasta_hoy` bajará hasta 30 días atrás.
        sync_boe_hasta_hoy(max_dias_inicial=30, max_dias_guardados=30)
    except Exception as e:
        # Usa logger si quieres
        print(f"Error al actualizar datos automáticamente: {e}")
    db = get_boe_db()
    hoy = datetime.today().strftime("%Y%m%d")
    deps = db.execute(
        """
        SELECT DISTINCT departamento
        FROM oposiciones
        WHERE departamento IS NOT NULL AND fecha = ?
        ORDER BY departamento
        """,
        (hoy,),
    ).fetchall()
    return render_template("index.html", departamentos=deps)


@main_bp.route("/departamento/<nombre>")
def mostrar_departamento(nombre):

    boe_db = get_boe_db()
    users_db = get_users_db()

    hoy = datetime.today().strftime("%Y%m%d")
    user = current_user
    busqueda = request.args.get("busqueda", "")
    provincia = request.args.get("provincia", "")
    orden = request.args.get("orden", "fecha_desc")
    page = int(request.args.get("page", 1))
    por_pagina = 10
    offset = (page - 1) * por_pagina

    # 🔥 SOLO oposiciones de hoy
    sql = "SELECT * FROM oposiciones WHERE departamento = ? AND fecha = ?"
    params = [nombre, hoy]

    # Filtro de búsqueda (opcional)
    if busqueda:
        like = f"%{busqueda}%"
        sql += " AND (titulo LIKE ? OR identificador LIKE ? OR control LIKE ?)"
        params += [like, like, like]

    # Filtro por provincia (opcional)
    if provincia:
        sql += " AND provincia = ?"
        params.append(provincia)

    # Orden + paginación
    if orden == "fecha_asc":
        order_direction = "ASC"
    elif orden == "fecha_desc":
        order_direction = "DESC"
    else:
        # Compatibilidad con valores antiguos
        order_direction = "DESC" if orden == "desc" else "ASC"
    
    sql += f" ORDER BY fecha {order_direction} LIMIT ? OFFSET ?"
    params += [por_pagina, offset]

    rows = boe_db.execute(sql, params).fetchall()

    # Total SOLO de hoy
    total = boe_db.execute(
        "SELECT COUNT(*) FROM oposiciones WHERE departamento = ? AND fecha = ?",
        (nombre, hoy),
    ).fetchone()[0]

    total_pages = (total + por_pagina - 1) // por_pagina

    # Provincias disponibles
    provincias = boe_db.execute(
        "SELECT DISTINCT provincia FROM oposiciones "
        "WHERE provincia IS NOT NULL ORDER BY provincia"
    ).fetchall()

    # Visitadas / Favoritas
    visitadas = []
    favoritas = []

    if user.is_authenticated:
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
        "tarjeta.html",
        departamento=nombre,
        rows=rows,
        page=page,
        total_pages=total_pages,
        provincias=provincias,
        busqueda=busqueda,
        provincia_filtro=provincia,
        orden=orden,
        hoy=hoy,
        visitadas=visitadas,
        favoritas=favoritas,
    )


@main_bp.route("/admin/scrape_ultimos_30")
@login_required
def admin_scrape_ultimos_30():
    nuevas = scrape_boe_ultimos_dias(30)
    flash(
        f"Se han insertado {len(nuevas)} oposiciones nuevas de los últimos 30 días.", "success")
    return redirect(url_for("user.oposiciones_vigentes"))


@main_bp.route("/estadisticas")
def estadisticas():
    boe_db = get_boe_db()
    users_db = get_users_db()

    visitas = users_db.execute(
        """
        SELECT oposicion_id, COUNT(id) AS total_visitas
        FROM visitas
        GROUP BY oposicion_id
        """
    ).fetchall()

    if not visitas:
        return render_template(
            "estadisticas.html",
            stats=[],
            labels=[],
            values=[],
        )

    opos_ids = [v["oposicion_id"] for v in visitas]
    placeholders = ",".join("?" * len(opos_ids))
    opos_rows = boe_db.execute(
        f"SELECT id, departamento FROM oposiciones WHERE id IN ({placeholders})",
        opos_ids,
    ).fetchall()
    dept_por_id = {row["id"]: row["departamento"] for row in opos_rows}

    agg = {}
    for v in visitas:
        dep = dept_por_id.get(v["oposicion_id"])
        if not dep:
            continue
        agg[dep] = agg.get(dep, 0) + v["total_visitas"]

    stats = [
        {"departamento": dep, "total_visitas": total}
        for dep, total in sorted(agg.items(), key=lambda x: x[1], reverse=True)
    ]
    labels = [s["departamento"] for s in stats]
    values = [s["total_visitas"] for s in stats]

    return render_template("estadisticas.html", stats=stats, labels=labels, values=values)


@main_bp.route("/admin/sync_boe")
@login_required
def admin_sync_boe():
    """
    Sincroniza la BBDD del BOE SOLO con los días que falten hasta hoy.
    Usa sync_boe_hasta_hoy y luego redirige a las oposiciones vigentes.
    """
    nuevas = sync_boe_hasta_hoy()  # por defecto, si está vacía baja hasta 30 días atrás
    flash(
        f"Sincronización completada. Insertadas {len(nuevas)} oposiciones nuevas.",
        "success",
    )
    return redirect(url_for("user.oposiciones_vigentes"))
