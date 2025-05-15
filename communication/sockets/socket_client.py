"""
Implementación del cliente de sockets para el sistema de agentes encubiertos.

Este módulo proporciona la clase SocketClient que permite a los agentes
establecer conexiones con el servidor central usando sockets TCP/IP.
"""

import socket
import json
import logging
import pickle
from typing import Any, Dict, Optional

from common.message import Message

logger = logging.getLogger(__name__)

class SocketClient:
    """Cliente de sockets para la comunicación con el servidor central."""

    def __init__(self, host: str = 'localhost', port: int = 5000, buffer_size: int = 4096):
        """
        Inicializa un nuevo cliente de sockets.

        Args:
            host: La dirección IP o nombre de host del servidor.
            port: El puerto del servidor.
            buffer_size: El tamaño del buffer para recibir datos.
        """
        self.host = host
        self.port = port
        self.buffer_size = buffer_size
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

    def send_message(self, message: Message) -> bool:
        """
        Envía un mensaje al servidor.

        Args:
            message: El mensaje a enviar.

        Returns:
            bool: True si el mensaje fue enviado exitosamente, False en caso contrario.
        """
        if not self.client_socket:
            logger.error("No hay conexión establecida con el servidor")
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
            logger.error("No hay conexión establecida con el servidor")
            return None

        try:
            # Recibir primero el tamaño del mensaje
            size_bytes = self.client_socket.recv(4)
            if not size_bytes:
                logger.warning("Conexión cerrada por el servidor")
                return None

            message_size = int.from_bytes(size_bytes, byteorder='big')

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