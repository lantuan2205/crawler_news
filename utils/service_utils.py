from fastapi import FastAPI, File, UploadFile, Form, HTTPException
import re
import os
import requests
import json
from datetime import datetime, timedelta, timezone
import time
from pathlib import Path
from utils.mongodb_utils import save_article, save_image_metadata, save_category
from constants.crawlerselenium import CRAWLERS_SELENIUM
import unicodedata
import concurrent.futures
from tqdm import tqdm
from io import BytesIO
import mimetypes
from kafka import KafkaProducer
import json
import pytz
from urllib.parse import urlparse
from kafka.errors import KafkaError
import logging
from kafka.admin import KafkaAdminClient, NewTopic, NewPartitions

# Cấu hình Kafka
# 1. Cấu hình Logging (Thay vì dùng print)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# 2. Cấu hình Env
NUM_PARTITIONS = 5
REPLICATION_FACTOR = 1
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "192.168.161.69:29092")

# Topic Configs
TOPIC_MAP = {
    "DEFAULT": os.getenv("KAFKA_RESULT_TOPIC", "news.crawler.raw"),
    "DARK_WEB": os.getenv("KAFKA_TOPIC_DARK_WEB", "darkweb.crawler.raw"),
    "TRACKING": os.getenv("KAFKA_TRACKING_STATUS", "tracking.status"),
    "PROFILE": os.getenv("KAFKA_TOPIC_PROFILE", "news.profile.crawler.raw"),
    "PROFILE_DARK_WEB": os.getenv("KAFKA_TOPIC_PROFILE_DARK_WEB", "darkweb.profile.crawler.raw"),
    "COMMENT": os.getenv("KAFKA_TOPIC_COMMENT", "news.comment.crawler.raw"),
    "PODCAST": os.getenv("KAFKA_TOPIC_PODCAST", "news.podcast.crawler.raw"),
    "LOGS": os.getenv("KAFKA_TOPIC_LOGS", "raw.logs"),
}

OUTPUT_FILE = "crawl_result.json"
# API Configs (Giữ nguyên nếu bạn dùng ở chỗ khác)
UPLOAD_API_HOST = "192.168.132.250"
UPLOAD_API_PORT = "8080"
UPLOAD_API_URL = f"http://{UPLOAD_API_HOST}:{UPLOAD_API_PORT}/api/upload/multiple"


def ensure_all_topics_setup():
    """
    Duyệt qua TẤT CẢ topic trong TOPIC_MAP.
    Đảm bảo cái nào cũng phải có 5 partitions.
    """
    logger.info("--- Bắt đầu kiểm tra cấu hình Kafka Topics ---")
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id='admin_initializer'
        )
        
        existing_topics = admin_client.list_topics()
        
        # Lấy danh sách các topic cần check (loại bỏ trùng lặp)
        topics_to_check = set(TOPIC_MAP.values())

        for topic_name in topics_to_check:
            # TH1: Topic chưa tồn tại -> Tạo mới
            if topic_name not in existing_topics:
                logger.info(f"[+] Tạo MỚI topic '{topic_name}' ({NUM_PARTITIONS} partitions).")
                new_topic = NewTopic(
                    name=topic_name, 
                    num_partitions=NUM_PARTITIONS, 
                    replication_factor=REPLICATION_FACTOR
                )
                admin_client.create_topics([new_topic])
            
            # TH2: Topic đã tồn tại -> Kiểm tra và Nâng cấp nếu cần
            else:
                topic_desc = admin_client.describe_topics([topic_name])
                current_parts = len(topic_desc[0]['partitions'])
                
                if current_parts < NUM_PARTITIONS:
                    logger.warning(f"[^] Nâng cấp '{topic_name}': {current_parts} -> {NUM_PARTITIONS} partitions.")
                    try:
                        admin_client.create_partitions({
                            topic_name: NewPartitions(total_count=NUM_PARTITIONS)
                        })
                    except Exception as create_err:
                        logger.error(f"Không thể nâng cấp {topic_name}: {create_err}")
                else:
                    logger.info(f"[OK] '{topic_name}' đã đủ {current_parts} partitions.")

        admin_client.close()
    except Exception as e:
        logger.error(f"Lỗi khởi tạo Kafka Admin: {e}")

