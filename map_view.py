import arcade
import random
import time

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_TITLE = "Mapa de los agentes"

ESTADOS = {
    "libre": arcade.color.GREEN,
    "en_llamada": arcade.color.BLUE,
    "en_mision": arcade.color.RED
}

ALERTAS = [
    "SECUESTRO",
    "ATRACO",
    "AMENAZA_BOMBA",
    "VIGILANCIA",
    "PERSECUCIÓN",
    "INFILTRACIÓN"
]

# Modelizo el objeto agente
class Agente:
    def __init__(self, x, y, id_agente):
        self.x = x
        self.y = y
        self.estado = "libre"
        self.id = id_agente
        self.log = f"[{self.id}] Conectado al servidor con RabbitMQ"

    def draw(self):
        color = ESTADOS[self.estado]
        arcade.draw_circle_filled(self.x, self.y, 15, color)
        arcade.draw_text(str(self.id), self.x - 15, self.y - 25, arcade.color.BLACK, 10)

    # El estado se asigna con random. Modificar para conectar a backend
    def cambiar_estado(self):
        self.estado = random.choice(list(ESTADOS.keys()))
        self.log = f"[{self.id}] Cambió estado a {self.estado.upper()}"

    # Las alertas se eligen de la lista con random. Modificar para conectar a backend (como la anterior)
    def enviar_alerta(self):
        tipo_alerta = random.choice(ALERTAS)
        self.log = f"[{self.id}] ALERTA: {tipo_alerta}"
        return tipo_alerta

# Modelizo el objeto peligro (para mostrar las alertas en el mapa)
class Peligro:
    def __init__(self, x, y, tipo):
        self.x = x
        self.y = y
        self.tipo = tipo
        self.tiempo_restante = 5.0

    def draw(self):
        size = 25
        arcade.draw_triangle_filled(
            self.x, self.y + size,
            self.x - size, self.y - size,
            self.x + size, self.y - size,
            arcade.color.RED
        )
        arcade.draw_text("!", self.x - 6, self.y - 10, arcade.color.WHITE, 20, bold=True)
        arcade.draw_text(self.tipo, self.x - 30, self.y - 40, arcade.color.BLACK, 10)

    def update(self, delta_time):
        self.tiempo_restante -= delta_time

    def activo(self):
        return self.tiempo_restante > 0

# Clase principal para controlar la simulación gráfica  
class SimuladorAgentes(arcade.Window):
    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        self.agentes = []
        self.peligros = []
        self.mensajes = []

    # Simulación con 6 agentes
    def setup(self):
        for i in range(6):
            x = random.randint(50, SCREEN_WIDTH - 50)
            y = random.randint(50, SCREEN_HEIGHT - 50)
            id_real = f"SPY00{i+1}"
            agente = Agente(x, y, id_real)
            self.agentes.append(agente)
            self.mensajes.append(agente.log)

    def agregar_peligro(self, tipo, x, y):
        self.peligros.append(Peligro(x, y, tipo))

    # Mapea las operaciones
    def on_draw(self):
        self.clear()  # ← CORREGIDO: limpiar pantalla correctamente

        for agente in self.agentes:
            agente.draw()

        for peligro in self.peligros:
            if peligro.activo():
                peligro.draw()

    # Dibujar mensajes recientes
        y_offset = SCREEN_HEIGHT - 20
        for mensaje in reversed(self.mensajes[-8:]):
            arcade.draw_text(mensaje, 10, y_offset, arcade.color.WHITE, 12)
            y_offset -= 20


    # simulaciones de cambios de estado y de peligro aleatorios
    def on_update(self, delta_time):
        for agente in self.agentes:
            if random.random() < 0.01:
                agente.cambiar_estado()
                self.mensajes.append(agente.log)

            if random.random() < 0.005:
                tipo_alerta = agente.enviar_alerta()
                x = agente.x + random.randint(-30, 30)
                y = agente.y + random.randint(-30, 30)
                self.agregar_peligro(tipo_alerta, x, y)
                self.mensajes.append(agente.log)

        for peligro in self.peligros:
            peligro.update(delta_time)
        self.peligros = [p for p in self.peligros if p.activo()]

if __name__ == "__main__":
    ventana = SimuladorAgentes()
    ventana.setup()
    arcade.run()
