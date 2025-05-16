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
from communication.rabbitmq import RabbitMQPublisher

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
    def __init__(self, spy_id, position=None):
        self.spy_id = spy_id
        self.position = position or generate_random_position()
        self.logger = setup_logger(f"spy.{spy_id}", f"spy_{spy_id}.log")
        self.stop_event = Event()
        self.comm_client = None
        self.logger.info(f"Esp\u00eda {spy_id} inicializado en posici\u00f3n {format_position(self.position)}")

    def connect(self):
        if config.COMMUNICATION_MODE == "sockets":
            self.comm_client = CommunicationClient(config.SOCKET_HOST, config.SOCKET_PORT)
        else:
            self.comm_client = RabbitMQPublisher(
                host=config.RABBITMQ_HOST,
                port=config.RABBITMQ_PORT,
                username=config.RABBITMQ_USER,
                password=config.RABBITMQ_PASSWORD,
                exchange='night_tasks',
                exchange_type='topic'
            )
            if not self.comm_client.connect():
                self.logger.error("No se pudo establecer conexi\u00f3n con RabbitMQ")
                raise RuntimeError("Fallo en la conexi\u00f3n con RabbitMQ")
        self.logger.info(f"Conectado al servidor usando {config.COMMUNICATION_MODE}")

    def disconnect(self):
        if self.comm_client:
            self.comm_client.close()
            self.logger.info("Desconectado del servidor")

    def move_randomly(self):
        try:
            lat, lon = self.position
            lat_delta = random.uniform(-0.001, 0.001)
            lon_delta = random.uniform(-0.001, 0.001)
            new_lat = max(min(lat + lat_delta, config.MAP_MAX_LAT), config.MAP_MIN_LAT)
            new_lon = max(min(lon + lon_delta, config.MAP_MAX_LON), config.MAP_MIN_LON)
            self.position = (new_lat, new_lon)
            self.logger.debug(f"Nueva posici\u00f3n: {format_position(self.position)}")
            if new_lat in [config.MAP_MIN_LAT, config.MAP_MAX_LAT]:
                self.logger.warning("El esp\u00eda alcanz\u00f3 el l\u00edmite de latitud")
            if new_lon in [config.MAP_MIN_LON, config.MAP_MAX_LON]:
                self.logger.warning("El esp\u00eda alcanz\u00f3 el l\u00edmite de longitud")
        except AttributeError:
            self.logger.exception("Error en los l\u00edmites del mapa")
            raise


    def generate_alert(self):
        try:
            level, emerg_type = generate_emergency()
        except Exception as e:
            self.logger.exception(f"Error al generar emergencia: {e}")
            return

        message = AlertMessage(
            sender_id=self.spy_id,
            position=self.position,
            emergency_level=level,
            emergency_type=emerg_type
        )

        json_message = message.to_json().encode("utf-8")
        self.logger.info(f"Enviando alerta: {level} - {emerg_type} desde {format_position(self.position)}")

        try:
            if hasattr(self.comm_client, "publish_message"):
                self.comm_client.publish_message(message, routing_key='task.broadcast')
            elif hasattr(self.comm_client, "publish"):
                self.comm_client.publish(message, routing_key='task.broadcast')
            else:
                self.logger.error("Cliente de comunicaci\u00f3n no soporta publicaci\u00f3n de mensajes")
        except Exception as e:
            self.logger.exception(f"Error al enviar la alerta: {e}")

    def alert_loop(self):
        if not self.comm_client:
            self.logger.error("No hay conexi\u00f3n activa con el servidor.")
            return

        self.logger.info(f"Esp\u00eda {self.spy_id} comenzando a enviar alertas")

        while not self.stop_event.is_set():
            try:
                self.generate_alert()
                self.move_randomly()
                min_interval = max(0, config.MIN_ALERT_INTERVAL)
                max_interval = max(min_interval, config.MAX_ALERT_INTERVAL)
                wait_time = get_random_sleep_time(min_interval, max_interval)
                self.logger.debug(f"[{self.spy_id}] Esperando {wait_time:.2f}s para la pr\u00f3xima alerta")
                safe_sleep(wait_time)
            except Exception as e:
                self.logger.exception(f"Error en el bucle de alertas: {e}")

        self.logger.info("Bucle de alertas detenido")

    def run(self):
        try:
            self.connect()
            self.alert_loop()
        except KeyboardInterrupt:
            self.logger.info("Interrupci\u00f3n de teclado recibida")
        except Exception as e:
            self.logger.exception(f"Error en el esp\u00eda {self.spy_id}: {e}")
        finally:
            self.disconnect()
            self.logger.info(f"Esp\u00eda {self.spy_id} finalizado")

    def stop(self):
        self.logger.info(f"Deteniendo esp\u00eda {self.spy_id}")
        self.stop_event.set()
