from fastapi import FastAPI, File, UploadFile, Form, HTTPException
import re
import os
import requests
import json
from datetime import datetime
import time
from pathlib import Path
from utils.mongodb_utils import save_article, save_image_metadata, save_category
from constants.crawlerselenium import CRAWLERS_SELENIUM
import unicodedata
import concurrent.futures
from tqdm import tqdm
from io import BytesIO
import mimetypes

OUTPUT_FILE = "crawl_result.json"
UPLOAD_API_HOST = "192.168.132.250"
# UPLOAD_API_HOST = "localhost"
UPLOAD_API_PORT = "8080"
UPLOAD_API_ENDPOINT = "/api/upload/multiple"
UPLOAD_API_URL = f"http://{UPLOAD_API_HOST}:{UPLOAD_API_PORT}{UPLOAD_API_ENDPOINT}"

def save_to_db(data, output_file=None):
    """
    Lưu dữ liệu vào MongoDB
    
    Args:
        data (dict/list): Dữ liệu cần lưu
        output_file (str, optional): Không sử dụng trong MongoDB, giữ lại để tương thích
    
    Returns:
        str: ID của bản ghi đã lưu hoặc None nếu có lỗi
    """
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


# Hàm lưu dữ liệu vào file JSON
def save_to_json(data):
    """Lưu dữ liệu vào file JSON"""
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
    text_date = unicodedata.normalize('NFC', text_date or "")
    text_date = re.sub(r"\s*[-|]\s*", ", ", text_date)
    text_date = re.sub(r"^Cập nhật lúc\s*", "", text_date, flags=re.IGNORECASE).strip()
    text_date = re.sub(r"(Thứ\s\w+|Chủ\sNhật)[,\s-]*(ngày\s*)?", "", text_date, flags=re.IGNORECASE).strip()
    # Loại bỏ từ "lúc" giữa ngày và giờ
    text_date = re.sub(r"\s*lúc\s*", " ", text_date, flags=re.IGNORECASE)

    # Loại bỏ (GMT) không rõ ràng
    text_date = re.sub(r"\(GMT\)", "", text_date)

    # Thay dấu "-" bằng dấu ","
    text_date = text_date.replace(" - ", ", ").replace(" -", ",").replace("- ", ",")

    # Nếu text có dạng [giờ phút][khoảng trắng][ngày/tháng/năm]
    match = re.search(r"(\d{1,2}):(\d{2})\s*,?\s*(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
    if match:
        hour, minute, day, month, year = match.groups()
        text_date = f"{int(day):02}/{int(month):02}/{year}, {int(hour):02}:{minute}"
    else:
        # Nếu là dạng ngày trước giờ sau
        # Chuẩn hóa ngày/tháng/năm thành dạng 2 chữ số (nếu thiếu)
        match_date = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
        if match_date:
            day, month, year = match_date.groups()
            text_date = text_date.replace(match_date.group(), f"{int(day):02}/{int(month):02}/{year}")

        # Chuẩn hóa giờ phút AM/PM (nếu có)
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

        # Đảm bảo có dấu "," giữa ngày và giờ nếu thiếu
        text_date = re.sub(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})", r"\1, \2", text_date)

    # Xử lý cho trường hợp có múi giờ và ngày tháng giờ kết hợp như "Thứ Sáu, 04/10/2024 16:40:00 +07:00"
    match_timezone = re.search(r"(\d{2}/\d{2}/\d{4})\s*(\d{2}:\d{2}):\d{2}\s*\+?\d{1,2}:\d{2}", text_date)
    if match_timezone:
        date, time = match_timezone.groups()
        text_date = f"{date}, {time} (GMT+7)"

    # Loại bỏ giây (nếu có) và múi giờ (+07:00) nếu có
    text_date = re.sub(r"(:\d{2})\s?\+?\d{1,2}:\d{2}", "", text_date)

    # Đảm bảo có dấu cách trước (GMT+7) nếu thiếu
    text_date = re.sub(r"(?<!\s)\(GMT\+7\)", r" (GMT+7)", text_date)

    if "(GMT+7)" not in text_date:
        text_date += " (GMT+7)"

    return text_date

def get_urls_of_type(self, article_type):
    articles_urls = set()
    page_number = 1
    progress = tqdm(desc="Pages", unit=" page")
    domain = self.base_url.split("/")[2]
    for suffix in [".com.vn", ".net.vn", ".gov.vn", ".org.vn", ".edu.vn", ".vn"]:
        if domain.endswith(suffix):
            domain = domain.replace(suffix, "")
            break
    num_workers = 1
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
