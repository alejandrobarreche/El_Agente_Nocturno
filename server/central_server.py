"""
Servidor central para el sistema de agentes encubiertos.

Este módulo implementa el servidor central que recibe alertas de los agentes encubiertos
y las distribuye a los agentes nocturnos más adecuados según su ubicación geográfica.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Set, Tuple
import multiprocessing
import queue

from common.message import Message
from common.geo import calculate_distance
from common.constants import EmergencyLevel, EmergencyType, AgentStatus
from communication.rabbitmq.consumer import RabbitMQConsumer
from communication.rabbitmq.publisher import RabbitMQPublisher

logger = logging.getLogger(__name__)

class CentralServer:
    """
    Servidor central que gestiona las alertas de los agentes encubiertos y
    las asigna a los agentes nocturnos disponibles más cercanos.
    """

    def __init__(self, rabbitmq_host: str = 'localhost', rabbitmq_port: int = 5672):
        """
        Inicializa el servidor central.

        Args:
            rabbitmq_host: Host del servidor RabbitMQ.
            rabbitmq_port: Puerto del servidor RabbitMQ.
        """
        self.rabbitmq_host = rabbitmq_host
        self.rabbitmq_port = rabbitmq_port

        # Colas para comunicación interna
        self.alert_queue = queue.Queue()

        # Estructura para mantener el registro de agentes nocturnos
        self.night_agents = {}  # Dict[str, Dict] - ID del agente -> detalles
        self.night_agents_lock = threading.RLock()

        # Estructura para mantener registro de alertas activas
        self.active_alerts = {}  # Dict[str, Dict] - ID de alerta -> detalles
        self.active_alerts_lock = threading.RLock()

        # Comunicación con RabbitMQ
        self.alert_consumer = None
        self.agent_status_consumer = None
        self.task_publisher = None

        # Control de estado del servidor
        self.running = False
        self.worker_threads = []

    def start(self):
        """
        Inicia el servidor central y todos sus componentes.
        """
        if self.running:
            logger.warning("El servidor ya está en ejecución")
            return

        logger.info("Iniciando servidor central...")
        self.running = True

        # Iniciar conexiones RabbitMQ
        self._setup_rabbitmq()

        # Iniciar hilos de trabajo
        self._start_worker_threads()

        logger.info("Servidor central en funcionamiento")

    def stop(self):
        """
        Detiene el servidor central y todos sus componentes.
        """
        if not self.running:
            logger.warning("El servidor no está en ejecución")
            return

        logger.info("Deteniendo servidor central...")
        self.running = False

        # Esperar a que los hilos terminen
        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)

        # Cerrar conexiones RabbitMQ
        if self.alert_consumer:
            self.alert_consumer.close()
        if self.agent_status_consumer:
            self.agent_status_consumer.close()
        if self.task_publisher:
            self.task_publisher.close()

        logger.info("Servidor central detenido")

    def _setup_rabbitmq(self):
        """
        Configura las conexiones con RabbitMQ para consumir alertas y publicar tareas.
        Implementa reconexión automática en caso de fallo.
        """
        while True:
            try:
                # Configurar consumidor para alertas de espías
                self.alert_consumer = RabbitMQConsumer(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    exchange='spy_alerts',
                    exchange_type='topic',
                    queue_name='server_alerts_queue',
                    binding_keys=['alert.*']  # Escuchar todas las alertas
                )

                # Configurar consumidor para actualizaciones de estado de agentes nocturnos
                self.agent_status_consumer = RabbitMQConsumer(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    exchange='agent_status',
                    exchange_type='topic',
                    queue_name='server_status_queue',
                    binding_keys=['status.*']  # Escuchar todos los estados
                )

                # Configurar publicador para tareas de agentes nocturnos
                self.task_publisher = RabbitMQPublisher(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    exchange='night_tasks',
                    exchange_type='direct'
                )

                # Conectar componentes
                self.alert_consumer.connect()
                self.agent_status_consumer.connect()
                self.task_publisher.connect()

                # Iniciar consumo de mensajes
                self.alert_consumer.start_consuming(self._handle_alert)
                self.agent_status_consumer.start_consuming(self._handle_agent_status)

                logger.info("Conexión con RabbitMQ establecida correctamente")
                break  # Salir del bucle si la conexión es exitosa

            except Exception as e:
                logger.error(f"Error al configurar RabbitMQ: {e}. Reintentando en 5 segundos...")
                time.sleep(5)  # Esperar antes de reintentar

    def _start_worker_threads(self):
        """
        Inicia los hilos de trabajo para procesar alertas y monitorear agentes.
        """
        # Hilo para procesar la cola de alertas
        alert_processor = threading.Thread(
            target=self._process_alerts,
            daemon=True,
            name="AlertProcessor"
        )
        self.worker_threads.append(alert_processor)
        alert_processor.start()

        # Hilo para monitorear agentes nocturnos y verificar su disponibilidad
        agent_monitor = threading.Thread(
            target=self._monitor_agents,
            daemon=True,
            name="AgentMonitor"
        )
        self.worker_threads.append(agent_monitor)
        agent_monitor.start()

    def _handle_alert(self, message: Message, routing_key: str):
        """
        Maneja las alertas recibidas de los agentes encubiertos.

        Args:
            message: El mensaje de alerta.
            routing_key: La clave de enrutamiento del mensaje.
        """
        try:
            logger.info(f"Alerta recibida - ID: {message.message_id}, Tipo: {message.alert_type}, "
                        f"Prioridad: {message.priority}, Ubicación: ({message.latitude}, {message.longitude})")

            # Encolar la alerta para procesamiento
            self.alert_queue.put((message, routing_key))

        except Exception as e:
            logger.error(f"Error al manejar alerta: {e}")

    def _handle_agent_status(self, message: Message, routing_key: str):
        """
        Maneja las actualizaciones de estado de los agentes nocturnos.

        Args:
            message: El mensaje de estado del agente.
            routing_key: La clave de enrutamiento del mensaje.
        """
        try:
            agent_id = message.agent_id
            status = message.status
            location = message.position

            with self.night_agents_lock:
                if agent_id not in self.night_agents:
                    # Nuevo agente
                    self.night_agents[agent_id] = {
                        'status': status,
                        'location': location,
                        'last_update': time.time(),
                        'current_task': None if status == AgentStatus.AVAILABLE else message.task_id
                    }
                    logger.info(f"Nuevo agente nocturno registrado - ID: {agent_id}, "
                                f"Ubicación: {location}, Estado: {status}")
                else:
                    # Actualizar agente existente
                    old_status = self.night_agents[agent_id]['status']
                    self.night_agents[agent_id].update({
                        'status': status,
                        'location': location,
                        'last_update': time.time(),
                        'current_task': None if status == AgentStatus.AVAILABLE else message.task_id
                    })

                    if old_status != status:
                        logger.info(f"Agente nocturno {agent_id} cambió estado: {old_status} -> {status}")

                        # Si un agente ha completado una tarea, actualizar la alerta correspondiente
                        if status == AgentStatus.AVAILABLE and old_status == AgentStatus.BUSY:
                            task_id = message.task_id
                            with self.active_alerts_lock:
                                if task_id in self.active_alerts:
                                    logger.info(f"Tarea completada - ID: {task_id} por agente {agent_id}")
                                    self.active_alerts.pop(task_id)

        except Exception as e:
            logger.error(f"Error al manejar actualización de estado de agente: {e}")

    def _process_alerts(self):
        """
        Procesa las alertas en la cola y asigna agentes nocturnos.
        Este método se ejecuta en un hilo separado.
        """
        while self.running:
            try:
                # Obtener alerta de la cola (con timeout para permitir comprobaciones periódicas)
                try:
                    alert, routing_key = self.alert_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # Registrar la alerta
                with self.active_alerts_lock:
                    self.active_alerts[alert.message_id] = {
                        'alert': alert,
                        'received_time': time.time(),
                        'assigned_agent': None,
                        'status': 'pending'
                    }

                # Encontrar el agente nocturno más adecuado
                assigned = self._assign_agent_to_alert(alert)

                if not assigned:
                    logger.warning(f"No hay agentes nocturnos disponibles para la alerta {alert.message_id}")
                    # Mantener la alerta en la cola, se volverá a intentar asignar en el siguiente ciclo

                # Marcar como procesada en la cola
                self.alert_queue.task_done()

            except Exception as e:
                logger.error(f"Error en el procesamiento de alertas: {e}")
                time.sleep(1)  # Breve pausa para evitar ciclos de error constantes

    def _assign_agent_to_alert(self, alert: Message) -> bool:
        """
        Asigna un agente nocturno disponible a una alerta.

        Args:
            alert: La alerta a asignar.

        Returns:
            bool: True si se asignó un agente, False si no hay agentes disponibles.
        """
        alert_location = (alert.latitude, alert.longitude)
        best_agent = None
        min_distance = float('inf')

        # Buscar el agente disponible más cercano
        with self.night_agents_lock:
            for agent_id, agent_info in self.night_agents.items():
                if agent_info['status'] == AgentStatus.AVAILABLE:
                    distance = calculate_distance(
                        alert_location,
                        agent_info['location']
                    )

                    if distance < min_distance:
                        min_distance = distance
                        best_agent = agent_id

        if best_agent:
            # Crear tarea para el agente
            task_message = Message(
                message_id=alert.message_id,
                message_type='task.assignment',
                agent_id=best_agent,
                alert_type=alert.alert_type,
                priority=alert.priority,
                latitude=alert.latitude,
                longitude=alert.longitude,
                details=alert.details,
                created_at=time.time(),
                spy_id=alert.agent_id  # Transferir ID del espía que generó la alerta
            )

            # Enviar tarea al agente
            success = self.task_publisher.publish_message(
                task_message,
                routing_key=best_agent  # Usar ID del agente como routing key
            )

            if success:
                logger.info(f"Alerta {alert.message_id} asignada al agente {best_agent} "
                            f"a una distancia de {min_distance:.2f} km")

                # Actualizar estado del agente
                with self.night_agents_lock:
                    self.night_agents[best_agent]['status'] = AgentStatus.BUSY
                    self.night_agents[best_agent]['current_task'] = alert.message_id

                # Actualizar estado de la alerta
                with self.active_alerts_lock:
                    self.active_alerts[alert.message_id]['assigned_agent'] = best_agent
                    self.active_alerts[alert.message_id]['status'] = 'assigned'
                    self.active_alerts[alert.message_id]['assigned_time'] = time.time()

                return True
            else:
                logger.error(f"Error al enviar tarea al agente {best_agent}")
                return False

        return False

    def _monitor_agents(self):
        """
        Monitorea el estado de los agentes nocturnos y verifica su disponibilidad.
        Este método se ejecuta en un hilo separado.
        """
        while self.running:
            try:
                current_time = time.time()
                inactive_agents = []

                # Revisar agentes inactivos
                with self.night_agents_lock:
                    for agent_id, agent_info in self.night_agents.items():
                        # Si un agente no ha enviado actualizaciones en más de 60 segundos, marcarlo como inactivo
                        if current_time - agent_info['last_update'] > 60:
                            logger.warning(f"Agente {agent_id} inactivo durante más de 60 segundos")
                            inactive_agents.append(agent_id)

                # Eliminar agentes inactivos
                if inactive_agents:
                    with self.night_agents_lock:
                        for agent_id in inactive_agents:
                            # Si el agente estaba ocupado, liberar su tarea
                            if (self.night_agents[agent_id]['status'] == AgentStatus.BUSY and
                                    self.night_agents[agent_id]['current_task']):
                                task_id = self.night_agents[agent_id]['current_task']
                                logger.warning(f"Liberando tarea {task_id} del agente inactivo {agent_id}")

                                # Volver a poner la alerta en estado pendiente
                                with self.active_alerts_lock:
                                    if task_id in self.active_alerts:
                                        self.active_alerts[task_id]['status'] = 'pending'
                                        self.active_alerts[task_id]['assigned_agent'] = None

                                        # Recrear el mensaje para volver a ponerlo en la cola
                                        alert = self.active_alerts[task_id]['alert']
                                        self.alert_queue.put((alert, f"alert.{alert.alert_type}"))

                            # Notificar al administrador sobre el agente inactivo
                            self._notify_admin_inactive_agent(agent_id)

                            logger.info(f"Eliminando agente inactivo {agent_id}")
                            self.night_agents.pop(agent_id)

                # Breve pausa antes de la siguiente verificación
                time.sleep(10)

            except Exception as e:
                logger.error(f"Error en el monitor de agentes: {e}")
                time.sleep(1)  # Breve pausa para evitar ciclos de error constantes

    def _notify_admin_inactive_agent(self, agent_id: str):
        """
        Notifica al administrador que un agente se ha marcado como inactivo.

        Args:
            agent_id (str): ID del agente inactivo.
        """
        try:
            # Aquí puedes implementar un mecanismo de notificación, como enviar un correo electrónico.
            # Por ahora, simplemente registraremos un mensaje crítico.
            logger.critical(f"NOTIFICACIÓN: El agente {agent_id} ha sido marcado como inactivo.")
        except Exception as e:
            logger.error(f"Error al notificar al administrador sobre el agente inactivo {agent_id}: {e}")

    def get_status(self) -> Dict:
        """
        Obtiene el estado actual del servidor.

        Returns:
            Dict: Diccionario con información sobre el estado del servidor.
        """
        with self.night_agents_lock, self.active_alerts_lock:
            return {
                'active_agents': len(self.night_agents),
                'available_agents': sum(1 for a in self.night_agents.values() if a['status'] == AgentStatus.AVAILABLE),
                'pending_alerts': sum(1 for a in self.active_alerts.values() if a['status'] == 'pending'),
                'assigned_alerts': sum(1 for a in self.active_alerts.values() if a['status'] == 'assigned'),
                'total_alerts': len(self.active_alerts)
            }

    def __enter__(self):
        """Soporte para patrón de contexto (with)."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Cierra el servidor al salir del contexto."""
        self.stop()