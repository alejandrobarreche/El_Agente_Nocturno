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

def main():
    """Función principal que inicia todos los componentes del sistema"""
    logger.info("Iniciando simulación del sistema de agentes encubiertos")

    # Lista para almacenar todos los procesos
    processes = []

    # Iniciar servidor central
    logger.info("Iniciando servidor central...")
    server_process = mp.Process(target=CentralServer().start)
    processes.append(server_process)
    server_process.start()

    # Dar tiempo al servidor para iniciar
    time.sleep(2)

    # Iniciar agentes nocturnos
    logger.info(f"Iniciando {config.NUM_NIGHT_AGENTS} agentes nocturnos...")
    for i in range(config.NUM_NIGHT_AGENTS):
        position = generate_random_position()
        agent_id = f"AGENT{i+1:03d}"
        agent_process = mp.Process(
            target=NightAgent(agent_id, position).run
        )
        processes.append(agent_process)
        agent_process.start()

    # Iniciar espías
    logger.info(f"Iniciando {config.NUM_SPIES} espías...")
    for i in range(config.NUM_SPIES):
        position = generate_random_position()
        spy_id = f"SPY{i+1:03d}"
        spy_process = mp.Process(
            target=Spy(spy_id, position).run
        )
        processes.append(spy_process)
        spy_process.start()

    # Iniciar visualización si está habilitada
    vis_process = start_visualization()
    if vis_process:
        processes.append(vis_process)
        vis_process.start()
        logger.info("Visualización iniciada")

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