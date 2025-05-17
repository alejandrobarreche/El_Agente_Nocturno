# El Agente Nocturno

Sistema de simulación y visualización para agentes encubiertos y espías, con comunicación asíncrona basada en RabbitMQ y visualización en tiempo real sobre un mapa.

## Características

- **Simulación de agentes nocturnos y espías** en diferentes zonas de operaciones.
- **Comunicación asíncrona** entre agentes y servidor central usando RabbitMQ (modo por defecto).
- **Visualización web interactiva** de agentes, alertas y tareas sobre un mapa (Folium/Leaflet).
- **Panel de estadísticas** en tiempo real y leyenda de elementos en el mapa.
- **Soporte para diferentes niveles y tipos de emergencia**.

## Estructura del Proyecto

- `agents/`: Lógica de agentes nocturnos y espías.
- `common/`: Constantes, mensajes y utilidades compartidas.
- `communication/`: Implementación de RabbitMQ (publisher/consumer).
- `server/`: Lógica del servidor central.
- `visual/`: Visualización web y recursos estáticos.
- `config.py`: Configuración global del sistema.
- `run_simulation.py`: Script principal para lanzar la simulación.
- `reset_rabbitmq.py`: Script para limpiar colas de RabbitMQ.

## Requisitos

- Python 3.11+
- RabbitMQ (servidor corriendo en `localhost:5672` por defecto)
- Paquetes Python: ver [`requirements.txt`](requirements.txt)

## Instalación

1. Clona el repositorio:
    ```sh
    git clone <URL_DEL_REPOSITORIO>
    cd El_Agente_Nocturno-master
    ```

2. Instala las dependencias:
    ```sh
    pip install -r requirements.txt
    ```

3. DockerFile:
    En el DockerFile encontrarás las instrucciones para instalar la imagen.

## Uso

### 1. Iniciar la simulación

Lanza la simulación de agentes y servidor:
```sh
python run_simulation.py
```

### 2. Visualización web

En otra terminal, inicia la visualización:
```sh
python visual/gui.py
```
Abre tu navegador en [http://localhost:5000](http://localhost:5000) para ver el mapa y panel de control si este no se abre automáticamente.

### 3. Resetear colas de RabbitMQ (opcional)

Para limpiar las colas de mensajes:
```sh
python reset_rabbitmq.py
```

## Configuración

Puedes modificar parámetros globales en [`config.py`](config.py), como:
- Modo de comunicación (`COMMUNICATION_MODE`)
- Zonas de operación
- Colores y visualización
- Parámetros de RabbitMQ

## Créditos

Desarrollado por Grupo B: Alejandro Barreche Ruiz, Álvaro Santamaría Antón, Paula Ying Mena Gutierrez, Victor Valdivia Calatrava.