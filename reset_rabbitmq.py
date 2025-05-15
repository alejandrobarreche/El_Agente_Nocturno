import subprocess
import time

def run(cmd: str):
    print(f"🔧 Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ OK: {result.stdout.strip()}")
    else:
        print(f"❌ ERROR: {result.stderr.strip()}")

def reset_rabbitmq():
    print("\n🚨 Reiniciando RabbitMQ Docker...\n")

    # 1. Detener y eliminar contenedor si existe
    run("docker stop rabbitmq || true")
    run("docker rm rabbitmq || true")

    # 2. Eliminar volumen de datos si existe
    run("docker volume rm rabbitmq_data || true")

    # 3. Re-crear volumen y contenedor
    run("docker volume create rabbitmq_data")
    time.sleep(1)
    run("""
    docker run -d --hostname rabbit --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management
    """)

    print("\n🚀 RabbitMQ reiniciado en http://localhost:15672 (user: guest / pass: guest)")

if __name__ == "__main__":
    reset_rabbitmq()
