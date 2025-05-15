"""
Implementación de la clase NightAgent (Agente Nocturno).
Los agentes nocturnos son los encargados de atender las alertas.
"""

import time
import logging
import threading
import random

import config
from common.message import Message, StatusMessage
from common.utils import safe_sleep, get_random_sleep_time, setup_logger
from common.geo import format_position, generate_random_position
from communication.rabbitmq.publisher import RabbitMQPublisher
# Determinar el tipo de comunicación según configuración
if config.COMMUNICATION_MODE == "sockets":
    from communication.sockets.socket_client import SocketClient as CommunicationClient
else:  # "rabbitmq"
    from communication.rabbitmq.consumer import RabbitMQConsumer as CommunicationClient

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
        "RABBITMQ_QUEUE_TASKS",
        "MIN_TASK_DURATION",
        "MAX_TASK_DURATION"
    ]
    for key in required_keys:
        if not hasattr(config, key):
            raise ValueError(f"Falta la configuración requerida: {key}")

class NightAgent:
    """
    Clase que representa un agente nocturno que atiende alertas.
    """

    def __init__(self, agent_id, position=None):
        """
        Inicializa un nuevo agente nocturno.

        Args:
            agent_id (str): Identificador único del agente
            position (tuple, optional): Coordenadas (lat, lon) iniciales
        """
        self.agent_id = agent_id
        self.position = position if position else generate_random_position()
        self.logger = setup_logger(f"night_agent.{agent_id}", f"agent_{agent_id}.log")
        self.busy = False
        self.stop_event = threading.Event()
        self.comm_client = None
        self.task_thread = None
        self.publisher = None

        self.logger.info(f"Agente {agent_id} inicializado en posición {format_position(self.position)}")

    def connect(self):
        """Establece conexión con el servidor según el modo configurado"""
        try:
            # Inicializar el publisher para RabbitMQ (se usará con ambos modos)
            if config.COMMUNICATION_MODE == "rabbitmq":
                self.publisher = RabbitMQPublisher(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    exchange='agent_status',
                    exchange_type='topic',
                    username=config.RABBITMQ_USER,
                    password=config.RABBITMQ_PASSWORD
                )
                self.publisher.connect()

                # Inicializar el consumidor de RabbitMQ
                self.comm_client = CommunicationClient(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    username=config.RABBITMQ_USER,
                    password=config.RABBITMQ_PASSWORD,
                    exchange='night_tasks',
                    exchange_type='direct',
                    queue_name=f"queue_{self.agent_id}",      # Cada agente escucha su propia cola
                    binding_keys=[self.agent_id]              # Solo escucha mensajes dirigidos a él
                )
            else:  # Socket mode
                self.comm_client = CommunicationClient(
                    host=config.SOCKET_HOST,
                    port=config.SOCKET_PORT,
                    message_handler=self.handle_task  # Pasar el manejador al constructor
                )
                # Para sockets, usamos el mismo cliente para enviar actualizaciones de estado
                self.publisher = self.comm_client

            self.logger.info(f"Conectado al servidor usando {config.COMMUNICATION_MODE}")
        except Exception as e:
            self.logger.exception(f"Error al conectar con el servidor: {e}")
            raise

    def disconnect(self):
        """Cierra la conexión con el servidor"""
        if self.comm_client:
            self.comm_client.close()
            self.logger.info("Desconectado del servidor")

        if self.publisher and self.publisher != self.comm_client:
            self.publisher.close()
            self.logger.info("Cerrada conexión del publisher")

    def send_status_update(self, is_busy):
        """
        Envía una actualización de estado al servidor.

        Args:
            is_busy (bool): True si el agente está ocupado, False si está disponible
        """
        status = "BUSY" if is_busy else "AVAILABLE"

        message = StatusMessage(
            sender_id=self.agent_id,
            position=self.position,
            status=status
        )

        # Enviar actualización de estado según el modo de comunicación
        try:
            if config.COMMUNICATION_MODE == "sockets":
                if hasattr(self.publisher, 'send_message'):
                    self.publisher.send_message(message.to_json())
                else:
                    self.logger.error("Cliente socket no tiene método send_message")
            else:  # rabbitmq
                if self.publisher:
                    self.publisher.publish_message(
                        message.to_json(),
                        routing_key=f"status.{self.agent_id}"
                    )
                else:
                    self.logger.error("Publisher de RabbitMQ no inicializado")

            self.logger.debug(f"Estado actualizado a {status}")
        except Exception as e:
            self.logger.exception(f"Error al enviar actualización de estado: {e}")

    def handle_task(self, task_json):
        """
        Manejador de tareas recibidas del servidor.

        Args:
            task_json (str): Mensaje JSON con la tarea a realizar

        Returns:
            bool: True si la tarea fue aceptada, False si no
        """
        # Solo procesar si no está ocupado
        if self.busy:
            self.logger.warning("Tarea recibida pero el agente está ocupado")
            self.requeue_task(task_json)  # Reenviar tarea al servidor
            return False

        try:
            task = Message.from_json(task_json)

            # Validar que la tarea tenga los campos necesarios
            required_fields = ["emergency_type", "emergency_level", "position", "alert_id"]
            missing_fields = [field for field in required_fields if not hasattr(task, field)]
            if missing_fields:
                self.logger.error(f"Tarea inválida: faltan los campos {', '.join(missing_fields)}")
                self.requeue_task(task_json)  # Reenviar tarea al servidor
                return False

            if task.message_type != "TASK":
                self.logger.warning(f"Mensaje recibido no es una tarea: {task.message_type}")
                self.requeue_task(task_json)  # Reenviar tarea al servidor
                return False

            # Marcar como ocupado
            self.busy = True
            self.send_status_update(True)

            self.logger.info(f"Tarea recibida: {task.emergency_level} - {task.emergency_type} "
                             f"desde {format_position(task.position)} (alerta #{task.alert_id})")

            # Iniciar la tarea en un hilo separado
            self.task_thread = threading.Thread(
                target=self.process_task,
                args=(task,)
            )
            self.task_thread.daemon = True
            self.task_thread.start()

            return True

        except Exception as e:
            self.logger.exception(f"Error procesando tarea: {e}")
            self.requeue_task(task_json)  # Reenviar tarea al servidor
            return False

    def requeue_task(self, task_json):
        """
        Reenvía una tarea no procesable al servidor para su análisis posterior.

        Args:
            task_json (str): Mensaje JSON con la tarea a reenviar
        """
        try:
            if config.COMMUNICATION_MODE == "sockets":
                if hasattr(self.comm_client, 'send_message'):
                    self.comm_client.send_message(task_json)
                    self.logger.info("Tarea reenviada al servidor para análisis posterior")
                else:
                    self.logger.error("No se pudo reenviar la tarea: el cliente de comunicación no soporta 'send_message'")
            else:  # rabbitmq
                if self.publisher:
                    # Reenviar a una cola específica para tareas no procesadas
                    self.publisher.publish_message(
                        task_json,
                        routing_key="tasks.unprocessed"
                    )
                    self.logger.info("Tarea reenviada a la cola de tareas no procesadas")
                else:
                    self.logger.error("No se pudo reenviar la tarea: publisher no inicializado")
        except Exception as e:
            self.logger.exception(f"Error al reenviar la tarea al servidor: {e}")

    def process_task(self, task):
        """
        Procesa una tarea recibida.

        Args:
            task (Message): Mensaje con la información de la tarea
        """
        try:
            emergency_type = task.emergency_type
            emergency_level = task.emergency_level
            target_position = task.position
            alert_id = task.alert_id

            self.logger.info(f"Procesando tarea #{alert_id}: {emergency_level} - {emergency_type} "
                             f"en {format_position(target_position)}")

            # Simular movimiento hacia la ubicación
            self.logger.info(f"Dirigiéndose a la ubicación del incidente...")
            move_time = max(0, get_random_sleep_time(2, 5))  # Validar tiempo positivo
            safe_sleep(move_time)

            self.logger.info(f"Llegó a la ubicación. Atendiendo emergencia...")

            # Simular atención del incidente
            task_duration = max(0, get_random_sleep_time(config.MIN_TASK_DURATION, config.MAX_TASK_DURATION))

            if emergency_level == "CRÍTICA":
                task_duration *= 1.5

            safe_sleep(task_duration)

            # Actualizar posición del agente a la del incidente
            self.position = target_position

            self.logger.info(f"Tarea #{alert_id} completada después de {task_duration:.2f} segundos")

            # Marcar como disponible nuevamente
            self.busy = False
            self.send_status_update(False)

        except Exception as e:
            self.logger.exception(f"Error durante el procesamiento de la tarea: {e}")
            self.busy = False
            self.send_status_update(False)

    def run(self):
        """
        Método principal para iniciar el agente.
        """
        try:
            # Validar configuraciones antes de iniciar
            validate_config()

            # Establecer conexiones
            self.connect()

            # Iniciar consumo de mensajes según el modo de comunicación
            if config.COMMUNICATION_MODE == "rabbitmq":
                # Para RabbitMQ, iniciar consumo explícitamente y pasar el callback
                self.comm_client.start_consuming(callback=self.handle_task)
            # Para sockets, el consumo ya se inicia automáticamente en el constructor

            # Enviar estado inicial
            self.send_status_update(False)

            # Mantener ejecución hasta recibir señal de parada
            while not self.stop_event.is_set():
                safe_sleep(1)

        except KeyboardInterrupt:
            self.logger.info("Interrupción de teclado recibida")
        except Exception as e:
            self.logger.exception(f"Error en el agente {self.agent_id}: {e}")
        finally:
            self.stop()  # Asegurarse de detener el agente correctamente
            self.disconnect()
            self.logger.info(f"Agente {self.agent_id} finalizado")

    def stop(self):
        """
        Detiene el agente.
        """
        self.logger.info(f"Deteniendo agente {self.agent_id}")
        self.stop_event.set()
        if self.task_thread and self.task_thread.is_alive():
            self.task_thread.join(timeout=5)  # Esperar a que el hilo termine
            if self.task_thread.is_alive():
                self.logger.warning("El hilo de la tarea no pudo detenerse correctamente")