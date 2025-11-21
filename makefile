# Nombre del entorno virtual
VENV_DIR=venv
PYTHON=$(VENV_DIR)/bin/python
PIP=$(VENV_DIR)/bin/pip

# Si estás en Windows sin WSL, puedes ajustar rutas manualmente.

.PHONY: help install run lint freeze clean

help:
	@echo "Comandos disponibles:"
	@echo "  make install   - Crea venv (si no existe) e instala dependencias"
	@echo "  make run       - Ejecuta la aplicación Flask (run.py)"
	@echo "  make lint      - Chequeo rápido de sintaxis (compileall)"
	@echo "  make freeze    - Actualiza requirements.txt desde venv"
	@echo "  make clean     - Borra la venv"

$(VENV_DIR):
	@echo "📦 Creando entorno virtual en $(VENV_DIR)..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 -m venv $(VENV_DIR); \
	else \
		python -m venv $(VENV_DIR); \
	fi

install: $(VENV_DIR)
	@echo "📥 Instalando dependencias..."
	@$(PIP) install --upgrade pip
	@if [ -f requirements.txt ]; then \
		$(PIP) install -r requirements.txt; \
	else \
		$(PIP) install -e .; \
	fi
	@mkdir -p static/uploads/profiles
	@echo "✅ Entorno listo."

run:
	@echo "🚀 Arrancando la aplicación..."
	@$(PYTHON) run.py

lint:
	@echo "🔍 Chequeando sintaxis con compileall..."
	@$(PYTHON) -m compileall app || (echo "❌ Hay errores de sintaxis"; exit 1)
	@echo "✅ Sintaxis OK."

freeze:
	@echo "📄 Actualizando requirements.txt..."
	@$(PIP) freeze > requirements.txt
	@echo "✅ requirements.txt actualizado."

clean:
	@echo "🧹 Borrando entorno virtual..."
	@rm -rf $(VENV_DIR)
	@echo "✅ Limpiado."
