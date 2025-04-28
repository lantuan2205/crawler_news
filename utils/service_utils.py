from fastapi import FastAPI, File, UploadFile, Form, HTTPException
import re
import os
import requests
import json
from datetime import datetime
import time
from pathlib import Path
from utils.mongodb_utils import save_article, save_image_metadata, save_category

OUTPUT_FILE = "crawl_result.json"
UPLOAD_API_HOST = "192.168.132.250"
UPLOAD_API_PORT = "8080"
UPLOAD_API_ENDPOINT = "/api/upload"
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
    with open(OUTPUT_FILE, "rb") as f:
        files = {"file": f}
        data = {"data": "NEWS_INFO"}  # Thêm metadata

        try:
            response = requests.post(UPLOAD_API_URL, files=files, data=data)
            print(f" [] Upload API Response: {response}")

        except requests.RequestException as e:
            print(f" [] Lỗi khi gửi file: {e}")
    # Nếu gửi thành công, xoá file JSON
    if response.status_code == 200:
        os.remove(OUTPUT_FILE)
        print(f"🗑 File {OUTPUT_FILE} đã bị xóa sau khi gửi!")

def clean_date(text_date):
    """Chuẩn hóa định dạng ngày giờ: giữ số 0, chuyển AM/PM sang 24h, thêm (GMT+7) nếu thiếu."""
    # Loại bỏ phần "Thứ ..., ngày", "Chủ Nhật, ngày", hoặc "Thứ ... -" / "Chủ Nhật -"
    text_date = re.sub(r"(Thứ\s\w+|Chủ\sNhật)[,\s-]*(ngày\s*)?", "", text_date, flags=re.IGNORECASE).strip()

    # Thay dấu "-" bằng dấu ","
    text_date = text_date.replace(" - ", ", ").replace(" -", ",").replace("- ", ",")

    # Nếu text có dạng [giờ phút][khoảng trắng][ngày/tháng/năm]
    match = re.search(r"(\d{1,2}):(\d{2})\s*(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
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

    # Đảm bảo có (GMT+7) nếu chưa có
    if "(GMT+7)" not in text_date:
        text_date += " (GMT+7)"

    return text_date

