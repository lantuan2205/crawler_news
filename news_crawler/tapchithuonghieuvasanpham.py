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
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class TapChiThuongHieuVaSanPhamCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thuonghieusanpham.vn/"
        self.article_type_dict = {
            0: "tieu-diem/vi-mo",
            1: "tieu-diem/cong-tac-hoi",
            2: "tieu-diem/khoa-hoc-va-cong-nghe",

            3: "san-pham/thong-tin-san-pham",
            4: "san-pham/san-pham-ocop",
            5: "san-pham/thien-nhien-tu-nhien",
            6: "san-pham/chat-luong-cao",

            7: "thuong-hieu/so-huu-tri-tue",
            8: "thuong-hieu/xay-dung-quan-tri",
            9: "thuong-hieu/uy-tin-ban-sac",

            10: "kinh-doanh/tai-chinh",
            11: "kinh-doanh/kinh-te",

            12: "doanh-nghiep-doanh-nhan/chuyen-dong-doanh-nghiep",
            13: "doanh-nghiep-doanh-nhan/doanh-nhan",
            14: "doanh-nghiep-doanh-nhan/khoi-nghiep",

            15: "thi-truong/chong-hang-gia",
            16: "thi-truong/hang-hoa-gia-ca",
            17: "thi-truong/dien-bien-du-bao",

            18: "song-khoe/bai-thuoc-dan-gian",
            19: "song-khoe/vi-suc-khoe-cong-dong",
            20: "song-khoe/bao-ve-nguoi-tieu-dung",

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
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: tapchithuonghieuvasanpham/category/date
            newspaper_name = "tapchithuonghieuvasanpham"
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
            date_tag = soup.find("span", class_='format_time')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="__MASTERCMS_CONTENT")
            content_images = []

            if not content_div:
                return [], []

            # Tìm toàn bộ table cần loại bỏ
            tables_to_exclude = content_div.find_all("table", class_="__mb_article_in_image")

            # Lấy tất cả ảnh
            images = content_div.find_all('img')

            for img in images:
                src = img.get('src')
                if not src:
                    continue

                # Kiểm tra ảnh này có thuộc table bị loại bỏ không
                in_excluded_table = any(table in img.parents for table in tables_to_exclude)

                if not in_excluded_table:
                    content_images.append(src)

            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            # Lấy nội dung chỉ từ các thẻ <p> trong <article>
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            author = None

            # Trường hợp 1: tìm div.article-detail-author
            author_box = soup.find('div', class_='article-detail-author')
            if author_box:
                author = author_box.get_text(strip=True).split('/')[0].strip()

            # Trường hợp 2: nếu trường hợp 1 không có thì fallback sang p[style="text-align: right"]
            if not author:
                right_aligned_p = soup.find("p", style=lambda x: x and "text-align: right" in x)
                if right_aligned_p:
                    # Nếu có thẻ strong thì ưu tiên lấy strong
                    strong_tag = right_aligned_p.find("strong")
                    if strong_tag:
                        author = strong_tag.get_text(strip=True)
                    else:
                        author = right_aligned_p.get_text(strip=True)

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
       
        page_number = (page_number - 1) * 20
        page_url = f"https://thuonghieusanpham.vn/{article_type}&s_cond=&BRSR={page_number}"
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            time.sleep(3)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Lỗi khi tải {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_div = soup.find("div", class_="bx-list fw lt mb clearfix")

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

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles