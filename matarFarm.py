# stop_farm.py
"""
Script de utilidad para detener forzosamente todos los procesos de la granja.
Este script buscará y terminará todos los procesos de 'node.exe' y los servidores
Appium ('node.exe' que ejecutan el main de Appium) que puedan haber quedado
corriendo en segundo plano.

Es un "botón de pánico" para limpiar el entorno y desbloquear los archivos de log.
"""
import subprocess
import platform
import os

def kill_processes_by_name(process_name: str):
    """Encuentra y elimina procesos por su nombre (para Windows)."""
    if platform.system() != "Windows":
        print("Este script está optimizado para Windows.")
        return

    try:
        # Comando para encontrar los procesos y sus PIDs
        command = f"tasklist | findstr /I {process_name}"
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        output = result.stdout.strip()
        if not output:
            print(f"No se encontraron procesos activos de '{process_name}'.")
            return

        print(f"Deteniendo procesos de '{process_name}'...")
        # Comando para matar todos los procesos con ese nombre
        kill_command = f"taskkill /F /IM {process_name}"
        subprocess.run(kill_command, shell=True, capture_output=True, text=True)
        print(f"Todos los procesos de '{process_name}' han sido detenidos.")

    except Exception as e:
        print(f"No se pudo detener los procesos de '{process_name}'. Error: {e}")

def main():
    """Función principal para detener todos los procesos de la granja."""
    print("==========================================")
    print("=   Deteniendo Todos los Procesos de la Granja   =")
    print("==========================================")
    
    # Node.js ejecuta tanto los workers como los servidores de Appium.
    # Detener todos los procesos 'node.exe' es la forma más efectiva de limpiar todo.
    kill_processes_by_name("node.exe")
    
    print("\nLimpieza completada. Ahora deberías poder acceder a los archivos de log.")

if __name__ == "__main__":
    main()
