import pika
import os
import requests

# Lấy thông tin RabbitMQ từ biến môi trường
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "test_queue")
API_URL = "http://127.0.0.1:8000/crawl"
UPLOAD_API_URL = "http://127.0.0.1:8000/upload"
OUTPUT_FILE = "crawl_result.json"

def save_to_json(data):
    """Lưu kết quả crawl vào file JSON"""
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f" Dữ liệu đã được lưu vào {OUTPUT_FILE}")

def send_json_to_api():
    """Gửi file JSON đến API để lưu trữ"""
    if not os.path.exists(OUTPUT_FILE):
        print(" [] Không tìm thấy file JSON để upload")
        return
    files = {"file": open(OUTPUT_FILE, "rb")}
    response = requests.post(UPLOAD_API_URL, files=files)

    print(f" [] Upload API Response: {response.status_code}: {response.text}")


def callback(ch, method, properties, body):
    message = body.decode()
    print(f" [x] Received: {message}")

    # Gửi message đến API nội bộ
    response = requests.post(API_URL, json={"message": message})
    print(f" [API Response] {response.status_code}: {response.text}")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ [API Response] {response.status_code}: {data}")

        # Lưu articles vào file JSON
        if "articles" in data and data["articles"]:
            save_to_json(data["articles"], OUTPUT_FILE)

            # Gửi file JSON lên API khác
            # send_json_to_api(OUTPUT_FILE)
        else:
            print("⚠️ Không có bài viết nào để lưu.")
    else:
        print(f"❌ [API Error] {response.status_code}: {response.text}")

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
