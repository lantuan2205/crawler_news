from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Union
from utils.service_utils import save_to_json, send_json_to_api, clean_date
import re
import os
import requests
import json
from datetime import datetime
import time
from constants.crawlers import CRAWLERS
app = FastAPI()

@app.post("/crawl/")
def crawl_article(data: dict):
    print(f"Processing message: {data}")
    print(f"START crawling.....")
    try:
        parsed_data = json.loads(data["message"]) if isinstance(data["message"], str) else data["message"]
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid JSON format")

    source = parsed_data.get("source")
    action = parsed_data.get("action")
    url = parsed_data.get("body", {}).get("url")

    if source != "NEWS" or action != "GENERAL":
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
    }

    is_article = any([
        re.search(r'\d{6,}\.htm[l]?$', url),
        re.search(r'/[^/]+-\d+\.htm[l]?$', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/\d{2}/', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/', url)
    ])

    # Xử lý URL bài viết cụ thể (chứa ID hoặc slug)
    if is_article:
        article = get_article_details(crawler, url, True)
        if not article:
            raise HTTPException(status_code=404, detail="Không tìm thấy bài viết hoặc URL không hợp lệ")
        response["articles"].append(article)
        return response
    elif url.rstrip("/").endswith(domain):
        try:
            urls = crawler.get_all_articles()
            for article_url in urls:
                if article_url:
                    get_article_details(crawler, article_url, False)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi khi lấy danh sách bài viết: {e}")

    else:
        raise HTTPException(status_code=400, detail="URL không hợp lệ hoặc chưa được hỗ trợ")
    print(f"Finished crawling..............")
    return {"status": "ok", "url": url, "message": f"Đã crawl {len(urls)} bài viết. Dữ liệu đang được lưu."}

def get_article_details(crawler, url: str, link) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    print(f"=====================Đang lấy thông tin url: {url}")
    try:
        title, description, content, published_date, author, content_image_urls = crawler.extract_content(url)
    except Exception as e:
        print(f"Lỗi khi lấy nội dung bài báo: {e}")
        return None

    if not title:
        return None

    article_data = {
        "dataSource": "/".join(url.split("/")[:3]),
        "title": title,
        "url": url,
        "author": author,
        "publishedDate": clean_date(published_date),
        "description": description,
        "content": content,
        "contentImageUrls": content_image_urls,
        "comments": [""],
    }
    save_to_json(article_data)
    # send_json_to_api()
    time.sleep(1)
    if link:
        return article_data

