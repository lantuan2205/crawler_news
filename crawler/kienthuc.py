import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
import re

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

class KienThucCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://kienthuc.net.vn/"
        self.article_type_dict = {
            0: "tuyen-sinh",
            1: "doc-30s",
            2: "soi-xet",
            3: "song-4-mau",
            4: "hoi-dap",
            5: "nguoi-tot-viec-tot",
            6: "cai-chinh-xin-loi",
            7: "tham-cung",
            8: "di-san",
            9: "ta-tay",
            10: "giai-ma",
            11: "phong-thuy",
            12: "tri-thuc-viet-toan-cau",
            13: "thien",
            14: "khoa-hoc",
            15: "cong-nghe",
            16: "tien-vang",
            17: "nha-dat",
            18: "doanh-nhan",
            19: "tieu-dung",
            20: "hang-hot",

            21: "tin-tuc-quan-su",
            22: "vu-khi",
            23: "quan-doi",
            24: "quan-su-viet-nam",

            25: "the-gioi-24h",
            26: "nong-sau",
            27: "ho-so",
            28: "doi-song-the-gioi",

            29: "xe",
            30: "phu-kien-xe",
            31: "dan-choi-xe",

            32: "doi-song",
            33: "lam-dep-giam-can",
            34: "me-be",
            35: "an-ngon",
            36: "dinh-duong-thuoc",
            37: "yeu-tam",

            38: "chat-sao",
            39: "showbiz",
            40: "showbiz-ngoai",
            41: "phong-cach-sao",
            42: "phim-nhac",
            43: "nhip-song",
            
            44: "sot-mang",
            45: "yeu-online",
            46: "the-thao",
            47: "choi-phuot",
            48: "ban-doc-dieu-tra",
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: kienthuc/category/date
            newspaper_name = "kienthuc"
            date_parts = clean_date(publish_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"
            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder
            print("----remote_dir-----", remote_dir)

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

            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title = soup.find('h1', class_='cms-title').get_text()
            # Lấy description
            description = soup.find('h2', class_='sapo cms-desc').text.strip()
            # Trích xuất ngày viết bài
            publish_date = soup.find('time').text.strip()
            # Lấy nội dung text trong các thẻ <p>
            body = soup.find('div', id='abody')
            # Lấy content text (giữ định dạng đoạn văn)
            content = []
            if body:
                for tag in body.find_all(['p', 'div'], style=lambda x: x and 'text-align: justify' in x):
                    content.append(tag.get_text(strip=True))


            content = '\n\n'.join(content)
            # Lấy ảnh
            content_images = [img['src'] for img in body.find_all('img') if img.get('src')]

            # Lấy tên tác giả
            author = soup.find('span', class_='name').text.strip()

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
        page_url = f"https://kienthuc.net.vn/{article_type}/?page={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        base_url = "https://kienthuc.net.vn"

        # Tìm section chứa danh sách bài viết
        section = soup.select_one('section.cat-listnews.hzol-clear')

        # Tìm tất cả các thẻ <a> trong <h2 class="title">
        urls = []
        if section:
            articles = section.select('h2.title a')
            for a in articles:
                href = a.get('href')
                if href and href.startswith('/'):
                    urls.append(base_url + href)

        return urls

