import random
from colorama import Fore, Style, init

init(autoreset=True)

# Llamadas simuladas
llamadas = [
    {"mensaje": "Actividad sospechosa detectada.", "ubicacion": "Casa Blanca", "quien": "Oficial de seguridad", "nivel": "Crítico"},
    {"mensaje": "Posible infiltrado en instalaciones.", "ubicacion": "Edificio de defensa", "quien": "Jefa de vigilancia", "nivel": "Alto"},
    {"mensaje": "Fallo en sistema de comunicación.", "ubicacion": "Base operativa", "quien": "Técnico de red", "nivel": "Moderado"},
    {"mensaje": "Objeto no identificado.", "ubicacion": "Almacén federal", "quien": "Guardia de turno", "nivel": "Leve"},
]

# Colores por nivel
colores_nivel = {
    "Leve": Fore.GREEN,
    "Moderado": Fore.YELLOW,
    "Alto": Fore.LIGHTRED_EX,
    "Crítico": Fore.RED
}

# Elegir llamada aleatoria
caso = random.choice(llamadas)

print("Tienes una llamada entrante.")
print(f"Mensaje: {caso['mensaje']}")
respuesta = input("¿Quieres coger la llamada? (si/no): ").strip().lower()

if respuesta in ["sí", "si", "s", "Si"]:
    color = colores_nivel[caso["nivel"]]

    print("\nLLAMADA CONECTADA")
    
    print(f"Ubicacion: {caso['ubicacion']}")
    print(f"Llamada de: {caso['quien']}")
    print(f"{color} Nivel de amenaza: {caso['nivel'].upper()}{Style.RESET_ALL}")

    acciones = {
        "1": "Has iniciado el rastreo de la llamada.",
        "2": "Has alertado a seguridad.",
        "3": "Estás esperando más información.",
        "4": "Has cortado la comunicación."  }
    
    opcion = ""
    while opcion != "4":

        print("\n¿Que deseas hacer?")
        print("1. Rastrear llamada")
        print("2. Alertar a seguridad")
        print("3. Esperar mas informacion")
        print("4. Cortar comunicación")

        opcion = input("Elige una opcion (1-4): ").strip()

        if opcion in acciones:
            print(f"\n {acciones[opcion]}")
        else:
            print("Opcion no valida. Intenta de nuevo")

else:
    print("Has ignorado la llamada.")