"""
Módulo para la visualización en tiempo real de la simulación de agentes encubiertos.
Crea un mapa interactivo con Folium que muestra la posición de espías, agentes nocturnos
y alertas generadas en tiempo real en múltiples zonas de operaciones.
"""

import os
import random
import time
import json
import threading
import webbrowser
import logging
import folium
from folium.plugins import MarkerCluster, HeatMap, Fullscreen, MiniMap
from flask import Flask, render_template, jsonify, send_from_directory
from pathlib import Path

# Configurar logging
logger = logging.getLogger("visualization")
logger.setLevel(logging.INFO)  # Puedes cambiarlo a DEBUG para más información
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler("visualization.log")
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Crear una aplicación Flask para servir el mapa
app = Flask(__name__)

# Diccionarios para almacenar el estado actual de los agentes y alertas
agents_data = {}
alerts_data = []
connections_data = []

# Definir múltiples zonas de operaciones en varias ciudades españolas
OPERATION_ZONES = {
    'Madrid': {
        'name': 'Madrid Centro',
        'min_lat': 40.38, 'max_lat': 40.48,
        'min_lon': -3.75, 'max_lon': -3.65,
        'color': 'blue'
    },
    'Madrid Norte': {
        'name': 'Madrid Norte',
        'min_lat': 40.47, 'max_lat': 40.57,
        'min_lon': -3.73, 'max_lon': -3.63,
        'color': 'green'
    },
    'Madrid Sur': {
        'name': 'Madrid Sur',
        'min_lat': 40.32, 'max_lat': 40.42,
        'min_lon': -3.73, 'max_lon': -3.63,
        'color': 'purple'
    },
    'Barcelona': {
        'name': 'Barcelona',
        'min_lat': 41.35, 'max_lat': 41.45,
        'min_lon': 2.13, 'max_lon': 2.23,
        'color': 'red'
    },
    'Valencia': {
        'name': 'Valencia',
        'min_lat': 39.45, 'max_lat': 39.55,
        'min_lon': -0.40, 'max_lon': -0.30,
        'color': 'orange'
    }
}

# Zona principal para centrar el mapa (Madrid)
PRIMARY_ZONE = 'Madrid'

# Constantes para la visualización
EMERGENCY_COLORS = {
    "BAJA": "green",
    "MEDIA": "orange",
    "ALTA": "red",
    "CRÍTICA": "darkred"
}

EMERGENCY_ICONS = {
    "ROBO": "plus",
    "INCENDIO": "fire",
    "ACCIDENTE": "ambulance",
    "DISTURBIOS": "warning-sign",
    "SOSPECHOSO": "eye-open"
}

EMERGENCY_LEVELS = ["BAJA", "MEDIA", "ALTA", "CRÍTICA"]
EMERGENCY_TYPES = ["ROBO", "INCENDIO", "ACCIDENTE", "DISTURBIOS", "SOSPECHOSO"]

