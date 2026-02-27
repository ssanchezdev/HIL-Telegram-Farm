# config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict

BASE_DIR = Path(__file__).resolve().parent

class DBConfig:
    """Configuración de la base de datos."""
    results_file = BASE_DIR / "results.txt"
    sim_list = BASE_DIR / "sim_list.txt"

@dataclass
class ModemConfig:
    ports: List[str] = field(default_factory=list)
    baudrate: int = 115200
    timeout: float = 1.0

@dataclass
class FarmConfig:
    """Configuración de la granja de dispositivos y servidores Appium."""
    adb_path: str = "adb"
    
    # Lista final de dispositivos (Se reemplazan los seriales reales por variables de entorno o plantillas por seguridad)
    devices: List[Dict[str, any]] = field(default_factory=lambda: [
        {"serial": "DEVICE_SERIAL_01", "appium_port": 4723},
        {"serial": "DEVICE_SERIAL_02", "appium_port": 4724},
        {"serial": "DEVICE_SERIAL_03", "appium_port": 4725},
        {"serial": "DEVICE_SERIAL_04", "appium_port": 4726},
        {"serial": "DEVICE_SERIAL_05", "appium_port": 4727},
        {"serial": "DEVICE_SERIAL_06", "appium_port": 4728},
        {"serial": "DEVICE_SERIAL_07", "appium_port": 4729},
        {"serial": "DEVICE_SERIAL_08", "appium_port": 4730},
        {"serial": "DEVICE_SERIAL_09", "appium_port": 4731},
        {"serial": "DEVICE_SERIAL_10", "appium_port": 4732},
        #(Podríamos agregar más dispositivos aquí si es necesario)
    ])



class LoggingConfig:
    log_file = BASE_DIR / "sms.txt"
    log_level = "INFO"
