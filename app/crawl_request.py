from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Union
from utils.service_utils import save_to_json, send_json_to_api, clean_date
from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler
import re
import os
import requests
import json
from datetime import datetime
import time

app = FastAPI()

CRAWLERS = {
    "vnexpress.net": VNExpressCrawler(),
    "vietnamnet.vn": VietNamNetCrawler()
}

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
        "error": ""
    }

    # Xử lý URL bài viết cụ thể (chứa ID hoặc slug)
    if re.search(r'\d{6,}.html$', url):
        article = get_article_details(crawler, url)
        if not article:
            raise HTTPException(status_code=404, detail="Không tìm thấy bài viết hoặc URL không hợp lệ")
        response["articles"].append(article)
    elif url.rstrip("/").endswith(domain):
        try:
            urls = crawler.get_all_articles(1)
            response["articles"] = [get_article_details(crawler, article_url) for article_url in urls if article_url]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi khi lấy danh sách bài viết: {e}")

    else:
        raise HTTPException(status_code=400, detail="URL không hợp lệ hoặc chưa được hỗ trợ")
    print(f"Finished crawling..............")
    return response

def get_article_details(crawler, url: str) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    print(f"=====================Đang lấy thông tin url: {url}")
    try:
        title, description, paragraphs, published_date, image_url, comments, author = crawler.extract_content(url)
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
        "imageUrl": image_url,
        "description": " ".join(list(description)),
        "content": ",".join(list(paragraphs)),
        "comments": list(comments) if comments else [""]
    }
    save_to_json(article_data)
    send_json_to_api()
    time.sleep(1)

    return article_data

