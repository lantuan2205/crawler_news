import pika
import os
import requests
import json

# Cấu hình RabbitMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "/")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "test_queue")
RABBITMQ_ROUTING_KEY = os.getenv("RABBITMQ_ROUTING_KEY", "")

# Cấu hình API
API_URL = "http://127.0.0.1:8000/crawl"

# Hàm xử lý khi nhận được message từ RabbitMQ
def callback(ch, method, properties, body):
    message = body.decode()
    print(f" [x] Received: {message}")

    # Gửi message đến API xử lý
    try:
        response = requests.post(API_URL, json={"message": message})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[] [Lỗi API] {e}")
        return

    if response.status_code == 200:
        data = response.json()
        print(f"[] [API Response] {response.status_code}: {data}")
    else:
        print(f"[] [API Error] {response.status_code}: {response.text}")

    ch.basic_ack(delivery_tag=method.delivery_tag)

# Kết nối đến RabbitMQ
def main():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        virtual_host=RABBITMQ_VHOST,
        credentials=credentials
    )

    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        # Khai báo queue (nếu chưa tồn tại)
        channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

        # Ràng buộc queue với routing key
        channel.queue_bind(exchange="amq.direct", queue=RABBITMQ_QUEUE, routing_key=RABBITMQ_ROUTING_KEY)

        # Lắng nghe queue
        channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback, auto_ack=True)

        print(f" [*] Đang lắng nghe queue '{RABBITMQ_QUEUE}' trên {RABBITMQ_HOST}:{RABBITMQ_PORT} ...")
        channel.start_consuming()

    except pika.exceptions.AMQPConnectionError as e:
        print(f"[] Lỗi kết nối RabbitMQ: {e}")

if __name__ == "__main__":
    main()