def wait_for_consumer_group(group_id, timeout=60):
    """
    Chặn luồng xử lý cho đến khi Consumer Group cụ thể đã online và sẵn sàng nhận tin.
    Khắc phục lỗi mất tin nhắn đầu tiên khi dùng auto.offset.reset=latest.
    """
    logger.info(f"⏳ Đang kiểm tra trạng thái Consumer Group: '{group_id}'...")
    
    try:
        admin_client = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
        start_time = time.time()
        
        while True:
            try:
                # Lấy thông tin group
                group_desc = admin_client.describe_consumer_groups([group_id])
                
                if not group_desc:
                    logger.warning(f"Group '{group_id}' chưa tìm thấy. Service Java có thể chưa bật.")
                else:
                    state = group_desc[0].state
                    members = group_desc[0].members
                    
                    # Log trạng thái để debug
                    # logger.info(f"Group State: {state} | Active Members: {len(members)}")

                    # Điều kiện thành công: Trạng thái STABLE hoặc đang cân bằng tải (REBALANCING) VÀ có ít nhất 1 member
                    if len(members) > 0:
                        logger.info(f"✅ Consumer Group '{group_id}' đã SẴN SÀNG! (Đang có {len(members)} consumer kết nối).")
                        break
                
                # Check Timeout
                if time.time() - start_time > timeout:
                    logger.warning(f"⚠️ Quá thời gian chờ ({timeout}s). Consumer '{group_id}' vẫn chưa sẵn sàng. Tiếp tục gửi và chấp nhận rủi ro.")
                    break
                    
                time.sleep(2) # Chờ 2 giây rồi check lại
                
            except Exception as inner_e:
                logger.warning(f"Đang chờ kết nối admin: {inner_e}")
                time.sleep(2)

        admin_client.close()
    except Exception as e:
        logger.error(f"Không thể khởi tạo Admin Client để check consumer: {e}")

CONSUMER_GROUP_ID_TO_WAIT = "news.profile.crawler.raw" 
wait_for_consumer_group(CONSUMER_GROUP_ID_TO_WAIT, timeout=45)

# Chạy setup ngay lập tức
ensure_all_topics_setup()

# 3. Khởi tạo Producer tối ưu
# - linger_ms: Đợi 5ms để gom batch (tăng throughput)
# - compression_type: Nén dữ liệu (tiết kiệm băng thông)
producer = KafkaProducer(
    bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    linger_ms=5, 
    compression_type='gzip' 
)

# 4. Callback Functions (Xử lý kết quả bất đồng bộ)
def on_send_success(record_metadata):
    # Chỉ log debug để tránh spam console khi chạy production
    logger.info(f"Gửi thành công tới {record_metadata.topic} - Part: {record_metadata.partition} - Offset: {record_metadata.offset}")

def on_send_error(excp):
    logger.error(f"Gửi Kafka thất bại: {excp}", exc_info=True)

# 5. Hàm Generic gửi dữ liệu
def _send_generic(topic_key, data, sync=False):
    topic = TOPIC_MAP.get(topic_key)
    if not topic:
        logger.error(f"Topic key '{topic_key}' không tồn tại.")
        return

    try:
        future = producer.send(topic, data)
        # Gắn callback để xử lý kết quả mà không chặn luồng chính
        future.add_callback(on_send_success).add_errback(on_send_error)
        
        # Chỉ flush khi thực sự cần thiết (VD: Logs quan trọng hoặc khi tắt app)
        if sync:
            producer.flush()
            logger.info(f"[Sync] Đã gửi tới {topic}")
            
    except Exception as e:
        logger.error(f"Lỗi khởi tạo gửi tới {topic}: {e}")

# 6. Các hàm Wrapper (Giữ lại interface cũ để không phải sửa code gọi)
def send_logs_to_kafka(logs: dict):
    # Logs có thể cần sync nếu là critical error, nếu không thì để async
    _send_generic("LOGS", logs, sync=False)

def send_tracking_status_to_kafka(tracking_status: dict):
    _send_generic("TRACKING", tracking_status)

def send_podcast_to_kafka(podcast_data: dict):
    _send_generic("PODCAST", podcast_data)

def send_clean_article_to_kafka(article_data: dict):
    _send_generic("DEFAULT", article_data)

def send_clean_article_dark_web_to_kafka(article_data: dict):
    _send_generic("DARK_WEB", article_data)

def send_comment_article_to_kafka(comment_data: dict):
    _send_generic("COMMENT", comment_data)

def send_profile_dark_web_to_kafka(profileInfor: dict):
    _send_generic("PROFILE_DARK_WEB", profileInfor)

def send_profile_to_kafka(profileInfor: dict):
    _send_generic("PROFILE", profileInfor)

