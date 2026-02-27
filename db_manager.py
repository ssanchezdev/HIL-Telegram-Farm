"""Helpers for storing and retrieving results.

Este módulo gestiona la lectura y escritura de archivos CSV donde se
almacenan los números analizados y si requieren 2FA.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Dict


class DBManager:
    """Manejo sencillo de almacenamiento de resultados en CSV."""

    def __init__(self, results_path: Path) -> None:
        # Ruta donde se almacenarán los resultados
        self.results_path = results_path
        self.results_path.parent.mkdir(parents=True, exist_ok=True)

    def append_result(self, row: Dict[str, str]) -> None:
        """Append a row of data to the results CSV."""
        file_exists = self.results_path.exists()
        with self.results_path.open("a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=row.keys())
            # Se escribe la cabecera si el archivo aún no existe
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def read_results(self) -> Iterable[Dict[str, str]]:
        """Iterar sobre los resultados almacenados."""
        if not self.results_path.exists():
            return []
        with self.results_path.open(newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            yield from reader
