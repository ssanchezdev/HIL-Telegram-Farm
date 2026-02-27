# utils.py
"""Utility functions used across the project.
Actualmente solo contiene la configuración básica de logging, pero se
pueden añadir más utilidades según crezca el proyecto.
"""

import logging
from logging import handlers
from pathlib import Path


def init_logging(log_file: Path, level: str = "INFO") -> None:
    """Configure basic logging to file and console."""
    # Nos aseguramos de que exista el directorio de logs
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    # Maneja la rotación de archivos para evitar logs gigantes
    file_handler = handlers.RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(root.level)
    # AÑADIR: encoding="utf-8"
    console_handler.set_name('console') # Añade un nombre si no lo tiene
    console_handler.stream.reconfigure(encoding='utf-8') # Asegura la reconfiguración del stream

    root.addHandler(file_handler)
    root.addHandler(console_handler)