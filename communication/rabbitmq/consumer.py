"""
Implementación del consumidor (consumer) de RabbitMQ para el sistema de agentes encubiertos.

Este módulo proporciona la clase RabbitMQConsumer que permite al servidor central y a los
agentes nocturnos recibir mensajes a través del patrón publicador/suscriptor de RabbitMQ.
"""

import json
import logging
import pickle
import threading
import pika
from typing import Dict, Any, Optional, Callable, List, Union
import time

from common.message import Message

logger = logging.getLogger(__name__)

class RabbitMQConsumer:
    """Consumidor de mensajes usando RabbitMQ."""

    def __init__(self, host: str = 'localhost', port: int = 5672,
                 exchange: str = 'spy_alerts', exchange_type: str = 'topic',
                 queue_name: str = '', queue: str = '', binding_keys: List[str] = None,
                 username: str = 'guest', password: str = 'guest',
                 virtual_host: str = '/', connection_attempts: int = 3,
                 retry_delay: int = 5, auto_reconnect: bool = True):
        self.host = host
        self.port = port
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.queue_name = queue_name
        self.queue = queue
        self.binding_keys = binding_keys or ['#']
        self.username = username
        self.password = password
        self.credentials = pika.PlainCredentials(username, password)
        self.virtual_host = virtual_host
        self.connection_attempts = connection_attempts
        self.retry_delay = retry_delay
        self.auto_reconnect = auto_reconnect
        # Configuración adicional...

        self.connection = None
        self.channel = None
        self._consumer_tag = None
        self._is_consuming = False
        self._consume_thread = None
        self._callback_func = None

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
                durable=True  # Asegurar que el intercambio sea persistente
            )

            # Declarar la cola (si no se especifica nombre, se crea una cola anónima)
            result = self.channel.queue_declare(
                queue=self.queue_name,
                exclusive=not bool(self.queue_name),  # Exclusiva si es una cola anónima
                durable=bool(self.queue_name)  # Persistente solo si tiene nombre
            )

            # Si no se especificó un nombre de cola, usar el generado
            if not self.queue_name:
                self.queue_name = result.method.queue

            # Vincular la cola al exchange con las claves de enrutamiento
            for binding_key in self.binding_keys:
                self.channel.queue_bind(
                    exchange=self.exchange,
                    queue=self.queue_name,
                    routing_key=binding_key
                )

            logger.info(f"Conectado a RabbitMQ en {self.host}:{self.port}, exchange: {self.exchange}, cola: {self.queue_name}")
            logger.info(f"Escuchando mensajes con claves de enrutamiento: {', '.join(self.binding_keys)}")
            return True

        except pika.exceptions.AMQPError as e:
            logger.error(f"Error al conectar con RabbitMQ: {e}")
            return False

    def _message_handler(self, channel, method, properties, body):
        """
        Manejador interno de mensajes recibidos.

        Args:
            channel: El canal de RabbitMQ.
            method: Información del método de entrega.
            properties: Propiedades del mensaje.
            body: El cuerpo del mensaje.
        """
        try:
            # Deserializar el mensaje
            message = pickle.loads(body)

            # Si hay una función de callback registrada, llamarla con el mensaje
            if self._callback_func:
                self._callback_func(message, method.routing_key)

            # Confirmar el procesamiento del mensaje
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            # En caso de error, no confirmar el mensaje para que se reintente
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def start_consuming(self, callback: Callable[[Message, str], None]) -> bool:
        """
        Inicia el consumo de mensajes de forma asíncrona.

        Args:
            callback: Función que será llamada cuando se reciba un mensaje.
                     Debe aceptar dos parámetros: el mensaje y la clave de enrutamiento.

        Returns:
            bool: True si se inició correctamente el consumo, False en caso contrario.
        """
        if self._is_consuming:
            logger.warning("Ya se está consumiendo mensajes")
            return False

        if not self.connection or not self.channel:
            if not self.connect():
                return False

        try:
            # Registrar la función de callback
            self._callback_func = callback

            # Configurar el consumo de mensajes
            # prefetch_count=1 asegura que solo se procese un mensaje a la vez
            self.channel.basic_qos(prefetch_count=1)
            self._consumer_tag = self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=self._message_handler
            )

            # Iniciar el consumo en un hilo separado
            self._is_consuming = True
            self._consume_thread = threading.Thread(
                target=self._consume_messages,
                daemon=True,
                name=f"RabbitMQ-Consumer-{self.queue_name}"
            )
            self._consume_thread.start()

            logger.info(f"Consumidor iniciado para la cola {self.queue_name}")
            return True

        except pika.exceptions.AMQPError as e:
            logger.error(f"Error al iniciar el consumo de mensajes: {e}")
            self._is_consuming = False
            return False

    def _consume_messages(self):
        """
        Método interno para consumir mensajes en un hilo separado.
        """
        try:
            # Comienza a consumir mensajes (bloqueante)
            self.channel.start_consuming()
        except Exception as e:
            logger.error(f"Error durante el consumo de mensajes: {e}")
        finally:
            self._is_consuming = False

            # Intentar reconectar si está configurado
            if self.auto_reconnect and not self.connection.is_closed:
                logger.info("Intentando reconectar automáticamente...")
                time.sleep(self.retry_delay)
                if self._callback_func:
                    self.start_consuming(self._callback_func)

    def stop_consuming(self) -> bool:
        """
        Detiene el consumo de mensajes.

        Returns:
            bool: True si se detuvo correctamente, False en caso contrario.
        """
        if not self._is_consuming:
            logger.warning("No se está consumiendo mensajes actualmente")
            return False

        try:
            if self.channel and self._consumer_tag:
                self.channel.basic_cancel(self._consumer_tag)

            if self.connection and self.channel:
                self.channel.stop_consuming()

            # Esperar a que termine el hilo de consumo
            if self._consume_thread and self._consume_thread.is_alive():
                self._consume_thread.join(timeout=5.0)

            self._is_consuming = False
            self._consumer_tag = None
            logger.info("Consumo de mensajes detenido")
            return True

        except pika.exceptions.AMQPError as e:
            logger.error(f"Error al detener el consumo de mensajes: {e}")
            return False

    def close(self) -> None:
        """Detiene el consumo y cierra la conexión con RabbitMQ."""
        if self._is_consuming:
            self.stop_consuming()

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
        """Permite usar el consumidor con el contexto 'with'."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cierra la conexión al salir del contexto 'with'."""
        self.close()
