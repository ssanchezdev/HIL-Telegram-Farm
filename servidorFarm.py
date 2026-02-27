# start_farm.py
"""
Script de utilidad para iniciar todos los servidores Appium necesarios para la granja.
- Incluye una función para buscar y eliminar procesos que estén ocupando los
  puertos necesarios antes de iniciar nuevos servidores.
- Esto soluciona el error 'EADDRINUSE: address already in use'.
- Optimizado para Windows.
"""
import subprocess
import time
import platform
import os
import signal
from pathlib import Path

# Importar solo la configuración necesaria desde el archivo config
from config import FarmConfig, BASE_DIR

def kill_process_on_port(port: int):
    """Encuentra y elimina el proceso que ocupa un puerto específico (para Windows)."""
    if platform.system() != "Windows":
        # Esta implementación es específica para Windows.
        # Se puede añadir lógica para Linux/macOS si es necesario.
        return

    try:
        # Comando para encontrar el PID del proceso usando el puerto
        command = f"netstat -ano | findstr :{port}"
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        output = result.stdout.strip()
        if not output:
            # print(f"Puerto {port} ya está libre.")
            return

        # Extraer el PID
        lines = output.split('\n')
        for line in lines:
            if 'LISTENING' in line:
                parts = line.split()
                pid = parts[-1]
                print(f"Puerto {port} está ocupado por el proceso PID {pid}. Intentando detenerlo...")
                
                # Comando para matar el proceso por su PID
                kill_command = f"taskkill /PID {pid} /F"
                subprocess.run(kill_command, shell=True, capture_output=True, text=True)
                time.sleep(0.5) # Dar un momento para que el puerto se libere
                break

    except Exception as e:
        print(f"No se pudo limpiar el puerto {port}. Error: {e}")


def start_appium_server(port: int, log_file: Path):
    """Lanza una única instancia del servidor Appium."""
    
    kill_process_on_port(port)

    print(f"Iniciando servidor Appium en el puerto {port}... Log en: {log_file.name}")
    
    command_name = "appium.cmd" if platform.system() == "Windows" else "appium"
    command = [command_name, '-p', str(port)]
    
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            process = subprocess.Popen(command, stdout=f, stderr=subprocess.STDOUT)
        return process
    except FileNotFoundError:
        print(f"\nERROR CRÍTICO: El comando '{command_name}' no se encontró.\nAsegúrate de que Appium está instalado globalmente (npm install -g appium).\n")
        return None
    except Exception as e:
        print(f"\nERROR INESPERADO al lanzar Appium en el puerto {port}: {e}")
        return None

def main():
    """Función principal para iniciar todos los servidores de la granja."""
    print("=====================================================")
    print("=   Iniciando Servidores Appium (con auto-limpieza)   =")
    print("=====================================================")
    
    farm_cfg = FarmConfig()
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    processes = []
    
    for device in farm_cfg.devices:
        port = device['appium_port']
        log_file = log_dir / f"appium_{device['serial']}_{port}.log"
        
        proc = start_appium_server(port, log_file)
        
        if proc is None:
            print("\nDeteniendo el arranque de la granja debido a un error crítico.")
            for p in processes:
                p.terminate()
            time.sleep(2)
            print("Todos los servidores iniciados han sido detenidos.")
            return
            
        processes.append(proc)
        time.sleep(1)
        
    print(f"\nSe han lanzado {len(processes)} servidores Appium en segundo plano.")
    print("Ahora puedes ejecutar 'python main.py' en otra terminal.")
    print("\nIMPORTANTE: Para detener todos los servidores, cierra esta ventana (o presiona Ctrl+C).")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nDeteniendo todos los servidores Appium...")
        for p in processes:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("Todos los servidores han sido detenidos.")

if __name__ == "__main__":
    main()
