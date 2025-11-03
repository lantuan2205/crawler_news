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

class ToChucNhaNuocCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://tcnnld.vn/"
        self.article_type_dict = {
            0: "5017/Thoi-su---Chinh-tri",
            1: "5020/Cai-cach-hanh-chinh",
            2: "1010187/Bo-Noi-vu---80-nam-xay-dung-va-phat-trien",
            3: "1010186/Cai-cach-tien-luong",
            4: "1010087/Hoc-tap-va-lam-theo-tu-tuong-dao-duc-phong-cach-Ho-Chi-Minh",
            5: "1010072/Xay-dung-chinh-quyen-dia-phuong",
            6: "9/Ban-doc-viet",
            7: "1010173/Phong-chong-tac-hai-cua-thuoc-la",

            8: "1010067/Nghien-cuu---Trao-doi",
            9: "1010153/Xay-dung-nong-thon-moi",
            10: "1010070/Thuc-tien---Kinh-nghiem",

            11: "1010185/Thi-dua---Khen-thuong",
            12: "1010073/Nhin-ra-the-gioi",
            13: "1010094/Tu-dien-Hanh-chinh-mo",
            14: "1010184/Thong-tin---Quang-cao",
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
            title_tag = soup.find('h1',class_='titleMain')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("div.noidung.fwd.fwb p")
            description = desc_tag.text.strip() if desc_tag else None



            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("div.thongke-ngay span")

            if date_tag:
                # Lấy toàn bộ text
                raw_text = date_tag.get_text(strip=True)

                # Tách và làm sạch phần sau "Ngày đăng:"
                if "Ngày đăng:" in raw_text:
                    publish_date = raw_text.split("Ngày đăng:")[-1].replace('\xa0', ' ').strip()
            
            noidung_divs = soup.find_all("div", class_="noidung")
            content_images = []
            # Chỉ xử lý div thứ 2 nếu có đủ
            if len(noidung_divs) >= 2:
                target_div = noidung_divs[1]
                images = target_div.find_all("img")
                base_url = "https://a.tcnn.vn/"

                # Thêm tiền tố vào ảnh
                content_images = [
                    urljoin(base_url, img.get("src")) for img in images if img.get("src")
                ]

            # Chỉ xử lý div thứ 2 nếu tồn tại
            if len(noidung_divs) >= 2:
                target_div = noidung_divs[1]  # div.noidung thứ 2 (index = 1)
                paragraphs = [
                    p for p in target_div.find_all("p")
                    if p.get("class") != ["pt5"]
                ]
                content_texts = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
                content = "\n".join(content_texts)
            else:
                content = ""

            # Trích xuất tác giả
            author_tag = soup.find('p', class_='pt5')
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
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://tcnnld.vn/news/category/{article_type}.html"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        try:
            wait = WebDriverWait(driver, 10)

            while True:

                articles = driver.find_elements(By.CSS_SELECTOR, "div.group div.item")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "div.wImage > a")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://tcnnld.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "i.fa-step-forward")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
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

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles