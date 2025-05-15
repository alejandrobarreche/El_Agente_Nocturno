"""
Implementación del cliente de sockets para el sistema de agentes encubiertos.

Este módulo proporciona la clase SocketClient que permite a los agentes
establecer conexiones con el servidor central usando sockets TCP/IP.
"""

import socket
import json
import logging
import pickle
import time
from typing import Any, Dict, Optional

from common.message import Message

logger = logging.getLogger(__name__)

class SocketClient:
    """Cliente de sockets para la comunicación con el servidor central."""

    def __init__(self, host='localhost', port=5000, buffer_size=4096, message_handler=None, max_message_size: int = 1048576):
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
        self.message_handler = message_handler
        self.max_message_size = max_message_size
        self.client_socket = None

    def connect(self) -> bool:
        """
        Establece una conexión con el servidor.

        Returns:
            bool: True si la conexión fue exitosa, False en caso contrario.
        """
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            logger.info(f"Conectado al servidor en {self.host}:{self.port}")
            return True
        except socket.error as e:
            logger.error(f"Error al conectar con el servidor: {e}")
            return False

    def _reconnect(self) -> bool:
        """
        Intenta reconectar con el servidor.

        Returns:
            bool: True si la reconexión fue exitosa, False en caso contrario.
        """
        logger.warning("Intentando reconectar con el servidor...")
        self.close()
        for attempt in range(3):  # Intentar reconectar 3 veces
            if self.connect():
                logger.info("Reconexión exitosa con el servidor")
                return True
            logger.warning(f"Reintento {attempt + 1}/3 fallido. Esperando...")
            time.sleep(2)
        logger.error("No se pudo reconectar con el servidor después de varios intentos")
        return False

    def send_message(self, message: Message) -> bool:
        """
        Envía un mensaje al servidor.

        Args:
            message: El mensaje a enviar.

        Returns:
            bool: True si el mensaje fue enviado exitosamente, False en caso contrario.
        """
        if not self.client_socket:
            logger.error("No hay conexión establecida con el servidor. Intentando reconectar...")
            if not self._reconnect():
                return False

        try:
            # Serializar el mensaje usando pickle para mantener la estructura del objeto
            serialized_message = pickle.dumps(message)

            # Enviar el tamaño del mensaje primero
            message_size = len(serialized_message)
            self.client_socket.sendall(message_size.to_bytes(4, byteorder='big'))

            # Luego enviar el mensaje completo
            self.client_socket.sendall(serialized_message)

            logger.debug(f"Mensaje enviado: {message}")
            return True
        except (socket.error, pickle.PickleError) as e:
            logger.error(f"Error al enviar mensaje: {e}")
            return False

    def receive_message(self) -> Optional[Message]:
        """
        Recibe un mensaje del servidor.

        Returns:
            Message: El mensaje recibido o None si ocurrió un error.
        """
        if not self.client_socket:
            logger.error("No hay conexión establecida con el servidor. Intentando reconectar...")
            if not self._reconnect():
                return None

        try:
            # Recibir primero el tamaño del mensaje
            size_bytes = self.client_socket.recv(4)
            if not size_bytes:
                logger.warning("Conexión cerrada por el servidor")
                return None

            message_size = int.from_bytes(size_bytes, byteorder='big')

            # Validar el tamaño del mensaje
            if message_size > self.max_message_size:
                logger.error(f"Mensaje recibido excede el tamaño máximo permitido ({message_size} bytes)")
                return None

            # Recibir el mensaje completo
            chunks = []
            bytes_received = 0
            while bytes_received < message_size:
                chunk = self.client_socket.recv(min(self.buffer_size, message_size - bytes_received))
                if not chunk:
                    logger.warning("Conexión cerrada por el servidor durante la recepción")
                    return None
                chunks.append(chunk)
                bytes_received += len(chunk)

            serialized_message = b''.join(chunks)
            message = pickle.loads(serialized_message)

            logger.debug(f"Mensaje recibido: {message}")
            return message
        except (socket.error, pickle.PickleError, ValueError) as e:
            logger.error(f"Error al recibir mensaje: {e}")
            return None

    def close(self) -> None:
        """Cierra la conexión con el servidor."""
        if self.client_socket:
            try:
                self.client_socket.close()
                logger.info("Conexión cerrada")
            except socket.error as e:
                logger.error(f"Error al cerrar la conexión: {e}")
            finally:
                self.client_socket = None

    def __enter__(self):
        """Permite usar el cliente con el contexto 'with'."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cierra la conexión al salir del contexto 'with'."""
        self.close()