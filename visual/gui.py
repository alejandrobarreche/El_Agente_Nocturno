
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
            cutoff_time = current_time - 7200  # 2 horas en segundos
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
        
        <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
        
        <!-- Incluir el contenido del mapa generado por Folium -->
        <script>
            // El mapa se cargará aquí desde index.html
            $(document).ready(function() {
                // Actualizar estadísticas periódicamente
                setInterval(function() {
                    $.getJSON('/stats', function(data) {
                        $('#agent-count').text(data.num_agents);
                        $('#spy-count').text(data.num_spies);
                        $('#alert-count').text(data.num_alerts);
                        // Actualizar contadores de alertas por nivel
                        $('#alert-low').text(data.alerts_by_level.BAJA);
                        $('#alert-medium').text(data.alerts_by_level.MEDIA);
                        $('#alert-high').text(data.alerts_by_level.ALTA);
                        $('#alert-critical').text(data.alerts_by_level.CRÍTICA);
                        
                        // Actualizar contadores de estado
                        $('#alert-pending').text(data.alerts_by_status.PENDIENTE);
                        $('#alert-processing').text(data.alerts_by_status['EN PROCESO']);
                        $('#alert-resolved').text(data.alerts_by_status.RESUELTA);
                    });
                }, 5000); // Actualizar cada 5 segundos
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

        # Iniciar simulación en hilos separados
        threading.Thread(target=simulate_agents, daemon=True).start()
        threading.Thread(target=generate_random_alerts, daemon=True).start()
        threading.Thread(target=update_map, daemon=True).start()

        # Iniciar servidor
        start_server()

        # Abrir navegador después de un breve retraso
        time.sleep(2)
        webbrowser.open('http://localhost:5000')

        logger.info("Sistema iniciado correctamente")

        # Mantener el programa principal en ejecución
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Sistema finalizado por el usuario")
    except Exception as e:
        logger.exception(f"Error fatal: {e}")

if __name__ == "__main__":
    main()