# Lưu ý: Khi ứng dụng crawler kết thúc, hãy gọi producer.flush() một lần cuối cùng
# để đảm bảo các tin nhắn còn trong bộ đệm được đẩy đi hết.
def close_producer():
    logger.info("Đang flush dữ liệu và đóng producer...")
    producer.flush()
    producer.close()


def parse_datetime_to_timestamp(date_str: str) -> int:
    date_str_clean = date_str.split(" (")[0]
    dt = datetime.strptime(date_str_clean, "%d/%m/%Y, %H:%M")
    tz_local = pytz.timezone("Asia/Ho_Chi_Minh")
    dt_local = tz_local.localize(dt)
    dt_utc = dt_local.astimezone(pytz.UTC)
    timestamp_sec = int(dt_utc.timestamp())

    return timestamp_sec


def save_to_db(data, output_file=None):

    try:
        if isinstance(data, list):
            # Nếu là danh sách bài viết
            saved_ids = []
            for article in data:
                # Lưu metadata ảnh nếu có
                if 'imageUrl' in article and article['imageUrl']:
                    image_data = {
                        'image_url': article['imageUrl'],
                        'local_path': article.get('localImagePath', ''),
                        'file_size': article.get('imageSize', 0)
                    }
                    save_image_metadata(image_data)
                
                # Lưu bài viết
                result = save_article(article)
                if result:
                    saved_ids.append(str(result.inserted_id))
            
            print(f"✅ Đã lưu {len(saved_ids)} bài viết vào MongoDB")
            return saved_ids
            
        elif isinstance(data, dict):
            # Nếu là một bài viết đơn lẻ
            # Lưu metadata ảnh nếu có
            if 'imageUrl' in data and data['imageUrl']:
                image_data = {
                    'image_url': data['imageUrl'],
                    'local_path': data.get('localImagePath', ''),
                    'file_size': data.get('imageSize', 0)
                }
                save_image_metadata(image_data)
            
            # Lưu bài viết
            result = save_article(data)
            if result:
                print(f"✅ Đã lưu bài viết vào MongoDB với ID: {result.inserted_id}")
                return str(result.inserted_id)
        
        return None
        
    except Exception as e:
        print(f"❌ Lỗi khi lưu dữ liệu vào MongoDB: {e}")
        return None

def save_to_json(data):
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f" Dữ liệu đã lưu vào {OUTPUT_FILE}")
    except IOError as e:
        print(f" Lỗi khi ghi file {OUTPUT_FILE}: {e}")

def send_json_to_api():
    """Gửi file JSON đến API để lưu trữ"""
    if not os.path.exists(OUTPUT_FILE):
        print(" [] Không tìm thấy file JSON để upload")
        return
    # 1. Đọc JSON
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    image_urls = json_data.get("contentImageUrls", [])

    files = []

    # 2. Đính kèm JSON file
    files.append(("files", ("data.json", open(OUTPUT_FILE, "rb"), "application/json")))

    # 3. Tải từng ảnh từ URL và thêm vào files
    for i, url in enumerate(image_urls):
        try:
            img_response = requests.get(url, timeout=5, stream=True)
            if img_response.status_code == 200:
                img_bytes = BytesIO(img_response.content)
                mime_type, _ = mimetypes.guess_type(url)
                if not mime_type:
                    mime_type = "application/octet-stream"
                clean_url = url.split('?')[0]
                filename = Path(clean_url).name
                files.append(("files", (filename, img_bytes, mime_type)))
            else:
                print(f" ⚠️ Không tải được ảnh: {url}")
        except Exception as e:
            print(f" ❌ Lỗi tải ảnh {url}: {e}")

    # 4. Gửi đến API
    data = {"data": "NEWS_INFO"}

    try:
        response = requests.post(UPLOAD_API_URL, files=files, data=data)
        print(f" [] Upload API Response: {response}")
        # Nếu gửi thành công, xoá file JSON
        if response.status_code == 200:
            os.remove(OUTPUT_FILE)
            print(f"🗑 File {OUTPUT_FILE} đã bị xóa sau khi gửi!")
    except requests.RequestException as e:
        print(f" [] Lỗi khi gửi file: {e}")

