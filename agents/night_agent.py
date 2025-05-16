
"""
Implementación de la clase NightAgent (Agente Nocturno).
Los agentes nocturnos son los encargados de atender las alertas.
"""

import time
import logging
import threading
import random

import config
from common.message import Message, StatusMessage, create_message_from_json
from common.utils import safe_sleep, get_random_sleep_time, setup_logger
from common.geo import format_position, generate_random_position
from communication.rabbitmq.publisher import RabbitMQPublisher
from communication.rabbitmq.consumer import RabbitMQConsumer

if config.COMMUNICATION_MODE == "sockets":
    from communication.sockets.socket_client import SocketClient as CommunicationClient
else:
    from communication.rabbitmq.consumer import RabbitMQConsumer as CommunicationClient

def validate_config():
    required_keys = [
        "COMMUNICATION_MODE", "SOCKET_HOST", "SOCKET_PORT",
        "RABBITMQ_HOST", "RABBITMQ_PORT", "RABBITMQ_USER", "RABBITMQ_PASSWORD",
        "RABBITMQ_QUEUE_TASKS", "MIN_TASK_DURATION", "MAX_TASK_DURATION"
    ]
    for key in required_keys:
        if not hasattr(config, key):
            raise ValueError(f"Falta la configuración requerida: {key}")

