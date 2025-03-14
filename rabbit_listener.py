import pika
import json
import requests
import os

# Lấy host của RabbitMQ từ biến môi trường (Docker sẽ tự điền)
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
QUEUE_NAME = "task_queue"
API_URL = "http://app:8000/crawl"  # Dùng tên service 'app' thay vì 'localhost'

# Kết nối tới RabbitMQ
connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
channel = connection.channel()
channel.queue_declare(queue=QUEUE_NAME, durable=True)

def callback(ch, method, properties, body):
    """Hàm nhận message, xử lý và gọi API crawl"""
    message = json.loads(body)
    print(f"📩 Received message: {message}")

    # Gửi request đến API crawl
    try:
        response = requests.post(API_URL, json=message)
        response.raise_for_status()  # Kiểm tra lỗi HTTP
        print(f"✅ API response: {response.json()}")
    except requests.RequestException as e:
        print(f"❌ API request failed: {e}")

    # Xác nhận đã xử lý xong
    ch.basic_ack(delivery_tag=method.delivery_tag)

# Lắng nghe queue và xử lý message
channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)

print("🚀 Waiting for messages. To exit press CTRL+C")
channel.start_consuming()
