"""
Utilidades y funciones auxiliares para el sistema.
"""

import os
import json
import logging
import random
import time
from datetime import datetime

import config
from common.constants import EmergencyLevel, EmergencyType

logger = logging.getLogger(__name__)

def setup_logger(name, log_file=None):
    """
    Configura y devuelve un logger personalizado.

    Args:
        name (str): Nombre del logger
        log_file (str, optional): Ruta al archivo de log específico

    Returns:
        logging.Logger: Logger configurado
    """
    logger = logging.getLogger(name)

    # Si ya tiene handlers, asumimos que ya está configurado
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.LOG_LEVEL))

    # Crear formatter
    formatter = logging.Formatter(config.LOG_FORMAT)

    # Añadir handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Añadir handler para archivo si se especifica
    if log_file:
        if not os.path.exists(config.LOGS_DIR):
            os.makedirs(config.LOGS_DIR)
        file_handler = logging.FileHandler(os.path.join(config.LOGS_DIR, log_file))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def generate_emergency():
    """
    Genera datos aleatorios para una emergencia.

    Returns:
        tuple: (nivel, tipo) de emergencia
    """
    level = random.choice(list(EmergencyLevel.keys()))
    emerg_type = random.choice(EmergencyType)
    return level, emerg_type

def get_timestamp():
    """
    Devuelve una marca de tiempo formateada.

    Returns:
        str: Timestamp en formato 'YYYY-MM-DD HH:MM:SS.mmm'
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

def get_random_sleep_time(min_time, max_time):
    """
    Genera un tiempo de espera aleatorio.

    Args:
        min_time (float): Tiempo mínimo en segundos
        max_time (float): Tiempo máximo en segundos

    Returns:
        float: Tiempo aleatorio entre min_time y max_time
    """
    return random.uniform(min_time, max_time)

def dict_to_json(data):
    """
    Convierte un diccionario a una cadena JSON.

    Args:
        data (dict): Diccionario a convertir

    Returns:
        str: Cadena JSON
    """
    return json.dumps(data)

def json_to_dict(json_str):
    """
    Convierte una cadena JSON a un diccionario. Intenta recuperar datos parciales si el JSON está mal formado.

    Args:
        json_str (str): Cadena JSON a convertir

    Returns:
        dict: Diccionario resultante o vacío si no se puede recuperar
    """
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Error decodificando JSON: {e}")
        logger.debug(f"Cadena problemática: {json_str}")

        # Intentar recuperar datos parciales
        try:
            # Eliminar caracteres problemáticos y volver a intentar
            cleaned_json_str = json_str.replace("\n", "").replace("\r", "").strip()
            return json.loads(cleaned_json_str)
        except json.JSONDecodeError as e2:
            logger.error(f"No se pudo recuperar datos parciales del JSON: {e2}")
            return {}

def safe_sleep(seconds):
    """
    Versión segura de time.sleep que maneja interrupciones.

    Args:
        seconds (float): Segundos a esperar
    """
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass

def save_failed_message(message):
    """
    Guarda un mensaje fallido en un archivo para análisis posterior.

    Args:
        message (Message): El mensaje que no se pudo enviar.
    """
    try:
        with open("failed_alerts.log", "a") as file:
            file.write(message.to_json() + "\n")
    except Exception as e:
        logger = setup_logger("failed_message_logger", "failed_messages.log")
        logger.error(f"Error al guardar el mensaje fallido: {e}")