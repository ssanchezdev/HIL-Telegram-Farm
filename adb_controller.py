"""Basic wrapper around ADB commands.

Este módulo simplifica llamadas comunes a ADB para controlar
dispositivos Android desde Python.
"""

from __future__ import annotations

import logging
import subprocess
from typing import List

logger = logging.getLogger(__name__)


class ADBController:
    """Wrapper sencillo para ejecutar comandos ADB."""
    def __init__(self, adb_path: str = "adb") -> None:
        # Ruta al ejecutable de adb, por defecto se asume en PATH
        self.adb_path = adb_path

    def run(self, args: List[str]) -> str:
        """Run an adb command and return its output."""
        # Construye y ejecuta el comando, devolviendo la salida estándar
        cmd = [self.adb_path] + args
        logger.debug("Running command: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.stderr:
            logger.warning(result.stderr.strip())
        return result.stdout.strip()

    def list_connected_devices(self) -> List[str]:
        """Lista los seriales de los dispositivos ADB conectados actualmente."""
        output = self.run(["devices"])
        devices = []
        for line in output.splitlines():
            if line.strip() and not line.startswith("List of devices attached"):
                parts = line.split("\t")
                if len(parts) >= 2 and parts[1] == "device":
                    devices.append(parts[0])
        logger.info("Dispositivos ADB REALMENTE conectados: %s", devices)
        return devices

    def start_app(self, device: str, package: str) -> None:
        # Inicia una aplicación en el dispositivo utilizando 'monkey'
        self.run([
            "-s",
            device,
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ])

    def input_text(self, device: str, text: str) -> None:
        # Envía texto al dispositivo simulado como si fuera tipeado
        self.run(["-s", device, "shell", "input", "text", text])

    def tap(self, device: str, x: int, y: int) -> None:
        # Realiza un tap en las coordenadas indicadas
        self.run(["-s", device, "shell", "input", "tap", str(x), str(y)])