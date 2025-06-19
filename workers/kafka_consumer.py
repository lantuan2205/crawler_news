from kafka import KafkaConsumer
import requests
import json
import os

# Cấu hình Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "192.168.132.250:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "news.crawler.request")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "news-crawler-consumer")

# Cấu hình API
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/crawl")

# Tạo consumer
consumer = KafkaConsumer(
    KAFKA_TOPIC,
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    group_id=KAFKA_GROUP_ID,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    auto_offset_reset='earliest',
    enable_auto_commit=True
)

print(f"[*] Đang lắng nghe topic '{KAFKA_TOPIC}' trên Kafka ({KAFKA_BOOTSTRAP_SERVERS})...")

for msg in consumer:
    message = msg.value
    print(f"[x] Nhận message: {message}")

    try:
        # Gửi message tới API xử lý
        response = requests.post(API_URL, json={"message": message})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[!] [Lỗi gửi API] {e}")
        continue

    if response.status_code == 200:
        data = response.json()
        print(f"[✓] [Phản hồi API] {response.status_code}: {data}")
    else:
        print(f"[✗] [Lỗi API] {response.status_code}: {response.text}")