def generate_base_map():
    """Genera el mapa base con Folium"""
    # Usar la zona principal para centrar el mapa
    primary = OPERATION_ZONES[PRIMARY_ZONE]
    center_lat = (primary['min_lat'] + primary['max_lat']) / 2
    center_lon = (primary['min_lon'] + primary['max_lon']) / 2

    # Crear mapa base
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles="OpenStreetMap"  # Volvemos a OpenStreetMap para más detalle
    )

    # Añadir plugins útiles
    Fullscreen().add_to(m)

    # Añadir un mini mapa para navegación
    MiniMap().add_to(m)

    # Añadir título con información sobre número de agentes
    num_agents = sum(1 for a in agents_data.values() if a['type'] == 'night_agent')
    num_spies = sum(1 for a in agents_data.values() if a['type'] == 'spy')
    num_alerts = len(alerts_data)

    stats_panel_html = """
    <div class="info-panel" style="
        position: fixed;
        top: 10px;
        right: 10px;
        background: rgba(255, 255, 255, 0.9);
        padding: 10px;
        border-radius: 5px;
        z-index: 1000;
        max-width: 300px;
        box-shadow: 0 0 10px rgba(0,0,0,0.2);">
        <h4>Estadísticas en tiempo real</h4>
        <div class="mt-2">
            <p>Agentes Nocturnos: <span id="agent-count" class="alert-counter">0</span></p>
            <p>Espías: <span id="spy-count" class="alert-counter">0</span></p>
            <p>Alertas: <span id="alert-count" class="alert-counter">0</span></p>
        </div>
        <hr>
        <h5>Alertas por nivel</h5>
        <div class="row">
            <div class="col-6">Baja: <span id="alert-low">0</span></div>
            <div class="col-6">Media: <span id="alert-medium">0</span></div>
            <div class="col-6">Alta: <span id="alert-high">0</span></div>
            <div class="col-6">Crítica: <span id="alert-critical">0</span></div>
        </div>
        <hr>
        <h5>Estado de alertas</h5>
        <div class="row">
            <div class="col-6">Pendientes: <span id="alert-pending">0</span></div>
            <div class="col-6">En proceso: <span id="alert-processing">0</span></div>
            <div class="col-12">Resueltas: <span id="alert-resolved">0</span></div>
        </div>
    </div>
    
    <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
    <script>
        $(document).ready(function() {
            function updateStats() {
                $.getJSON('/stats')
                    .done(function(data) {
                        $('#agent-count').text(data.num_agents);
                        $('#spy-count').text(data.num_spies);
                        $('#alert-count').text(data.num_alerts);
                        $('#alert-low').text(data.alerts_by_level.BAJA || 0);
                        $('#alert-medium').text(data.alerts_by_level.MEDIA || 0);
                        $('#alert-high').text(data.alerts_by_level.ALTA || 0);
                        $('#alert-critical').text(data.alerts_by_level.CRÍTICA || 0);
                        $('#alert-pending').text(data.alerts_by_status.PENDIENTE || 0);
                        $('#alert-processing').text(data.alerts_by_status["EN PROCESO"] || 0);
                        $('#alert-resolved').text(data.alerts_by_status.RESUELTA || 0);
                    })
                    .fail(function() {
                        console.warn("Fallo al obtener estadísticas");
                    });
            }
    
            updateStats();
            setInterval(updateStats, 5000);
        });
    </script>
    """

    m.get_root().html.add_child(folium.Element(stats_panel_html))

    # Añadir todas las zonas de operaciones como rectángulos
    for zone_name, zone_data in OPERATION_ZONES.items():
        folium.Rectangle(
            bounds=[(zone_data['min_lat'], zone_data['min_lon']),
                    (zone_data['max_lat'], zone_data['max_lon'])],
            color=zone_data['color'],
            fill=True,
            fill_opacity=0.1,
            tooltip=f"Zona: {zone_data['name']}",
            popup=f"<b>{zone_data['name']}</b><br>"
                  f"Agentes: {sum(1 for a in agents_data.values() if a['type'] == 'night_agent' and is_in_zone(a['position'], zone_name))}<br>"
                  f"Espías: {sum(1 for a in agents_data.values() if a['type'] == 'spy' and is_in_zone(a['position'], zone_name))}"
        ).add_to(m)

    # Crear grupos y clusters para organizar los elementos del mapa
    agent_cluster = MarkerCluster(name="Agentes Nocturnos")
    m.add_child(agent_cluster)

    spy_cluster = MarkerCluster(name="Espías")
    m.add_child(spy_cluster)

    alert_cluster = MarkerCluster(name="Alertas")
    m.add_child(alert_cluster)

    # Crear capa de calor para mostrar concentración de alertas
    heat_group = folium.FeatureGroup(name="Mapa de calor de alertas")
    m.add_child(heat_group)

    # Añadir control de capas
    folium.LayerControl().add_to(m)

    # Asegurar que el directorio templates existe
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)

    return m, agent_cluster, spy_cluster, alert_cluster, heat_group

def is_in_zone(position, zone_name):
    """Determina si una posición está dentro de una zona específica"""
    zone = OPERATION_ZONES[zone_name]
    lat, lon = position
    return (zone['min_lat'] <= lat <= zone['max_lat'] and
            zone['min_lon'] <= lon <= zone['max_lon'])

