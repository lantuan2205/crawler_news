import argparse
from utils.service_utils import (save_to_json, clean_date, send_clean_article_to_kafka, send_profile_to_kafka,
send_tracking_status_to_kafka ,send_comment_article_to_kafka, normalize_url_to_root_https, send_logs_to_kafka,
send_profile_dark_web_to_kafka, send_clean_article_dark_web_to_kafka)
import re
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Dict, Any, Optional
import requests
import socks
from constants.crawlers import CRAWLERS
from typing import Optional, Dict
from constants.search_url_builders import SEARCH_URL_BUILDERS
import os
import signal
import sys
import uuid
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, urlencode, quote_plus
import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
JSON_PATH = BASE_DIR / "dark.json"

def load_items_from_file():
    if not JSON_PATH.exists():
        return []
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Crawl timeout exceeded")

# Register signal handler
signal.signal(signal.SIGALRM, timeout_handler)


BACKEND_CRAWL_MANAGEMENT_SERVER = os.getenv("BACKEND_CRAWL_MANAGEMENT_SERVER", "http://192.168.161.69:8001")
URL_SERVICE_CRAWL_DARK_WEB = os.getenv("URL_SERVICE_CRAWL_DARK_WEB", "https://blackweb.cloud/crawl")
API_TOKEN="darkwebcrawler"

headers_darkweb = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Content-Type": "application/json"
}

# try:
#     from app.server import start_background_server
#     start_background_server(port=8111)
#     print("[INFO] Stop/Health API started on port 8111")
# except Exception as e:
#     print(f"[WARN] Không thể khởi động stop server: {e}")

def setup_proxy_session(proxy_config: dict) -> Optional[requests.Session]:
    """Thiết lập session với proxy"""
    if not proxy_config:
        print("[INFO] Không có proxy config, trả về session mặc định.")
        return requests.Session(), "No proxy config provided"

    try:
        username = proxy_config.get("username")
        password = proxy_config.get("password")
        host = proxy_config.get("host")
        port = proxy_config.get("port")
        proxy_type = proxy_config.get("proxyType", "HTTP").upper()

        if not all([host, port]):
            print("[WARN] Thiếu thông tin host hoặc port proxy.")
            return None, "Proxy host-port missing"

        session = requests.Session()

        # Tạo URL proxy dựa trên loại proxy
        if username and password:
            proxy_url = f"{proxy_type.lower()}://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"{proxy_type.lower()}://{host}:{port}"

        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }

        session.proxies = proxies
        print(f"[INFO] Đã thiết lập {proxy_type} proxy: {host}:{port}")

        # Kiểm tra và cài đặt SOCKS nếu cần
        if proxy_type in ["SOCKS4", "SOCKS5"]:
            try:
                import socks as _socks
                # Dòng này là cần thiết để requests có thể dùng SOCKS
                # Nó sẽ vá module socket của Python để hoạt động với PySocks
                # requests.get("http://example.com", proxies={"http": "socks5://..."})
                # sẽ không hoạt động nếu thiếu dòng này
                session.mount('http://', requests.adapters.HTTPAdapter())
                session.mount('https://', requests.adapters.HTTPAdapter())

            except ImportError:
                return None, ""

        # Test proxy connection
        try:
            r = session.get("http://httpbin.org/ip", timeout=10)
            if r.status_code == 200:
                print(f"[INFO] Proxy kết nối thành công: {host}:{port}")
                return session, f"Proxy OK: {host}:{port}"
            return None, f"Proxy test failed (HTTP {r.status_code}) → {host}:{port}"
        except Exception as e:
            print(f"[WARN] Không thể test proxy: {e}")
            return None, f"Proxy connection failed → {host}:{port} | {str(e)}"
    except Exception as e:
        print(f"[ERROR] Lỗi khi thiết lập proxy: {e}")
        return None, f"Proxy setup error → {str(e)}"

