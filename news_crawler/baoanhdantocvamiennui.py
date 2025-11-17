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
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException


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

class BaoDanTocMienNuiCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://dantocmiennui.baotintuc.vn/"
        self.article_type_dict = {
            0: "54-dan-toc-viet-nam",
            1: "chinh-sach",
            2: "doi-song",
            3: "van-hoa",
            4: "du-lich",
            5: "kinh-nghiem-lam-an",
            6: "guong-sang-soi-chung",
            
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
            title_tag = soup.find('h1',class_='article__title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("div", class_="article__sapo")
            desc_tag = (
                soup.find("div", class_="article__sapo") or 
                soup.find('p', class_='t1')
            )
            description = desc_tag.get_text(strip=True) if desc_tag else None



            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("time", class_='time')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            content_div = soup.find("div", class_="article__body")
            images = content_div.find_all('img')
            # Lọc ảnh
            content_images = []
            for img in images:
                # Kiểm tra và lấy cả src và data-large-src
                for attr in ['src', 'data-src']:
                    src = img.get(attr)
                    if not src:
                        continue
                    if src.startswith("data:image"):
                        continue  # ❌ Bỏ base64
                    if any(x in src for x in ["gg-news", "zalo", "logo", "icon"]):
                        continue  # ❌ Bỏ ảnh giao diện
                    if urlparse(src).path.lower().endswith(".jpg") or urlparse(src).path.lower().endswith(".png"):
                        content_images.append(src)
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            paragraphs = content_div.find_all("p")
            paragraphs = (
                content_div.find_all("p") or 
                content_div.find('div', class_='t3')
            )
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))


            # Trích xuất tác giả
            author_tag = soup.find(["a","span"], class_=["name","cms-author"])
            # author_tag = soup.find("span", class_="cms-author")
            author = author_tag.get_text(strip=True).split('/')[0].strip() if author_tag else None

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

        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date) if publish_date else None,
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            # # "localContentImagePaths": content_image_paths
        }

        return article_data

    def get_urls_of_type_thread(self, article_type, page_number):
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless 
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux                                                
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://dantocmiennui.baotintuc.vn/{article_type}"
        driver.get(page_url)
        seen_links = set()
        seen_article_ids = set()  # set theo object id hoặc nội dung text
        page_count = 0
        max_pages = 5
        last_size = 0  
        try:
            wait = WebDriverWait(driver, 10)

            while page_count < max_pages:
                # Scroll và đợi DOM render
                driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                time.sleep(1)

                # Tìm tất cả bài viết hiện có
                articles = driver.find_elements(By.CSS_SELECTOR, "div.content-list article.story")
                new_found = 0

                for article in articles:
                    try:
                        # Lấy text hoặc ID duy nhất để tránh quét lại
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)

                        title_link = article.find_element(By.CSS_SELECTOR, "figure.story__thumb > a")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://dantocmiennui.baotintuc.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                                # print("🔗 New link:", href)
                                new_found += 1
                    except Exception:
                        continue

                if new_found == 0:
                    print("✅ Không còn bài mới sau khi cuộn/trang mới.")
                    break
                
                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.control__loadmore")))
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