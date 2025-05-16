# """
# Implementación del servidor de sockets para el sistema de agentes encubiertos.
#
# Este módulo proporciona la clase SocketServer que permite al servidor central
# recibir conexiones y mensajes de los agentes mediante sockets TCP/IP.
# """
#
# import socket
# import threading
# import logging
# import pickle
# from typing import Callable, Optional, Dict, List, Tuple
# import time
#
# #from common.message import Message
#
# logger = logging.getLogger(__name__)
#
# class ClientHandler(threading.Thread):
#     """Manejador de conexiones de clientes individuales."""
#
#     def __init__(self, client_socket: socket.socket, address: Tuple[str, int],
#                  message_callback: Callable[[Message, Tuple[str, int]], None],
#                  buffer_size: int = 4096, max_message_size: int = 1048576):
#         """
#         Inicializa un nuevo manejador de cliente.
#
#         Args:
#             client_socket: El socket del cliente.
#             address: La dirección del cliente (ip, puerto).
#             message_callback: Función a llamar cuando se recibe un mensaje.
#             buffer_size: Tamaño del buffer para recibir datos.
#             max_message_size: Tamaño máximo permitido para los mensajes (en bytes).
#         """
#         super().__init__()
#         self.daemon = True
#         self.client_socket = client_socket
#         self.address = address
#         self.message_callback = message_callback
#         self.buffer_size = buffer_size
#         self.max_message_size = max_message_size
#         self.running = True
#
#     def run(self) -> None:
#         """Procesa los mensajes entrantes del cliente."""
#         logger.info(f"Cliente conectado desde {self.address[0]}:{self.address[1]}")
#
#         try:
#             while self.running:
#                 # Recibir primero el tamaño del mensaje
#                 size_bytes = self.client_socket.recv(4)
#                 if not size_bytes:
#                     logger.info(f"Cliente {self.address[0]}:{self.address[1]} desconectado")
#                     break
#
#                 message_size = int.from_bytes(size_bytes, byteorder='big')
#
#                 # Verificar si el tamaño del mensaje excede el límite
#                 if message_size > self.max_message_size:
#                     logger.error(f"Mensaje de {self.address[0]}:{self.address[1]} excede el tamaño máximo permitido ({message_size} bytes)")
#                     self.close()
#                     return
#
#                 # Recibir el mensaje completo
#                 chunks = []
#                 bytes_received = 0
#                 while bytes_received < message_size:
#                     chunk = self.client_socket.recv(min(self.buffer_size, message_size - bytes_received))
#                     if not chunk:
#                         logger.warning(f"Cliente {self.address[0]}:{self.address[1]} desconectado durante la recepción")
#                         return
#                     chunks.append(chunk)
#                     bytes_received += len(chunk)
#
#                 serialized_message = b''.join(chunks)
#
#                 try:
#                     # Deserializar el mensaje usando pickle
#                     message = pickle.loads(serialized_message)
#                     logger.debug(f"Mensaje recibido de {self.address[0]}:{self.address[1]}: {message}")
#
#                     # Llamar al callback con el mensaje recibido
#                     if self.message_callback:
#                         self.message_callback(message, self.address)
#
#                 except pickle.PickleError as e:
#                     logger.error(f"Error al deserializar mensaje de {self.address[0]}:{self.address[1]}: {e}")
#
#         except socket.error as e:
#             logger.error(f"Error en la conexión con {self.address[0]}:{self.address[1]}: {e}")
#
#         finally:
#             self.close()
#
#     def send_message(self, message: Message) -> bool:
#         """
#         Envía un mensaje al cliente.
#
#         Args:
#             message: El mensaje a enviar.
#
#         Returns:
#             bool: True si el mensaje fue enviado exitosamente, False en caso contrario.
#         """
#         if not self.running or not self.client_socket:
#             return False
#
#         try:
#             # Serializar el mensaje usando pickle
#             serialized_message = pickle.dumps(message)
#
#             # Enviar el tamaño del mensaje primero
#             message_size = len(serialized_message)
#             self.client_socket.sendall(message_size.to_bytes(4, byteorder='big'))
#
#             # Luego enviar el mensaje completo
#             self.client_socket.sendall(serialized_message)
#
#             logger.debug(f"Mensaje enviado a {self.address[0]}:{self.address[1]}: {message}")
#             return True
#
#         except (socket.error, pickle.PickleError) as e:
#             logger.error(f"Error al enviar mensaje a {self.address[0]}:{self.address[1]}: {e}")
#             return False
#
#     def close(self) -> None:
#         """Cierra la conexión con el cliente."""
#         self.running = False
#         if self.client_socket:
#             try:
#                 self.client_socket.close()
#                 logger.info(f"Conexión cerrada con {self.address[0]}:{self.address[1]}")
#             except socket.error as e:
#                 logger.error(f"Error al cerrar la conexión con {self.address[0]}:{self.address[1]}: {e}")
#
#
# class SocketServer:
#     """Servidor de sockets para la comunicación con los agentes."""
#
#     def __init__(self, host: str = '0.0.0.0', port: int = 5000,
#                  message_callback: Optional[Callable[[Message, Tuple[str, int]], None]] = None,
#                  max_connections: int = 10, buffer_size: int = 4096, max_message_size: int = 1048576):
#         """
#         Inicializa un nuevo servidor de sockets.
#
#         Args:
#             host: La dirección IP en la que escuchar (0.0.0.0 para todas las interfaces).
#             port: El puerto en el que escuchar.
#             message_callback: Función a llamar cuando se recibe un mensaje.
#             max_connections: Número máximo de conexiones en espera.
#             buffer_size: Tamaño del buffer para recibir datos.
#             max_message_size: Tamaño máximo permitido para los mensajes (en bytes).
#         """
#         self.host = host
#         self.port = port
#         self.message_callback = message_callback
#         self.max_connections = max_connections
#         self.buffer_size = buffer_size
#         self.max_message_size = max_message_size
#         self.server_socket = None
#         self.clients: Dict[Tuple[str, int], ClientHandler] = {}
#         self.running = False
#         self.accept_thread = None
#
#         # Métricas
#         self.connected_clients = 0
#
#     def start(self) -> bool:
#         """
#         Inicia el servidor y comienza a aceptar conexiones.
#
#         Returns:
#             bool: True si el servidor se inició correctamente, False en caso contrario.
#         """
#         try:
#             self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             # Permitir la reutilización del puerto
#             self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#             self.server_socket.bind((self.host, self.port))
#             self.server_socket.listen(self.max_connections)
#
#             self.running = True
#             logger.info(f"Servidor iniciado en {self.host}:{self.port}")
#
#             # Iniciar el hilo para aceptar conexiones
#             self.accept_thread = threading.Thread(target=self._accept_connections)
#             self.accept_thread.daemon = True
#             self.accept_thread.start()
#
#             return True
#
#         except socket.error as e:
#             logger.error(f"Error al iniciar el servidor: {e}")
#             return False
#
#     def _accept_connections(self) -> None:
#         """Acepta conexiones entrantes y crea manejadores para cada cliente."""
#         while self.running:
#             try:
#                 client_socket, address = self.server_socket.accept()
#
#                 # Crear un manejador para el cliente
#                 handler = ClientHandler(
#                     client_socket,
#                     address,
#                     self.message_callback,
#                     self.buffer_size,
#                     self.max_message_size
#                 )
#
#                 # Registrar el cliente
#                 self.clients[address] = handler
#                 self.connected_clients += 1
#                 logger.info(f"Cliente conectado desde {address[0]}:{address[1]}. Total clientes conectados: {self.connected_clients}")
#
#                 # Iniciar el hilo del manejador
#                 handler.start()
#
#             except socket.error as e:
#                 if self.running:  # Solo registrar errores si aún estamos en ejecución
#                     logger.error(f"Error al aceptar conexión: {e}")
#                     time.sleep(0.1)  # Evitar consumo excesivo de CPU en caso de error
#
#     def broadcast_message(self, message: Message) -> None:
#         """
#         Envía un mensaje a todos los clientes conectados.
#
#         Args:
#             message: El mensaje a enviar.
#         """
#         for address, handler in list(self.clients.items()):
#             if not handler.send_message(message):
#                 # Si falla el envío, eliminar el cliente
#                 logger.warning(f"No se pudo enviar mensaje a {address[0]}:{address[1]}, eliminando cliente")
#                 self.clients.pop(address, None)
#
#     def send_message_to(self, address: Tuple[str, int], message: Message) -> bool:
#         """
#         Envía un mensaje a un cliente específico.
#
#         Args:
#             address: La dirección del cliente (ip, puerto).
#             message: El mensaje a enviar.
#
#         Returns:
#             bool: True si el mensaje fue enviado exitosamente, False en caso contrario.
#         """
#         if address in self.clients:
#             return self.clients[address].send_message(message)
#         return False
#
#     def get_connected_clients(self) -> List[Tuple[str, int]]:
#         """
#         Obtiene la lista de clientes conectados.
#
#         Returns:
#             List[Tuple[str, int]]: Lista de direcciones de clientes conectados.
#         """
#         return list(self.clients.keys())
#
#     def stop(self) -> None:
#         """Detiene el servidor y cierra todas las conexiones."""
#         self.running = False
#
#         # Cerrar todas las conexiones con clientes
#         for address, handler in list(self.clients.items()):
#             handler.close()
#             self.connected_clients -= 1
#
#         self.clients.clear()
#
#         # Cerrar el socket del servidor
#         if self.server_socket:
#             try:
#                 self.server_socket.close()
#                 logger.info("Servidor detenido")
#             except socket.error as e:
#                 logger.error(f"Error al cerrar el socket del servidor: {e}")
#
#     def get_metrics(self) -> Dict[str, int]:
#         """
#         Devuelve las métricas del servidor.
#
#         Returns:
#             dict: Diccionario con las métricas del servidor.
#         """
#         return {
#             "connected_clients": self.connected_clients
#         }
#
#     def __enter__(self):
#         """Permite usar el servidor con el contexto 'with'."""
#         self.start()
#         return self
#
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         """Detiene el servidor al salir del contexto 'with'."""
#         self.stop()