from kafka import KafkaConsumer
import requests
import json
import os
import re
from utils.service_utils import process_crawl

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
    try:
        message = msg.value  # Đã là dict nhờ value_deserializer
        print(f"[📥] Nhận message từ Kafka: {message}")

        # Gọi trực tiếp hàm xử lý thay vì gọi API
        result = process_crawl({"message": message})

        # In kết quả nếu có
        print(f"[✅] Kết quả xử lý: {result}")

    except Exception as e:
        print(f"[💥] Lỗi xử lý message: {e}")