import os
import requests
import sys
from pathlib import Path
import re
import uuid 

import json
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Optional  
from selenium.common.exceptions import TimeoutException, WebDriverException


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https,time_to_seconds

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VovCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vov.vn/"
        self.article_type_dict = {
            0: "chinh-tri/dang",
            1: "nhan-su",
            2: "chinh-tri/quoc-hoi",
            3: "chinh-tri/nhan-dien-su-that",
            4: "xa-hoi/tin-24h",
            5: "du-bao-thoi-tiet",
            6: "xa-hoi/giao-duc",
            7: "xa-hoi/dau-an-vov",
            8: "viec-lam",
            9: "bien-dao",
            10: "the-gioi/quan-sat",
            11: "the-gioi/cuoc-song-do-day",
            12: "the-gioi/ho-so",
            13: "kinh-te/dia-oc",
            14: "khoi-nghiep",
            15: "thi-truong/gia-vang",
            16: "thi-truong/ty-gia",
            17: "thi-truong/chung-khoan",
            18: "thi-truong/gia-ca-phe",
            19: "vu-an",
            20: "tin-nong",
            21: "phap-luat/tu-van-luat",
            22: "quan-su-quoc-phong/vu-khi",
            23: "quan-su-quoc-phong/viet-nam",
            24: "quan-su-quoc-phong/phan-tich",
            25: "the-thao/bong-da",
            26: "the-thao/bong-da-quoc-te",
            27: "the-thao/lich-thi-dau-bong-da",
            28: "the-thao/the-gioi-the-thao",
            29: "the-theo/esports",
            30: "the-thao/hau-truong",
            31: "oto-xe-may/oto",
            32: "oto-xe-may/xe-may",
            33: "oto-xe-may/tuvan",
            34: "thong-tin-doanh-nghiep",
            35: "doanh-nghiep-24h",
            36: "doanh-nhan",
            37: "vi-cong-dong",
            38: "cong-nghe/sanh-dieu",
            39: "cong-nghe/tin-cong-nghe",
            40: "cong-nghe/trai-nghiem",
            41: "chuyen-doi-so",
            42: "dinh-duong-mon-ngon",
            43: "suc-khoe/cay-thuoc",
            44: "suc-khoe/san-phu-khoa",
            45: "suc-khoe/nhi-khoa",
            46: "suc-khoe/nam-khoa",
            47: "lam-dep-giam-can",
            48: "suc-khoe/phong-mach-online",
            49: "an-sach-song-khoe",
            50: "nha-dep",
            51: "blog",
            52: "tin-yeu-gia-dinh",
            53: "van-hoa/dien-anh",
            54: "van-hoa/van-hoc",
            55: "van-hoa/am-nhac",
            56: "di-san",
            57: "van-hoa/nghe-si",
            58: "thoi-trang-lam-dep",
            59: "giai-tri/hau-truong-showbiz",
            60: "du-lich/tu-van",
            61: "du-lich/san-tour",
            62: "du-lich/checkin",
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
            container = soup.find("div", class_="logo--image")
            h1_tag = container.find("a", class_="branding") if container else None
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "footer.vovvn-footer"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("footer", class_="vovvn-footer")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 2:
                    info["description"] = f"{lines[0]} - {lines[1]}"

                # License
                if "Giấy phép số " in text:
                    license_line = [line for line in lines if "Giấy phép số " in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép số ", "").strip()

                # Tổng biên tập
                if "Tổng Biên tập: " in text:
                    editor_line = [line for line in lines if "Tổng Biên tập: " in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng Biên tập: ", "").strip()

                # Địa chỉ
                if "Trụ sở:" in text:
                    addr_line = [line for line in lines if "Trụ sở:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Trụ sở:", "").strip()

                # Điện thoại
                if "Điện thoại:" in text:
                    phone_line = [line for line in lines if "Điện thoại:" in line]
                    if phone_line:
                        info["phone"] = phone_line[0].replace("Điện thoại:", "").strip()

                # Email
                if "Thư điện tử:" in text:
                    email_tag = [line for line in lines if "Thư điện tử:" in line]
                    if email_tag:
                        info["email"] = email_tag[0].replace("Thư điện tử:", "").strip()
                # Ban quyen
                if "Không được sao chép" in text:
                    copyright_tag = [line for line in lines if "Không được sao chép" in line]
                    if copyright_tag:
                        info["infor_copyright"] = copyright_tag[0]


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

    def extract_content(self, url: str, has_video) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.find('h1', class_='article-title')
            title = title_tag.get_text(strip=True) if title_tag else None
            # Lấy description
            desc_tag = soup.select_one("div.article-summary div.col h2 div")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("div", class_='col-md-4 mb-2')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="article-content")
            content_images = []

            if content_div:
                figures = content_div.find_all("figure", class_="gallery-embed")
                for figure in figures:
                    imgs = figure.find_all("img")
                    for img in imgs:
                        src = img.get("src")
                        if src:
                            content_images.append(src)
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            if not content_div:
                content = ""
                content_images = []
            else:
                content = content_div.get_text(separator="\n", strip=True)
                images = content_div.find_all("img") or []
                content_images = [img.get("src") for img in images if img.get("src")]


            # Trích xuất tác giả
            author = ""
            author_box = soup.find('div', class_='article-author')
            if author_box:
                author_tag = author_box.find('a')
                if author_tag:
                    author = author_tag.get_text(strip=True).split('/')[0].strip()
            # categories = "XÃ HỘI"
            a = soup.select_one("li.breadcrumb-item-first a")
            categories = a.get_text(strip=True) if a else ""
            location = ""
            h1 = soup.select_one("h1.article-title")
            if h1:
                txt = h1.get_text(" ", strip=True)
                m = re.match(r'^\s*([^:：]+)\s*[:：]\s*', txt)
                if m:
                    location = m.group(1).strip()
            video_url = ""
            thumbnail_url = ""
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument("--disable-notifications")
                chrome_options.add_argument("--window-size=1200,900")

                driver = webdriver.Chrome(options=chrome_options)
                driver.get(url)
                try:
                    el = WebDriverWait(driver, 6).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.gallery-embed.video_file.videojs-player"))
                    )
                    video_url = (el.get_attribute("data-url") or "").strip()
                except TimeoutException:
                    print("⚠️ Không tìm thấy video_url")
                    video_url = ""

                try:
                    el_thumb = driver.find_element(By.CSS_SELECTOR, "div.gallery-embed.video_file.videojs-player")
                    thumbnail_url = (el_thumb.get_attribute("data-thumb") or "").strip()
                except NoSuchElementException:
                    print("⚠️ Không tìm thấy thumbnail_url")
                    thumbnail_url = ""

            except WebDriverException as e:
                print(f"❌ Lỗi Selenium: {e}")
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

            
            return title, description, content, publish_date, author, content_images,categories, video_url, thumbnail_url, location

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi tải trang: {e}")
            return None, None, None, None, None, []
        except Exception as e:
            print(f"Lỗi trong quá trình phân tích HTML: {e}")
            return None, None, None, None, None, []

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
        """" Get URLs of articles in a specific type on a given page"""
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
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://vov.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        page_count = 0
        max_pages = 5 
        try:
            wait = WebDriverWait(driver, 10)

            while True:

                articles = driver.find_elements(By.CSS_SELECTOR, "div.views-content div.taxonomy-content")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "div.article-media > a.vovvn-title.position-relative")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://vov.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)
                if page_count >= max_pages:
                    break
                try:
                    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn--read-more")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    page_count += 1
                    print("➡️ Đã click nút 'Trang sau'")
                    time.sleep(1)

                except Exception:
                    print("✅ Không còn nút Trang sau. Dừng lại.")
                    break

        except Exception as e:
            print("⚠️ Lỗi collect links:", e)
        finally:
            driver.quit()
        print(f"📄 Tổng số bài thu thập: {len(seen_links)}")
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles
    
    def get_audio_from_article(self, url):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
            chrome_options.add_argument("--no-sandbox")   
            chrome_options.add_argument("--headless=new")  # chạy ẩn

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            html = driver.page_source
            soup = BeautifulSoup(html,"html.parser")
            article= soup.select_one("div.node-content-audio") or soup

            audio_tag = soup.find("video", src=True)
            if audio_tag:
                audio_url = audio_tag.get("src", "").strip()
            
            # 2 DESCRIPTION
            s_tag = article.select_one("p")
            if s_tag:
                text = s_tag.get_text(strip=True)
                description = text.split("-", 1)[1].strip() if "-" in text else text.strip()


            # 3PUBLISHED DATE
            t_tag = article.select_one("div.content span")
            time_text = t_tag.get_text(strip=True) if t_tag else ""
            publishedDate = parse_vnexpress_time_ms(time_text)

            # 4AUTHOR
            a_tag = article.select_one("div.speed span a")
            author = a_tag.get_text(strip=True) if a_tag else ""


            duration_tag = article.select("span.duration")
            if duration_tag:
                end_time_mp3_url = duration_tag[-1].get_text(strip=True)

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
            "description": description,
            "author": author,
            "duration": end_time_mp3_url,
            "publishedDate": publishedDate,
        }


    def crawl_podcast_bs4(self, category_url: str):
        def build_domain_username(domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(category_url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("div.col-12") 
        domain = "vov"
        BASE_DOMAIN = "https://vov.vn"
        podcasts = []
        try :
            for item in items:
                # 1. Title + URL
                title_elem = item.select_one("div.article-media")
                if not title_elem:
                    continue

                # Lấy thẻ <h5> chứa tiêu đề
                title_tag = title_elem.select_one("h5.media-title")
                title = title_tag.get_text(strip=True) if title_tag else ""

                # Lấy href của thẻ <a> chứa tiêu đề
                a_tag = title_elem.select_one("div.media-body a.vovvn-title")
                url = a_tag.get("href", "") if a_tag else ""

                if url.startswith("/"):
                    url = BASE_DOMAIN + url

                # 2. Thumbnail (từ <img> hoặc <source data-srcset>)
                thumb_elem = title_elem.select_one("a.vovvn-title picture img")
                thumbnail = thumb_elem.get("src", "") if thumb_elem else ""
                
                # 3. Category (nếu cần)
                cat_tag = soup.select_one("title")
                category = cat_tag.get_text(strip=True).split("|")[0].strip() if cat_tag else ""

                # 4. Audio URL (trong data-player)
                meta = self.get_audio_from_article(url)
                audio_url     = meta["audio_url"]
                content_url   = meta["description"]
                author_url    = meta["author"]
                end_time_url  = meta["duration"]
                datetime_url  = meta["publishedDate"]
                domain_username = build_domain_username(domain, author_url) if author_url else ""
                
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
                }
                send_podcast_to_kafka(podcast)
        except Exception as e:
            print("❌ Lỗi trong quá trình crawl:", e)

    def crawl_postcast(self):
        podcast_type_dict = {
            0: "cau-chuyen-thoi-su",
            1: "doc-truyen-dem-khuya",
            2: "cua-so-tinh-yeu",
            3: "ke-chuyen-cho-be",
            4: "hat-giong-tam-hon",
        }

        BASE_URL = "https://vov.vn/podcast/"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url)
