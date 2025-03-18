from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Union
from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler
import re
import json

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

    print(f"======================response======================", response["articles"])
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
        "title": title,
        "url": url,
        "published_date": published_date,
        "image_url": image_url,
        "description": list(description),
        "content": list(paragraphs),
        "comments": list(comments) if comments else ["Không có bình luận"]
    }

# @app.get("/")
# def read_root():
#     return {"message": "API is running"}

# @app.post("/process_message/")
# def process_message(data: dict):
#     print(f"Processing message: {data}")
#     return {"status": "processed"}

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