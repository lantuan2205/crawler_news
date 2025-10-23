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

class ThoiBaoVanHocNgheThuatCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://arttimes.vn/"
        self.article_type_dict = {
            0: "tin-lien-hiep-vhnt-c45",
            1: "xa-hoi-c46",
            2: "gia-dinh-c59",
            3: "kinh-te-c6",
            4: "giao-thong-c40",
            5: "cong-nghe-c61",

            6: "kien-truc-quy-hoach-c9",

            7: "phe-binh-ly-luan-c48",

            8: "tac-pham-moi-c49",

            9: "nhiep-anh-c3",

            10: "my-thuat-dong-duong-c71",
            11: "my-thuat-khang-chien-c72",
            12: "my-thuat-duong-dai-c73",

            13: "du-lich-c43",

            14: "mv-c64",
            15: "nghe-si-c65",

            16: "phim-c66",
            17: "giai-tri-c47",

            18: "ban-doc-c50",
            
        }

    def extract_content(self, url: str) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.select_one("h1.fw-bold-lexend.color-main")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("h2.fw-bold-inter")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("time.art-time-bv.mar-r-20.d-flex")

            if date_tag:
                raw_date = date_tag.get_text(strip=True)
                # Chuyển định dạng từ 22-01-2025 15:22 về 22/01/2025 15:22
                from datetime import datetime
                try:
                    date_obj = datetime.strptime(raw_date, "%d-%m-%Y %H:%M")
                    publish_date = date_obj.strftime("%d/%m/%Y %H:%M")
                except ValueError:
                    # Nếu không đúng định dạng, giữ nguyên giá trị gốc
                    publish_date = raw_date
            else:
                publish_date = None

            content_images = []
            entry_div = soup.find('article', class_='art-cont-arti')
            paragraphs = entry_div.find_all('p')

            contents = []
            for p in paragraphs:
                # Kiểm tra tổ tiên (parents) của thẻ <p>
                if not p.find_parent(class_='sc-longform-header'):
                    contents.append(p.get_text(strip=True))

            # Nếu muốn gộp nội dung

            # 2. Lấy tất cả hình ảnh và chú thích
            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("article", class_="art-cont-arti")

            if not content_div:
                return [], []

            # Tìm tất cả ảnh trong article
            all_images = content_div.find_all('img')

            # Loại bỏ ảnh nằm trong 2 div không mong muốn
            exclude_selectors = [
                "div.d-flex.align-items-center.justify-content-between",
                "div.bv-lq"
            ]

            # Tìm tất cả ảnh trong vùng cần loại trừ
            excluded_images = []
            for selector in exclude_selectors:
                exclude_div = content_div.select_one(selector)
                if exclude_div:
                    excluded_images.extend(exclude_div.find_all('img'))

            # Tạo set chứa các src của ảnh cần loại bỏ
            excluded_srcs = set(img['src'] for img in excluded_images if img.get('src'))

            # Lọc lại những ảnh hợp lệ
            content_images = [
                img['src'] for img in all_images
                if img.get('src') and img['src'] not in excluded_srcs
            ]

            content = "\n".join(contents)

            author = None
            author_tag = soup.select_one("div.art-author-bv p.fw-bold-inter")
            if author_tag:
                author_text = author_tag.get_text(strip=True)
                author = author_text
            author = author_text.split('(')[0].strip() if author_text else None

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
        try:
            title, description, content, publish_date, author, content_images = self.extract_content(url)
            if not title:
                print(f"⚠️ Bỏ qua bài không có tiêu đề: {url}")
                return None
        except Exception as e:
            print(f"❌ Lỗi trong quá trình phân tích HTML ở bài: {url}")
            print(f"   Chi tiết lỗi: {e}")
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
        page_url = f"https://arttimes.vn/{article_type}.html"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        seen_article_ids = set()
        try:
            wait = WebDriverWait(driver, 10)

            while True:
                # Scroll và đợi DOM render
                driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                time.sleep(2)

                # Tìm tất cả bài viết hiện có
                articles = driver.find_elements(By.CSS_SELECTOR, "section.art-news-random article.art-news-random-items")
                new_found = 0

                for article in articles:
                    try:
                        # Lấy text hoặc ID duy nhất để tránh quét lại
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)    
                        title_link = article.find_element(By.CSS_SELECTOR, "figure.art-news-random__img > a")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://arttimes.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.text-uppercase.fw-semi-bold-lexend.color-main.hover-color-art")))
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
