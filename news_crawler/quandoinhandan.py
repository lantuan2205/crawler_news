import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime, timedelta, timezone
import json
from typing import Dict, Any, Optional

import paramiko
from io import BytesIO
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import extract_author_from_strong_tags ,  is_author_strong_tag, clean_prefix
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https, time_to_seconds

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class QuanDoiNhanDanCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://www.qdnd.vn/"
        self.article_type_dict = {
            0: "chinh-tri",
            1: "quoc-phong-an-ninh",
            2: "da-phuong-tien",
            3: "bao-ve-nen-tang-tu-tuong-cua-dang",
            4: "kinh-te",
            5: "van-hoa",
            6: "xa-hoi",
            7: "phong-su-dieu-tra",
            8: "giao-duc-khoa-hoc",
            9: "phap-luat",
            10: "ban-doc",
            11: "y-te",
            12: "the-thao",
            13: "quoc-te"
        }   
    
    def extract_profile_domain(self, url: str):
        job_id = 1
        info = {
            "name": url,
            "description": "",
            "license": None,
            "editor_in_chief": None,
            "address": None,
            "phone": None,
            "email": None,
            "infor_copyright": None,
            "jobId": job_id or str(uuid.uuid4()),
            "logo": None,
        }

        # --- Phase 1: lấy logo bằng requests ---
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            container = soup.find("div", class_="vlogo")
            h1_tag = container.find("h1") if container else None
            logo_src = h1_tag.find("img")["src"] if h1_tag and h1_tag.find("img") else None
            info["logo"] = logo_src
        except Exception as e:
            print("⚠️ Lỗi khi lấy logo:", e)

        # --- Phase 2: lấy footer bằng Selenium ---
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,  # tắt ảnh
                "profile.managed_default_content_settings.javascript": 1,  # bật JS
            }
        )
        chrome_options.set_capability("pageLoadStrategy", "eager")

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(100)

            try:
                driver.get(url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
                return info

            # Chờ phần footer xuất hiện
            try:
                footer = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footerBot-content"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="footerBot-content")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                info["description"] = soup.find("meta", id="MetaDescription")["content"]

                # License
                if "Giấy phép số:" in text:
                    license_line = [line for line in lines if "Giấy phép số:" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép số:", "").strip()

                # Tổng biên tập
                box = soup.select_one("div.copyright")
                if box:
                    # ưu tiên thẻ <strong> nếu có
                    strong = box.find("strong")
                    if strong and strong.get_text(strip=True):
                        editor_in_chief = strong.get_text(strip=True)
                    else:
                        # fallback: tách từ phần text sau cụm "Tổng biên tập"
                        import re
                        text = box.get_text(" ", strip=True)
                        m = re.search(r"Tổng\s*biên\s*tập[:\-]?\s*(.+)", text, flags=re.I)
                        if m:
                            editor_in_chief = m.group(1).strip().strip('"')

                info["editor_in_chief"] = editor_in_chief
                # Địa chỉ
                if "Toà soạn:" in text:
                    addr_line = [line for line in lines if "Toà soạn:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Toà soạn:", "").strip()

                # Điện thoại
                if "Điện thoại:" in text:
                    phone_line = [line for line in lines if "Điện thoại:" in line]
                    if phone_line:
                        info["phone"] = phone_line[0].replace("Điện thoại:", "").strip()

                # Email
                if "E-mail :" in text:
                    email_line = [line for line in lines if "E-mail :" in line]
                    if email_line:
                        info["email"] = email_line[0].replace("E-mail :", "").strip()      

                # Thông tin bản quyền
                foot = footer_copyright.select_one("div.footer-end")
                if foot:
                    lines = [s.strip(' "').strip() for s in foot.get_text(separator="\n").splitlines()]
                    lines = [l for l in lines if l]
                    last2 = lines[-2:] if len(lines) >= 2 else lines
                    infor_copyright = " ".join(last2) 

                info["infor_copyright"] = infor_copyright

        except WebDriverException as e:
            print("⚠️ Lỗi Selenium:", e)
        finally:
            if driver:
                driver.quit()

        return (
            info.get("license", ""),
            info.get("description", ""),
            info.get("editor_in_chief", ""),
            info.get("address", ""), 
            info.get("phone", ""),
            info.get("email", ""),
            info.get("infor_copyright", ""),
            info.get("logo", "")
        )

    def extract_content(self, url: str,has_video) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Tiêu đề chính
            title = soup.select_one("h1")
            title = title.get_text(strip=True) if title else None
            
            # Mô tả ngắn
            description_tag = soup.select_one("div.post-summary p")
            description = description_tag.get_text(strip=True) if description_tag else ""


            date_el = soup.select_one("span.post-subinfo > span")
            publish_date = date_el.get_text(strip=True) if date_el else ""

            container = soup.select_one("div.post-content div[itemprop='articleBody']") or soup.select_one("div.post-content")

            # --- TEXT: lấy mọi <p> bên trong container (kể cả nằm trong table/td/figure, v.v.)
            if container:
                ps = container.find_all("p")
                content = "\n".join(
                    t for t in (p.get_text(strip=True) for p in ps)
                    if t
                )
            else:
                content = ""

            # --- IMAGES: lấy mọi ảnh trong container, ưu tiên src -> data-src -> data-original -> srcset
            content_images = []
            if container:
                for img in container.find_all("img"):
                    src = (img.get("src") or img.get("data-src") or img.get("data-original") or "").strip()
                    if not src and img.get("srcset"):
                        # lấy URL đầu trong srcset
                        src = img["srcset"].split(",")[0].strip().split(" ")[0]
                    if src:
                        # chuẩn hoá về absolute URL
                        content_images.append(urljoin(url, src))
            # Tác giả
            author = extract_author_from_strong_tags(soup)
            cate_all = soup.select_one("div.brcrum-title span.head")
            if cate_all:
                a_tags = cate_all.select("a")
                # lấy đúng 2 cái đầu
                cats = [a.get_text(strip=True) for a in a_tags[:2] if a.get_text(strip=True)]
                categories = " - ".join(cats)   
            else:
                categories = ""

            h1 = soup.find("h1", class_="post-title")
            title = h1.get_text(strip=True) if h1 else ""

            location = title.split(":", 1)[0].strip() if ":" in title else ""
            video_url = ""

            box = soup.select_one('div[itemprop="articleBody"]')
            if box:
                v = box.find('video', src=True)
                if v:
                    video_url = v['src'].strip()
                else:
                    v = box.find('video')
                    if v:
                        s = v.find('source', src=True)
                        if s:
                            video_url = s['src'].strip()
            # k co thumb
            thumbnail_url = ""
            return title, description, content, publish_date, author, content_images, categories, video_url, thumbnail_url, location

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi tải trang: {e}")
            return None, None, None, None, None, [], None, None, None, None
        except Exception as e:
            print(f"Lỗi trong quá trình phân tích HTML: {e}")
            return None, None, None, None, None, [], None, None, None, None
        
    def write_content(self, url: str, article_type: str) -> bool:
        """
        From url, extract title, description and paragraphs then write in output_fpath
        @param url (str): url to crawl
        @param output_fpath (str): file path to save crawled result
        @return (bool): True if crawl successfully and otherwise
        """
        title, description, content, publish_date, author, content_images = self.extract_content(url)
        if not title:
            return None
            
        # Tải và lưu ảnh nội dung
        '''content_image_paths = []
        for img_url in content_images:
            if img_url:
                img_path = self.download_image(img_url, title, article_type, publish_date)
                if img_path:
                    content_image_paths.append(img_path)'''
                    
        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date),
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            # "localContentImagePaths": content_image_paths
        }

        return article_data
    
    def get_urls_of_type_thread(self, article_type, page_number):

        page_url = f"https://www.qdnd.vn/{article_type}/p/{page_number}"
        if page_number == 5:
            return []
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        article_tags = soup.select("div.list-news-category article a[href]")
        if (len(article_tags) == 0):
            return []

        articles_urls = list({a["href"] for a in article_tags if a["href"].startswith("http")})
        return articles_urls
    
    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles
    
    def get_all_articles_by_keyword(self, page_url):
        print(f"page_url: {page_url}")

        try:
            content = requests.get(page_url, headers=headers, timeout=10).content
            sleep_time = random.uniform(1, 2)
            time.sleep(sleep_time)
            soup = BeautifulSoup(content, "html.parser")
            urls = set()
            results_div = soup.find("div", class_="search-result")

            if results_div:
                articles = results_div.find_all("article", class_="float-image")
                for article in articles:
                    a_tag = article.find("a", href=True)
                    if a_tag:
                        urls.add(a_tag["href"])
            return list(urls)
        except Exception as e:
            return []
        
    def get_audio_from_article(self, url):
        driver = None
        try:   
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument("--disable-images")
            # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")
            chrome_options.set_capability("pageLoadStrategy", "eager")

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            headers = {
                "User-Agent": "Mozilla/5.0"
            }
            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")

            article = soup.select_one("div.uk-padding") or soup

            # 1 AUDIO
            audio_url = ""
            box = article.select_one('div.media-thumb.mediaurl[data-src]')
            if box:
                audio_url = box.get('data-src', '').strip()
            else:
                audio_url = ""

            # 2 DESCRIPTION
            s_tag = article.select_one("div.media-des")
            description = s_tag.get_text(strip=True) if s_tag else ""

            # 3PUBLISHED DATE
            t_tag = article.select_one("time.media-time")
            time_text = t_tag.get_text(strip=True) if t_tag else ""
            publishedDate = parse_vnexpress_time_ms(time_text)

            # 4AUTHOR
            author = ""

            # 5 END TIME (tổng thời lượng)
            try:
                end_time_elem = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, "span.player__duration"))
                )
                # Lấy text thật sau khi JS render xong
                end_time_mp3 = end_time_elem.text.strip()
            except Exception:
                end_time_mp3 = ""

        except Exception as e:
            print(f"❌ Lỗi trong quá trình crawl {url}: {e}")
            return {
                "audio_url": "",
                "description": "",
                "author": "",
                "duration": "",
                "publishedDate":"",
            }

        finally:
            if driver:
                driver.quit()

        return {
            "audio_url": audio_url,
            "description": content_url,
            "author": author_url,
            "duration": end_time_mp3_url,
            "publishedDate": datetime_url
        }

    def crawl_podcast_bs4(self, category_url: str, number_post: int, crawl_id: Optional[str] = None):

        def build_domain_username(domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"

        base = "vnexpress"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        page = 1
        podcasts = []

        while True:
            url = category_url if page == 1 else f"{category_url}/p/{page}"
            print(f"🔎 Đang quét trang {page}: {url}")

            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
            except Exception as e:
                print(f"⚠️ Không thể tải {url}: {e}")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("div.list-news-category article")

            if not items:
                print(f"✅ Hết dữ liệu ở trang {page}")
                break

            for idx, item in enumerate(items):
                if idx >= number_post:
                    break
                try:
                    title_elem = item.select_one("a[title]")
                    if not title_elem:
                        continue
                    title = title_elem.get("title", "").strip()
                    url = title_elem.get("href", "")
                    thumb_elem = item.select_one("img")
                    thumbnail = thumb_elem.get("src", "") if thumb_elem else ""

                    cat_tag = soup.select_one("h1.name-s")
                    category = cat_tag.get_text(strip=True) if cat_tag else ""

                    meta = self.get_audio_from_article(url)
                    audio_url = meta.get("audio_url", "")
                    content_url = meta.get("description", "")
                    author_url = meta.get("author", "")
                    end_time_url = meta.get("duration", "")
                    datetime_url = meta.get("publishedDate", "")
                    domain_username = build_domain_username(base, author_url) if author_url else ""

                    crawled_at = int(datetime.now(timezone.utc).timestamp())
                    podcast = {
                        "domain": normalize_url_to_root_https(url),
                        "title": title,
                        "url": url,
                        "thumbnail": thumbnail,
                        "category": category,
                        "audio_url": audio_url,
                        "author": author_url,
                        "description": content_url,
                        "duration": time_to_seconds(end_time_url),
                        "publishedDate": datetime_url,
                        "authorId": domain_username,
                        "crawlId": crawl_id or str(uuid.uuid4()),
                        "crawledAt": crawled_at
                    }
                    tracking_status = {
                        "id": url,
                        "platform": "news",
                        "data_type": "podcast",
                        "crawled_at": crawled_at,
                        "pre_status": None,
                        "pre_processed_at": None,
                        "pre_message": None,
                        "post_status": None,
                        "post_processed_at": None,
                        "post_message": None,
                        "crawl_id": crawl_id or str(uuid.uuid4()),
                    }
                    send_tracking_status_to_kafka(tracking_status)
                    send_podcast_to_kafka(podcast)
                    podcasts.append(podcast)

                except Exception as e:
                    print(f"⚠️ Lỗi khi xử lý {url}: {e}")
                    continue

            page += 1
            time.sleep(0.5)  # tránh bị chặn

        print(f"🎯 Tổng số bài đã thu thập: {len(podcasts)}")
        return podcasts

    def crawl_postcast(self, number_post: int, crawl_id: Optional[str] = None):
        podcast_type_dict = {
            0: "podcast",
        }

        BASE_URL = "https://www.qdnd.vn/da-phuong-tien/"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url, number_post, crawl_id=crawl_id)
