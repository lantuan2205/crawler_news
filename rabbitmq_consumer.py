import pika
import os
import requests
import json

# Cấu hình RabbitMQ
RABBITMQ_HOST = "192.168.132.250"
RABBITMQ_PORT = 5672
RABBITMQ_USER = "guest"
RABBITMQ_PASS = "guest"
RABBITMQ_VHOST = "/"
RABBITMQ_QUEUE = "news.crawler.queue"
RABBITMQ_ROUTING_KEY = "news.crawler.route"

# Cấu hình API
API_URL = "http://127.0.0.1:8000/crawl"
OUTPUT_FILE = "crawl_result.json"

# API upload
UPLOAD_API_HOST = "192.168.132.250"
UPLOAD_API_PORT = "8080"
UPLOAD_API_ENDPOINT = "/api/upload"
UPLOAD_API_URL = f"http://{UPLOAD_API_HOST}:{UPLOAD_API_PORT}{UPLOAD_API_ENDPOINT}"

# Hàm lưu dữ liệu vào file JSON
def save_to_json(data):
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"[] Dữ liệu đã lưu vào {OUTPUT_FILE}")
    except IOError as e:
        print(f"[] Lỗi khi ghi file {OUTPUT_FILE}: {e}")

def send_json_to_api():
    """Gửi file JSON đến API để lưu trữ"""
    if not os.path.exists(OUTPUT_FILE):
        print(" [] Không tìm thấy file JSON để upload")
        return

    with open(OUTPUT_FILE, "rb") as f:
        files = {"file": f}
        data = {"data": "NEWS_INFO"}  # Thêm metadata

        try:
            response = requests.post(UPLOAD_API_URL, files=files, data=data)
            print(f" [] Upload API Response: {response}")
        except requests.RequestException as e:
            print(f" [] Lỗi khi gửi file: {e}")

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

        # Lưu dữ liệu vào file nếu có bài viết
        if "articles" in data and data["articles"]:
            save_to_json(data["articles"][0])
            send_json_to_api()
        else:
            print("[] Không có bài viết nào để lưu.")
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
        channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback)

        print(f" [*] Đang lắng nghe queue '{RABBITMQ_QUEUE}' trên {RABBITMQ_HOST}:{RABBITMQ_PORT} ...")
        channel.start_consuming()

    except pika.exceptions.AMQPConnectionError as e:
        print(f"[] Lỗi kết nối RabbitMQ: {e}")

if __name__ == "__main__":
    main()

