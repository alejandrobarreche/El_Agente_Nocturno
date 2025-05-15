"""
Implementación de la clase Spy (Espía).
Los espías son agentes encubiertos que generan alertas aleatorias.
"""

import random
import time
import logging
from threading import Thread, Event

import config
from common.message import Message, AlertMessage
from common.utils import generate_emergency, get_random_sleep_time, safe_sleep, setup_logger
from common.geo import generate_random_position, format_position

# Determinar el tipo de comunicación según configuración
if config.COMMUNICATION_MODE == "sockets":
    from communication.sockets.socket_client import SocketClient as CommunicationClient
else:  # "rabbitmq"
    from communication.rabbitmq.publisher import RabbitMQPublisher as CommunicationClient

# Validar configuraciones críticas al inicio del programa
def validate_config():
    """Valida que las configuraciones necesarias estén presentes"""
    required_keys = [
        "COMMUNICATION_MODE",
        "SOCKET_HOST",
        "SOCKET_PORT",
        "RABBITMQ_HOST",
        "RABBITMQ_PORT",
        "RABBITMQ_USER",
        "RABBITMQ_PASSWORD",
        "RABBITMQ_EXCHANGE",
        "MIN_ALERT_INTERVAL",
        "MAX_ALERT_INTERVAL",
        "MAP_MIN_LAT",
        "MAP_MAX_LAT",
        "MAP_MIN_LON",
        "MAP_MAX_LON"
    ]
    for key in required_keys:
        if not hasattr(config, key):
            raise ValueError(f"Falta la configuración requerida: {key}")

class Spy:
    """
    Clase que representa un agente encubierto (espía) que genera alertas.
    """

    def __init__(self, spy_id, position=None):
        """
        Inicializa un nuevo espía.

        Args:
            spy_id (str): Identificador único del espía
            position (tuple, optional): Coordenadas (lat, lon) iniciales
        """
        validate_config()  # Validar configuración al inicializar
        self.spy_id = spy_id
        self.position = position if position else generate_random_position()
        self.logger = setup_logger(f"spy.{spy_id}", f"spy_{spy_id}.log")
        self.stop_event = Event()
        self.comm_client = None

        self.logger.info(f"Espía {spy_id} inicializado en posición {format_position(self.position)}")

    def connect(self):
        """Establece conexión con el servidor según el modo configurado"""
        if config.COMMUNICATION_MODE == "sockets":
            self.comm_client = CommunicationClient(config.SOCKET_HOST, config.SOCKET_PORT)
        else:  # "rabbitmq"
            self.comm_client = CommunicationClient(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                username=config.RABBITMQ_USER,
                password=config.RABBITMQ_PASSWORD,
                exchange=config.RABBITMQ_EXCHANGE,
                routing_key="alerts"
            )
            connected = self.comm_client.connect()
            if not connected:
                self.logger.error("No se pudo establecer conexión con RabbitMQ")
                raise RuntimeError("Fallo en la conexión con RabbitMQ")
        self.logger.info(f"Conectado al servidor usando {config.COMMUNICATION_MODE}")

    def disconnect(self):
        """Cierra la conexión con el servidor"""
        if self.comm_client:
            self.comm_client.close()
            self.logger.info("Desconectado del servidor")

    def move_randomly(self):
        """
        Mueve el espía a una posición aleatoria cercana a su posición actual.
        """
        try:
            lat, lon = self.position
            lat_delta = random.uniform(-0.001, 0.001)
            lon_delta = random.uniform(-0.001, 0.001)

            new_lat = max(min(lat + lat_delta, config.MAP_MAX_LAT), config.MAP_MIN_LAT)
            new_lon = max(min(lon + lon_delta, config.MAP_MAX_LON), config.MAP_MIN_LON)

            self.position = (new_lat, new_lon)
            self.logger.debug(f"Nueva posición: {format_position(self.position)}")

            if new_lat == config.MAP_MIN_LAT or new_lat == config.MAP_MAX_LAT:
                self.logger.warning("El espía alcanzó el límite de latitud")
            if new_lon == config.MAP_MIN_LON or new_lon == config.MAP_MAX_LON:
                self.logger.warning("El espía alcanzó el límite de longitud")

        except AttributeError as e:
            self.logger.exception("Error en los límites del mapa: asegúrese de que MAP_MIN_LAT, MAP_MAX_LAT, etc., estén configurados")
            raise

    def generate_alert(self):
        """
        Genera y envía una alerta al servidor.
        """
        try:
            # Generar datos de emergencia
            level, emerg_type = generate_emergency()
        except Exception as e:
            self.logger.exception(f"Error al generar datos de emergencia: {e}")
            return

        # Crear mensaje
        message = AlertMessage(
            sender_id=self.spy_id,
            position=self.position,
            emergency_level=level,
            emergency_type=emerg_type
        )

        # Enviar alerta
        self.logger.info(f"Enviando alerta: {level} - {emerg_type} desde {format_position(self.position)}")
        self.comm_client.publish_message(message, routing_key="alert.vigilancia")

    def alert_loop(self):
        """
        Bucle principal que genera alertas periódicamente.
        """
        if not self.comm_client:
            self.logger.error("No hay conexión activa con el servidor. Abortando bucle de alertas.")
            return

        self.logger.info(f"Espía {self.spy_id} comenzando a enviar alertas")

        while not self.stop_event.is_set():
            try:
                # Generar y enviar alerta
                self.generate_alert()

                # Mover a nueva posición
                self.move_randomly()

                # Validar tiempos de espera
                min_interval = max(0, config.MIN_ALERT_INTERVAL)
                max_interval = max(min_interval, config.MAX_ALERT_INTERVAL)

                # Esperar un tiempo aleatorio antes de la siguiente alerta
                wait_time = get_random_sleep_time(min_interval, max_interval)
                self.logger.debug(f"[{self.spy_id}] Esperando {wait_time:.2f} segundos para la próxima alerta")

                # Esperar, pero permitiendo interrupciones
                safe_sleep(wait_time)
            except Exception as e:
                self.logger.exception(f"Error en el bucle de alertas: {e}")
        self.logger.info("Bucle de alertas detenido")

    def run(self):
        """
        Método principal para iniciar el espía.
        """
        try:
            self.connect()
            self.alert_loop()
        except KeyboardInterrupt:
            self.logger.info("Interrupción de teclado recibida")
        except Exception as e:
            self.logger.exception(f"Error en el espía {self.spy_id}: {e}")
        finally:
            self.disconnect()
            self.logger.info(f"Espía {self.spy_id} finalizado")

    def send_message(self, message: str):
        """Publica un mensaje en el intercambio configurado."""
        if not self.channel:
            raise RuntimeError("No hay conexión activa con RabbitMQ")
        self.channel.basic_publish(
            exchange=self.exchange,
            routing_key=self.routing_key,
            body=message
        )

    def stop(self):
        """
        Detiene el espía.
        """
        self.logger.info(f"Deteniendo espía {self.spy_id}")
        self.stop_event.set()