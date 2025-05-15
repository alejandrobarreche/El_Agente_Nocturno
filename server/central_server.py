"""
Servidor central para el sistema de agentes encubiertos.

Este módulo implementa el servidor central que recibe alertas de los agentes encubiertos
y las distribuye a los agentes nocturnos más adecuados según su ubicación geográfica.
"""

import logging
import random
import threading
import time
import json
import os.path
from typing import Dict, List, Optional, Set, Tuple
import multiprocessing
import queue
import heapq

from common.message import Message, TaskMessage
from common.geo import calculate_distance
from common.constants import EmergencyLevel, EmergencyType, AgentStatus
from communication.rabbitmq.consumer import RabbitMQConsumer
from communication.rabbitmq.publisher import RabbitMQPublisher

logger = logging.getLogger(__name__)

# Constantes mejoradas para el sistema
MAX_REASSIGNMENT_ATTEMPTS = 3  # Máximo número de intentos de reasignación de una alerta
MAX_ASSIGNMENT_DISTANCE = 50.0  # Distancia máxima (en km) para asignar un agente
AGENT_TIMEOUT = 60  # Tiempo en segundos para marcar un agente como inactivo
ALERT_PRIORITY_WEIGHTS = {
    EmergencyLevel.LOW: 1,
    EmergencyLevel.MEDIUM: 5,
    EmergencyLevel.HIGH: 10,
    EmergencyLevel.CRITICAL: 25
}
STATE_PERSISTENCE_FILE = "server_state.json"
STATE_SAVE_INTERVAL = 300  # Guardar estado cada 5 minutos


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

        # Cola prioritaria para alertas (usando heapq)
        self.alert_queue = []  # Prioridad, tiempo, mensaje, routing_key
        self.alert_queue_lock = threading.RLock()

        # Estructura para mantener el registro de agentes nocturnos
        self.night_agents = {}  # Dict[str, Dict] - ID del agente -> detalles
        self.night_agents_lock = threading.RLock()

        # Estructura para mantener registro de alertas activas
        self.active_alerts = {}  # Dict[str, Dict] - ID de alerta -> detalles
        self.active_alerts_lock = threading.RLock()

        # Contador de intentos de asignación por alerta
        self.assignment_attempts = {}  # Dict[str, int] - ID de alerta -> número de intentos

        # Comunicación con RabbitMQ
        self.alert_consumer = None
        self.agent_status_consumer = None
        self.task_publisher = None
        self.admin_publisher = None

        # Control de estado del servidor
        self.running = False
        self.worker_threads = []

        # Control de persistencia
        self.last_state_save = 0

    def start(self):
        """
        Inicia el servidor central y todos sus componentes.
        """
        if self.running:
            logger.warning("El servidor ya está en ejecución")
            return

        logger.info("Iniciando servidor central...")
        self.running = True

        # Cargar estado anterior si existe
        self._load_state()

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

        # Guardar el estado actual
        self._save_state()

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
        if self.admin_publisher:
            self.admin_publisher.close()

        logger.info("Servidor central detenido")

    def _setup_rabbitmq(self):
        """
        Configura las conexiones con RabbitMQ para consumir alertas y publicar tareas.
        Implementa reconexión automática en caso de fallo.
        """
        max_retries = 5
        retry_count = 0

        while retry_count < max_retries:
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

                # Configurar publicador para notificaciones administrativas
                self.admin_publisher = RabbitMQPublisher(
                    host=self.rabbitmq_host,
                    port=self.rabbitmq_port,
                    exchange='admin_notifications',
                    exchange_type='topic'
                )

                # Conectar componentes
                self.alert_consumer.connect()
                self.agent_status_consumer.connect()
                self.task_publisher.connect()
                self.admin_publisher.connect()

                # Iniciar consumo de mensajes
                self.alert_consumer.start_consuming(self._handle_alert)
                self.agent_status_consumer.start_consuming(self._handle_agent_status)

                logger.info("Conexión con RabbitMQ establecida correctamente")
                break  # Salir del bucle si la conexión es exitosa

            except Exception as e:
                retry_count += 1
                backoff_time = min(30, 2 ** retry_count)  # Backoff exponencial
                logger.error(f"Error al configurar RabbitMQ ({retry_count}/{max_retries}): {e}. "
                             f"Reintentando en {backoff_time} segundos...")
                time.sleep(backoff_time)

        if retry_count >= max_retries:
            logger.critical("No se pudo establecer conexión con RabbitMQ después de múltiples intentos.")
            self.running = False

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

        # Hilo para persistencia de datos periódica
        state_persistence = threading.Thread(
            target=self._periodic_state_save,
            daemon=True,
            name="StatePersistence"
        )
        self.worker_threads.append(state_persistence)
        state_persistence.start()

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

            # Calcular prioridad numérica para la cola prioritaria
            priority_value = ALERT_PRIORITY_WEIGHTS.get(message.priority, 1)

            # Si es una reasignación, reducir la prioridad para evitar hambruna
            if message.message_id in self.assignment_attempts:
                # Aumentar prioridad por cada intento anterior para evitar postergación indefinida
                priority_value = max(1, priority_value - self.assignment_attempts[message.message_id])

            # Agregar a la cola prioritaria (menor número = mayor prioridad)
            with self.alert_queue_lock:
                heapq.heappush(
                    self.alert_queue,
                    (priority_value, time.time(), message, routing_key)
                )

            # Inicializar o incrementar contador de intentos
            if message.message_id not in self.assignment_attempts:
                self.assignment_attempts[message.message_id] = 0
            else:
                self.assignment_attempts[message.message_id] += 1

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
                        'current_task': None if status == AgentStatus.AVAILABLE else message.task_id,
                        'completed_tasks': 0,
                        'successful_tasks': 0,
                        'workload': 0.0  # Factor de carga de trabajo (0-1)
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

                                    # Actualizar estadísticas del agente
                                    self.night_agents[agent_id]['completed_tasks'] += 1
                                    if message.success:  # Si el agente informa éxito
                                        self.night_agents[agent_id]['successful_tasks'] += 1

                                    # Actualizar factor de carga de trabajo
                                    self._update_agent_workload(agent_id)

                                    # Eliminar intentos de asignación para esta alerta
                                    if task_id in self.assignment_attempts:
                                        del self.assignment_attempts[task_id]

        except Exception as e:
            logger.error(f"Error al manejar actualización de estado de agente: {e}")

    def _update_agent_workload(self, agent_id: str):
        """
        Actualiza el factor de carga de trabajo para un agente.

        Args:
            agent_id: ID del agente nocturno.
        """
        if agent_id not in self.night_agents:
            return

        # Implementación simple - basada en la razón de tareas exitosas
        agent = self.night_agents[agent_id]
        if agent['completed_tasks'] > 0:
            success_rate = agent['successful_tasks'] / agent['completed_tasks']
            # Ajustar workload - agentes con mayor tasa de éxito reciben más trabajo
            agent['workload'] = min(1.0, max(0.1, success_rate))
        else:
            # Para nuevos agentes, usar valor neutro
            agent['workload'] = 0.5

    def _process_alerts(self):
        """
        Procesa las alertas en la cola prioritaria y asigna agentes nocturnos.
        Este método se ejecuta en un hilo separado.
        """
        while self.running:
            try:
                # Obtener alerta de la cola prioritaria
                with self.alert_queue_lock:
                    if not self.alert_queue:
                        time.sleep(0.5)  # Esperar si no hay alertas
                        continue

                    # Obtener la alerta con mayor prioridad (menor valor numérico)
                    priority, timestamp, alert, routing_key = heapq.heappop(self.alert_queue)

                # Verificar si la alerta ya está en proceso o es demasiado antigua
                with self.active_alerts_lock:
                    if alert.message_id in self.active_alerts:
                        if self.active_alerts[alert.message_id]['status'] == 'assigned':
                            # Ya asignada, ignorar
                            continue

                    # Comprobar si la alerta es demasiado antigua (más de 30 minutos)
                    alert_age = time.time() - timestamp
                    if alert_age > 1800:  # 30 minutos
                        logger.warning(f"Alerta {alert.message_id} expirada después de {alert_age:.1f} segundos")

                        # Notificar al administrador sobre la alerta sin atender
                        admin_message = Message(
                            message_id=f"admin_{alert.message_id}",
                            message_type='admin.alert_expired',
                            details=f"La alerta {alert.message_id} ha expirado sin ser atendida",
                            alert_type=alert.alert_type,
                            priority=alert.priority,
                            latitude=alert.latitude,
                            longitude=alert.longitude,
                            created_at=time.time()
                        )
                        self.admin_publisher.publish_message(
                            admin_message,
                            routing_key='admin.alert_expired'
                        )

                        # Si hay muchos intentos de asignación, desechar la alerta
                        if self.assignment_attempts.get(alert.message_id, 0) >= MAX_REASSIGNMENT_ATTEMPTS:
                            logger.error(f"Alerta {alert.message_id} descartada después de "
                                         f"{self.assignment_attempts[alert.message_id]} intentos fallidos")
                            if alert.message_id in self.assignment_attempts:
                                del self.assignment_attempts[alert.message_id]
                            continue

                # Registrar o actualizar la alerta
                with self.active_alerts_lock:
                    if alert.message_id not in self.active_alerts:
                        self.active_alerts[alert.message_id] = {
                            'alert': alert,
                            'received_time': timestamp,
                            'assigned_agent': None,
                            'status': 'pending',
                            'attempts': self.assignment_attempts.get(alert.message_id, 0)
                        }
                    else:
                        self.active_alerts[alert.message_id]['attempts'] += 1
                        self.active_alerts[alert.message_id]['status'] = 'pending'

                # Encontrar el agente nocturno más adecuado
                assigned = self._assign_agent_to_alert(alert)

                if not assigned:
                    logger.warning(f"No hay agentes nocturnos disponibles para la alerta {alert.message_id}")

                    # Verificar si hemos alcanzado el límite de intentos
                    if self.assignment_attempts.get(alert.message_id, 0) < MAX_REASSIGNMENT_ATTEMPTS:
                        # Volver a poner en la cola con delay y mayor prioridad
                        time.sleep(5)  # Esperar 5 segundos antes de reintentar
                        self._handle_alert(alert, routing_key)
                    else:
                        logger.error(f"Alerta {alert.message_id} no puede ser asignada después de "
                                     f"{self.assignment_attempts[alert.message_id]} intentos")

                        # Notificar al administrador
                        admin_message = Message(
                            message_id=f"admin_{alert.message_id}",
                            message_type='admin.alert_unassignable',
                            details=f"La alerta {alert.message_id} no puede ser asignada después de "
                                    f"{self.assignment_attempts[alert.message_id]} intentos",
                            alert_type=alert.alert_type,
                            priority=alert.priority,
                            created_at=time.time()
                        )
                        self.admin_publisher.publish_message(
                            admin_message,
                            routing_key='admin.alert_unassignable'
                        )

            except Exception as e:
                logger.error(f"Error en el procesamiento de alertas: {e}")
                time.sleep(1)  # Breve pausa para evitar ciclos de error constantes

    def _assign_agent_to_alert(self, alert: Message) -> bool:
        """
        Asigna aleatoriamente un agente nocturno disponible a una alerta.

        Args:
            alert: La alerta a asignar.

        Returns:
            bool: True si se asignó un agente, False si no hay agentes disponibles.
        """
        with self.night_agents_lock:
            available_agents = [
                agent_id for agent_id, info in self.night_agents.items()
                if info['status'] == AgentStatus.AVAILABLE
            ]

        if not available_agents:
            return False

        # Seleccionar uno al azar
        selected_agent = random.choice(available_agents)

        task_message = TaskMessage(
            alert_id=alert.message_id,
            position=(alert.latitude, alert.longitude),
            emergency_level=alert.priority,
            emergency_type=alert.alert_type,
            description=alert.details,
            target_agent_id=selected_agent,
            estimated_duration=random.randint(10, 30),  # o según config
            sender_id="central_server"
        )

        success = self.task_publisher.publish_message(task_message, routing_key=selected_agent)

        if not success:
            logger.error(f"Error al enviar tarea al agente {selected_agent}")
            return False

        logger.info(f"Alerta {alert.message_id} asignada aleatoriamente al agente {selected_agent}")

        with self.night_agents_lock:
            self.night_agents[selected_agent]['status'] = AgentStatus.BUSY
            self.night_agents[selected_agent]['current_task'] = alert.message_id

        with self.active_alerts_lock:
            self.active_alerts[alert.message_id]['assigned_agent'] = selected_agent
            self.active_alerts[alert.message_id]['status'] = 'assigned'
            self.active_alerts[alert.message_id]['assigned_time'] = time.time()

        return True

    def _monitor_agents(self):
        """
        Monitorea el estado de los agentes nocturnos y maneja agentes inactivos.
        Este método se ejecuta en un hilo separado.
        """
        while self.running:
            try:
                current_time = time.time()
                inactive_agents = []

                # Revisar agentes inactivos
                with self.night_agents_lock:
                    for agent_id, agent_info in self.night_agents.items():
                        # Si un agente no ha enviado actualizaciones en más de AGENT_TIMEOUT segundos, marcarlo como inactivo
                        if current_time - agent_info['last_update'] > AGENT_TIMEOUT:
                            logger.warning(f"Agente {agent_id} inactivo durante más de {AGENT_TIMEOUT} segundos")
                            inactive_agents.append(agent_id)

                # Procesar agentes inactivos
                if inactive_agents:
                    self._handle_inactive_agents(inactive_agents)

                # Breve pausa antes de la siguiente verificación
                time.sleep(10)

            except Exception as e:
                logger.error(f"Error en el monitor de agentes: {e}")
                time.sleep(1)  # Breve pausa para evitar ciclos de error constantes

    def _handle_inactive_agents(self, inactive_agents: List[str]):
        """
        Maneja agentes marcados como inactivos, reasignando sus tareas.

        Args:
            inactive_agents: Lista de IDs de agentes inactivos
        """
        with self.night_agents_lock:
            for agent_id in inactive_agents:
                if agent_id not in self.night_agents:
                    continue

                # Si el agente estaba ocupado, liberar su tarea
                if (self.night_agents[agent_id]['status'] == AgentStatus.BUSY and
                        self.night_agents[agent_id]['current_task']):
                    task_id = self.night_agents[agent_id]['current_task']
                    logger.warning(f"Liberando tarea {task_id} del agente inactivo {agent_id}")

                    # Recuperar información de la alerta
                    with self.active_alerts_lock:
                        if task_id in self.active_alerts:
                            alert = self.active_alerts[task_id]['alert']
                            routing_key = f"alert.{alert.alert_type}"

                            # Marcar como pendiente nuevamente
                            self.active_alerts[task_id]['status'] = 'pending'
                            self.active_alerts[task_id]['assigned_agent'] = None

                            # Volver a poner en cola con alta prioridad
                            # (valor bajo significa mayor prioridad)
                            with self.alert_queue_lock:
                                priority = max(1, ALERT_PRIORITY_WEIGHTS.get(alert.priority, 5) - 2)
                                heapq.heappush(
                                    self.alert_queue,
                                    (priority, time.time(), alert, routing_key)
                                )

                # Notificar al administrador sobre el agente inactivo
                self._notify_admin_inactive_agent(agent_id)

                logger.info(f"Eliminando agente inactivo {agent_id}")
                self.night_agents.pop(agent_id)

    def _notify_admin_inactive_agent(self, agent_id: str):
        """
        Notifica al administrador que un agente se ha marcado como inactivo.

        Args:
            agent_id (str): ID del agente inactivo.
        """
        try:
            # Crear mensaje de notificación
            admin_message = Message(
                message_id=f"admin_inactive_{agent_id}_{int(time.time())}",
                message_type='admin.agent_inactive',
                details=f"El agente {agent_id} ha sido marcado como inactivo",
                created_at=time.time(),
                agent_id=agent_id
            )

            # Publicar notificación
            self.admin_publisher.publish_message(
                admin_message,
                routing_key='admin.agent_inactive'
            )

            logger.critical(f"NOTIFICACIÓN: El agente {agent_id} ha sido marcado como inactivo.")
        except Exception as e:
            logger.error(f"Error al notificar al administrador sobre el agente inactivo {agent_id}: {e}")

    def _periodic_state_save(self):
        """
        Guarda periódicamente el estado del servidor.
        Este método se ejecuta en un hilo separado.
        """
        while self.running:
            try:
                current_time = time.time()

                # Guardar estado cada STATE_SAVE_INTERVAL segundos
                if current_time - self.last_state_save > STATE_SAVE_INTERVAL:
                    self._save_state()
                    self.last_state_save = current_time

                time.sleep(60)  # Comprobar cada minuto

            except Exception as e:
                logger.error(f"Error al guardar estado periódicamente: {e}")
                time.sleep(10)

    def _save_state(self):
        """
        Guarda el estado actual del servidor en un archivo JSON.
        """
        try:
            state = {
                'timestamp': time.time(),
                'night_agents': {},
                'active_alerts': {},
                'assignment_attempts': self.assignment_attempts
            }

            # Guardar información de agentes
            with self.night_agents_lock:
                for agent_id, agent_info in self.night_agents.items():
                    # Crear copia de la información del agente sin objetos no serializables
                    agent_data = {
                        'status': agent_info['status'].value if hasattr(agent_info['status'], 'value') else agent_info['status'],
                        'location': agent_info['location'],
                        'last_update': agent_info['last_update'],
                        'current_task': agent_info['current_task'],
                        'completed_tasks': agent_info.get('completed_tasks', 0),
                        'successful_tasks': agent_info.get('successful_tasks', 0),
                        'workload': agent_info.get('workload', 0.5)
                    }
                    state['night_agents'][agent_id] = agent_data

            # Guardar información de alertas activas
            with self.active_alerts_lock:
                for alert_id, alert_info in self.active_alerts.items():
                    state['active_alerts'][alert_id] = {
                        'status': alert_info['status'],
                        'assigned_agent': alert_info['assigned_agent'],
                        'received_time': alert_info['received_time'],
                        'attempts': alert_info.get('attempts', 0)
                    }

            # Escribir en archivo JSON
            with open(STATE_PERSISTENCE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
                logger.info("Estado del servidor guardado correctamente en disco.")

        except Exception as e:
            logger.error(f"Error al guardar estado del servidor: {e}")

    def _load_state(self):
        """
        Carga el estado previo del servidor desde archivo JSON (si existe).
        """
        if not os.path.exists(STATE_PERSISTENCE_FILE):
            logger.info("No se encontró estado previo del servidor.")
            return

        try:
            with open(STATE_PERSISTENCE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            with self.night_agents_lock:
                self.night_agents = state.get('night_agents', {})

            with self.active_alerts_lock:
                self.active_alerts = state.get('active_alerts', {})

            self.assignment_attempts = state.get('assignment_attempts', {})

            logger.info("Estado del servidor restaurado correctamente desde disco.")

        except Exception as e:
            logger.error(f"Error al cargar estado del servidor: {e}")