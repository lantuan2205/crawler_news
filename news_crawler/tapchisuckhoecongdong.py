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

class TapChiSucKhoeCongDongCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://suckhoecongdongonline.vn/"
        self.article_type_dict = {
            0: "suc-khoe-doi-song/",
            1: "chuyen-gia/",
            2: "phong-kham-online/",
            3: "dinh-duong/",
            4: "duoc-pham/",
            5: "lam-dep/",
            6: "moi-truong-suc-khoe/",
            7: "benh-thuong-gap/",
            8: "vi-cong-dong/",
            9: "ban-doc/",
            10: "san-pham-vi-suc-khoe/",

        }

    def extract_content(self, url: str) -> tuple:
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
            title_tag = soup.find('h1', id='ti_tle')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("div.sabo")
            description = desc_tag.get_text(strip=True) if desc_tag else None


            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("div.time-detail span")
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="content-skcd")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)

            author = None

            # Tìm p có style="text-align: right;"
            right_aligned_p = soup.find("p", style=lambda x: x and "text-align: right" in x)

            if right_aligned_p:
                # Ưu tiên tìm strong trước
                strong_tag = right_aligned_p.find("strong")
                if strong_tag:
                    author_raw = strong_tag.get_text(strip=True)
                else:
                    # Nếu không có strong, thử tìm em
                    em_tag = right_aligned_p.find("em")
                    if em_tag:
                        author_raw = em_tag.get_text(strip=True)
                    else:
                        # Nếu cả strong lẫn em đều không có, fallback lấy toàn bộ p
                        author_raw = right_aligned_p.get_text(strip=True)
                
                # Loại bỏ phần trong ()
                author_cleaned = re.sub(r'\s*\(.*?\)', '', author_raw).strip()
                author = author_cleaned
                
            return title, description, content, publish_date, author, content_images

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
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://suckhoecongdongonline.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        try:
            wait = WebDriverWait(driver, 10)

            while True:

                articles = driver.find_elements(By.CSS_SELECTOR, "div.big-center div.item-cate")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "h3 > a")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://suckhoecongdongonline.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.load_more_page")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(2)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(3)

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

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles
