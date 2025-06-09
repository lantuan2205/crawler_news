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

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class BaoQuocTeCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baoquocte.vn/"
        self.article_type_dict = {
            0: "tin-moi",

            1: "thoi-su/xay-dung-dang",
            2: "thoi-su/suy-ngam",
            3: "thoi-su/viet-nam-va-asean",
            4: "thoi-su/phan-tich-chuyen-thoi-su",

            5: "bien-dong-247",

            6: "the-gioi/toan-canh",
            7: "the-gioi/tieu-diem",
            8: "the-gioi/binh-luan",
            9: "the-gioi/ho-so", 
            10: "the-gioi/doc-bao-nuoc-ngoai",

            11: "ngoai-giao/tin-bo-ngoai-giao",
            12: "ngoai-giao/bao-ho-cong-dan",
            13: "ngoai-giao/thuong-thuc-ngoai-giao",
            14: "ngoai-giao/chuyen-ngoai-giao",

            15: "kinh-te/kinh-te-the-gioi",
            16: "kinh-te/ngoai-giao-kinh-te",
            17: "kinh-te/hoi-nhap-phat-trien",
            18: "kinh-te/bat-dong-san",
            19: "kinh-te/tai-chinh-chung-khoan",
            20: "kinh-te/thuong-hieu-san-pham",

            21: "nguoi-viet",

            22: "van-hoa/di-san-van-hoa",
            23: "van-hoa/du-lich",
            24: "van-hoa/so-tay-van-hoa",
            25: "van-hoa/doanh-nhan-va-cuoc-song",

            26: "xa-hoi/giao-duc",
            27: "xa-hoi/doi-song",
            28: "xa-hoi/y-te",

            29: "giai-tri/hau-truong",
            30: "giai-tri/chuyen-bon-phuong",
            31: "giai-tri/xem-nghe",

            32: "the-thao/ngoai-hang-anh",
            33: "the-thao/v-league",
            34: "the-thao/cup-c1",
            35: "the-thao/asean-cup",
            36: "the-thao/chuyen-nhuong",

            37: "khoa-hoc-cong-nghe/chuyen-doi-so",
            38: "khoa-hoc-cong-nghe/kham-pha",
            39: "khoa-hoc-cong-nghe/meo-hay",
            40: "khoa-hoc-cong-nghe/thu-thuat",

            41: "o-to/xe-moi",

            42: "goc-nhin-nhan-quyen/tin-tuc-7-ngay",
            43: "goc-nhin-nhan-quyen/tieu-diem",
            44: "goc-nhin-nhan-quyen/y-kien-chuyen-gia",
            45: "goc-nhin-nhan-quyen/y-kien-chuyen-gia",

        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baoquocte/category/date
            newspaper_name = "baoquocte"
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
            title_tag = soup.find('h1', class_='article-detail-title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find('div',class_='article-detail-desc')
            description = desc_tag.get_text(strip=True) if desc_tag else None


            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("div", class_='article-date')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="__MASTERCMS_CONTENT")
            images = content_div.find_all('img')
            content_images = [
                img['src'] for img in images
                if img.get('src') and not (img['src'].lower().endswith('.jpg') or img['src'].lower().endswith('.png'))
            ]
            if not content_div:
                return [], []

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            # Lấy nội dung chỉ từ các thẻ <p> trong <article>
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            # Trích xuất tác giả
            author_tag = soup.find(["div","span"], class_=["article-member","cms-author"])
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

        page_number = (page_number - 1) * 15
        page_url = f"https://baoquocte.vn/{article_type}&s_cond=&BRSR={page_number}"
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            time.sleep(random.uniform(1, 2))
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Lỗi khi tải {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_div = soup.find("div", class_="bx-listing")

        urls = []
        if target_div:
            a_tags = target_div.find_all("h3", class_="article-title")
            if(len(a_tags) == 0):
                return []
            for a_tag in a_tags:
                tag = a_tag.find("a")
                if tag and tag.get("href"):
                    urls.append(tag["href"])

        return urls
    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles

    def get_all_articles(self):
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles