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
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: vov/category/date
            newspaper_name = "vov"
            date_parts = clean_date(publish_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"
            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder

            clean_url = image_url.split('?')[0]
            image_filename = Path(clean_url).name
            remote_path = remote_dir / image_filename

            # Tải ảnh
            response = requests.get(image_url, headers=headers)
            response.raise_for_status()
            image_data = BytesIO(response.content)

            # Kết nối SSH/SFTP
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ssh_host, username=ssh_user, password=ssh_password)
            sftp = ssh.open_sftp()

            # Xử lý URL ảnh
            # Tạo thư mục nếu chưa có (đệ quy)
            path_parts = str(remote_dir).split('/')
            current = ''
            for part in path_parts:
                if not part:
                    continue
                current += f'/{part}'
                try:
                    sftp.stat(current)
                except IOError:
                    sftp.mkdir(current)

            # Lưu ảnh
            with sftp.file(str(remote_path), 'wb') as f:
                f.write(image_data.getvalue())

            # Đóng kết nối
            sftp.close()
            ssh.close()

            return str(remote_path)
            
        except Exception as e:
            self.logger.error(f"Error downloading image {image_url}: {e}")
            return None
        
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
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('div', class_='article-author')
            author_tag = author_box.find('a')
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
        content_image_paths = []
        for img_url in content_images:
            if img_url:
                img_path = self.download_image(img_url, title, article_type, publish_date)      
                if img_path:
                    content_image_paths.append(img_path)
                    
        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date),
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            "localContentImagePaths": content_image_paths
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
        page_url = f"https://vov.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        try:
            wait = WebDriverWait(driver, 10)

            while True:

                articles = driver.find_elements(By.CSS_SELECTOR, "div.views-content div.taxonomy-content")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "div.article-media > a.vovvn-title.position-relative")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
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

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn--read-more")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(4)

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