def clean_date(text_date):
    """Chuẩn hóa định dạng ngày giờ: giữ số 0, chuyển AM/PM sang 24h, thêm (GMT+7) nếu thiếu."""
    # Loại bỏ phần "Thứ ..., ngày", "Chủ Nhật, ngày", hoặc "Thứ ... -" / "Chủ Nhật -"
    try:
        iso_match = re.match(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?",
            text_date
        )
        if iso_match:
            dt = datetime.fromisoformat(text_date)
            dt = dt.replace(tzinfo=timezone.utc).astimezone(
                timezone(timedelta(hours=7))
            )
            return int(dt.timestamp())

        match_dash_date = re.match(r"(\d{2})-(\d{2})-(\d{4})\s+(\d{1,2}):(\d{2})", text_date)
        if match_dash_date:
            day, month, year, hour, minute = match_dash_date.groups()
            text_date = f"{day}/{month}/{year}, {int(hour):02}:{minute} (GMT+7)"
            return parse_datetime_to_timestamp(text_date)
        text_date = unicodedata.normalize('NFC', text_date or "")

        match_vn_full = re.search(
            r"(Chủ\s*nhật|Thứ\s*\w+)\s*,?\s*(\d{1,2}/\d{1,2}/\d{4})\s*\|\s*(\d{1,2}:\d{2}:\d{2})",
            text_date,
            flags=re.IGNORECASE
        )
        if match_vn_full:
            _, date_part, time_part = match_vn_full.groups()
            d, m, y = date_part.split("/")
            h, mi, _ = time_part.split(":")
            text_date = f"{int(d):02}/{int(m):02}/{y}, {int(h):02}:{mi} (GMT+7)"
            return parse_datetime_to_timestamp(text_date)

        text_date = re.sub(r"\s*[-|]\s*", ", ", text_date)
        text_date = re.sub(r"^Cập nhật lúc\s*", "", text_date, flags=re.IGNORECASE).strip()
        text_date = re.sub(r"(Thứ\s\w+|Chủ\sNhật)[,\s-]*(ngày\s*)?", "", text_date, flags=re.IGNORECASE).strip()

        text_date = re.sub(r"\s*lúc\s*", " ", text_date, flags=re.IGNORECASE)

        text_date = re.sub(r"\(GMT\)", "", text_date)

        text_date = text_date.replace(" - ", ", ").replace(" -", ",").replace("- ", ",")

        match = re.search(r"(\d{1,2}):(\d{2})\s*,?\s*(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
        if match:
            hour, minute, day, month, year = match.groups()
            text_date = f"{int(day):02}/{int(month):02}/{year}, {int(hour):02}:{minute}"
        else:
            match_date = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
            if match_date:
                day, month, year = match_date.groups()
                text_date = text_date.replace(match_date.group(), f"{int(day):02}/{int(month):02}/{year}")

            match_time = re.search(r"(\d{1,2}):(\d{2})\s?(AM|PM)?", text_date, re.IGNORECASE)
            if match_time:
                hour, minute, period = match_time.groups()
                hour = int(hour)
                if period:
                    if period.upper() == "PM" and hour != 12:
                        hour += 12
                    elif period.upper() == "AM" and hour == 12:
                        hour = 0
                text_date = re.sub(r"(\d{1,2}):(\d{2})\s?(AM|PM)?", f"{hour:02}:{minute}", text_date)

            text_date = re.sub(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})", r"\1, \2", text_date)

        match_timezone = re.search(r"(\d{2}/\d{2}/\d{4})\s*(\d{2}:\d{2}):\d{2}\s*\+?\d{1,2}:\d{2}", text_date)
        if match_timezone:
            date, time = match_timezone.groups()
            text_date = f"{date}, {time} (GMT+7)"

        text_date = re.sub(r"(:\d{2})\s?\+?\d{1,2}:\d{2}", "", text_date)

        text_date = re.sub(r"(?<!\s)\(GMT\+7\)", r" (GMT+7)", text_date)
        # Nếu chỉ có ngày (không có giờ), thêm mặc định 00:00
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text_date.strip()):
            text_date = f"{text_date.strip()}, 00:00"

        if "(GMT+7)" not in text_date:
            text_date += " (GMT+7)"
        return parse_datetime_to_timestamp(text_date)
    except Exception as e:
        print(f"[clean_date] Cannot parse: {text_date}. Error: {e}")
        return None

