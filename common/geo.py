"""
Utilidades para manejar coordenadas geográficas y cálculos relacionados.
"""

import math
import random
from typing import Tuple, List

import config


def generate_random_position() -> Tuple[float, float]:
    """
    Genera una posición aleatoria dentro de los límites configurados

    Returns:
        tuple: (latitud, longitud)
    """
    lat = random.uniform(config.MAP_MIN_LAT, config.MAP_MAX_LAT)
    lon = random.uniform(config.MAP_MIN_LON, config.MAP_MAX_LON)
    return (round(lat, 6), round(lon, 6))


def calculate_distance(pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
    """
    Calcula la distancia en kilómetros entre dos posiciones usando
    la fórmula de Haversine (para distancias en la superficie terrestre).

    Args:
        pos1: Tupla (latitud, longitud) de la primera posición
        pos2: Tupla (latitud, longitud) de la segunda posición

    Returns:
        float: Distancia en kilómetros
    """
    # Radio de la Tierra en kilómetros
    earth_radius = 6371.0

    # Convertir coordenadas de grados a radianes
    lat1, lon1 = math.radians(pos1[0]), math.radians(pos1[1])
    lat2, lon2 = math.radians(pos2[0]), math.radians(pos2[1])

    # Diferencias de coordenadas
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Fórmula de Haversine
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = earth_radius * c

    return distance


def find_closest_position(target_pos: Tuple[float, float],
                          positions: List[Tuple[float, float]]) -> Tuple[int, float]:
    """
    Encuentra la posición más cercana a un objetivo de entre una lista de posiciones.

    Args:
        target_pos: Posición objetivo (latitud, longitud)
        positions: Lista de posiciones a comparar

    Returns:
        tuple: (índice de la posición más cercana, distancia en km)
    """
    if not positions:
        return -1, float('inf')

    distances = [calculate_distance(target_pos, pos) for pos in positions]
    min_idx = distances.index(min(distances))

    return min_idx, distances[min_idx]


def convert_geo_to_pixel(pos: Tuple[float, float], width: int, height: int) -> Tuple[int, int]:
    """
    Convierte coordenadas geográficas a coordenadas de píxeles para visualización.

    Args:
        pos: Coordenadas (latitud, longitud)
        width: Ancho de la pantalla en píxeles
        height: Alto de la pantalla en píxeles

    Returns:
        tuple: Coordenadas (x, y) en píxeles
    """
    # Normalizar coordenadas
    x_norm = (pos[1] - config.MAP_MIN_LON) / (config.MAP_MAX_LON - config.MAP_MIN_LON)
    y_norm = 1.0 - (pos[0] - config.MAP_MIN_LAT) / (config.MAP_MAX_LAT - config.MAP_MIN_LAT)

    # Convertir a píxeles
    x = int(x_norm * width)
    y = int(y_norm * height)

    return (x, y)


def convert_pixel_to_geo(pixel: Tuple[int, int], width: int, height: int) -> Tuple[float, float]:
    """
    Convierte coordenadas de píxeles a coordenadas geográficas.

    Args:
        pixel: Coordenadas (x, y) en píxeles
        width: Ancho de la pantalla en píxeles
        height: Alto de la pantalla en píxeles

    Returns:
        tuple: Coordenadas (latitud, longitud)
    """
    # Normalizar píxeles
    x_norm = pixel[0] / width
    y_norm = pixel[1] / height

    # Convertir a coordenadas geográficas
    lon = config.MAP_MIN_LON + x_norm * (config.MAP_MAX_LON - config.MAP_MIN_LON)
    lat = config.MAP_MAX_LAT - y_norm * (config.MAP_MAX_LAT - config.MAP_MIN_LAT)

    return (lat, lon)

def generate_random_position():
    """
    Genera coordenadas aleatorias dentro de los límites del mapa.

    Returns:
        tuple: Par de coordenadas (latitud, longitud)
    """
    lat = random.uniform(config.MAP_MIN_LAT, config.MAP_MAX_LAT)
    lon = random.uniform(config.MAP_MIN_LON, config.MAP_MAX_LON)
    return (lat, lon)

def calculate_distance(pos1, pos2):
    """
    Calcula la distancia entre dos puntos geográficos usando la fórmula Haversine.

    Args:
        pos1 (tuple): Coordenadas del primer punto (latitud, longitud)
        pos2 (tuple): Coordenadas del segundo punto (latitud, longitud)

    Returns:
        float: Distancia en kilómetros
    """
    # Radio de la Tierra en kilómetros
    earth_radius = 6371.0

    lat1, lon1 = pos1
    lat2, lon2 = pos2

    # Convertir grados a radianes
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Diferencias en radianes
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Fórmula Haversine
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = earth_radius * c

    return distance

def get_nearest_agent(current_pos, agents_positions):
    """
    Encuentra el agente más cercano a una posición dada.

    Args:
        current_pos (tuple): Posición actual (latitud, longitud)
        agents_positions (dict): Diccionario de {agent_id: position}

    Returns:
        tuple: (agent_id, distancia) del agente más cercano
    """
    if not agents_positions:
        return None, float('inf')

    nearest = None
    min_distance = float('inf')

    for agent_id, pos in agents_positions.items():
        dist = calculate_distance(current_pos, pos)
        if dist < min_distance:
            min_distance = dist
            nearest = agent_id

    return nearest, min_distance

def format_position(position):
    """
    Formatea una posición para mostrarla de forma legible.

    Args:
        position (tuple): Par de coordenadas (latitud, longitud)

    Returns:
        str: Posición formateada
    """
    lat, lon = position
    lat_dir = 'N' if lat >= 0 else 'S'
    lon_dir = 'E' if lon >= 0 else 'W'

    return f"{abs(lat):.6f}°{lat_dir}, {abs(lon):.6f}°{lon_dir}"