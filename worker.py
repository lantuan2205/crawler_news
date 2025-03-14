import pika
import json
import requests
import time
import os

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "task_queue"
API_URL = os.getenv("API_URL", "http://app:8000/crawl")

# Kết nối RabbitMQ có retry
retries = 5
while retries > 0:
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST)
        )
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        break
    except pika.exceptions.AMQPConnectionError:
        print(f"🔁 RabbitMQ chưa sẵn sàng, thử lại ({retries})...")
        retries -= 1
        time.sleep(5)

if retries == 0:
    print("❌ Không thể kết nối RabbitMQ, thoát chương trình!")
    exit(1)

def callback(ch, method, properties, body):
    message = json.loads(body)
    print(f"📩 Received: {message}")

    try:
        response = requests.post(API_URL, json=message)
        response.raise_for_status()
        print(f"✅ API Response: {response.json()}")
    except requests.RequestException as e:
        print(f"❌ API Request Failed: {e}")

    ch.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
print("🚀 Worker lắng nghe RabbitMQ...")
channel.start_consuming()
