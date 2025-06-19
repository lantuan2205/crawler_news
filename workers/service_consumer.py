import re
import json
import time
from pathlib import Path
from typing import Optional, Dict
from constants.crawlers import CRAWLERS

def process_crawl(data: dict):
    print(f"Processing message: {data}")
    print(f"START crawling.....")
    try:
        parsed_data = json.loads(data["message"]) if isinstance(data["message"], str) else data["message"]
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Invalid JSON format")

    source = parsed_data.get("source")
    action = parsed_data.get("action")
    url = parsed_data.get("body", {}).get("url")

    if source != "NEWS" or action != "GENERAL":
        raise ValueError("Sai source hoặc action")

    if not url:
        raise ValueError("URL không được để trống")
    
    domain = url.split("/")[2]
    crawler = CRAWLERS.get(domain)
    if not crawler:
        raise ValueError("Không hỗ trợ domain này")

    response = {
        "status": "success",
        "url": url,
        "articles": [],
    }

    is_article = any([
        re.search(r'\d{6,}\.htm[l]?$', url),
        re.search(r'/[^/]+-\d+\.htm[l]?$', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/\d{2}/', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/', url),
        re.search(r'-i\d+/?$', url)
    ])

    if is_article:
        article = get_article_details(crawler, url, True)
        if not article:
            raise ValueError("Không tìm thấy bài viết hoặc URL không hợp lệ")
        response["articles"].append(article)
        return response
    elif url.rstrip("/").endswith(domain):
        try:
            for category in crawler.article_type_dict.values():
                urls = crawler.get_all_articles(category)
                for article_url in urls:
                    if article_url:
                        get_article_details(crawler, article_url, False)
        except Exception as e:
            raise ValueError(f"Lỗi khi lấy danh sách bài viết: {e}")
    else:
        raise ValueError("URL không hợp lệ hoặc chưa được hỗ trợ")
    print(f"Finished crawling..............")
    return {"status": "ok", "url": url, "message": f"Đã crawl {len(urls)} bài viết. Dữ liệu đang được lưu."}

def get_article_details(crawler, url: str, link) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    print(f"==========Đang lấy thông tin url===========: {url}")
    try:
        title, description, content, published_date, author, content_image_urls = crawler.extract_content(url)
    except Exception as e:
        print(f"Lỗi khi lấy nội dung bài báo: {e}")
        return None

    if not title:
        return None

    # Xử lý Url ảnh
    photoInfos = {}
    for url_image in content_image_urls:
        clean_url = url_image.split('?')[0]
        filename = Path(clean_url).name
        photoInfos[filename] = url_image

    article_data = {
        "dataSource": "/".join(url.split("/")[:3]),
        "title": title,
        "url": url,
        "author": author,
        "publishedDate": clean_date(published_date),
        "description": description,
        "content": content,
        "contentImageUrls": content_image_urls,
        "photoInfos": photoInfos,
        "comments": [""]
    }
    save_to_json(article_data)
    #send_json_to_api()
    send_clean_article_to_kafka(article_data)
    time.sleep(1)
    if link:
        return article_data
