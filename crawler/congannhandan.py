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
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class CongAnNhanDanCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://cand.com.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "su-kien-binh-luan-thoi-su",
            2: "van-de-hom-nay-thoi-su",
            3: "chong-dien-bien-hoa-binh",
            4: "nhan-quyen",
            5: "cong-an",
            6: "lanh-dao-bo-cong-an",
            7: "gin-giu-hoa-binh-lhq",
            8: "hoat-dong-ll-cand",
            9: "guong-sang",
            10: "xa-hoi",
            11: "giao-duc",
            12: "giao-thong",
            13: "y-te",
            14: "doi-song",
            15: "phong-su-tu-lieu",
            16: "phap-luat",
            17: "ban-tin-113",
            18: "lan-theo-dau-vet-toi-pham",
            19: "thonng-tin-phap-luat",
            20: "quoc-te",
            21: "the-gioi-24h",
            22: "binh-luan-quoc-te",
            23: "tu-lieu-quoc-te",
            24: "vu-khi-chien-tranh",
            25: "van-hoa",
            26: "Chuyen-dong-van-hoa",
            27: "the-thao",
            28: "Tieu-diem-van-hoa",
            29: "van-hoa-24h",
            30: "giai-tri-van-hoa",
            31: "ban-doc-cand",
            32: "dieu-tra-theo-don-ban-doc",
            33: "hop-thu",
            34: "giai-dap-phap-luat",
            35: "tai-chinh-40",
            36: "Kinh-te",
            37: "dia-oc",
            38: "Thi-truong",
            39: "doanh-nghiep",
            40: "cuoc-song-muon-mau",
            41: "hon-nhan-gia-dinh",
            42: "Chuyen-kho-tin-nhung-co-that-goc",
            43: "Khoa-hoc-Quan-su",
            44: "the-gioi-phuong-tien",
            45: "Van-hoa-PT",
            46: "Cong-nghe",
            47: "eMagazine",
            48: "Xa-hoi-tu-thien",
            49: "nhip-cau-nhan-ai",
            50: "Vuot-len-so-phan",

        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: congannhandan/category/date
            newspaper_name = "congannhandan"
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
            title_tag = soup.find('h1', class_='box-title-detail')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("div.box-des-detail p")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("div", class_='box-date')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="detail-content-body")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('div', class_='box-author')
            author_tag = author_box.find('strong')
            author = author_tag.get_text(strip=True).rstrip('-').strip() if author_tag else None

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
        page_url = f"https://cand.com.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        ul_element = driver.find_element(By.CSS_SELECTOR, "div.box-widget-loaded")
        try:
            while True:
                wait = WebDriverWait(driver, 10)

                container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.box-widget-loaded")))
                articles = container.find_elements(By.TAG_NAME, "article")

                for article in articles:
                    anchors = article.find_elements(By.TAG_NAME, "a")
                    for a in anchors:
                        href = a.get_attribute("href")
                        if href and href.startswith("http") and href not in seen_links:
                            seen_links.add(href)

                # articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.box-category-title-text a")
                # # Lấy các bài viết hiện tại
                # for article in articles:
                #         link = article.get_attribute("href")
                #         seen_links.add(link)
    
                # print(f"📄 Đã lấy được {len(seen_links)} bài.")

                # Nếu không có thêm bài mới → thoát
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                # Cuộn xuống một chút sau mỗi lần nhấn
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
                time.sleep(1)

                try:
                        next_button = driver.find_element(By.CSS_SELECTOR, "a.btn-next-page")
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        next_button.click()
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(3)

                except Exception:
                        print("✅ Không còn nút Trang sau. Dừng lại.")
                        break
        finally:    
            driver.quit()

        return seen_links
    
    def get_all_articles(self):
        
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles
