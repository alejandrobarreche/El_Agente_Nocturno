"""
Script principal para iniciar la simulación completa del sistema.
Ejecuta todos los componentes en sus respectivos procesos.
"""

import os
import time
import logging
import multiprocessing as mp
from pathlib import Path

import config
from server.central_server import CentralServer
from agents.spy import Spy
from agents.night_agent import NightAgent
from common.geo import generate_random_position

# Configurar logging
if not os.path.exists(config.LOGS_DIR):
    os.makedirs(config.LOGS_DIR)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(os.path.join(config.LOGS_DIR, "simulation.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("simulation")

def start_visualization():
    """Inicia el módulo de visualización si está habilitado en la configuración"""
    if config.VISUALIZATION_ENABLED:
        try:
            from visual.gui import start_gui
            return mp.Process(target=start_gui)
        except ImportError:
            logger.warning("Módulo de visualización no disponible")
            return None
    return None

def launch_server():
    server = CentralServer()
    server.start()

def launch_night_agent(agent_id, position):
    agent = NightAgent(agent_id, position)
    agent.run()

def launch_spy(spy_id, position):
    spy = Spy(spy_id, position)
    spy.run()

def main():
    """Función principal que inicia todos los componentes del sistema"""
    logger.info("Iniciando simulación del sistema de agentes encubiertos")

    # Lista para almacenar todos los procesos
    processes = []

    # Iniciar servidor central
    logger.info("Iniciando servidor central...")
    try:
        server_process = mp.Process(target=launch_server)
        server_process.start()
        if not server_process.is_alive():
            raise RuntimeError("El proceso del servidor central no se inició correctamente")
        processes.append(server_process)
    except Exception as e:
        logger.error(f"Error al iniciar el servidor central: {e}")
        return

    # Dar tiempo al servidor para iniciar
    time.sleep(2)

    # Iniciar agentes nocturnos
    logger.info(f"Iniciando {config.NUM_NIGHT_AGENTS} agentes nocturnos...")
    for i in range(config.NUM_NIGHT_AGENTS):
        try:
            position = generate_random_position()
            agent_id = f"AGENT{i+1:03d}"
            agent_process = mp.Process(
                target=launch_night_agent,
                args=(agent_id, position)
            )
            agent_process.start()
            if not agent_process.is_alive():
                raise RuntimeError(f"El proceso del agente nocturno {agent_id} no se inició correctamente")
            processes.append(agent_process)
        except Exception as e:
            logger.error(f"Error al iniciar el agente nocturno {i+1}: {e}")

    # Iniciar espías
    logger.info(f"Iniciando {config.NUM_SPIES} espías...")
    for i in range(config.NUM_SPIES):
        try:
            position = generate_random_position()
            spy_id = f"SPY{i+1:03d}"
            spy_process = mp.Process(
                target=launch_spy,
                args=(spy_id, position)
            )
            spy_process.start()
            if not spy_process.is_alive():
                raise RuntimeError(f"El proceso del espía {spy_id} no se inició correctamente")
            processes.append(spy_process)
        except Exception as e:
            logger.error(f"Error al iniciar el espía {i+1}: {e}")

    # Iniciar visualización si está habilitada
    vis_process = start_visualization()
    if vis_process:
        try:
            vis_process.start()
            if not vis_process.is_alive():
                raise RuntimeError("El proceso de visualización no se inició correctamente")
            processes.append(vis_process)
            logger.info("Visualización iniciada")
        except Exception as e:
            logger.error(f"Error al iniciar el módulo de visualización: {e}")

    # Esperar a que el usuario termine la simulación
    try:
        logger.info("Simulación en ejecución. Presione Ctrl+C para terminar.")
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        logger.info("Terminando simulación...")
        for p in processes:
            if p.is_alive():
                p.terminate()
        logger.info("Simulación terminada correctamente")

if __name__ == "__main__":
    main()