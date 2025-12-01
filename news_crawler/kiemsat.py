import os
import requests
import sys
from pathlib import Path
import re

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
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class KiemSatCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://kiemsat.vn/"
        self.article_type_dict = {
            0: "su-kien-van-de",
            1: "kiem-sat-24h",
            2: "luat-cuoc-song",
            3: "phap-luat-nghiep-vu",
            4: "ban-can-biet",
            5: "chung-toi-la-vien-kiem-sat-vien",
            6: "tap-chi-in",
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
            header_logo = soup.find("a", class_="khungAnhCrop0")
            img_tag = header_logo.find("img")
            info["logo"] = img_tag["src"].strip()
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.mid_footer"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="mid_footer")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 1:
                    info["description"] = f"{lines[0]}"
                # License
                if "Giấy phép" in text:
                    license_line = [line for line in lines if "Giấy phép " in line]
                    if license_line:
                        info["license"] = license_line[0].strip()

                # Tổng biên tập
                if "Tổng Biên tập:" in text:
                    editor_line = [line for line in lines if "Tổng Biên tập:" in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng Biên tập:", "").strip()

                 # Địa chỉ
                if "Địa chỉ:" in text:
                    addr_line = [line for line in lines if "Địa chỉ:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Địa chỉ:", "").strip()

                # Điện thoại
                info["phone"] = ""

                # Email
                if "Email:" in text:
                    email_line = [line for line in lines if "Email:" in line]
                    if email_line:
                        info["email"] = email_line[0].replace("Email:", "").strip()

                # Thông tin bản quyền
                box = footer_copyright.select_one("div.info")
                if box:
                    spans = box.find_all("span")
                    if len(spans) >= 2:
                        last_two = spans[-2:]
                        infor_copyright = " ".join(s.get_text(" ", strip=True) for s in last_two)
                    elif spans:
                        infor_copyright = spans[-1].get_text(" ", strip=True)

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

    def extract_content(self, url: str, has_video=False) -> tuple:
        """
        Return:
            title, description, content, publish_date, author,
            content_images, categories, video_url, thumbnail_url, audio_url
        """
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # ----- TITLE -----
            title_tag = soup.find("h1")
            title = title_tag.get_text(strip=True) if title_tag else None

            # ----- DESCRIPTION -----
            desc_tag = soup.select_one("div.mota h2")
            if desc_tag:
                headline = desc_tag.find("div", class_="headline-makeup")
                if headline:
                    headline.decompose()
                description = desc_tag.get_text(strip=True)
            else:
                description = None

            # ----- DATE -----
            date_tag = soup.find("div", class_="time")
            publish_date = date_tag.get_text(strip=True).rstrip("|").strip() if date_tag else None

            # ----- AUDIO URL -----
            audio_url = ""
            audio_tag = soup.select_one("#audio-player audio")
            if audio_tag and audio_tag.get("src"):
                audio_url = audio_tag.get("src")

            # ----- CONTENT + IMAGES -----
            content_div = soup.find("div", class_="noidung")
            if content_div:
                # text
                content = content_div.get_text(separator="\n", strip=True)

                # images
                imgs = content_div.find_all("img")
                content_images = [i["src"] for i in imgs if i.get("src")]
            else:
                content = ""
                content_images = []

            # ----- AUTHOR -----
            author = None
            author_box = soup.find("div", class_="chuky")
            if author_box:
                atag = author_box.find("a")
                if atag:
                    author = atag.get_text(strip=True).split("/")[0].strip()

            # ---------- SELENIUM PART ----------
            categories = ""
            video_url = ""
            thumbnail_url = ""
            location = ""

            return (
                title, description, content, publish_date, author,
                content_images, categories, video_url, thumbnail_url, location
            )

        except Exception as e:
            print("❌ ERROR:", e)
            return None, None, None, None, None, [], None, None, None, None, "", "", "", ""

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
        """ Get URLs of articles in a specific type (e.g., 'su-kien-van-de') """
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
                "profile.managed_default_content_settings.images": 2,  # tắt ảnh
                "profile.managed_default_content_settings.javascript": 1,  # bật JS
            }
        )
        chrome_options.set_capability("pageLoadStrategy", "eager")
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://kiemsat.vn/{article_type}"
        driver.get(page_url)
        
        seen_links = set()
        last_size = 0
        page_count = 0
        max_pages = 5
        try:
            wait = WebDriverWait(driver, 10)

            while page_count < max_pages:
                # Lấy tất cả bài trên trang hiện tại
                articles = driver.find_elements(By.CSS_SELECTOR, "div.loadmore-list div.item.loadmore-item")

                for article in articles:
                    try:
                        link_tag = article.find_element(By.CSS_SELECTOR, "div.khungAnh > a.khungAnhCrop")
                        href = link_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://kiemsat.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        continue

                # Nếu không có link mới → dừng
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                # Click nút 'Xem thêm bài viết' nếu có
                try:
                    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.view_more")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click nút 'Xem thêm bài viết'")
                    time.sleep(2)
                    page_count += 1
                except Exception:
                    print("✅ Không còn nút 'Xem thêm bài viết'. Dừng lại.")
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