class NightAgent:
    def __init__(self, agent_id, position=None):
        self.agent_id = agent_id
        self.position = position if position else generate_random_position()
        self.logger = setup_logger(f"night_agent.{agent_id}", f"agent_{agent_id}.log")
        self.busy = False
        self.stop_event = threading.Event()
        self.comm_client = None
        self.task_thread = None
        self.publisher = None
        self.current_delivery_tag = None
        self.current_channel = None
        self.logger.info(f"Agente {agent_id} inicializado en posición {format_position(self.position)}")

    def connect(self):
        try:
            if config.COMMUNICATION_MODE == "rabbitmq":
                self.comm_client = RabbitMQConsumer(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    username=config.RABBITMQ_USER,
                    password=config.RABBITMQ_PASSWORD,
                    queue_name='tasks_shared_queue',
                    exchange='night_tasks',
                    exchange_type='topic',
                    binding_keys=['task.broadcast']
                )
                self.comm_client.connect()
                self.comm_client.start_consuming(callback=self._rabbitmq_dispatch)

                # Inicializar publisher
                self.publisher = RabbitMQPublisher(
                    host=config.RABBITMQ_HOST,
                    port=config.RABBITMQ_PORT,
                    username=config.RABBITMQ_USER,
                    password=config.RABBITMQ_PASSWORD,
                    exchange='night_status',
                    exchange_type='topic'
                )
                self.publisher.connect()

            else:
                self.comm_client = CommunicationClient(
                    host=config.SOCKET_HOST,
                    port=config.SOCKET_PORT,
                    message_handler=self.handle_task
                )
                self.publisher = self.comm_client

            self.logger.info(f"Conectado al servidor usando {config.COMMUNICATION_MODE}")

        except Exception as e:
            self.logger.exception(f"Error al conectar con el servidor: {e}")
            raise

    def _rabbitmq_dispatch(self, message, routing_key):
        try:
            task_json = message.to_json()
            self.handle_task(task_json)
        except Exception as e:
            self.logger.exception("Error al despachar mensaje desde RabbitMQ")

    def disconnect(self):
        if self.comm_client:
            self.comm_client.close()
            self.logger.info("Desconectado del servidor")
        if self.publisher and self.publisher != self.comm_client:
            self.publisher.close()
            self.logger.info("Cerrada conexión del publisher")


    def send_status_update(self, is_busy):
        status = "BUSY" if is_busy else "AVAILABLE"
        message = StatusMessage(
            sender_id=self.agent_id,
            position=self.position,
            status=status
        )
        message.to_json()
        try:
            if config.COMMUNICATION_MODE == "rabbitmq":
                self.publisher.publish_message(
                    message,
                    routing_key='task.broadcast'
                )
            elif hasattr(self.publisher, 'send_message'):
                self.publisher.send_message(message)
            else:
                self.logger.error("Publisher no configurado correctamente")
            self.logger.debug(f"Estado actualizado a {status}")
        except Exception as e:
            self.logger.exception(f"Error al enviar estado: {e}")

    def handle_task(self, task_json, delivery_tag=None, channel=None):
        try:
            task = create_message_from_json(task_json)
            self.logger.info(f"Tarea recibida: {task}")
            return True
        except Exception as e:
            self.logger.exception(f"Error procesando tarea: {e}")
            return False

    def requeue_task(self, task_json):
        try:
            if config.COMMUNICATION_MODE == "sockets":
                if hasattr(self.comm_client, 'send_message'):
                    self.comm_client.send_message(task_json)
                    self.logger.info("Tarea reenviada al servidor para análisis posterior")
                else:
                    self.logger.error("No se pudo reenviar la tarea: el cliente no soporta 'send_message'")
            elif self.publisher:
                self.publisher.publish_message(task_json, routing_key="tasks.unprocessed")
                self.logger.info("Tarea reenviada a la cola de tareas no procesadas")
        except Exception as e:
            self.logger.exception(f"Error al reenviar la tarea: {e}")

    def send_task_completion(self, task):
        """Envía confirmación de que una tarea ha sido completada"""
        try:
            completion_message = {
                "message_type": "TASK_COMPLETION",
                "alert_id": task.alert_id,
                "agent_id": self.agent_id,
                "completion_time": time.time(),
                "position": self.position
            }

            if config.COMMUNICATION_MODE == "rabbitmq":
                self.publisher.publish_message(
                    Message.to_json(completion_message),
                    routing_key="tasks.completed"
                )
            elif hasattr(self.publisher, 'send_message'):
                self.publisher.send_message(Message.to_json(completion_message))

            self.logger.info(f"Enviada confirmación de finalización de tarea #{task.alert_id}")

            # Ahora confirmar el mensaje original en RabbitMQ si aplica
            if config.COMMUNICATION_MODE == "rabbitmq" and self.current_delivery_tag and self.current_channel:
                self.current_channel.basic_ack(delivery_tag=self.current_delivery_tag)
                self.logger.info(f"Mensaje con delivery_tag {self.current_delivery_tag} confirmado (ACK)")
                self.current_delivery_tag = None
                self.current_channel = None

        except Exception as e:
            self.logger.exception(f"Error al enviar confirmación de finalización: {e}")

    def process_task(self, task):
        try:
            self.logger.info(f"Procesando tarea #{task.alert_id}: {task.emergency_level} - {task.emergency_type} en {format_position(task.position)}")
            self.logger.info(f"Dirigiéndose a la ubicación del incidente...")
            move_time = max(0, get_random_sleep_time(2, 5))
            safe_sleep(move_time)
            self.logger.info(f"Llegó a la ubicación. Atendiendo emergencia...")
            task_duration = max(0, get_random_sleep_time(config.MIN_TASK_DURATION, config.MAX_TASK_DURATION))
            if task.emergency_level == "CRÍTICA":
                task_duration *= 1.5
            safe_sleep(task_duration)
            self.position = task.position
            self.logger.info(f"Tarea #{task.alert_id} completada después de {task_duration:.2f} segundos")

            # Enviar confirmación de finalización de tarea
            self.send_task_completion(task)

            self.busy = False
            self.send_status_update(False)
        except Exception as e:
            self.logger.exception(f"Error durante el procesamiento de la tarea: {e}")
            # En caso de error, rechazar el mensaje si estamos usando RabbitMQ
            if config.COMMUNICATION_MODE == "rabbitmq" and self.current_delivery_tag and self.current_channel:
                self.current_channel.basic_reject(delivery_tag=self.current_delivery_tag, requeue=True)
                self.logger.info(f"Mensaje con delivery_tag {self.current_delivery_tag} rechazado por error")
                self.current_delivery_tag = None
                self.current_channel = None
            self.busy = False
            self.send_status_update(False)

    def run(self):
        try:
            validate_config()
            self.connect()
            self.send_status_update(False)
            while not self.stop_event.is_set():
                safe_sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Interrupción de teclado recibida")
        except Exception as e:
            self.logger.exception(f"Error en el agente {self.agent_id}: {e}")
        finally:
            self.stop()
            self.disconnect()
            self.logger.info(f"Agente {self.agent_id} finalizado")

    def stop(self):
        self.logger.info(f"Deteniendo agente {self.agent_id}")
        self.stop_event.set()
        if self.task_thread and self.task_thread.is_alive():
            self.task_thread.join(timeout=5)
            if self.task_thread.is_alive():
                self.logger.warning("El hilo de la tarea no pudo detenerse correctamente")