def get_random_zone():
    """Devuelve el nombre de una zona aleatoria"""
    return random.choice(list(OPERATION_ZONES.keys()))

def get_random_position(zone_name=None):
    """Genera una posición aleatoria dentro de una zona específica o cualquier zona"""
    if zone_name is None:
        zone_name = get_random_zone()

    zone = OPERATION_ZONES[zone_name]
    lat = random.uniform(zone['min_lat'], zone['max_lat'])
    lon = random.uniform(zone['min_lon'], zone['max_lon'])
    return lat, lon, zone_name

def simulate_agents():
    """Simula el movimiento y comportamiento de agentes y espías"""
    logger.info("Iniciando simulación de agentes")

    # Número inicial de agentes por zona
    num_agents_per_zone = 30  # Más agentes por zona
    num_spies_per_zone = 15   # Más espías por zona

    # Inicializar agentes y espías en todas las zonas
    for zone_name in OPERATION_ZONES.keys():
        for i in range(1, num_agents_per_zone + 1):
            agent_id = f"AGENT_{zone_name}_{i:03d}"
            lat, lon, _ = get_random_position(zone_name)
            agents_data[agent_id] = {
                'type': 'night_agent',
                'position': (lat, lon),
                'zone': zone_name,
                'status': random.choice(['AVAILABLE', 'BUSY']),
                'last_update': time.time()
            }

        for i in range(1, num_spies_per_zone + 1):
            spy_id = f"SPY_{zone_name}_{i:03d}"
            lat, lon, _ = get_random_position(zone_name)
            agents_data[spy_id] = {
                'type': 'spy',
                'position': (lat, lon),
                'zone': zone_name,
                'last_update': time.time()
            }

    # Bucle principal de simulación
    while True:
        try:
            # Actualizar posiciones de todos los agentes
            for agent_id, agent_info in list(agents_data.items()):
                # Obtener la zona actual del agente
                current_zone = agent_info['zone']

                # Probabilidad pequeña de cambiar de zona
                if random.random() < 0.01:  # 1% de probabilidad de cambiar
                    new_zone = get_random_zone()
                    if new_zone != current_zone:
                        lat, lon, _ = get_random_position(new_zone)
                        agents_data[agent_id]['position'] = (lat, lon)
                        agents_data[agent_id]['zone'] = new_zone
                        continue

                # Movimiento normal dentro de la zona
                lat, lon = agent_info['position']

                # El movimiento es más pronunciado para crear más dinamismo
                lat += random.uniform(-0.005, 0.005)
                lon += random.uniform(-0.005, 0.005)

                # Asegurar que permanezca en la zona asignada
                zone = OPERATION_ZONES[current_zone]
                lat = max(zone['min_lat'], min(zone['max_lat'], lat))
                lon = max(zone['min_lon'], min(zone['max_lon'], lon))

                # Actualizar posición
                agents_data[agent_id]['position'] = (lat, lon)
                agents_data[agent_id]['last_update'] = time.time()

                # Para los agentes nocturnos, actualizar su estado ocasionalmente
                if agent_info['type'] == 'night_agent' and random.random() < 0.05:
                    agents_data[agent_id]['status'] = random.choice(['AVAILABLE', 'BUSY'])

            # Actualizar conexiones entre agentes y espías
            connections_data.clear()

            # Crear más conexiones para una visualización más dinámica
            for zone_name in OPERATION_ZONES.keys():
                # Obtener agentes y espías en esta zona
                zone_agents = [aid for aid, a in agents_data.items()
                               if a['type'] == 'night_agent' and a['zone'] == zone_name]
                zone_spies = [aid for aid, a in agents_data.items()
                              if a['type'] == 'spy' and a['zone'] == zone_name]

                # Saltar si no hay suficientes agentes o espías
                if not zone_agents or not zone_spies:
                    continue

                # Crear conexiones aleatorias en esta zona
                for _ in range(min(len(zone_agents), len(zone_spies), 20)):
                    agent = random.choice(zone_agents)
                    spy = random.choice(zone_spies)
                    connections_data.append((agent, spy))

            # Esperar antes de la próxima actualización
            time.sleep(2)

        except Exception as e:
            logger.exception(f"Error simulando agentes: {e}")
            time.sleep(5)

