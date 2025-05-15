"""
Configuración global del sistema de agentes encubiertos.
Este archivo centraliza todas las constantes y configuraciones necesarias.
"""

import os
from pathlib import Path

# ===== RUTAS =====
BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# ===== SISTEMA =====
# Modo de comunicación: "sockets" o "rabbitmq"
COMMUNICATION_MODE = "rabbitmq"

# ===== SERVIDORES =====
# Configuración para servidor socket
SOCKET_HOST = "localhost"
SOCKET_PORT = 5555

# Configuración para RabbitMQ
RABBITMQ_HOST = "localhost"
RABBITMQ_PORT = 5672
RABBITMQ_USER = "guest"
RABBITMQ_PASSWORD = "guest"
RABBITMQ_EXCHANGE = "agents_exchange"
RABBITMQ_QUEUE_ALERTS = "alerts_queue"
RABBITMQ_QUEUE_TASKS = "tasks_queue"

# ===== AGENTES =====
# Número de agentes a simular
NUM_SPIES = 20
NUM_NIGHT_AGENTS = 10

# Tiempos (segundos)
MIN_ALERT_INTERVAL = 5
MAX_ALERT_INTERVAL = 20
MIN_TASK_DURATION = 10
MAX_TASK_DURATION = 30
SERVER_PROCESSING_TIME = 2

# ===== GEOGRÁFICOS =====
# Límites del mapa virtual (coordenadas geográficas)
MAP_MIN_LAT = 40.70
MAP_MAX_LAT = 40.80
MAP_MIN_LON = -74.05
MAP_MAX_LON = -73.95

# ===== EMERGENCIAS =====
# Niveles de emergencia y sus pesos para asignación
EMERGENCY_LEVELS = {
    "BAJA": 1,
    "MEDIA": 2,
    "ALTA": 3,
    "CRÍTICA": 4
}

# Tipos de emergencia
EMERGENCY_TYPES = [
    "VIGILANCIA",
    "INTRUSIÓN",
    "ROBO",
    "SECUESTRO",
    "AMENAZA_BOMBA"
]

# ===== VISUALIZACIÓN =====
# Configuración visual
VISUALIZATION_ENABLED = False
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 30

# Colores
COLOR_SPY = (0, 0, 255)        # Azul
COLOR_NIGHT_AGENT = (0, 255, 0) # Verde
COLOR_SERVER = (255, 0, 0)      # Rojo
COLOR_ALERT = (255, 255, 0)     # Amarillo
COLOR_TASK = (255, 165, 0)      # Naranja

# ===== LOGGING =====
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"