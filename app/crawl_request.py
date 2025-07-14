import argparse
from utils.service_utils import save_to_json, clean_date, send_clean_article_to_kafka
import re
from urllib.parse import urlencode, quote_plus
import json
from datetime import datetime
from pathlib import Path
import time
from constants.crawlers import CRAWLERS
from typing import Optional, Dict
from constants.search_url_builders import SEARCH_URL_BUILDERS

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
    
    if url.startswith("http://") or url.startswith("https://"):
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
        return {"status": "ok", "url": url, "message": f"Đã crawl {len(urls)} bài viết. Dữ liệu đang được lưu."}
    else:
        keyword = url.strip()
        domains_to_crawl = [
                            "baotintuc.vn",
                            "thuonghieuvaphapluat.vn",]

        for domain in domains_to_crawl:
            try:
                search_url = build_search_url(domain, keyword)
                print(f"[INFO] Search URL for {domain}: {search_url}")

                crawler = CRAWLERS.get(domain)
                if not crawler:
                    print(f"[WARN] Không hỗ trợ crawler cho domain: {domain}")
                    continue

                urls = crawler.get_all_articles_by_keyword(search_url)
                print(f"[INFO] Found {len(urls)} articles for {domain}")

                for article_url in urls:
                    if article_url:
                        get_article_details(crawler, article_url, False)

            except Exception as e:
                print(f"[ERROR] Lỗi khi crawl {domain}: {e}")

    print(f"Finished crawling..............")

def build_search_url(domain, keyword):
    if domain in SEARCH_URL_BUILDERS:
        return SEARCH_URL_BUILDERS[domain](keyword)
    else:
        raise ValueError(f"Domain không hỗ trợ: {domain}")

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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl a news article by JSON config")
    parser.add_argument('--conf', required=True, help='JSON config string')
    args = parser.parse_args()

    # Parse JSON string
    try:
        data = json.loads(args.conf)
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi parse JSON conf: {e}")
        exit(1)

    try:
        # Gọi process_crawl như cũ
        result = process_crawl({"message": data})
        print("✅ Kết quả crawl:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"❌ Lỗi trong quá trình crawl: {e}")