def generate_random_alerts():
    """Genera alertas aleatorias emitidas por espías"""
    logger.info("Iniciando generación de alertas aleatorias")

    alert_id_counter = 1

    while True:
        try:
            # Limitar activas: solo si hay menos de 60 activas generamos más
            active_alerts = [a for a in alerts_data if a['status'] in ['PENDIENTE', 'EN PROCESO']]
            if len(active_alerts) < 60:
                for zone_name in OPERATION_ZONES.keys():
                    zone_spies = [aid for aid, a in agents_data.items()
                                  if a['type'] == 'spy' and a['zone'] == zone_name]

                    if not zone_spies:
                        continue

                    if random.random() < 0.5:
                        num_alerts = random.randint(1, 3)

                        for _ in range(num_alerts):
                            sender_id = random.choice(zone_spies)
                            base_position = agents_data[sender_id]['position']
                            position = (
                                base_position[0] + random.uniform(-0.002, 0.002),
                                base_position[1] + random.uniform(-0.002, 0.002)
                            )

                            emergency_level_weights = [0.1, 0.2, 0.35, 0.35]
                            emergency_level = random.choices(EMERGENCY_LEVELS, weights=emergency_level_weights)[0]
                            emergency_type = random.choice(EMERGENCY_TYPES)

                            alert_id = f"alert_{alert_id_counter}"
                            alert_id_counter += 1

                            alerts_data.append({
                                'id': alert_id,
                                'sender_id': sender_id,
                                'position': position,
                                'zone': zone_name,
                                'emergency_level': emergency_level,
                                'emergency_type': emergency_type,
                                'timestamp': time.time(),
                                'status': 'PENDIENTE'
                            })

                            if random.random() < 0.1:
                                logger.info(f"Alerta generada en {zone_name}: {emergency_level} - {emergency_type}")

            # Resolver alertas activas gradualmente
            for alert in active_alerts:
                if alert['status'] == 'PENDIENTE' and random.random() < 0.2:
                    alert['status'] = 'EN PROCESO'
                elif alert['status'] == 'EN PROCESO' and random.random() < 0.3:
                    alert['status'] = 'RESUELTA'

            # Mantener solo las últimas 500
            if len(alerts_data) > 500:
                alerts_data[:] = alerts_data[-500:]

            time.sleep(random.uniform(0.6, 1.2))

        except Exception as e:
            logger.exception(f"Error generando alertas: {e}")
            time.sleep(3)

