import logging
from pathlib import Path
import time
from typing import Dict, List, Set
import re

# Imports necesarios para que el script sea autoejecutable
from config import DBConfig, LoggingConfig, BASE_DIR
from utils import init_logging
from modem_controller import ModemController

logger = logging.getLogger(__name__)

def load_results_from_file(results_path: Path) -> List[Dict[str, str]]:
    """Lee el archivo results.txt y devuelve la información de los módems."""
    results = []
    try:
        with results_path.open(encoding='utf-8') as f:
            next(f)  # Saltar la cabecera
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 5:
                    results.append({
                        "phone_number": parts[0],
                        "device_serial": parts[1],
                        "sim_number_icc_id": parts[2],
                        "modem_port": parts[3],
                        "timestamp": parts[4]
                    })
    except FileNotFoundError:
        logger.error(f"El archivo de resultados no fue encontrado en: {results_path}")
    except Exception as e:
        logger.error(f"Error al leer el archivo results.txt: {e}")
    return results

def monitor_sms(modems: Dict[str, ModemController], results: List[Dict[str, str]]) -> None:
    """
    Monitorea SMS, extrae el código de Telegram y lo escribe en el archivo .txt
    preexistente en la carpeta 'numerosNode'.
    """
    logger.info("Iniciando bucle de monitoreo de SMS...")
    
    node_output_dir = BASE_DIR / "numerosNode"
    # Conjunto para mantener un registro de los contenidos de mensajes ya procesados
    # para evitar reprocesar el mismo SMS si el borrado de la SIM falla o si el mensaje es re-leído.
    logged_messages: Set[str] = set() 

    try:
        while True:
            logger.info("--- Nueva Ronda de Consultas ---")
            for entry in results:
                modem_port = entry.get("modem_port")
                phone_number = entry.get("phone_number", "N/A")

                if not modem_port or modem_port not in modems:
                    logger.debug(f"Saltando {modem_port}: no está en la lista de módems activos o es nulo.")
                    continue

                modem = modems[modem_port]
                try:
                    logger.info(f"Consultando buzón en {modem_port} (Asociado a {phone_number})...")
                    
                    # El modem_controller.read_sms() ahora borra los SMS de la SIM
                    # después de leerlos, por lo que solo deberíamos ver mensajes nuevos.
                    new_messages = modem.read_sms()
                    
                    if not new_messages:
                        logger.info(f"El buzón del módem {modem_port} está vacío o no hay nuevos SMS.")
                        continue

                    for msg in new_messages:
                        content = msg.get("content", "")
                        
                        # Evitar procesar el mismo mensaje si ya se ha visto.
                        if content in logged_messages:
                            logger.debug(f"Mensaje duplicado detectado y omitido en {modem_port}.")
                            continue

                        if "Telegram" in content or "Code" in content or "Código" in content: # Más genérico para Telegram
                            # Buscar códigos de 5 o 6 dígitos
                            code_match = re.search(r'(\d{5,6})', content) 
                            
                            if code_match and phone_number != "N/A_No_Number_Found":
                                telegram_code = code_match.group(1)
                                logger.info(f"¡CÓDIGO ENCONTRADO ({telegram_code}) para {phone_number} en {modem_port}! Actualizando archivo...")
                                
                                output_path = node_output_dir / f"{phone_number}.txt"
                                
                                # Asegurarse de que el directorio existe antes de escribir
                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                
                                # Escribe el código en el archivo (sobrescribiendo el archivo vacío/antiguo)
                                with open(output_path, "w", encoding="utf-8") as f:
                                    f.write(telegram_code)
                                
                                logger.info(f"Código actualizado en: {output_path}")
                                logged_messages.add(content) # Añadir el contenido a los mensajes ya procesados
                            else:
                                logger.warning(f"Mensaje de Telegram en {modem_port} sin código numérico válido o número de teléfono asociado para escribir. Contenido: '{content[:100]}...'")
                        else:
                            logger.info(f"Mensaje en {modem_port} descartado (no parece ser de Telegram). Contenido: '{content[:100]}...'")

                except Exception as e:
                    logger.error(f"Error al procesar el módem {modem_port}: {e}", exc_info=True) # Incluir stack trace

            logger.info("Ronda finalizada. Esperando 10 segundos para la siguiente ronda...")
            time.sleep(10) # Reducido a 10 segundos

    except KeyboardInterrupt:
        logger.info("Monitoreo detenido por el usuario.")
    except Exception as e:
        logger.critical(f"Error fatal en el bucle principal de monitoreo: {e}", exc_info=True)
    finally:
        logger.info("Desconectando todos los módems activos...")
        for modem in modems.values():
            modem.disconnect()
        logger.info("Monitoreo de SMS finalizado.")

if __name__ == "__main__":
    init_logging(LoggingConfig.log_file, LoggingConfig.log_level)
    
    logger.info("--- Iniciando Proceso de Monitoreo de SMS ---")
    
    results_file_path = DBConfig.results_file
    results_to_monitor = load_results_from_file(results_file_path)

    if not results_to_monitor:
        logger.error("El archivo results.txt está vacío o no se pudo leer. No se puede continuar.")
    else:
        # Asegura que el directorio numerosNode existe y crea archivos vacíos
        # para cada número, lo que el script de Node.js espera.
        node_output_dir = BASE_DIR / "numerosNode"
        node_output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Preparando archivos en '{node_output_dir.name}' para Node.js...")
        for entry in results_to_monitor:
            phone_number = entry.get("phone_number")
            if phone_number and phone_number != "N/A_No_Number_Found":
                output_path = node_output_dir / f"{phone_number}.txt"
                # Crea un archivo vacío si no existe, para que Node sepa qué procesar.
                # Si ya existe, `touch()` simplemente actualiza su timestamp.
                output_path.touch() 
                logger.debug(f"Archivo 'touch' para {phone_number}")
        logger.info("Archivos preparados.")

        logger.info(f"Se encontraron {len(results_to_monitor)} módems para monitorear.")
        
        active_modems = {}
        for entry in results_to_monitor:
            port = entry.get("modem_port")
            if port and port not in active_modems:
                try:
                    logger.info(f"Intentando conectar a {port}...")
                    modem = ModemController(port)
                    modem.connect()
                    active_modems[port] = modem
                    logger.info(f"Conexión exitosa en {port}.")
                except Exception as e:
                    logger.warning(f"Fallo al conectar con {port}: {e}")

        if active_modems:
            monitor_sms(active_modems, results_to_monitor)
        else:
            logger.error("No se pudo establecer conexión con ninguno de los módems listados. Finalizando.")
