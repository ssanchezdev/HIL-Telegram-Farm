"""
Abstraction to communicate with a Quectel modem via AT commands.
Versión corregida que incluye el método read_sms y el borrado de mensajes.
"""
from __future__ import annotations
import logging
import time
import re
from typing import Dict, List, Optional
import serial

logger = logging.getLogger(__name__)

class ModemController:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial: Optional[serial.Serial] = None
        self._phone_number: Optional[str] = None
        self._sim_icc_id: Optional[str] = None

    def connect(self) -> None:
        logger.debug(f"Connecting to modem on {self.port}")
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            time.sleep(0.5) 
            self.send_command("AT", wait=0.2)
            self.send_command("ATE0", wait=0.2)
            self.send_command("AT+CMGF=1", wait=0.2)
            logger.info(f"Conectado y configurado módem en {self.port}.")
        except serial.SerialException as e:
            logger.error(f"Error al conectar con el módem en {self.port}: {e}")
            self.serial = None
            raise

    def disconnect(self) -> None:
        if self.serial and self.serial.is_open:
            logger.debug(f"Disconnecting from modem on {self.port}")
            self.serial.close()
            self.serial = None

    def send_command(self, command: str, wait: float = 0.5) -> str:
        """
        Envía un comando AT al módem y devuelve la respuesta.
        Añade depuración detallada para entender la comunicación.
        """
        if not self.serial or not self.serial.is_open:
            logger.error(f"Puerto {self.port} no está conectado. No se puede enviar el comando: {command}")
            return ""
        try:
            full_command = f"{command}\r\n"
            self.serial.write(full_command.encode('utf-8'))
            logger.debug(f"Enviado a {self.port}: '{command}'")
            
            time.sleep(wait)

            response_bytes = self.serial.read_all()
            response = response_bytes.decode('utf-8', errors='ignore').strip()
            
            logger.debug(f"Respuesta cruda (bytes) de {self.port}: {response_bytes.hex()}") 
            logger.debug(f"Respuesta decodificada de {self.port}: '{response}'")
            
            return response
        except Exception as e:
            logger.error(f"Error al enviar el comando '{command}' al módem en {self.port}: {e}", exc_info=True)
            return ""

    def read_phone_number_from_modem(self) -> None:
        """
        Intenta leer el número de teléfono (MSISDN) y el ICCID de la SIM.
        """
        self._phone_number = None
        self._sim_icc_id = None
        
        try:
            response_ccid = self.send_command("AT+CCID", wait=1.0)
            match_ccid = re.search(r'\d{18,22}', response_ccid)
            if match_ccid:
                self._sim_icc_id = match_ccid.group(0).strip()
                logger.info(f"ICCID encontrado para {self.port}: {self._sim_icc_id}")
            else:
                 logger.warning(f"No se pudo parsear un ICCID de la respuesta en {self.port}: '{response_ccid}'")
        except Exception as e:
            logger.error(f"Error al obtener ICCID en {self.port}: {e}")

        try:
            response_cnum = self.send_command("AT+CNUM", wait=2.0)
            match_cnum = re.search(r'\"(\+?\d{7,15})\"', response_cnum)
            if match_cnum:
                self._phone_number = match_cnum.group(1).strip()
                logger.info(f"Número de teléfono (CNUM) encontrado para {self.port}: {self._phone_number}")
                return
        except Exception as e:
            logger.error(f"Error al obtener número (CNUM) en {self.port}: {e}")
        
        try:
            response_cpbr = self.send_command("AT+CPBR=1", wait=2.0)
            match_cpbr = re.search(r'"(\+?\d{7,15})"', response_cpbr)
            if match_cpbr:
                self._phone_number = match_cpbr.group(1).strip()
                logger.info(f"Número de teléfono (CPBR) encontrado para {self.port}: {self._phone_number}")
                return
        except Exception as e:
            logger.error(f"Error al obtener número (CPBR) en {self.port}: {e}")

        if not self._phone_number:
            logger.warning(f"No se pudo determinar el número de teléfono para el módem en {self.port}.")

    def read_sms(self) -> List[Dict[str, str]]:
        """
        Lee todos los SMS almacenados y los ELIMINA después de leerlos.
        """
        if not self.serial or not self.serial.is_open:
            logger.warning(f"Puerto {self.port} no está conectado o abierto para leer SMS.")
            return []

        messages = []
        try:
            # Aumentamos significativamente el tiempo de espera para CMGL
            logger.debug(f"Enviando AT+CMGL=\"ALL\" a {self.port}...")
            response = self.send_command("AT+CMGL=\"ALL\"", wait=10.0) # <-- TIEMPO DE ESPERA AUMENTADO
            
            # Registrar la respuesta cruda para depuración
            if response:
                logger.debug(f"Respuesta cruda completa de CMGL en {self.port}:\n---INICIO_CMGL_RAW---\n{response}\n---FIN_CMGL_RAW---")
            else:
                logger.debug(f"Comando AT+CMGL=\"ALL\" en {self.port} no devolvió respuesta.")
            
            # Patrón más robusto para SMS. 
            sms_pattern = re.compile(
                r'\+CMGL:\s*(\d+),\"([^\"]*)\",\"([^\"]*)\",\"([^\"]*)\"\r\n(.*?)(?=\r\n\+CMGL:|\r\nOK|\r\nERROR|$)', 
                re.DOTALL | re.IGNORECASE
            )
            matches = sms_pattern.finditer(response)
            
            for match in matches:
                sms_index = match.group(1).strip()
                content = match.group(5).strip() 
                messages.append({"content": content, "index": sms_index}) 
                
                # Borrar el mensaje de la SIM para no procesarlo de nuevo.
                self.send_command(f"AT+CMGD={sms_index}", wait=0.5) 
                logger.debug(f"SMS con índice {sms_index} eliminado de {self.port}.")
        
        except Exception as e:
            logger.error(f"Error al leer o procesar SMS en {self.port}: {e}", exc_info=True)
        
        return messages