def update_map():
    """Actualiza el mapa con los datos más recientes"""
    logger.info("Iniciando actualización del mapa")
    update_count = 0

    while True:
        try:
            update_count += 1

            # Regenerar mapa con datos actualizados
            m, agent_cluster, spy_cluster, alert_cluster, heat_group = generate_base_map()

            # Añadir agentes al mapa
            for agent_id, agent_info in agents_data.items():
                if agent_info['type'] == 'night_agent':
                    position = agent_info['position']
                    status = agent_info.get('status', 'UNKNOWN')
                    zone = agent_info.get('zone', 'Desconocida')
                    color = 'green' if status == 'AVAILABLE' else 'red'

                    folium.Marker(
                        location=position,
                        popup=f"<b>Agente: {agent_id}</b><br>Estado: {status}<br>Zona: {zone}",
                        tooltip=agent_id,
                        icon=folium.Icon(color=color, icon='user', prefix='fa')
                    ).add_to(agent_cluster)

                elif agent_info['type'] == 'spy':
                    position = agent_info['position']
                    zone = agent_info.get('zone', 'Desconocida')

                    # Usar CircleMarker en lugar de Marker para los espías
                    folium.CircleMarker(
                        location=position,
                        radius=4,
                        popup=f"<b>Espía: {agent_id}</b><br>Zona: {zone}",
                        tooltip=agent_id,
                        color='blue',
                        fill=True,
                        fill_color='blue',
                        fill_opacity=0.7
                    ).add_to(spy_cluster)

            # Limitar las conexiones mostradas para no sobrecargar el mapa
            # Mostrar máximo 50 conexiones, priorizando las más recientes
            connection_sample = connections_data[-50:] if len(connections_data) > 50 else connections_data

            for agent_id, spy_id in connection_sample:
                if agent_id in agents_data and spy_id in agents_data:
                    agent_pos = agents_data[agent_id]['position']
                    spy_pos = agents_data[spy_id]['position']

                    # Comprobar si la conexión cruza entre zonas muy distantes
                    # Si es así, omitirla para mantener el mapa limpio
                    distance = ((agent_pos[0] - spy_pos[0])**2 + (agent_pos[1] - spy_pos[1])**2)**0.5
                    if distance > 0.2:  # Umbral arbitrario para conexiones muy distantes
                        continue

                    folium.PolyLine(
                        [agent_pos, spy_pos],
                        color="gray",
                        weight=1,
                        opacity=0.5,
                        tooltip=f"Conexión {agent_id} - {spy_id}"
                    ).add_to(m)

            # Preparar datos para el mapa de calor y añadir alertas recientes
            alert_heat_data = []

            # Seleccionar solo alertas recientes (últimas 2 horas simuladas)
            current_time = time.time()
            cutoff_time = current_time - 7200
            recent_alerts = [a for a in alerts_data if a['timestamp'] > cutoff_time]

            # Usar las 200 alertas más recientes como máximo
            display_alerts = recent_alerts[-200:] if len(recent_alerts) > 200 else recent_alerts

            for alert in display_alerts:
                position = alert['position']
                emergency_level = alert['emergency_level']
                emergency_type = alert['emergency_type']
                status = alert['status']
                timestamp = time.strftime('%H:%M:%S', time.localtime(alert['timestamp']))

                # Definir color y icono basado en el nivel y tipo de emergencia
                color = EMERGENCY_COLORS.get(emergency_level, 'gray')
                icon = EMERGENCY_ICONS.get(emergency_type, 'info-sign')

                # Para alertas resueltas, usar un icono diferente
                if status == 'RESUELTA':
                    icon = 'ok-sign'

                # Crear el marcador con información detallada
                folium.Marker(
                    location=position,
                    popup=f"""
                    <b>Alerta: {emergency_level} - {emergency_type}</b><br>
                    Emitida por: {alert['sender_id']}<br>
                    Zona: {alert.get('zone', 'Desconocida')}<br>
                    Estado: {status}<br>
                    Hora: {timestamp}
                    """,
                    tooltip=f"{emergency_level}: {emergency_type} ({status})",
                    icon=folium.Icon(color=color, icon=icon, prefix='glyphicon')
                ).add_to(alert_cluster)

                # Añadir punto al mapa de calor con peso según nivel de emergencia
                # Solo incluir alertas pendientes o en proceso en el mapa de calor
                if status != 'RESUELTA':
                    weight = {
                        'BAJA': 0.3,
                        'MEDIA': 0.6,
                        'ALTA': 0.8,
                        'CRÍTICA': 1.0
                    }.get(emergency_level, 0.5)

                    alert_heat_data.append([position[0], position[1], weight])

            # Actualizar mapa de calor si hay datos
            if alert_heat_data:
                HeatMap(
                    alert_heat_data,
                    radius=20,
                    blur=15,
                    max_zoom=13,
                    gradient={0.4: 'blue', 0.65: 'yellow', 0.8: 'orange', 1: 'red'}
                ).add_to(heat_group)

            # Añadir leyenda al mapa
            legend_html = """
            <div style="position: fixed; 
                        bottom: 50px; 
                        right: 50px; 
                        width: 180px; 
                        height: 240px; 
                        z-index:9999; 
                        background-color: white; 
                        padding: 10px; 
                        border-radius: 5px;
                        box-shadow: 0 0 5px rgba(0,0,0,0.3);">
                <h4 style="margin-bottom: 10px; text-align: center;">Leyenda</h4>
                <div><i class="fa fa-user fa-1x" style="color:green"></i> Agente disponible</div>
                <div><i class="fa fa-user fa-1x" style="color:red"></i> Agente ocupado</div>
                <div><i class="fa fa-circle fa-1x" style="color:blue; font-size: 8px;"></i> Espía</div>
                <hr style="margin: 10px 0;">
                <div><i class="glyphicon glyphicon-plus" style="color:green"></i> Robo (Baja)</div>
                <div><i class="glyphicon glyphicon-fire" style="color:orange"></i> Incendio (Media)</div>
                <div><i class="glyphicon glyphicon-ambulance" style="color:red"></i> Accidente (Alta)</div>
                <div><i class="glyphicon glyphicon-warning-sign" style="color:darkred"></i> Disturbios (Crítica)</div>
                <div><i class="glyphicon glyphicon-eye-open" style="color:purple"></i> Sospechoso</div>
            </div>
            """
            m.get_root().html.add_child(folium.Element(legend_html))

            # Guardar mapa actualizado
            templates_dir = Path(__file__).parent / "templates"
            m.save(templates_dir / "index.html")

            # Loguear periódicamente para monitoreo
            if update_count % 10 == 0:
                logger.info(f"Mapa actualizado: {len(agents_data)} agentes, {len(alerts_data)} alertas")

            # Esperar antes de la próxima actualización
            time.sleep(5)  # Aumentado para reducir la carga del navegador

        except Exception as e:
            logger.exception(f"Error al actualizar mapa: {e}")
            time.sleep(5)

