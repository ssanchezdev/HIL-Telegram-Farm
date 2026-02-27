# main.py
from __future__ import annotations

import logging
import subprocess
import sys
import time
import re
import serial.tools.list_ports
from multiprocessing import Process
from pathlib import Path

from config import DBConfig, LoggingConfig, ModemConfig, FarmConfig, BASE_DIR
from modem_controller import ModemController
from db_manager import DBManager
from utils import init_logging

logger = logging.getLogger(__name__)

def get_available_serial_ports() -> list[str]:
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def is_valid_phone_number(number: str) -> bool:
    return bool(re.fullmatch(r'^\+?\d{7,20}$', number or ""))

def load_sim_list(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        logger.error(f"El archivo de configuración de SIMs '{path.name}' no fue encontrado.")
        return []
    sim_entries = []
    try:
        with path.open(encoding='utf-8') as txtfile:
            header = [h.strip() for h in txtfile.readline().strip().split(',')]
            for line in txtfile:
                parts = [p.strip() for p in line.strip().split(',')]
                if len(parts) == len(header):
                    sim_entries.append(dict(zip(header, parts)))
    except Exception as e:
        logger.error(f"Error al leer la lista de SIMs desde {path}: {e}")
    return sim_entries

def run_node_worker(phone_number: str, device_serial: str, appium_port: int):
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_name = log_dir / f"node_{device_serial}.log"
    logger.info(f"Iniciando worker para {phone_number} en dispositivo {device_serial}...")
    node_script_path = str(BASE_DIR / 'telegram_reader.js')
    command = ['node', node_script_path, phone_number, device_serial, str(appium_port)]
    try:
        with open(log_file_name, "w", encoding="utf-8") as log_file:
            process = subprocess.Popen(command, stdout=log_file, stderr=subprocess.STDOUT, text=True)
            process.wait(timeout=240)
            logger.info(f"Worker para {phone_number} en {device_serial} ha finalizado.")
    except subprocess.TimeoutExpired:
        logger.warning(f"Worker para {phone_number} en {device_serial} ha excedido el tiempo límite.")
        process.kill()
    except Exception as e:
        logger.error(f"Error al ejecutar worker para {phone_number}: {e}")

def main() -> None:
    init_logging(LoggingConfig.log_file, LoggingConfig.log_level)
    db_cfg = DBConfig()
    modem_cfg = ModemConfig()
    farm_cfg = FarmConfig()
    
    if db_cfg.results_file.exists():
        db_cfg.results_file.unlink()

    logger.info("--- Fase 1: Recolectando información de módems ---")
    if not modem_cfg.ports:
        modem_cfg.ports.extend(get_available_serial_ports())
    sim_data_map = {}
    for port in modem_cfg.ports:
        modem = ModemController(port, modem_cfg.baudrate, modem_cfg.timeout)
        try:
            modem.connect()
            modem.read_phone_number_from_modem()
            phone_number = modem._phone_number if is_valid_phone_number(modem._phone_number) else modem._sim_icc_id
            if phone_number:
                sim_data_map[port] = {"phone_number": phone_number, "modem_port": port}
                logger.info(f"Detectado en {port}: {phone_number}")
            else:
                logger.warning(f"No se pudo obtener un identificador válido para {port}.")
        except Exception as e:
            logger.error(f"Error durante la detección en {port}: {e}")
        finally:
            if modem.serial and modem.serial.is_open:
                modem.disconnect()

    logger.info("--- Fase 2: Mapeando SIMs a dispositivos ---")
    sim_device_associations = load_sim_list(db_cfg.sim_list)
    tasks = []
    device_map = {device['serial']: device for device in farm_cfg.devices}
    for association in sim_device_associations:
        device_serial = association.get('device_serial')
        modem_port = association.get('modem_port')
        sim_info = sim_data_map.get(modem_port)
        device_info = device_map.get(device_serial)
        if sim_info and device_info:
            tasks.append({**sim_info, **device_info})
        else:
            logger.warning(f"Se omitió la asociación para {modem_port} / {device_serial} por falta de datos.")
            
    if not tasks:
        logger.error("No se crearon tareas. Verifique sim_list.txt y los módems. Finalizando.")
        return
        
    logger.info(f"Se han creado {len(tasks)} tareas para procesar.")

    logger.info("--- Fase 3: Iniciando el monitor de SMS en segundo plano ---")
    temp_db = DBManager(db_cfg.results_file)
    for task in tasks:
        temp_db.append_result({
            "phone_number": task['phone_number'], "device_serial": task.get('serial', ''),
            "sim_number_icc_id": "", "modem_port": task.get('modem_port', ''), "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
    monitor_script_path = str(BASE_DIR / 'sms_monitor.py')
    monitor_process = subprocess.Popen([sys.executable, monitor_script_path])
    logger.info(f"Monitor de SMS iniciado (PID: {monitor_process.pid}). Esperando 10 segundos...")
    time.sleep(10)

    # --- INICIO DE LA CORRECCIÓN DE PARALELISMO ---
    logger.info("--- Fase 4: Lanzando TODOS los workers en paralelo ---")
    
    processes = []
    for task in tasks:
        p = Process(target=run_node_worker, args=(task['phone_number'], task['serial'], task['appium_port']))
        processes.append(p)
    
    # Primero se inician TODOS
    for p in processes:
        p.start()
        
    # Y después se espera a que TODOS terminen
    for p in processes:
        p.join()

    logger.info("--- Fase 5: Todos los workers han finalizado. Deteniendo monitor de SMS... ---")
    if monitor_process and monitor_process.poll() is None:
        monitor_process.terminate()
        try:
            monitor_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            monitor_process.kill()
        logger.info("Monitor de SMS detenido.")
    
    logger.info("=======================================")
    logger.info("=     PROCESO DE LA GRANJA COMPLETO     =")
    logger.info("=======================================")

if __name__ == "__main__":
    main()
