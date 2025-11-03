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
            title_tag = soup.find('h1')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("div.mota h2")
            if desc_tag:
                headline = desc_tag.find("div", class_="headline-makeup")
                if headline:
                    headline.decompose()
                description = desc_tag.get_text(strip=True)
            else:
                description = None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("div", class_='time')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="noidung")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('div', class_='chuky')
            author_tag = author_box.find('a')
            author = author_tag.get_text(strip=True).split('/')[0].strip() if author_tag else None
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                driver = webdriver.Chrome(options=chrome_options)
                driver.get(url) 
                # Chờ cho slick-slider render xong
                cat_tag = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.slick-current.slick-active"))
                )
                categories = cat_tag.text.strip()
            except Exception as e:
                print("Không tìm thấy category:", e)
            finally:
                driver.quit()

            location = ""
            thumbnail_url = ""
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument("--disable-notifications")
                chrome_options.add_argument("--window-size=1200,900")
                chrome_options.add_argument("--log-level=3")

                driver = webdriver.Chrome(options=chrome_options)
                driver.get(url)
                try:
                    cat_tag = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.slick-current.slick-active"))
                    )
                    categories = cat_tag.text.strip()
                except Exception as e:
                    print("Không tìm thấy category:", e)

                try:
                    driver.switch_to.default_content()
                    yt_iframe = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((
                            By.CSS_SELECTOR,
                            'iframe[src*="youtube.com"], iframe[src*="youtube-nocookie.com"]'
                        ))
                    )
                    driver.switch_to.frame(yt_iframe)

                    poster = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.ytp-cued-thumbnail-overlay-image"))
                    )
                    style_attr = poster.get_attribute("style") or ""
                    m = re.search(r'url\((["\']?)(.*?)\1\)', style_attr)
                    if m:
                        thumbnail_url = m.group(2).strip()
                    else:
                        # computed style fallback
                        bg = driver.execute_script(
                            "return getComputedStyle(arguments[0]).getPropertyValue('background-image');", poster
                        ) or ""
                        m2 = re.search(r'url\((["\']?)(.*?)\1\)', bg)
                        thumbnail_url = m2.group(2).strip() if m2 else ""

                    driver.switch_to.default_content()
                except TimeoutException:
                    thumbnail_url = ""

                try:
                    iframe = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='youtube.com/embed/']"))
                    )
                    driver.switch_to.frame(iframe)

                    link_tag = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.ytp-impression-link"))
                    )
                    video_url = link_tag.get_attribute("href")
                except Exception as e:
                    video_url = ""
                finally:
                    driver.quit()
            except WebDriverException as e:
                print("⚠️ Selenium error:", e)
            finally:
                try:
                    if driver:
                        driver.quit()
                except:
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
        page_url = f"https://kiemsat.vn/{article_type}"
        driver.get(page_url)
        seen_links = set()
        last_size = 0
        max_pages = 20
        page_count = 0
        try:
            wait = WebDriverWait(driver, 10)

            while page_count < max_pages:

                articles = driver.find_elements(By.CSS_SELECTOR, "div.loadmore-list div.item.loadmore-item")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "div.khungAnh > a.khungAnhCrop")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://kiemsat.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.view_more")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        page_count += 1

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
