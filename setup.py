from setuptools import setup, find_packages

setup(
    name="boe_oposiciones",
    version="0.1.0",
    description="Aplicación Flask para scraping del BOE y gestión de oposiciones con usuarios",
    packages=find_packages(exclude=["tests", "venv"]),
    include_package_data=True,
    install_requires=[
        "Flask==3.0.2",
        "Flask-Login==0.6.3",
        "Flask-Mail==0.9.1",
        "Werkzeug==3.0.1",
        "requests==2.31.0",
        "beautifulsoup4==4.12.2",
        "lxml==5.1.0",
        "itsdangerous==2.1.2",
        "Jinja2==3.1.3",
        "click==8.1.7",
        "MarkupSafe==2.1.5",
    ],
    entry_points={
        "console_scripts": [
            # Para poder ejecutar con: `boe-oposiciones`
            "boe-oposiciones = run:app.run",
        ]
    },
    python_requires=">=3.10",
)
