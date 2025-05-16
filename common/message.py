"""
Define la estructura de mensajes intercambiados entre agentes, espías y servidor.
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Tuple, Optional

from common.constants import MessageType


@dataclass
class Message:
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    message_type: str = field(default=MessageType.GENERIC)
    sender_id: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        data = json.loads(json_str)
        return cls(**data)


@dataclass
class AlertMessage(Message):
    position: Tuple[float, float] = field(default=(0.0, 0.0))
    emergency_level: str = "BAJA"
    emergency_type: str = "VIGILANCIA"
    description: str = ""

    def __post_init__(self):
        self.message_type = MessageType.ALERT
        if not isinstance(self.position, tuple) or len(self.position) != 2:
            raise ValueError(f"Posici\u00f3n inv\u00e1lida: {self.position}.")
        if self.emergency_level not in ["BAJA", "MEDIA", "ALTA", "CR\u00cdTICA"]:
            raise ValueError(f"Nivel de emergencia inv\u00e1lido: {self.emergency_level}.")
        if not self.emergency_type:
            raise ValueError("El tipo de emergencia no puede estar vac\u00edo.")

    @classmethod
    def from_json(cls, json_str: str) -> 'AlertMessage':
        data = json.loads(json_str)
        data['position'] = tuple(data['position'])
        return cls(**data)


@dataclass
class TaskMessage(Message):
    """Mensaje de tarea enviado por el servidor central a un agente nocturno"""
    alert_id: str = ""  # ID del mensaje de alerta original
    position: Tuple[float, float] = field(default=(0.0, 0.0))  # (latitud, longitud)
    emergency_level: str = "BAJA"
    emergency_type: str = "VIGILANCIA"
    description: str = ""
    target_agent_id: str = ""  # ID del agente al que se asigna la tarea
    estimated_duration: int = 0  # Duración estimada en segundos

    def __post_init__(self):
        self.message_type = MessageType.TASK

        # Validar posición
        if not isinstance(self.position, tuple) or len(self.position) != 2:
            raise ValueError(f"Posición inválida: {self.position}. Debe ser una tupla (latitud, longitud).")

        # Validar duración estimada
        if not isinstance(self.estimated_duration, int) or self.estimated_duration < 0:
            raise ValueError(f"Duración estimada inválida: {self.estimated_duration}. Debe ser un entero no negativo.")

    @classmethod
    def from_json(cls, json_str: str) -> 'TaskMessage':
        data = json.loads(json_str)
        data['position'] = tuple(data['position'])
        return cls(**data)


@dataclass
class StatusMessage(Message):
    """Mensaje de estado enviado por agentes nocturnos para reportar su disponibilidad"""
    position: Tuple[float, float] = field(default=(0.0, 0.0))
    status: str = "DISPONIBLE"  # DISPONIBLE, OCUPADO
    current_task_id: Optional[str] = None  # ID de la tarea actual si está ocupado
    estimated_completion_time: Optional[float] = None  # Tiempo estimado de finalización

    def __post_init__(self):
        self.message_type = MessageType.STATUS

    @classmethod
    def from_json(cls, json_str: str) -> 'StatusMessage':
        data = json.loads(json_str)
        data['position'] = tuple(data['position'])
        return cls(**data)


@dataclass
class AcknowledgementMessage(Message):
    """Mensaje de confirmación de recepción"""
    received_message_id: str = ""
    success: bool = True
    details: str = ""

    def __post_init__(self):
        self.message_type = MessageType.ACK

    @classmethod
    def from_json(cls, json_str: str) -> 'AcknowledgementMessage':
        data = json.loads(json_str)
        return cls(**data)


def create_message_from_json(json_str: str) -> Message:
    """
    Crea el tipo correcto de mensaje basado en el JSON recibido
    """
    data = json.loads(json_str)
    message_type = data.get('message_type', MessageType.GENERIC)

    if message_type == MessageType.ALERT:
        return AlertMessage.from_json(json_str)
    elif message_type == MessageType.TASK:
        return TaskMessage.from_json(json_str)
    elif message_type == MessageType.STATUS:
        return StatusMessage.from_json(json_str)
    elif message_type == MessageType.ACK:
        return AcknowledgementMessage.from_json(json_str)
    else:
        return Message.from_json(json_str)