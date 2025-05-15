"""
Implementación del publicador (publisher) de RabbitMQ para el sistema de agentes encubiertos.

Este módulo proporciona la clase RabbitMQPublisher que permite a los agentes enviar
mensajes al servidor central a través del patrón publicador/suscriptor de RabbitMQ.
"""

import json
import logging
import pickle
import pika
from typing import Dict, Any, Optional
import time

from common.message import Message

logger = logging.getLogger(__name__)

class RabbitMQPublisher:
    """Publicador de mensajes usando RabbitMQ."""

    def __init__(self, host: str = 'localhost', port: int = 5672,
                 exchange: str = 'spy_alerts', exchange_type: str = 'topic',
                 username: str = 'guest', password: str = 'guest',
                 virtual_host: str = '/', connection_attempts: int = 3,
                 retry_delay: int = 5):
        """
        Inicializa un nuevo publicador de RabbitMQ.

        Args:
            host: La dirección IP o nombre de host del servidor RabbitMQ.
            port: El puerto del servidor RabbitMQ.
            exchange: El nombre del exchange a utilizar.
            exchange_type: El tipo de exchange (topic, direct, fanout, etc.).
            username: Nombre de usuario para la autenticación.
            password: Contraseña para la autenticación.
            virtual_host: Host virtual de RabbitMQ.
            connection_attempts: Número de intentos de conexión.
            retry_delay: Tiempo de espera entre intentos de conexión (segundos).
        """
        self.host = host
        self.port = port
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.credentials = pika.PlainCredentials(username, password)
        self.virtual_host = virtual_host
        self.connection_attempts = connection_attempts
        self.retry_delay = retry_delay

        self.connection = None
        self.channel = None
        self.failed_messages = []  # Cola local para mensajes no publicados

    def connect(self) -> bool:
        """
        Establece una conexión con el servidor RabbitMQ.

        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario.
        """
        try:
            # Parámetros de conexión
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                virtual_host=self.virtual_host,
                credentials=self.credentials,
                connection_attempts=self.connection_attempts,
                retry_delay=self.retry_delay
            )

            # Establecer la conexión
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declarar el exchange
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type=self.exchange_type,
                durable=True  # Persistente para mantener los mensajes si RabbitMQ se reinicia
            )

            logger.info(f"Conectado a RabbitMQ en {self.host}:{self.port}, exchange: {self.exchange}")
            return True

        except pika.exceptions.AMQPError as e:
            logger.error(f"Error al conectar con RabbitMQ: {e}")
            return False

    def _reconnect(self) -> bool:
        """
        Intenta reconectar con RabbitMQ.

        Returns:
            bool: True si la reconexión fue exitosa, False en caso contrario.
        """
        logger.warning("Intentando reconectar con RabbitMQ...")
        self.close()
        for attempt in range(self.connection_attempts):
            if self.connect():
                logger.info("Reconexión exitosa con RabbitMQ")
                return True
            logger.warning(f"Reintento {attempt + 1}/{self.connection_attempts} fallido. Esperando...")
            time.sleep(self.retry_delay)
        logger.error("No se pudo reconectar con RabbitMQ después de varios intentos")
        return False

    def publish_message(self, message: Message, routing_key: str = '') -> bool:
        """
        Publica un mensaje en el exchange.

        Args:
            message: El mensaje a publicar.
            routing_key: La clave de enrutamiento para el mensaje.

        Returns:
            bool: True si el mensaje fue publicado exitosamente, False en caso contrario.
        """
        if not self.connection or not self.channel:
            logger.error("No hay conexión establecida con RabbitMQ. Intentando reconectar...")
            if not self._reconnect():
                self.failed_messages.append((message, routing_key))
                logger.error("Mensaje almacenado en la cola local para reintento")
                return False

        try:
            # Si no hay routing_key específica, usar el tipo de mensaje como routing_key
            if not routing_key and hasattr(message, 'message_type'):
                routing_key = message.message_type

            # Serializar el mensaje
            serialized_message = pickle.dumps(message)

            # Propiedades del mensaje
            properties = pika.BasicProperties(
                delivery_mode=2,  # Persistente
                content_type='application/python-pickle',
                timestamp=int(time.time())
            )

            # Publicar el mensaje
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=serialized_message,
                properties=properties
            )

            logger.debug(f"Mensaje publicado con routing_key '{routing_key}': {message}")
            return True

        except (pika.exceptions.AMQPError, pickle.PickleError) as e:
            logger.error(f"Error al publicar mensaje: {e}")
            self.failed_messages.append((message, routing_key))
            logger.error("Mensaje almacenado en la cola local para reintento")
            return False

    def resend_failed_messages(self) -> None:
        """
        Reintenta publicar los mensajes almacenados en la cola local.
        """
        if not self.failed_messages:
            return

        logger.info(f"Reintentando publicar {len(self.failed_messages)} mensajes fallidos...")
        for message, routing_key in list(self.failed_messages):
            if self.publish_message(message, routing_key):
                self.failed_messages.remove((message, routing_key))
                logger.info(f"Mensaje reenviado exitosamente: {message}")

    def close(self) -> None:
        """Cierra la conexión con RabbitMQ."""
        if self.connection:
            try:
                self.connection.close()
                logger.info("Conexión con RabbitMQ cerrada")
            except pika.exceptions.AMQPError as e:
                logger.error(f"Error al cerrar la conexión con RabbitMQ: {e}")
            finally:
                self.connection = None
                self.channel = None

    def __enter__(self):
        """Permite usar el publicador con el contexto 'with'."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cierra la conexión al salir del contexto 'with'."""
        self.close()