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
from utils.service_utils import clean_date, get_urls_of_type


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

class TapChiKhoaHocVaCongNgheCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vjst.vn//"
        self.article_type_dict = {
            0: "39/chuong-trinh-kx-01-16-20",
            1: "15/chuong-trinh-nong-thon-mien-nui",
            2: "31/khcn-va-doi-moi-sang-tao",
            3: "41/khcn-dia-phuong",
            4: "4/dien-dan-khoa-hoc-va-cong-nghe",
            5: "44/cong-nghe---san-pham-va-doi-song",

            6: "17/cach-mang-cong-nghiep-4-0",
            7: "6/khcn-nuoc-ngoai",
            8: "46/chuyen-doi-so",
            9: "18/khoi-nghiep-doi-moi-sang-tao",

            10: "48/nghi-quyet-57",
            11: "51/chao-mung-dai-hoi-dang-bo-cac-cap-tien-toi-dai-hoi-xiv-cua-dang",
            12: "16/so-huu-tri-tue",
            13: "38/Ho-tro-nghie-cuu-va-dao-tao",
            14: "47/cai-cach-hanh-chinh",
            15: "9/chuong-trinh-592",

            16: "37/Thong-tin-hoi-nghi-hoi-thao",
            17: "34/Tuyen-sinh-sau-dai-hoc",
            18: "35/Tuyen-chon-de-tai-du-an",

        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: tapchikhoahocvacongnghe/category/date
            newspaper_name = "tapchikhoahocvacongnghe"
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
            title_tag = soup.find('h1', class_='News_Detail_Title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("div#divArticleDescription1 p")
            description = desc_tag.get_text(strip=True) if desc_tag else None


            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_='News_Time_Post')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", id="divArticleDescription2")
            images = content_div.find_all('img')
            content_images = []
            for img in images:
                src = img.get('src')
                if src:
                    if not src.startswith('data'):
                        src = urljoin("https://vjst.vn", src)
                    content_images.append(src)
            
            # Lấy nội dung chỉ từ các thẻ <p> trong <article>
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            content = content_div.get_text(separator="\n", strip=True)
           
            # Trích xuất tác giả
            author = None
            # Tìm div chứa nội dung
            target_div = soup.find("div", id="divArticleDescription2")

            if target_div:
                prim_author = target_div.select_one("div.Author_Write_TG > p")
                if prim_author:
                    author = prim_author.get_text(strip=True) if prim_author else None

                # 1. Ưu tiên: p > em > strong
                primary_author = target_div.select("p > em > strong")
                if primary_author:
                    author = primary_author[-1].get_text(strip=True) if primary_author else None
                
                pri_author = target_div.select("p > strong")
                if pri_author:
                    author = pri_author[-1].get_text(strip=True) if pri_author else None

                # 2. Nếu chưa có, tìm tất cả p > strong > em và lấy thẻ cuối cùng
                if not author:
                    fallback_authors = target_div.select("p > strong > em")
                    if fallback_authors:
                        author = fallback_authors[-1].get_text(strip=True) if fallback_authors else None

                # 3. Nếu vẫn chưa có, tìm p có style="text-align:" chứa strong
                if not author:
                    right_aligned = target_div.select_one("p[style*='text-align: justify'] > strong")
                    if right_aligned:
                        author = right_aligned.get_text(strip=True)  if right_aligned else None


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
        # in link lỗi
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
        import requests
        import time, random
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin

        page_url = f"https://vjst.vn/vn/chuyen-muc/{article_type}.aspx?page={page_number}"
        print(f"📄 Đang xử lý trang: {page_url}")

        try:
            response = requests.get(page_url, headers=headers, timeout=10, verify=False)
            time.sleep(random.uniform(1, 2))
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"❌ Lỗi khi tải {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")

        # Lấy tất cả div.listnews_item
        items = soup.find_all("div", class_="listnews_item")
        urls = []

        for item in items:
            a_tag = item.select_one("div.listnews_item_title a")
            if a_tag and a_tag.get("href"):
                href = a_tag["href"]
                full_url = urljoin("https://vjst.vn/", href)
                # print("🔗 Found:", full_url)
                urls.append(full_url)

        return urls
    def get_all_articles(self):
        """Lấy tất cả bài báo từ các danh mục trên VNExpress."""
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles