import pika
import os
import requests

# Lấy thông tin RabbitMQ từ biến môi trường
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "test_queue")
API_URL = "http://127.0.0.1:8000/process_message"

def callback(ch, method, properties, body):
    message = body.decode()
    print(f" [x] Received: {message}")

    # Gửi message đến API nội bộ
    response = requests.post(API_URL, json={"message": message})
    print(f" [API Response] {response.status_code}: {response.text}")

    ch.basic_ack(delivery_tag=method.delivery_tag)  # Xác nhận đã xử lý message

def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()

    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)

    print(" [*] Waiting for messages. To exit press CTRL+C")
    channel.start_consuming()

if __name__ == "__main__":
    main()
