from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler
from ui_checker import UIChecker
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
    body: Dict[str, Optional[str | List[str]]] = Field(..., description="Thông tin chính của yêu cầu")
    params: Optional[Dict[str, Optional[str | int]]] = Field(None, description="Tham số tùy chọn")

@app.post("/crawl/")
def crawl_article(data: dict):
    print(f"Processing message1111111111111: {data}")
    parsed_data = json.loads(data["message"])

    # Truy cập vào các phần tử bên trong
    source = parsed_data["source"]
    action = parsed_data["action"]
    url = parsed_data["body"]["url"]
    if source != "NEWS" or action != "ARTICLE":
        return {"status": "error", "error": "Sai source hoặc action"}

    # body = data.body
    # params = data.params or {}

 
    # keywords = body.get("keywords", [])
    # max_articles = params.get("maxArticles")

    response = {
        "status": "success",
        "url": url,
        # "keywords": keywords,
        # "maxArticles": max_articles,
        "articles": [],
        "error": ""
    }
    domain = url.split("/")[2]
    crawler = CRAWLERS.get(domain)
    # Xử lý khi URL là bài viết cụ thể (chứa slug hoặc ID bài viết)
    if re.search(r'\d{6,}.html$', url):
        article = get_article_details(crawler, url)
        if not article:
            return {"status": "error", "error": "Không tìm thấy bài viết hoặc URL không hợp lệ"}
        response["articles"].append(article)
        print(f"======================response======================", response)
        return response
    # Xử lý khi URL là trang chủ hoặc danh mục
    elif url.endswith(domain):
        urls = crawler.get_all_articles(1)
        response["articles"] = [get_article_details(crawler, url) for url in urls]
        print(f"=======================Processing 1 trang bao: {response}")
        save_output_to_json(response)
        return response

    else:
        return {"status": "error", "error": "URL không hợp lệ hoặc chưa được hỗ trợ"}

def get_article_details(crawler, url: str) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    title, description, paragraphs, published_date, image_url, comments = crawler.extract_content(url)
    
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


@app.get("/")
def read_root():
    return {"message": "API is running"}

@app.post("/process_message/")
def process_message(data: dict):
    print(f"Processing message: {data}")
    return {"status": "processed"}
