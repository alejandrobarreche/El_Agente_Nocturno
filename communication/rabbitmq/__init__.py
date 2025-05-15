"""
Submódulo de comunicación basado en RabbitMQ.

Este submódulo proporciona implementaciones de publicación/suscripción
y productor/consumidor usando RabbitMQ para la comunicación asíncrona
entre componentes del sistema.
"""

from communication.rabbitmq.publisher import RabbitMQPublisher
from communication.rabbitmq.consumer import RabbitMQConsumer