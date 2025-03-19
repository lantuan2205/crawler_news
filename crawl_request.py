from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Union
from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler
import re
import json
from datetime import datetime

app = FastAPI()

CRAWLERS = {
    "vnexpress.net": VNExpressCrawler(),
    "vietnamnet.vn": VietNamNetCrawler()
}

class RequestBody(BaseModel):
    source: str = Field(..., description="Nguồn dữ liệu (VD: NEWS)")
    action: str = Field(..., description="Loại hành động (VD: ARTICLE)")
    body: Dict[str, Optional[Union[str, List[str]]]] = Field(..., description="Thông tin chính của yêu cầu")
    params: Optional[Dict[str, Optional[Union[str, int]]]] = Field(None, description="Tham số tùy chọn")


def clean_date(text_date):
    """Chuẩn hóa định dạng ngày giờ: giữ số 0, chuyển AM/PM sang 24h, thêm (GMT+7) nếu thiếu."""
    # Loại bỏ phần "Thứ ..., ngày"
    text_date = re.sub(r"Thứ\s\w+,?\s*(ngày\s*)?", "", text_date, flags=re.IGNORECASE).strip()

    # Thay dấu "-" bằng dấu ","
    text_date = text_date.replace(" - ", ", ")

    # Chuẩn hóa ngày/tháng/năm thành dạng 2 chữ số (nếu thiếu)
    match_date = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text_date)
    if match_date:
        day, month, year = match_date.groups()
        text_date = text_date.replace(match_date.group(), f"{int(day):02}/{int(month):02}/{year}")

    # Chuyển định dạng "00:20 AM" thành 24h (00:20)
    match_time = re.search(r"(\d{1,2}):(\d{2})\s?(AM|PM)?", text_date, re.IGNORECASE)
    if match_time:
        hour, minute, period = match_time.groups()
        hour = int(hour)
        if period:
            if period.upper() == "PM" and hour != 12:
                hour += 12
            elif period.upper() == "AM" and hour == 12:
                hour = 0
        text_date = text_date.replace(match_time.group(), f"{hour:02}:{minute}")

    # Đảm bảo có dấu "," giữa ngày và giờ nếu thiếu
    text_date = re.sub(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})", r"\1, \2", text_date)

    # Đảm bảo có (GMT+7) nếu chưa có
    if "(GMT+7)" not in text_date:
        text_date += " (GMT+7)"

    return text_date

@app.post("/crawl/")
def crawl_article(data: dict):
    print(f"Processing message: {data}")

    try:
        parsed_data = json.loads(data["message"]) if isinstance(data["message"], str) else data["message"]
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    source = parsed_data.get("source")
    action = parsed_data.get("action")
    url = parsed_data.get("body", {}).get("url")

    if source != "NEWS" or action != "ALL":
        raise HTTPException(status_code=400, detail="Sai source hoặc action")

    if not url:
        raise HTTPException(status_code=400, detail="URL không được để trống")

    domain = url.split("/")[2]
    crawler = CRAWLERS.get(domain)

    if not crawler:
        raise HTTPException(status_code=400, detail="Không hỗ trợ domain này")

    response = {
        "status": "success",
        "url": url,
        "articles": [],
        "error": ""
    }

    # Xử lý URL bài viết cụ thể (chứa ID hoặc slug)
    if re.search(r'\d{6,}.html$', url):
        article = get_article_details(crawler, url)
        if not article:
            raise HTTPException(status_code=404, detail="Không tìm thấy bài viết hoặc URL không hợp lệ")
        response["articles"].append(article)
    # Xử lý URL trang chủ hoặc danh mục
    elif url.endswith(domain):
        try:
            urls = crawler.get_all_articles(1)
            response["articles"] = [get_article_details(crawler, article_url) for article_url in urls if article_url]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi khi lấy danh sách bài viết: {e}")

    else:
        raise HTTPException(status_code=400, detail="URL không hợp lệ hoặc chưa được hỗ trợ")
    return response

def get_article_details(crawler, url: str) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    try:
        title, description, paragraphs, published_date, image_url, comments = crawler.extract_content(url)
    except Exception as e:
        print(f"Lỗi khi lấy nội dung bài báo: {e}")
        return None

    if not title:
        return None

    return {
        "dataSource": "/".join(url.split("/")[:3]),
        "title": title,
        "url": url,
        "publishedDate": clean_date(published_date),
        "imageUrl": image_url,
        "description": " ".join(list(description)),
        "content": ",".join(list(paragraphs)),
        "comments": list(comments) if comments else [""]
    }

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), data: str = Form(...)):
    """
    API nhận file JSON nhưng KHÔNG lưu vào thư mục.
    Chỉ trả về thông tin file và metadata.
    """
    return {
        "message": "File received successfully",
        "filename": file.filename,
        "content_type": file.content_type,
        "size": file.size,
        "data": data
    }