# Rutas de la aplicación Flask
@app.route('/')
def index():
    """Página principal con el mapa"""
    return render_template('index.html')

@app.route('/data')
def get_data():
    """API para obtener datos actualizados para el mapa"""
    return jsonify({
        'agents': {k: v for k, v in agents_data.items() if k in list(agents_data.keys())[:200]},  # Limitar cantidad de datos
        'alerts': alerts_data[-100:],  # Solo las últimas 100 alertas
        'connections': connections_data[-50:]  # Solo las últimas 50 conexiones
    })

@app.route('/static/<path:path>')
def send_static(path):
    """Servir archivos estáticos"""
    return send_from_directory('static', path)

@app.route('/stats')
def stats():
    """Proporcionar estadísticas sobre la simulación"""
    stats = {
        'num_agents': sum(1 for a in agents_data.values() if a['type'] == 'night_agent'),
        'num_spies': sum(1 for a in agents_data.values() if a['type'] == 'spy'),
        'num_alerts': len(alerts_data),
        'alerts_by_level': {level: sum(1 for a in alerts_data if a['emergency_level'] == level) for level in EMERGENCY_LEVELS},
        'alerts_by_type': {type_: sum(1 for a in alerts_data if a['emergency_type'] == type_) for type_ in EMERGENCY_TYPES},
        'alerts_by_status': {
            'PENDIENTE': sum(1 for a in alerts_data if a['status'] == 'PENDIENTE'),
            'EN PROCESO': sum(1 for a in alerts_data if a['status'] == 'EN PROCESO'),
            'RESUELTA': sum(1 for a in alerts_data if a['status'] == 'RESUELTA')
        },
        'agents_by_zone': {zone: sum(1 for a in agents_data.values()
                                     if a['type'] == 'night_agent' and a.get('zone') == zone)
                           for zone in OPERATION_ZONES},
        'spies_by_zone': {zone: sum(1 for a in agents_data.values()
                                    if a['type'] == 'spy' and a.get('zone') == zone)
                          for zone in OPERATION_ZONES}
    }
    return jsonify(stats)

