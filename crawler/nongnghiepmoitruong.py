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
from utils.service_utils import clean_date

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class NongNghiepMoiTruongCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://nongnghiepmoitruong.vn/"
        self.article_type_dict = {
            0: "chinh-tri",
            1: "thoi-su-nong-nghiep-moi-truong",

            2: "chan-nuoi",
            3: "thu-y",
            4: "trong-trot",
            5: "khuyen-nong",
            6: "tai-co-cau-nong-nghiep",
            7: "khoa-hoc---cong-nghe",
            8: "thuy-san",
            9: "lam-nghiep",

            10: "xe-may",
            11: "cau-chuyen-moi-truong",
            12: "quan-ly-chat-thai-ran",
            13: "bien-doi-khi-hau-moitruong",
            14: "khoa-hoc-cong-nghe",
            15: "tin-tuc",

            16: "khoang-san",
            17: "tai-nguyen-nuoc",
            18: "bien-dao",

            19: "bat-dong-san-nong-thon",
            20: "bat-dong-san-du-lich",
            21: "do-thi-va-doi-song",
            22: "quy-hoach",
            23: "chinh-sach-datdai",

            24: "kinh-te-thi-truong",
            25: "viec-lam",
            26: "doanh-nghiep-doanh-nhan",
            27: "dau-tu-tai-chinh",
            28: "cong-khai-ngan-sach",
            29: "thong-tin-can-biet",

            30: "doi-song",
            31: "phong-su",

            32: "tu-van-phap-luat",
            33: "dieu-tra-theo-thu-ban-doc",
            34: "an-ninh-trat-tu",
            35: "canh-sat-moi-truong",
            36: "nhung-manh-doi-bat-hanh",
            37: "van-ban-moi",

            
            38: "van-hoa",
            39: "nn-the-thao",
            40: "giai-tri-vanhoathethao",
            41: "du-lich",
            42: "goc-anh-do-thi",
            
            43: "lang-kinh",
            44: "phan-bon",
            45: "thuoc-bao-ve-thuc-vat",
            46: "thuc-an-chan-nuoi",
            47: "thuoc-thu-y",

            48: "chinh-sach",
            49: "mo-hinh-hay-ntm",
            50: "ocop",

            51: "diem-nong",
            52: "vu-khi",
            53: "bien-doi-khi-hau",
            54: "cuoc-song-muon-mau",
            55: "kham-pha",

            56: "ung-thu",
            57: "nghe-thuat-song",
            58: "song-gio-gia-dinh",
            59: "tam-su-da-huong",
            60: "tieu-duong",
            61: "cay-thuoc---vi-thuoc",

            62: "tri-thuc-nong-dan/chuyen-nho-khoi-nghiep",
            63: "tri-thuc-nong-dan/tri-thuc-nghe-nong",
            64: "tri-thuc-nong-dan/tieng-viet--van-viet--nguoi-viet",
            65: "tri-thuc-nong-dan/doanh-nong",
            66: "tri-thuc-nong-dan/nhin-ra-the-gioi",
            67: "tri-thuc-nong-dan/nhip-cau-nha-nong",
        


        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: nongnghiepmoitruong/category/date
            newspaper_name = "nongnghiepmoitruong"
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
            title_tag = soup.find('h1', class_='main-title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            # desc_tag = soup.select_one("div.mota h2")
            desc_tag = soup.find("h2",class_= "main-intro")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách sau dấu "-" đầu tiên
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_='time-detail')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="content")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('p', class_='content-author')
            author = author_box.get_text(strip=True).split('/')[0].strip() if author_box else None

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
        page_url = f"https://nongnghiepmoitruong.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        try:
            wait = WebDriverWait(driver, 10)

            while True:
                articles = driver.find_elements(By.CSS_SELECTOR, "div.main-content-page li.news-home-item")
                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "a.expthumb.thumb")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://nongnghiepmoitruong.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span#loadmore")))
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

        print(f"📄 Tổng số bài thu thập: {len(seen_links)}")
        return seen_links