def extract_main_domain(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.hostname or ''
    host = host.lower()
    if host.endswith('.onion'):
        return host.replace('.onion', '')

    # --- Special platforms ---
    if host.endswith('.blogspot.com'):
        return host.replace('.blogspot.com', '')
    if host.endswith('.wordpress.com'):
        return host.replace('.wordpress.com', '')
    if host.endswith('.medium.com'):
        return host.replace('.medium.com', '')
    if host.endswith('.substack.com'):
        return host.replace('.substack.com', '')
    if host in ('x.com', 'twitter.com'):
        path = parsed.path.strip('/')
        if path.startswith('@'):
            return path.lstrip('@').split('/')[0]

    # --- Generic domain handler ---
    parts = host.split('.')
    # Loại bỏ các hậu tố phổ biến (.com, .vn, .net, .org, .co, .uk, ...)
    common_tlds = {"com", "vn", "net", "org", "co", "uk", "gov", "edu", "info", "me", "biz", "news"}
    parts = [p for p in parts if p not in common_tlds]

    if parts:
        return parts[-1]
    return host or None

def safe_json(val, default=None):
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return default or {}
    return default or {}

def parse_crawl_setting(raw):
    setting = safe_json(raw)
    post = setting.get("POST", {})
    profile = setting.get("PROFILE", {})

    return {
        "audience_enable": post.get("AUDIENCE_INFORMATION", True),
        "comments_enable": post.get("COMMENTS", {}).get("ENABLE", True),
        "comments_limit": post.get("COMMENTS", {}).get("NUMBER_OF_COMMENTS", 10),
        "date_range": post.get("DATE_RANGE", 30),
        "post_enable": post.get("ENABLE", True),
        "location_enable": post.get("LOCATION", False),
        "image_download_enable": post.get("IMAGE_DOWNLOAD", True),
        "video_download_enable": post.get("VIDEO_DOWNLOAD", False),
        "video_thumbnail_enable": post.get("VIDEO_THUMBNAIL", False),
        "number_post": post.get("NUMBER_OF_POSTS", 1000),
        "profile_enable": profile.get("ENABLE", False),
    }

def crawl_by_cms(cms, input_url, crawler, proxy_session, jobId, crawlId,
                 has_video, profile_enable, data_to_collect,
                 image_download_enable, video_download_enable,
                 location_enable, video_thumbnail_enable):

    url = re.sub(r"/+$", "", input_url)

    if "profile" in data_to_collect or profile_enable:
        get_profile_domain(crawler, url, False, proxy_session, jobId, crawlId)

    if cms in ("WordPress", "Blogger"):
        links = crawler.get_article_links(max_pages=10)
        for link in links:
            get_article_details(
                crawler, link, False, has_video, proxy_session,
                jobId, crawlId, None,
                image_download_enable,
                video_download_enable,
                location_enable,
                video_thumbnail_enable
            )
        return

    if cms == "Joomla":
        return

    raise ValueError(f"Không hỗ trợ CMS: {cms}")

def create_darkweb_crawl(crawl_id, start_url):
    payload = {
        "crawl_id": crawl_id,
        "start_url": start_url,
        "strategy": "HYBRID",
        "options": {
            "raw_html": True,
            "download_images": True,
            "recrawl_policy": "force",
            "max_pages": 5,
            "max_runtime_hours": 2,
            "max_urls": 100,
            "max_depth": 3,
        }
    }

    print(f"[ONION] Created crawl: {payload}")
    try:
        print(f"🚀 Connecting to: {URL_SERVICE_CRAWL_DARK_WEB} ...")
        
        resp = requests.post(
            f"{URL_SERVICE_CRAWL_DARK_WEB}",
            json=payload,
            headers=headers_darkweb,
            timeout=10
        )
        
        # Log trạng thái trả về
        print(f"✅ Status Code: {resp.status_code}")
        print(f"📄 Response Body: {resp.text}") # Hoặc resp.json() nếu server trả về json
        resp.raise_for_status()
        print(f"[ONION] Created crawl DONE: {crawl_id} for {start_url}")
        return resp.json()
    except requests.exceptions.Timeout:
        raise TimeoutException("Darkweb create crawl timeout")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "N/A"
        body = e.response.text if e.response else ""
        raise RuntimeError(
            f"Darkweb create crawl failed (HTTP {status}): {body}"
        )

    except requests.exceptions.RequestException as e:
        raise RuntimeError(
            f"Darkweb create crawl connection error: {e}"
        )

def check_darkweb_status(crawl_id):
    resp = requests.get(
        f"{URL_SERVICE_CRAWL_DARK_WEB}/{crawl_id}/status",
        headers=headers_darkweb,
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()

def is_onion_url(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return host.endswith(".onion")
    except Exception:
        return False

def get_darkweb_results(
    crawl_id: str,
    from_crawled_at: str | None = None,
    limit: int = 1000,
    fmt: str = "json",
    enrich: bool = True,
    ):
    params = {
        "limit": limit,
        "format": fmt,
        "enrich": enrich,
    }
    if from_crawled_at:
        params["from_crawled_at"] = from_crawled_at

    resp = requests.get(
        f"{URL_SERVICE_CRAWL_DARK_WEB}/{crawl_id}/results",
        params=params,
        headers=headers_darkweb,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def poll_darkweb_results(
    crawl_id,
    jobId,
    crawlId,
    poll_interval=60,
    max_idle_rounds=30,
    crawl_cfg: dict = None,
    ):
    last_crawled_at = None
    number_post = 0
    idle_round = 0
    max_post = crawl_cfg.get("number_post", 0) if crawl_cfg else 0
    try:
        while idle_round <= max_idle_rounds:
            result = get_darkweb_results(
                crawl_id=crawl_id,
                from_crawled_at=last_crawled_at,
                limit=1000,
                enrich=True,
            )
            # items = []
            items = result.get("items", [])
            # Get items from file for testing
            # if not items:
            #     result = load_items_from_file()
            #     items = result.get("items", [])

            if not items:
                print(f"[ONION] No new items, idle round")

            for item in items:
                if crawl_cfg["post_enable"]:
                    save_darkweb_article(item, crawlId, jobId, crawl_cfg)
                else : return
            last_crawled_at = max(
                item.get("crawled_at")
                for item in items
                if item.get("crawled_at")
            )
            idle_round += 1
            time.sleep(poll_interval)

    finally:
        try:
            # delete_darkweb_crawl(crawl_id)
            print(f"[ONION] Crawl {crawl_id} deleted")
        except Exception as e:
            print(f"[WARN] Cannot delete crawl {crawl_id}: {e}")

def delete_darkweb_crawl(crawl_id: str):
    resp = requests.delete(
        f"{URL_SERVICE_CRAWL_DARK_WEB}/{crawl_id}",
        headers=headers_darkweb,
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()

def save_darkweb_profile(url, crawlId, jobId):

    crawled_at = int(datetime.now(timezone.utc).timestamp())

    email =  None
    phone =  None

    license_infor = None
    editor_in_chief = None
    address = None
    infor_copyright = None
    logo = None
    description = None

    # ===== Logs =====
    logs = {
        "loggable_id": crawlId,
        "loggable_type": "Crawl profile Darkweb",
        "log_level": "INFO",
        "message": f"Profile has been crawled!: {normalize_url_to_root_https(url)}",
        "created_at": crawled_at,
        "metadata": "Crawl profile Darkweb",
        "exception": None
    }

    # ===== Profile Info =====
    profile_info = {
        "domain": normalize_url_to_root_https(url),
        "name": extract_main_domain(url),
        "description": description,
        "license": license_infor,
        "editorInChief": editor_in_chief,
        "address": address,
        "phone": phone,
        "email": email,
        "inforCopyright": infor_copyright,
        "logo": logo,
        "crawledAt": crawled_at
    }

    # ===== Tracking Status =====
    tracking_status = {
        "id": normalize_url_to_root_https(url),
        "platform": "darkweb",
        "data_type": "profile",
        "crawled_at": crawled_at,
        "pre_status": None,
        "pre_processed_at": None,
        "pre_message": None,
        "post_status": None,
        "post_processed_at": None,
        "post_message": None,
    }

    if jobId:
        profile_info['jobId'] = jobId

    if crawlId:
        profile_info['crawlId'] = crawlId
        tracking_status['crawlId'] = crawlId

    send_profile_dark_web_to_kafka(profile_info)
    send_tracking_status_to_kafka(tracking_status)
    send_logs_to_kafka(logs)

def save_darkweb_article(
    item,
    crawlId,
    jobId,
    crawl_cfg: dict = None
    ):

    # image_download_enable=crawl_cfg["image_download_enable"] or False # comment downloan image darkweb
    image_download_enable= False
    
    video_download_enable=False
    video_thumbnail_enable=False
    url = item.get("url")
    crawled_at = int(datetime.now(timezone.utc).timestamp())

    title = item.get("title")
    description = item.get("description")
    author = item.get("author")
    published_date = item.get("crawled_at")

    # ===== Content =====
    content_obj = item.get("content", {})
    content = content_obj.get("text") or content_obj.get("html")

    # ===== Images =====
    content_image_urls = item.get("images", [])
    photoInfos = content_obj.get("photo_infos", {})

    # ===== Categories / tags =====
    categories_list = item.get("tags", [])
    categories = ",".join(categories_list)
    # ===== Video =====
    video_url = content_obj.get("video_url")
    thumbnail_url = content_obj.get("thumbnail_url")

    # ===== Location (darkweb thường null) =====
    location = None

    # ===== AuthorId (darkweb thường không có) =====
    author_id = None

    # ================= LOGS =================
    logs = {
        "loggable_id": crawlId,
        "loggable_type": "Crawl post Darkweb",
        "log_level": "INFO",
        "message": f"Crawl Url: {url}",
        "created_at": crawled_at,
        "metadata": f"Crawl Url: {url}",
        "exception": None
    }
    send_logs_to_kafka(logs)

    # ================= ARTICLE DATA =================
    article_data = {
        "dataSource": normalize_url_to_root_https(url),
        "title": title,
        "url": url,
        "author": author,
        "authorId": author_id,
        "publishedDate": clean_date(published_date),
        "description": description,
        "content": content,
        "contentImageUrls": content_image_urls if image_download_enable else [],
        "photoInfos": photoInfos if image_download_enable else {},
        "categories": categories,
        "thumbnailUrl": thumbnail_url if video_thumbnail_enable else None,
        "location": location if image_download_enable else None,
        "videoUrl": video_url if video_download_enable else None,
        "crawledAt": crawled_at,
    }

    print("darkweb article:", article_data["title"], article_data["url"])

    # ================= TRACKING STATUS =================
    tracking_status = {
        "id": url,
        "platform": "darkweb",
        "data_type": "content",
        "crawled_at": crawled_at,
        "pre_status": None,
        "pre_processed_at": None,
        "pre_message": None,
        "post_status": None,
        "post_processed_at": None,
        "post_message": None,
    }

    if jobId:
        article_data['jobId'] = jobId

    if crawlId:
        article_data['crawlId'] = crawlId
        tracking_status['crawl_id'] = crawlId

    s_title = title.strip() if title else ""
    s_content = content.strip() if content else ""
    is_valid_title = len(s_title) > 0
    is_valid_content = len(s_content) > 20

    if is_valid_title and is_valid_content:
        send_clean_article_dark_web_to_kafka(article_data)
        send_tracking_status_to_kafka(tracking_status)

def process_crawl(data: Dict[str, Any]):
    signal.alarm(900)

    try:
        parsed = safe_json(data.get("message"))
        body = parsed.get("body", {})

        source, action = parsed.get("source"), parsed.get("action")
        input_data = body.get("inputData")
        jobId, crawlId = body.get("jobId"), body.get("crawlId")

        if source not in ("NEWS", "DARKWEB") or action != "GENERAL":
            raise ValueError("False source or action")
        if not input_data:
            raise ValueError("URL is required")

        crawl_cfg = parse_crawl_setting(body.get("crawlSetting"))
        data_to_collect = body.get("dataToCollect", [])
        has_video = "video" in data_to_collect

        send_logs_to_kafka({
            "loggable_id": crawlId,
            "loggable_type": "Crawl website",
            "log_level": "INFO",
            "message": f"Start crawl website: {input_data}",
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        })

        proxy_session, _ = setup_proxy_session(parsed.get("proxy"))

        if not input_data.startswith(("http://", "https://")):
            raise ValueError("No support for keyword crawl")

        parsed_url = urlparse(input_data)
        if not parsed_url.hostname:
            raise ValueError(f"Invalid URL: {input_data}")

        domain = extract_main_domain(input_data)
        from news_crawler.factory import get_crawler
        crawler = get_crawler(domain, proxy_session=proxy_session)

        if is_onion_url(input_data):
            create_darkweb_crawl(crawlId, input_data)
            time.sleep(60)
            start = time.time()
            timeout = 60 * 60 * 2

            while True:
                status_resp = check_darkweb_status(crawlId)
                print(f"[ONION] Crawl status: {status_resp}")
                status = status_resp.get("status")
                # Get items from file for testing
                # status = "completed"


                save_darkweb_profile(input_data, crawlId, jobId)
                # print("[ONION] Crawl completed")
                print(status)
                poll_darkweb_results(
                    crawl_id=crawlId,
                    jobId=jobId,
                    crawlId=crawlId,
                    poll_interval=60,
                    max_idle_rounds=100,
                    crawl_cfg=crawl_cfg,
                )
                update_status(jobId, "SUCCESS", "Completed")
                return

                if status in ("cancelled", "TIMEOUT"):
                    raise ValueError(f"Dark web crawl failed: {status}")

                if time.time() - start > timeout:
                    raise TimeoutException("Dark web crawl timeout")

                time.sleep(15)
            return

        if not crawler:
            cms = detect_cms(input_data).get("cms")
            if cms == "WordPress":
                from news_crawler.cms.wordpress import WordPressCrawler
                crawler = WordPressCrawler(input_data, proxy_session, limit_posts=crawl_cfg["number_post"])
            elif cms == "Blogger":
                from news_crawler.cms.blogger import BloggerCrawler
                crawler = BloggerCrawler(input_data, jobId, proxy_session, limit_posts=crawl_cfg["number_post"])
            elif cms == "Joomla":
                from news_crawler.cms.joomla import JoomlaCrawler
                crawler = JoomlaCrawler(input_data, proxy_session)
            else:
                raise ValueError(f"Không hỗ trợ domain {domain}")

            crawl_by_cms(cms, input_data, crawler, proxy_session,
                         jobId, crawlId, has_video,
                         crawl_cfg["profile_enable"], data_to_collect,
                         crawl_cfg["image_download_enable"],
                         crawl_cfg["video_download_enable"],
                         crawl_cfg["location_enable"],
                         crawl_cfg["video_thumbnail_enable"])
            return

        if crawl_cfg["profile_enable"] or "profile" in data_to_collect:
            get_profile_domain(crawler, input_data, False, proxy_session, jobId, crawlId)

        if crawl_cfg["post_enable"]:
            count = 0
            for category in crawler.article_type_dict.values():
                for url in crawler.get_all_articles(category):
                    if crawl_cfg["number_post"] and count >= crawl_cfg["number_post"]:
                        return
                    get_article_details(
                        crawler, url, False, has_video, proxy_session,
                        jobId, crawlId,
                        crawl_cfg["date_range"],
                        crawl_cfg["image_download_enable"],
                        crawl_cfg["video_download_enable"],
                        crawl_cfg["location_enable"],
                        crawl_cfg["video_thumbnail_enable"]
                    )
                    if "comment" in data_to_collect and crawl_cfg["comments_enable"]:
                        get_comment_details(
                            crawler, url, False, proxy_session,
                            jobId, crawlId, crawl_cfg["comments_limit"]
                        )
                    count += 1

        if crawl_cfg["audience_enable"]:
            number_audio = 60
            if hasattr(crawler, "crawl_podcast") and callable(getattr(crawler, "crawl_podcast")):
                data = crawler.crawl_podcast(number_post=number_audio, crawl_id=crawlId)
                return
            else:
                print("⚠ Crawler does not support crawl_podcast")

    except TimeoutException as e:
        update_status(jobId, "FAIL", str(e))
    except Exception as e:
        update_status(jobId, "FAIL", f"Darkweb error: {e}")
    finally:
        signal.alarm(0)

def detect_cms(url):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
    }

    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url

    parsed = urlparse(url)
    if not parsed.netloc:
        return {"url": url, "cms": None, "error": "Invalid URL"}

    hostname = parsed.netloc.lower()

    if ".wordpress.com" in hostname:
        return {"url": url, "cms": "WordPress", "error": None}
    if ".blogspot." in hostname:
        return {"url": url, "cms": "Blogger", "error": None}

    html = None
    error_msg = None

    try:
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        html = r.text
    except Exception as e:
        error_msg = f"Requests error: {e}"

    created_driver = False
    if not html:
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")
            chrome_options.add_experimental_option(
                "prefs",
                {
                    "profile.managed_default_content_settings.images": 2,
                    "profile.managed_default_content_settings.javascript": 1,
                }
            )
            chrome_options.set_capability("pageLoadStrategy", "eager")
            driver = webdriver.Chrome(options=chrome_options)
            created_driver = True

            driver.get(url)
            html = driver.page_source
        except Exception as e:
            if created_driver:
                driver.quit()
            return {"url": url, "cms": None, "error": f"Selenium error: {e}"}
        finally:
            if created_driver:
                driver.quit()

    if not html:
        return {"url": url, "cms": None, "error": error_msg or "No HTML fetched"}

    html_lower = html.lower()
    soup = BeautifulSoup(html, "html.parser")

    generator_text = " ".join(
        tag.get("content", "").lower()
        for tag in soup.find_all("meta", attrs={"name": "generator"})
    )

    if any(x in html_lower or x in generator_text for x in ["wp-content", "wordpress", "/wp-json"]):
        return {"url": url, "cms": "WordPress", "error": None}
    if "blogger" in html_lower or "blogger" in generator_text:
        return {"url": url, "cms": "Blogger", "error": None}
    if "joomla" in html_lower or "joomla" in generator_text:
        return {"url": url, "cms": "Joomla", "error": None}
    if "drupal" in html_lower or "data-drupal-selector" in html_lower:
        return {"url": url, "cms": "Drupal", "error": None}
    if "ghost" in html_lower or "ghost" in generator_text:
        return {"url": url, "cms": "Ghost", "error": None}
    if "cdn.shopify.com" in html_lower:
        return {"url": url, "cms": "Shopify", "error": None}
    if "wixstatic.com" in html_lower:
        return {"url": url, "cms": "Wix", "error": None}
    if "squarespace.com" in html_lower:
        return {"url": url, "cms": "Squarespace", "error": None}

    cms_endpoints = {
        "WordPress": "/wp-json/",
        "Joomla": "/administrator/",
        "Ghost": "/ghost/api/content/posts/",
        "Drupal": "/sites/default/files/",
    }

    for cms, path in cms_endpoints.items():
        try:
            resp = requests.head(urljoin(url, path), headers=headers, timeout=5, allow_redirects=True)
            if resp.status_code in (200, 403):
                return {"url": url, "cms": cms, "error": None}
        except Exception:
            continue

    return {"url": url, "cms": None, "error": None}

def build_search_url(domain, keyword):
    if domain in SEARCH_URL_BUILDERS:
        return SEARCH_URL_BUILDERS[domain](keyword)
    else:
        raise ValueError(f"Domain không hỗ trợ: {domain}")

def get_article_details(
    crawler,
    url: str,
    link, has_video,
    proxy_session=None,
    jobId=None,
    crawlId=None,
    date_range: Optional[int] = None,
    image_download_enable: Optional[bool] = None,
    video_download_enable: Optional[bool] = None,
    location_enable: Optional[bool] = None,
    video_thumbnail_enable: Optional[bool] = None,
    ) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    # Inject proxy session vào crawler nếu có
    if proxy_session:

        crawler.proxy_session = proxy_session

        if hasattr(crawler, 'session'):
            crawler.session = proxy_session

        if hasattr(crawler, 'proxies'):
            crawler.proxies = proxy_session.proxies

    try:
        title, description, content, published_date, author, content_image_urls, categories, video_url, thumbnail_url, location  = crawler.extract_content(url, has_video)
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
    author_clean = (author or "").strip().replace(" ", "")
    if author_clean:
        author_id = f"{extract_main_domain(url)}_{author_clean}"
    else:
        author_id = None
    crawled_at = int(datetime.now(timezone.utc).timestamp())

    logs = {
        "loggable_id": crawlId,
        "loggable_type": "Crawl post website",
        "log_level": "INFO",
        "message": f"Crawl Url: {url}",
        "created_at": crawled_at,
        "metadata": f"Crawl Url: {url}",
        "exception": None
    }
    send_logs_to_kafka(logs)

    article_data = {
        "dataSource": normalize_url_to_root_https(url),
        "title": title,
        "url": url,
        "author": author,
        "authorId": author_id,
        "publishedDate": clean_date(published_date),
        "description": description,
        "content": content,
        "contentImageUrls": content_image_urls if image_download_enable else [],
        "photoInfos": photoInfos if image_download_enable else {},
        "categories": categories,
        "thumbnailUrl": thumbnail_url if video_thumbnail_enable else None,
        "location": location if image_download_enable else None,
        "videoUrl": video_url if video_download_enable else None,
        "crawledAt": crawled_at,
    }

    tracking_status = {
        "id": url,
        "platform": "news",
        "data_type": "content",
        "crawled_at": crawled_at,
        "pre_status": None,
        "pre_processed_at": None,
        "pre_message": None,
        "post_status": None,
        "post_processed_at": None,
        "post_message": None,
    }

    # if has_video:
    #     article_data["videoUrl"] = video_url

    if jobId:
        article_data['jobId'] = jobId

    if crawlId:
        article_data['crawlId'] = crawlId
        tracking_status['crawl_id'] = crawlId

    # save_to_json(article_data)
    if is_within_date_range_ms(article_data["publishedDate"], date_range):
        send_clean_article_to_kafka(article_data)
        send_tracking_status_to_kafka(tracking_status)
    if link:
        return article_data

def is_within_date_range_ms(published_date_ms, date_range_days):
    if not published_date_ms or date_range_days is None:
        return True

    try:
        published_date = datetime.fromtimestamp(published_date_ms)
    except Exception as e:
        print(f"Lỗi convert publishedDate: {e}")
        return False

    limit_date = datetime.now() - timedelta(days=date_range_days)
    return published_date >= limit_date

def get_comment_details(crawler, url: str, link, proxy_session=None, jobId=None, crawlId=None, limit: int = 10) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    # Inject proxy session vào crawler nếu có
    if proxy_session:
        print(f"[INFO] Áp dụng proxy cho crawler: {url}")
        # Lưu proxy session vào crawler để sử dụng
        crawler.proxy_session = proxy_session

        # Nếu crawler có thuộc tính session, cập nhật nó
        if hasattr(crawler, 'session'):
            crawler.session = proxy_session
            print(f"[INFO] Đã cập nhật session của crawler với proxy")

        # Nếu crawler có thuộc tính proxies, cập nhật nó
        if hasattr(crawler, 'proxies'):
            crawler.proxies = proxy_session.proxies
            print(f"[INFO] Đã cập nhật proxies của crawler")

    if hasattr(crawler, "extract_comment"):
        try:
            comments = crawler.extract_comment(url)
        except Exception as e:
            print(f"Lỗi khi lấy comment: {e}")
            return None
        comments = comments[:limit]
        for comment in comments:
            user_clean = (comment["username"] or "").strip().replace(" ", "")
            if user_clean:
                user_id = f"{extract_main_domain(url)}_{user_clean}"
            else:
                user_id = None
            crawled_at = int(datetime.now(timezone.utc).timestamp())
            comment["userId"] = user_id
            comment["username"] = user_clean
            comment["crawlId"] = crawlId
            comment["crawledAt"] = crawled_at

            tracking_status = {
                "id": comment["commentId"],
                "platform": "news",
                "data_type": "comment",
                "crawled_at": crawled_at,
                "pre_status": None,
                "pre_processed_at": None,
                "pre_message": None,
                "post_status": None,
                "post_processed_at": None,
                "post_message": None,
                "crawl_id": crawlId
            }

            send_comment_article_to_kafka(comment)
            send_tracking_status_to_kafka(tracking_status)
            time.sleep(0.2)
        if link:
            return comments

def get_profile_domain(crawler, url: str, link, proxy_session=None, jobId=None, crawlId=None) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    # Inject proxy session vào crawler nếu có
    if proxy_session:
        # Lưu proxy session vào crawler để sử dụng
        crawler.proxy_session = proxy_session

        # Nếu crawler có thuộc tính session, cập nhật nó
        if hasattr(crawler, 'session'):
            crawler.session = proxy_session

        # Nếu crawler có thuộc tính proxies, cập nhật nó
        if hasattr(crawler, 'proxies'):
            crawler.proxies = proxy_session.proxies

    try:
        license_infor, description, editor_in_chief, address, phone, email, infor_copyright, logo = crawler.extract_profile_domain(url)
    except Exception as e:
        print(f"Lỗi khi lấy profile: {e}")
        return None
    crawled_at = int(datetime.now(timezone.utc).timestamp())
    logs = {
        "loggable_id": crawlId,
        "loggable_type": "Crawl profile news",
        "log_level": "INFO",
        "message": f"Profile has been crawled!: {normalize_url_to_root_https(url)}",
        "created_at": crawled_at,
        "metadata": "Crawl profile news",
        "exception": None
    }
    
    profile_info = {
        "domain": normalize_url_to_root_https(url),
        "name": extract_main_domain(url),
        "description": description,
        "license": license_infor,
        "editorInChief": editor_in_chief,
        "address": address,
        "phone": phone,
        "email": email,
        "inforCopyright": infor_copyright,
        "logo": logo,
        "crawledAt": crawled_at
    }

    tracking_status = {
        "id": normalize_url_to_root_https(url),
        "platform": "news",
        "data_type": "profile",
        "crawled_at": crawled_at,
        "pre_status": None,
        "pre_processed_at": None,
        "pre_message": None,
        "post_status": None,
        "post_processed_at": None,
        "post_message": None,
    }

    if jobId:
        profile_info['jobId'] = jobId

    if crawlId:
        profile_info['crawlId'] = crawlId
        tracking_status['crawl_id'] = crawlId
    
    # save_to_json(profile_info)
    send_profile_to_kafka(profile_info)
    send_tracking_status_to_kafka(tracking_status)
    send_logs_to_kafka(logs)
    time.sleep(0.5)
    if link:
        return profile_info

def update_status(job_id: str, final_status: str, message: str):
    api_url = f"{BACKEND_CRAWL_MANAGEMENT_SERVER}/api/crawl-management/keywords/{job_id}/status"
    params = {"status": final_status,
              "statusMessage": message}

    try:
        response = requests.patch(api_url, params=params, timeout=5)
        response.raise_for_status()
        print(f"✅ Update status [{final_status}] OK → {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Update status [{final_status}] FAIL → {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl a news article by JSON config")
    parser.add_argument('--conf', required=True, help='JSON config string')
    args = parser.parse_args()

    # Parse JSON string
    try:
        data = json.loads(args.conf)
        jobId = data.get("body", {}).get("jobId")
    except json.JSONDecodeError as e:
        print(f"❌ Lỗi parse JSON conf: {e}")
        exit(1)

    try:
        # Gọi process_crawl như cũ
        result = process_crawl({"message": data})
        print("✅ Done:")
        update_status(jobId, "SUCCESS", "Completed")
        # pid = 1
        # os.kill(pid, signal.SIGTERM)
        exit(0)
    except Exception as e:
        print(f"❌ Lỗi trong quá trình crawl: {e}")
        update_status(jobId, "FAIL", f"Crawl job failed (Details: {e})")
        exit(1)