def create_custom_html():
    """Crear HTML personalizado con JavaScript para actualización dinámica"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistema de Monitoreo de Agentes Encubiertos</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css">
        <style>
            body, html {
                height: 100%;
                margin: 0;
                padding: 0;
            }
            #map {
                height: 100%;
                width: 100%;
            }
            .info-panel {
                position: fixed;
                top: 10px;
                right: 10px;
                background: rgba(255, 255, 255, 0.9);
                padding: 10px;
                border-radius: 5px;
                z-index: 1000;
                max-width: 300px;
                box-shadow: 0 0 10px rgba(0,0,0,0.2);
            }
            .alert-counter {
                font-weight: bold;
                font-size: 18px;
            }
        </style>
    </head>
    <body>
        <div id="map"></div>
        <div class="info-panel">
            <h4>Estadísticas en tiempo real</h4>
            <div class="mt-2">
                <p>Agentes Nocturnos: <span id="agent-count" class="alert-counter">0</span></p>
                <p>Espías: <span id="spy-count" class="alert-counter">0</span></p>
                <p>Alertas: <span id="alert-count" class="alert-counter">0</span></p>
            </div>
            <hr>
            <h5>Alertas por nivel</h5>
            <div class="row">
                <div class="col-6">Baja: <span id="alert-low">0</span></div>
                <div class="col-6">Media: <span id="alert-medium">0</span></div>
                <div class="col-6">Alta: <span id="alert-high">0</span></div>
                <div class="col-6">Crítica: <span id="alert-critical">0</span></div>
            </div>
            <hr>
            <h5>Estado de alertas</h5>
            <div class="row">
                <div class="col-6">Pendientes: <span id="alert-pending">0</span></div>
                <div class="col-6">En proceso: <span id="alert-processing">0</span></div>
                <div class="col-12">Resueltas: <span id="alert-resolved">0</span></div>
            </div>
        </div>
        <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
            <script>
                $(document).ready(function() {
                    function updateStats() {
                        $.getJSON('/stats')
                            .done(function(data) {
                                $('#agent-count').text(data.num_agents);
                                $('#spy-count').text(data.num_spies);
                                $('#alert-count').text(data.num_alerts);
            
                                $('#alert-low').text(data.alerts_by_level.BAJA || 0);
                                $('#alert-medium').text(data.alerts_by_level.MEDIA || 0);
                                $('#alert-high').text(data.alerts_by_level.ALTA || 0);
                                $('#alert-critical').text(data.alerts_by_level.CRÍTICA || 0);
            
                                $('#alert-pending').text(data.alerts_by_status.PENDIENTE || 0);
                                $('#alert-processing').text(data.alerts_by_status['EN PROCESO'] || 0);
                                $('#alert-resolved').text(data.alerts_by_status.RESUELTA || 0);
                            })
                            .fail(function() {
                                console.warn("Fallo al obtener estadísticas");
                            });
                    }
            
                    // Llamar inicialmente y luego cada 5 segundos
                    updateStats();
                    setInterval(updateStats, 5000);
                });
            </script>
    </body>
    </html>
    """

    # Guardar HTML personalizado
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)

    with open(templates_dir / "dynamic.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def start_server():
    """Inicia el servidor Flask"""
    # Crear directorio de templates si no existe
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)

    # Generar mapa inicial
    m, _, _, _, _ = generate_base_map()
    m.save(templates_dir / "index.html")

    # Crear HTML personalizado
    create_custom_html()

    # Iniciar el servidor en un hilo separado
    # Usar '0.0.0.0' para que sea accesible desde la red local
    threading.Thread(target=app.run, kwargs={
        'host': '0.0.0.0',
        'port': 5000,
        'debug': False,
        'use_reloader': False
    }).start()

def main():
    """Función principal que inicia toda la aplicación"""
    try:
        logger.info("Iniciando sistema de visualización...")
        threading.Thread(target=simulate_agents, daemon=True).start()
        threading.Thread(target=generate_random_alerts, daemon=True).start()
        threading.Thread(target=update_map, daemon=True).start()

        # Iniciar servidor
        start_server()

        # Abrir navegador después de un breve retraso
        time.sleep(2)
        webbrowser.open('http://localhost:5000')
        logger.info("Sistema iniciado correctamente")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Sistema finalizado por el usuario")
    except Exception as e:
        logger.exception(f"Error fatal: {e}")

if __name__ == "__main__":
    main()