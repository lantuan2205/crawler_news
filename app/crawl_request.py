import argparse
from utils.service_utils import save_to_json, clean_date, send_clean_article_to_kafka, send_profile_to_kafka, send_comment_article_to_kafka, normalize_url_to_root_https
import re
from urllib.parse import urlencode, quote_plus
import json
from datetime import datetime, timedelta
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
from urllib.parse import urljoin, urlparse


BACKEND_CRAWL_MANAGEMENT_SERVER = os.getenv("BACKEND_CRAWL_MANAGEMENT_SERVER", "http://192.168.161.69:8001")

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
                print("[WARN] Thư viện PySocks không được cài đặt. SOCKS proxy sẽ không hoạt động.")
                print("[INFO] Cài đặt: pip install PySocks")
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

def process_crawl(data: Dict[str, Any]):
    """
    Xử lý tác vụ crawl web, hỗ trợ crawl URL cụ thể hoặc tìm kiếm theo từ khóa.
    """
    print(f"Processing message: {data}")
    print(f"START crawling.....")

    try:
        parsed_data = json.loads(data["message"]) if isinstance(data["message"], str) else data["message"]
    except (json.JSONDecodeError, TypeError):
        raise ValueError("Invalid JSON format")

    body = parsed_data.get("body") or {}

    source = parsed_data.get("source")
    action = parsed_data.get("action")
    input_data = body.get("inputData")
    crawl_setting_raw = body.get("crawlSetting")
    # Kiểm tra kiểu dữ liệu
    if not crawl_setting_raw:
        # crawlSetting null hoặc rỗng
        crawl_setting = {}
    elif isinstance(crawl_setting_raw, str):
        # Nếu là JSON string → parse
        try:
            crawl_setting = json.loads(crawl_setting_raw)
        except Exception as e:
            print(f"Lỗi khi parse crawlSetting: {e}")
            crawl_setting = {}
    elif isinstance(crawl_setting_raw, dict):
        # Nếu đã là dict → dùng trực tiếp
        crawl_setting = crawl_setting_raw
    else:
        # Loại dữ liệu khác → dùng default
        crawl_setting = {}

    print(f"Crawl setting: {crawl_setting}")
    # Lấy từng nhóm
    post = crawl_setting.get("POST", {})
    profile = crawl_setting.get("PROFILE", {})

    # Lấy các giá trị trong POST
    audience_enable = post.get("AUDIENCE_INFORMATION", True)
    comments_enable = post.get("COMMENTS", {}).get("ENABLE", True)
    comments_limit = post.get("COMMENTS", {}).get("NUMBER_OF_COMMENTS", 10)
    date_range = post.get("DATE_RANGE", 30)
    post_enable = post.get("ENABLE", True)
    location_enable = post.get("LOCATION", False)
    image_download_enable = post.get("IMAGE_DOWNLOAD", True)
    video_download_enable = post.get("VIDEO_DOWNLOAD", False)
    video_thumbnail_enable = post.get("VIDEO_THUMBNAIL", False)

    # Lấy trong PROFILE
    profile_enable = profile.get("ENABLE")

    # In kết quả
    print("POST settings:")
    print(audience_enable, comments_enable, comments_limit, date_range,
        post_enable, image_download_enable,
        video_download_enable, video_thumbnail_enable)

    print("PROFILE settings:")
    print(profile_enable)
    jobId = body.get("jobId")
    crawlId = body.get("crawlId")
    proxy_config = parsed_data.get("proxy")
    data_to_collect = body.get("dataToCollect", [])
    number_post = body.get("numberPost") or 1000
    number_audio = body.get("numberAudio") or 60
    number_video = body.get("numberVideo") or 0
    has_video = "video" in data_to_collect


    if source != "NEWS" or action != "GENERAL":
        raise ValueError("False source or action")

    if not input_data:
        raise ValueError("URL or keyword is required")

    # Thiết lập proxy session nếu có
    # Hàm setup_proxy_session() được giả định đã được cập nhật
    # để trả về một requests.Session đã cấu hình proxy.
    proxy_session, proxy_msg = setup_proxy_session(proxy_config)

    if proxy_session:
        print(f"[INFO] Sử dụng proxy: {proxy_config.get('host')}:{proxy_config.get('port')}")
    else:
        print("[INFO] Không sử dụng proxy")

    # Sử dụng session để tạo crawler
    def _create_crawler(domain: str):
        from news_crawler.factory import get_crawler
        return get_crawler(domain, proxy_session=proxy_session)

    if input_data.startswith("http://") or input_data.startswith("https://"):
        domain = extract_main_domain(input_data)
        crawler = _create_crawler(domain)

        if not crawler:
            print(f"[INFO] Không có crawler cho {domain}, thử nhận diện CMS...")
            cms_info = detect_cms(input_data)
            cms = cms_info.get("cms")
            print(f"[INFO] CMS detect: {cms}")
            url_cms = re.sub(r"/+$", "", input_data)
            if cms == "WordPress":
                from news_crawler.cms.wordpress import WordPressCrawler
                crawler = WordPressCrawler(input_data, proxy_session)
                if profile_enable is True:
                    get_profile_domain(crawler, url_cms, False, proxy_session, jobId, crawlId)
                links = crawler.get_article_links(max_pages=10)
                for url in links:
                    get_article_details(
                        crawler=crawler,
                        url=article_url,
                        link=False,
                        has_video=has_video,
                        proxy_session=proxy_session,
                        jobId=jobId,
                        crawlId=crawlId,
                        date_range=None,
                        image_download_enable=image_download_enable,
                        video_download_enable=video_download_enable,
                        location_enable=location_enable,
                        video_thumbnail_enable=video_thumbnail_enable
                    )
                return
            elif cms == "Blogger":
                from news_crawler.cms.blogger import BloggerCrawler
                crawler = BloggerCrawler(input_data, jobId, proxy_session)
                if profile_enable is True:
                    get_profile_domain(crawler, url_cms, False, proxy_session, jobId, crawlId)
                links = crawler.get_article_links(max_pages=10)
                for url in links:
                    get_article_details(
                        crawler=crawler,
                        url=article_url,
                        link=False,
                        has_video=has_video,
                        proxy_session=proxy_session,
                        jobId=jobId,
                        crawlId=crawlId,
                        date_range=None,
                        image_download_enable=image_download_enable,
                        video_download_enable=video_download_enable,
                        location_enable=location_enable,
                        video_thumbnail_enable=video_thumbnail_enable
                    )
                return
            elif cms == "Joomla":
                from news_crawler.cms.joomla import JoomlaCrawler
                crawler = JoomlaCrawler(input_data, proxy_session)
                if profile_enable is True:
                    get_profile_domain(crawler, url_cms, False, proxy_session, jobId, crawlId)
                return
            else:
                raise ValueError(f"Không hỗ trợ domain {domain} (không có crawler & không nhận diện CMS được)")

        response = {
            "status": "success",
            "url": input_data,
            "articles": [],
        }

        # Kiểm tra xem có phải là URL bài viết cụ thể không
        is_article = any([
            re.search(r'\d{6,}\.htm[l]?$', input_data),
            re.search(r'/[^/]+-\d+\.htm[l]?$', input_data),
            re.search(r'/[^/]+/\d{4}/\d{2}/\d{2}/', input_data),
            re.search(r'/[^/]+/\d{4}/\d{2}/', input_data),
            re.search(r'-i\d+/?$', input_data),
            re.search(r'-post\d+\.vov($|\?)', input_data),
            re.search(r'-\d+\.vov($|\?)', input_data),
            re.search(r'/[^/]+\.htm[l]?$', input_data),
            re.search(r'-(?!page-)\d+(?:/|$|\?)', input_data),  
        ])

        url = re.sub(r"/+$", "", input_data)
        if is_article:
            raise ValueError("No support for single article crawl in this mode")
            # article = get_article_details(crawler, url, True, has_video, proxy_session, jobId, crawlId)
            # if "comment" in data_to_collect or comments_enable:
            #     get_comment_details(crawler, url, False, proxy_session, jobId, crawlId, limit=comments_limit)
            # if not article:
            #     raise ValueError("Không tìm thấy bài viết hoặc URL không hợp lệ")
            # response["articles"].append(article)
            # return response
        else:
            if "profile" in data_to_collect or profile_enable:
                get_profile_domain(crawler, url, False, proxy_session, jobId, crawlId)

            if post_enable:
                stop = False
                total_articles_crawled = 0
                for category in crawler.article_type_dict.values():
                    urls = crawler.get_all_articles(category)
                    for article_url in urls:
                        if number_post and total_articles_crawled >= number_post:
                            stop = True
                            break

                        if article_url:
                            get_article_details(
                                crawler=crawler,
                                url=article_url,
                                link=False,
                                has_video=has_video,
                                proxy_session=proxy_session,
                                jobId=jobId,
                                crawlId=crawlId,
                                date_range=date_range,
                                image_download_enable=image_download_enable,
                                video_download_enable=image_download_enable,
                                location_enable=location_enable,
                                video_thumbnail_enable=video_thumbnail_enable
                            )
                            if "comment" in data_to_collect and comments_enable:
                                get_comment_details(crawler, article_url, False, proxy_session, jobId, crawlId, limit=comments_limit)
                            total_articles_crawled += 1
                    if stop:
                        break
                if "podcast" in data_to_collect and audience_enable:
                    if hasattr(crawler, "crawl_postcast") and callable(getattr(crawler, "crawl_postcast")):
                        data = crawler.crawl_postcast(number_post=number_audio)
                        return
                    else:
                        print("⚠ Crawler does not support crawl_postcast")

    else:
        raise ValueError("No support for keyword crawl in this mode")
        # keyword = input_data.strip()
        # domains_to_crawl = [
        #     "vietnamnet",
        #     "vnexpress",
        #     "dantri",
        #     "thoibaotaichinhvietnam",
        #     "thanhtra",
        #     "qdnd",
        #     "baotintuc",
        #     "baovephapluat",
        #     "baodantoc",
        #     "tapchicongthuong",
        #     "tainguyenvamoitruong",
        #     "dangcongsan",
        #     "phunumoi",
        #     "vneconomy",
        #     "kinhtedouong",
        #     "thuonghieuvaphapluat",
        # ]

        # for domain in domains_to_crawl:
        #     try:
        #         search_url = build_search_url(domain, keyword)
        #         print(f"[INFO] Search URL for {domain}: {search_url}")
        #         # Tạo crawler với proxy session
        #         if proxy_session:
        #             from news_crawler.factory import get_crawler
        #             try:
        #                 crawler = get_crawler(domain, proxy_session=proxy_session)
        #             except KeyError as e:
        #                 print(f"[ERROR] {e}")
        #                 continue
        #         else:
        #             crawler = CRAWLERS.get(domain)

        #         if not crawler:
        #             print(f"[WARN] Không hỗ trợ crawler cho domain: {domain}")
        #             continue

        #         urls = crawler.get_all_articles_by_keyword(search_url)
        #         print(f"[INFO] Found {len(urls)} articles for {domain}")

        #         for article_url in urls:
        #             if article_url:
        #                 get_article_details(crawler, article_url, False, has_video, proxy_session, jobId, crawlId)

        #     except Exception as e:
        #         print(f"[ERROR] Lỗi khi crawl {domain}: {e}")
        #         update_status(jobId, "FAIL", f"Crawl job failed (Details: {e})")
        #         continue

        # return {"status": "ok", "keyword": keyword, "message": "Đã hoàn thành crawl theo keyword. Dữ liệu đang được lưu."}

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
        # print(f"[INFO] Áp dụng proxy cho crawler: {url}")

        crawler.proxy_session = proxy_session

        if hasattr(crawler, 'session'):
            crawler.session = proxy_session
            # print(f"[INFO] Đã cập nhật session của crawler với proxy")

        if hasattr(crawler, 'proxies'):
            crawler.proxies = proxy_session.proxies
            # print(f"[INFO] Đã cập nhật proxies của crawler")

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
    print(f"[INFO] Đã lấy bài viết: {published_date} - {title}")

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
    }

    # if has_video:
    #     article_data["videoUrl"] = video_url

    if jobId:
        article_data['jobId'] = jobId

    if crawlId:
        article_data['crawlId'] = crawlId

    save_to_json(article_data)
    if is_within_date_range_ms(article_data["publishedDate"], date_range):
        send_clean_article_to_kafka(article_data)
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
            print(f"Lỗi khi lấy nội dung bài báo: {e}")
            return None
        comments = comments[:limit]
        for comment in comments:
            send_comment_article_to_kafka(comment)
            time.sleep(0.2)
        if link:
            return comments

def get_profile_domain(crawler, url: str, link, proxy_session=None, jobId=None, crawlId=None) -> Optional[Dict]:
    """Hàm lấy chi tiết bài báo"""
    # Inject proxy session vào crawler nếu có
    print(f"[INFO] ======================= PROFILE INFORMATION=====================: {url}")
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

    try:
        license_infor, description, editor_in_chief, address, phone, email, infor_copyright, logo = crawler.extract_profile_domain(url)
    except Exception as e:
        print(f"Lỗi khi lấy nội dung bài báo: {e}")
        return None

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
    }

    if jobId:
        profile_info['jobId'] = jobId

    if crawlId:
        profile_info['crawlId'] = crawlId
    
    save_to_json(profile_info)
    send_profile_to_kafka(profile_info)
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
        update_status(jobId, "SUCCESS", "Crawl completed successfully!")
        # pid = 1
        # os.kill(pid, signal.SIGTERM)
        exit(0)
    except Exception as e:
        print(f"❌ Lỗi trong quá trình crawl: {e}")
        update_status(jobId, "FAIL", f"Crawl job failed (Details: {e})")
        exit(1)
