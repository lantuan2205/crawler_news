from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler
from ui_checker import UIChecker
import re

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

@app.post("/crawl")
def crawl_article(request: RequestBody):
    if request.source != "NEWS" or request.action != "ARTICLE":
        return {"status": "error", "error": "Sai source hoặc action"}

    body = request.body
    params = request.params or {}

    url = body.get("url")
    # keywords = body.get("keywords", [])
    # max_articles = params.get("maxArticles")
    from_date = params.get("fromDate")

    response = {
        "status": "success",
        "url": url,
        # "keywords": keywords,
        # "maxArticles": max_articles,
        "fromDate": from_date,
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
        return response

    # Xử lý khi URL là trang chủ hoặc danh mục
    elif url.endswith(domain):
        urls = crawler.get_all_articles(1)
        response["articles"] = [get_article_details(crawler, url) for url in urls]
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