def get_urls_of_type(self, article_type):
    articles_urls = set()
    page_number = 1
    progress = tqdm(desc="Pages", unit=" page")
    num_workers_default = 5
    domain = self.base_url.split("/")[2]
    for suffix in [".com.vn", ".net.vn", ".gov.vn", ".org.vn", ".edu.vn", ".vn"]:
        if domain.endswith(suffix):
            domain = domain.replace(suffix, "")
            break
    num_workers = 1 if domain in CRAWLERS_SELENIUM else num_workers_default
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {}
        while True:
            # Gửi batch gồm num_workers page một lúc
            for _ in range(num_workers):
                future = executor.submit(self.get_urls_of_type_thread, article_type, page_number)
                futures[future] = page_number
                page_number += 1

            stop = False
            for future in concurrent.futures.as_completed(futures):
                page = futures[future]
                try:
                    result = future.result()
                    progress.update(1)
                    if not result:
                        print(f"[!] Page {page} returned empty. Stopping further crawl.")
                        stop = True
                    elif type(result) == set:
                        stop = True
                        result = list(result)
                    articles_urls.update(result)
                except Exception as e:
                    print(f"[!] Error on page {page}: {e}")

            futures.clear()
            if stop:
                break

    return list(articles_urls)

def remove_duplicate_urls(urls):
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls

def normalize_url_to_root_https(url: str) -> str:
    if not url:
        raise ValueError("Empty url")
    if "://" not in url:
        url = "https://" + url

    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]

    if not host:
        raise ValueError(f"Cannot extract host from: {url}")

    return f"https://{host}"

def parse_vnexpress_time_ms(time_str):
    """
    Chuyển thời gian comment VNExpress sang timestamp milliseconds.
    Bao quát các case:
    - "4h trước", "50' trước"
    - "1 ngày trước"
    - "Hôm nay HH:MM", "Hôm qua HH:MM"
    - "DD/MM/YYYY HH:MM"
    """
    if not time_str:
        return None

    now = datetime.now()
    time_str = time_str.strip()
    time_str = time_str.lower().strip()
    time_str = re.sub(r"\s+", " ", time_str)
    time_str = time_str.replace("giờ", "giờ")


    #Case: "-5882 giây trước" hoặc "5882 giây trước"
    match_seconds = re.search(r"(-?\d+)\s*giây", time_str)
    if match_seconds:
        secs = abs(int(match_seconds.group(1)))
        dt = now - timedelta(seconds=secs)
        return int(dt.timestamp() * 1000)

    # Case: 'X giờ trước' hoặc 'Xh trước' hoặc "X' trước"
    match_hour_vi = re.match(r"(\d+)\s*giờ", time_str, flags=re.IGNORECASE)
    if match_hour_vi:
        value = int(match_hour_vi.group(1))
        dt = now - timedelta(hours=value)
        return int(dt.timestamp() * 1000)

    # Case: 'Xh trước' hoặc "Y' trước"
    match = re.match(r"(\d+)\s*([hH]|')", time_str)
    if match:
        value, unit = match.groups()
        value = int(value)
        dt = now - timedelta(hours=value) if unit.lower() == "h" else now - timedelta(minutes=value)
        return int(dt.timestamp() * 1000)

    # Case: 'Z ngày trước'
    match_day = re.match(r"(\d+)\s*ngày trước", time_str)
    if match_day:
        value = int(match_day.group(1))
        dt = now - timedelta(days=value)
        return int(dt.timestamp() * 1000)
    match = re.match(r"(\d+)\s*tháng", time_str)
    if match:
        months = int(match.group(1))
        # Lùi lại X tháng (ước lượng mỗi tháng = 30 ngày)
        dt = now - timedelta(days=months * 30)
        return int(dt.timestamp() * 1000)
    # Case: 'Hôm nay HH:MM'
    match_today = re.match(r"Hôm nay\s*(\d{1,2}):(\d{2})", time_str)
    if match_today:
        hour, minute = map(int, match_today.groups())
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return int(dt.timestamp() * 1000)

    # Case: 'Hôm qua HH:MM'
    match_yesterday = re.match(r"Hôm qua\s*(\d{1,2}):(\d{2})", time_str)
    if match_yesterday:
        hour, minute = map(int, match_yesterday.groups())
        yesterday = now - timedelta(days=1)
        dt = yesterday.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return int(dt.timestamp() * 1000)

    # Case: 'DD/MM/YYYY HH:MM'
    s = time_str.replace("\u200b", "").replace("\xa0", " ").strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y, %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            pass
        
    # Case: 'DD-MM-YYYY HH:MM' hoặc 'DD-MM-YYYY, HH:MM'
    for fmt in ("%d-%m-%Y %H:%M", "%d-%m-%Y, %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return int(dt.timestamp() * 1000)
        except ValueError:
            pass

    # Thứ , DD/MM/YYYY, HH:MM (GMT+7)
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}).*?(\d{1,2}:\d{2})", s)
    if m: return int(datetime.strptime(f"{m[1]} {m[2]}", "%d/%m/%Y %H:%M").timestamp()*1000)      
        # Case: "Thứ Năm, 09:43, 29/05/2025" (giờ trước, ngày sau)
    m = re.search(r"(\d{1,2}:\d{2}).*?(\d{1,2}/\d{1,2}/\d{4})", s)
    if m: return int(datetime.strptime(f"{m[2]} {m[1]}", "%d/%m/%Y %H:%M").timestamp()*1000)


    return None  # Không parse được

