# BOE Oposiciones — Scraper y Plataforma de Gestión

Proyecto Flask para extraer, almacenar y mostrar oposiciones del BOE (sección 2B).

Resumen
- Scraper que descarga el sumario del BOE por fecha y guarda registros en SQLite.
- Web app modular con blueprints `main`, `auth` y `user`.
- Dos bases de datos separadas: `oposiciones` (BOE) y `users` (usuarios, visitas, favoritas, suscripciones).
- Sincronización automática: al entrar en `/` la app sincroniza los días faltantes hasta hoy y mantiene una ventana de 30 días.

Estado: refactorizado a paquete `app/` con utilidades de bootstrap y scripts para desarrollo.

Estructura principal (rutas de archivos)
- `run.py` — (./run.py) Launcher: `app = create_app(); app.run(debug=True)`
- `app/__init__.py` — (./app/__init__.py) Fábrica de la aplicación: configuración, init DBs, registro de blueprints, context processors.
- `app/config.py` — (./app/config.py) Clase `Config` con settings y rutas a DBs.
- `app/db.py` — (./app/db.py) Conexiones y scripts de inicialización/migración de DBs (`get_boe_db`, `init_boe_db`, `get_users_db`, `init_users_db`).
- `app/email_utils.py` — (./app/email_utils.py) Envío de emails (resúmenes).
- `app/models.py` — (./app/models.py) `User` model + loader para `flask-login`.
- `app/routes/main.py` — (./app/routes/main.py) Rutas públicas y admin; `index()` invoca la sincronización (`sync_boe_hasta_hoy`).
- `app/routes/auth.py` — (./app/routes/auth.py) Registro / login / change password.
- `app/routes/user.py` — (./app/routes/user.py) Rutas protegidas de usuario: `user_oposiciones`, `user_alertas`, favoritos, etc.
- `app/scraping/boe_scraper.py` — (./app/scraping/boe_scraper.py) Scraper modular: `scrape_boe_dia`, `scrape_boe_ultimos_dias`, `sync_boe_hasta_hoy`.
- `templates/` — (./templates/) Plantillas Jinja (base.html, index.html, tarjeta.html, user_*.html, etc.).
- `static/` — (./static/) CSS, imágenes, uploads.

Requisitos y setup
1. Clona el repositorio y sitúate en la raíz del proyecto.
2. Usa el script de bootstrap o Makefile para preparar el entorno y dependencias.

Linux / macOS (recomendado):
```
bash bootstrap.sh
source venv/bin/activate
python run.py
```

Windows (PowerShell):
```
.\\bootstrap.bat
venv\\Scripts\\activate
python run.py
```

Opción Makefile (Unix):
```
make install
make run
```

Variables de entorno recomendadas
- `SECRET_KEY` — clave secreta Flask.
- `USERS_DB_PATH` — ruta a DB usuarios (por defecto `usuarios.db`).
- `BOE_DB_PATH` — ruta a DB oposiciones (por defecto `oposiciones.db`).
- `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_SERVER`, `MAIL_PORT` — configuración SMTP.

Funcionamiento clave
- `sync_boe_hasta_hoy(max_dias_inicial=30, max_dias_guardados=30)`
  - Si la tabla `oposiciones` está vacía, baja hasta `max_dias_inicial` días (por defecto 30).
  - Si ya hay datos, sincroniza desde el día siguiente al último guardado hasta hoy.
  - Al final borra registros anteriores al cutoff para mantener solo `max_dias_guardados` días.
- La ruta `/user_oposiciones` (vista `user`) muestra los datos de la BBDD y NO ejecuta scraping.

Limpieza del repositorio (evitar subir archivos innecesarios)
- El proyecto ahora incluye `.gitignore` para evitar commitear:
  - `venv/`, `*.pyc`, `__pycache__/`, `*.db`, `static/uploads/`, `.vscode/`, etc.
- Para eliminar archivos que ya están en el índice (p.ej. `venv` o `usuarios.db`), ejecuta localmente:
```
# Elimina del índice (deja los archivos en disco)
git rm -r --cached venv
git rm --cached usuarios.db
git rm --cached oposiciones.db
git add .gitignore README.md
git commit -m "chore: add .gitignore and README; remove venv and DB files from tracking"
```
- Si necesitas eliminar por completo archivos sensibles del historial (p.ej. credenciales o DBs), usa BFG o git filter-repo con precaución. Ejemplo con BFG:
```
# instalar BFG, luego:
bfg --delete-files usuarios.db
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```
Advertencia: reescribir history obliga a forzar push y romperá clones/PRs; coordina con tu equipo antes.

Cambios recientes en este commit (resumen)
- Refactor a package `app/` (routes, scraping, models, db, config).
- Añadidos scripts de bootstrap y Makefile.
- Añadida separación de BBDD y mejora de sincronización del scraper.

Contacto
- Si quieres que haga la limpieza completa del historial o que añada la sincronización en background, dime y preparo el parche.

End of README
