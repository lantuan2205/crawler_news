from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler

app = FastAPI()

CRAWLERS = {
    "vnexpress.net": VNExpressCrawler(),
    "vietnamnet.vn": VietNamNetCrawler()
}

class ArticleRequest(BaseModel):
    url: Optional[str] = Field(None, description="URL cụ thể của bài báo")
    domain: Optional[str] = Field(None, description="Tên miền website")
    category: Optional[str] = Field(None, description="Thể loại bài báo")
    page: Optional[int] = Field(1, description="Số trang bài báo")

@app.post("/crawl")
def crawl_article(request: ArticleRequest):
    response = {
        "status": "success",
        "domain": request.domain,
        "category": request.category,
        "page": request.page,
        "articles": [],
        "error": ""
    }

    # Nếu có URL → Chỉ crawl bài báo đó
    if request.url:
        domain = request.url.split("/")[2]
        crawler = CRAWLERS.get(domain)

        if not crawler:
            return {"status": "error", "error": f"Không hỗ trợ crawl từ {domain}"}

        article = get_article_details(crawler, request.url)
        if not article:
            return {"status": "error", "error": "Không tìm thấy bài viết hoặc URL không hợp lệ"}

        response["articles"].append(article)
        return response

    # Nếu chỉ có domain, crawl toàn bộ bài báo của domain đó
    if request.domain and not request.category:
        crawler = CRAWLERS.get(request.domain)
        if not crawler:
            return {"status": "error", "error": f"Không hỗ trợ crawl từ {request.domain}"}
        max_pages = 1 if request.page is None else request.page
        urls = crawler.get_all_articles(max_pages)
        response["articles"] = [get_article_details(crawler, url) for url in urls]
        return response

    # Nếu có domain + category, crawl danh sách bài báo của category đó
    if request.domain and request.category:
        crawler = CRAWLERS.get(request.domain)
        if not crawler:
            return {"status": "error", "error": f"Không hỗ trợ crawl từ {request.domain}"}

        urls = crawler.get_urls_of_type_thread(request.category, request.page)
        response["articles"] = [get_article_details(crawler, url) for url in urls]
        return response

    return {"status": "error", "error": "Cần cung cấp ít nhất một trong các tham số: url, domain, category"}

def get_article_details(crawler, url: str) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    title, description, paragraphs, published_date, image_url, comments = crawler.extract_content(url)
    
    if not title:
        return None

    return {
        "title": title,
        "published_date": published_date,
        "image_url": image_url,
        "description": list(description),
        "content": list(paragraphs),
        "comments": list(comments) if comments else ["Không có bình luận"]
    }