def normalize_tuple_date(input_date):
    try:
        # Nếu input là tuple/list thì lấy phần tử đầu tiên
        if isinstance(input_date, (tuple, list)):
            input_date = input_date[0] if input_date else ""

        text_date = str(input_date).strip()
        # NEW: Trường hợp tiếng Anh có thứ trong tuần, ví dụ: "Sunday, 31 January 2021"
        m_en_day = re.match(
            r"(?i)^(monday|tuesday|wednesday|thursday|friday|saturday|sunday),\s*(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})$",
            text_date
        )
        if m_en_day:
            _, day, month_en, year = m_en_day.groups()
            try:
                from datetime import datetime
                dt = datetime.strptime(f"{day} {month_en} {year}", "%d %B %Y")
                return f"{dt.day:02}/{dt.month:02}/{dt.year}, 00:00 (GMT+7)"
            except ValueError:
                pass  # fallback to next format if needed

        # NEW: Trường hợp tiếng Anh có thứ: "Wednesday, December 3, 2025"
        m_en_day_month = re.match(
            r"(?i)^(monday|tuesday|wednesday|thursday|friday|saturday|sunday),\s*([a-zA-Z]+)\s+(\d{1,2}),\s*(\d{4})$",
            text_date
        )
        if m_en_day_month:
            _, month_en, day, year = m_en_day_month.groups()
            try:
                from datetime import datetime
                dt = datetime.strptime(f"{day} {month_en} {year}", "%d %B %Y")
                return f"{dt.day:02}/{dt.month:02}/{dt.year}, 00:00 (GMT+7)"
            except ValueError:
                pass

        # Loại bỏ tiền tố "Thứ ...," trong tiếng Việt
        text_date = re.sub(r"^(thứ\s+[a-zA-ZÀ-ỹ]+|chủ\s+nhật),?\s*", "", text_date, flags=re.IGNORECASE)
        m_vi_month_num = re.match(
            r"(?i)^tháng\s+(\d{1,2})\s+(\d{1,2}),\s*(\d{4})$",
            text_date
        )


        # NEW: Trường hợp tiếng Pháp có thứ trong tuần: "vendredi 7 novembre 2025"
        m_fr_day = re.match(
            r"^\s*[a-zA-Zéèêîôûàùçäëïöüÿâœæ-]+\s+(\d{1,2})\s+([a-zA-Zéèêîôûàùçäëïöüÿâœæ-]+)\s+(\d{4})$",
            text_date,
            re.IGNORECASE
        )
        if m_fr_day:
            day, month_fr, year = m_fr_day.groups()
            month_fr = month_fr.strip().lower()

            fr_months = {
                "janvier": 1, "février": 2, "fevrier": 2, "mars": 3,
                "avril": 4, "mai": 5, "juin": 6,
                "juillet": 7, "août": 8, "aout": 8,
                "septembre": 9, "octobre": 10,
                "novembre": 11, "décembre": 12, "decembre": 12
            }

            month = fr_months.get(month_fr)
            if month:
                return f"{int(day):02}/{month:02}/{int(year)}, 00:00 (GMT+7)"

        # NEW: Trường hợp ngày tiếng Pháp "03 avril 2022"
        m_fr = re.match(
            r"^\s*(\d{1,2})\s+([a-zA-Zéèêîôûàùçäëïöüÿâœæ-]+)\s+(\d{4})\s*$",
            text_date,
            re.IGNORECASE
        )
        if m_fr:
            day, month_fr, year = m_fr.groups()
            month_fr = month_fr.strip().lower()

            fr_months = {
                "janvier": 1, "février": 2, "fevrier": 2, "mars": 3,
                "avril": 4, "mai": 5, "juin": 6,
                "juillet": 7, "août": 8, "aout": 8,
                "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12
            }

            month = fr_months.get(month_fr)
            if month:
                return f"{int(day):02}/{month:02}/{int(year)}, 00:00 (GMT+7)"

        # NEW: Trường hợp "tháng 11 13, 2020"
        m_vi_month_num = re.match(
            r"(?i)^tháng\s+(\d{1,2})\s+(\d{1,2}),\s*(\d{4})$",
            text_date
        )
        if m_vi_month_num:
            month, day, year = map(int, m_vi_month_num.groups())
            if 1 <= month <= 12:
                return f"{day:02}/{month:02}/{year}, 00:00 (GMT+7)"

        # NEW: Trường hợp "Tháng Một 7, 2025"
        m_vi_enlike = re.match(
            r"(?i)^tháng\s+([A-Za-zÀ-ỹ]+)\s+(\d{1,2}),\s*(\d{4})$",
            text_date
        )
        if m_vi_enlike:
            mon_token, day, year = m_vi_enlike.groups()

            def _strip_accents(s: str) -> str:
                import unicodedata
                return ''.join(c for c in unicodedata.normalize('NFD', s)
                            if unicodedata.category(c) != 'Mn')

            key = _strip_accents(mon_token).lower().strip()

            vn_months = {
                "mot": 1, "một": 1,
                "hai": 2,
                "ba": 3,
                "bon": 4, "bốn": 4, "tư": 4,
                "nam": 5, "năm": 5,
                "sau": 6, "sáu": 6,
                "bay": 7, "bảy": 7,
                "tam": 8, "tám": 8,
                "chin": 9, "chín": 9,
                "muoi": 10, "mười": 10,
                "muoi mot": 11, "mười một": 11,
                "muoi hai": 12, "mười hai": 12,
            }

            month = vn_months.get(key)
            if month and 1 <= month <= 12:
                return f"{int(day):02}/{int(month):02}/{int(year):04}, 00:00 (GMT+7)"

        # dd.MM.yyyy  hoặc  dd.MM.yyyy HH:mm
        m_dot = re.match(
            r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})(?:\s+(\d{1,2}):(\d{2}))?\s*$",
            text_date
        )
        if m_dot:
            d, m, y, hh, mm = m_dot.groups()
            hh = int(hh) if hh is not None else 0
            mm = mm if mm is not None else "00"
            return f"{int(d):02}/{int(m):02}/{y}, {hh:02}:{mm} (GMT+7)"

        m_ymd = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?\s*$", text_date)
        if m_ymd:
            year, month, day, hh, mm = m_ymd.groups()
            hh = int(hh) if hh else 0
            mm = int(mm) if mm else 0
            return f"{int(day):02}/{int(month):02}/{int(year):04}, {hh:02}:{mm:02} (GMT+7)"

        # 2) Month DD, YYYY (English)  → "October 22, 2015" / "Oct 22, 2015"
        mdy_match = re.match(r"^[A-Za-z]+\s+\d{1,2},\s*\d{4}$", text_date)
        if mdy_match:
            try:
                dt = datetime.strptime(text_date, "%B %d, %Y")
            except ValueError:
                dt = datetime.strptime(text_date, "%b %d, %Y")
            return f"{dt.day:02}/{dt.month:02}/{dt.year}, 00:00 (GMT+7)"
        # 2b) DD Tháng <tên-tháng>, YYYY  → "1 Tháng Bảy, 2025"
        m_vi_day_first = re.match(
            r"(?i)^\s*(\d{1,2})\s*tháng\s*([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+)?)\s*,?\s*(\d{4})\s*$",
            text_date
        )
        if m_vi_day_first:
            day, mon_token, year = m_vi_day_first.groups()

            # bỏ dấu và chuẩn hoá token tháng
            import unicodedata
            def _strip_accents(s: str) -> str:
                return ''.join(c for c in unicodedata.normalize('NFD', s)
                            if unicodedata.category(c) != 'Mn')

            key = _strip_accents(mon_token).lower().strip()
            key = re.sub(r"\s+", " ", key)

            vn_months = {
                "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5,
                "sau": 6, "bay": 7, "tam": 8, "chin": 9,
                "muoi": 10, "muoi mot": 11, "muoi hai": 12,
            }
            if key.isdigit():
                month = int(key)
            else:
                month = vn_months.get(key)
                if month is None and key.startswith("muoi "):
                    if " mot" in key: month = 11
                    elif " hai" in key: month = 12

            if month and 1 <= month <= 12:
                return f"{int(day):02}/{int(month):02}/{int(year):04}, 00:00 (GMT+7)"

        # 3) Tháng <chữ/số> DD, YYYY (tiếng Việt) → "Tháng Tám 17, 2020", "tháng 12 5, 2024"
        m_vi = re.match(
            r"(?i)^\s*tháng\s+([A-Za-zÀ-ỹ]+(?:\s+[A-Za-zÀ-ỹ]+)?|\d{1,2})\s+(\d{1,2}),\s*(\d{4})\s*$",
            text_date
        )
        if m_vi:
            mon_token, day, year = m_vi.groups()

            def _strip_accents(s: str) -> str:
                import unicodedata, re as _re
                return ''.join(c for c in unicodedata.normalize('NFD', s)
                            if unicodedata.category(c) != 'Mn')

            key = _strip_accents(mon_token).lower().strip()
            key = re.sub(r"\s+", " ", key)

            vn_months = {
                "mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5,
                "sau": 6, "bay": 7, "tam": 8, "chin": 9,
                "muoi": 10, "muoi mot": 11, "muoi hai": 12,
            }

            if key.isdigit():
                month = int(key)
            else:
                month = vn_months.get(key)
                if month is None and key.startswith("muoi "):
                    if " mot" in key: month = 11
                    elif " hai" in key: month = 12

            if month and 1 <= month <= 12:
                return f"{int(day):02}/{int(month):02}/{int(year):04}, 00:00 (GMT+7)"
        if isinstance(input_date, (tuple, list)):
            input_date = input_date[0] if input_date else ""

        if not input_date or str(input_date).strip().lower() in {"", "none", "None"}:
            return ""

        # Trường hợp: ISO 8601 có timezone → chuyển về dạng chuẩn dd/mm/yyyy, HH:MM (GMT+7)
        m_iso = re.match(
            r"^\s*(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})\+(\d{2}):?(\d{2})\s*$",
            text_date
        )
        if m_iso:
            y, m, d, hh, mm, ss, tzh, tzm = map(int, m_iso.groups())
            dt = datetime(y, m, d, hh, mm, ss) + timedelta(hours=tzh, minutes=tzm)
            return dt.strftime("%d/%m/%Y, %H:%M (GMT+7)")

        # Trường hợp: "Ngày 25 / 08 / 2025"
        m_ngay = re.match(r"(?i)^ngày\s*(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})$", text_date)
        if m_ngay:
            d, m, y = map(int, m_ngay.groups())
            return f"{d:02}/{m:02}/{y}, 00:00 (GMT+7)"


        # 1) Support format: "Chủ Nhật, 5 tháng 5, 2024"
        match_vn = re.search(r"(\d{1,2})\s*tháng\s*(\d{1,2}),\s*(\d{4})", text_date, re.IGNORECASE)
        if match_vn:
            day, month, year = match_vn.groups()
            text_date = f"{int(day):02}/{int(month):02}/{year}"

        # 2) Format d/m/yyyy or m/d/yyyy
        match_slash = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
        if match_slash:
            d1, d2, year = match_slash.groups()
            d1, d2 = int(d1), int(d2)
            if d1 <= 12 and d2 > 12:  # swap nếu d1 là tháng và d2 là ngày
                d1, d2 = d2, d1
            text_date = f"{d1:02}/{d2:02}/{year}"

        # 3) Nếu chưa có giờ → thêm mặc định
        if not re.search(r"\d{1,2}:\d{2}", text_date):
            text_date += " 00:00"

        # 4) Nếu chưa có timezone → thêm GMT+7
        if not re.search(r"GMT|UTC|Z|\+\d{1,2}", text_date, re.IGNORECASE):
            text_date += " (GMT+7)"

        return text_date

    except Exception as e:
        print(f"[normalize_tuple_date] Error xử lý: {input_date}, Error: {e}")
        return ""

def time_to_seconds(time_str: str) -> int:
    if not time_str:
        return 0
    s = str(time_str).strip().replace(" ", "")
    parts = s.split(":")
    # Chỉ giữ tối đa 3 phần (HH:MM:SS); nếu dài hơn thì lấy 3 phần cuối
    parts = parts[-3:]
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return 0

    if len(nums) == 1:
        # "45" -> 45 giây
        return nums[0]
    elif len(nums) == 2:
        # "09:48" -> 9*60 + 48
        m, sec = nums
        return m * 60 + sec
    else:
        # "1:02:03" -> 1*3600 + 2*60 + 3
        h, m, sec = nums
        return h * 3600 + m * 60 + sec
