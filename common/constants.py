"""
Constantes utilizadas en todo el sistema.
"""

class MessageType:
    """Tipos de mensajes intercambiados en el sistema"""
    GENERIC = "GENERIC"
    ALERT = "ALERT"        # Alerta de espía
    TASK = "TASK"          # Tarea enviada a agente nocturno
    STATUS = "STATUS"      # Estado de agente nocturno
    ACK = "ACK"            # Confirmación

class AgentStatus:
    """Estados posibles de un agente nocturno"""
    AVAILABLE = "DISPONIBLE"
    BUSY = "OCUPADO"
    OFFLINE = "DESCONECTADO"

class EmergencyLevel:
    """Niveles de emergencia posibles"""
    LOW = "BAJA"
    MEDIUM = "MEDIA"
    HIGH = "ALTA"
    CRITICAL = "CRÍTICA"

class EmergencyType:
    """Tipos de emergencia"""
    SURVEILLANCE = "VIGILANCIA"
    INTRUSION = "INTRUSIÓN"
    THEFT = "ROBO"
    KIDNAPPING = "SECUESTRO"
    BOMB_THREAT = "AMENAZA_BOMBA"

class CommunicationMode:
    """Modos de comunicación disponibles"""
    SOCKETS = "sockets"
    RABBITMQ = "rabbitmq"

class LoggingTags:
    """Tags para categorizar los logs"""
    COMMUNICATION = "COMUNICACIÓN"
    AGENT = "AGENTE"
    SERVER = "SERVIDOR"
    SPY = "ESPÍA"
    SYSTEM = "SISTEMA"