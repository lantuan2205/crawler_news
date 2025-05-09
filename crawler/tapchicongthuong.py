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

class TapChiCongThuongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://tapchicongthuong.vn/"
        self.article_type_dict = {
            0: "bao-ve-nen-tang-tu-tuong-cua-dang-10818",
            1: "doanh-nghiep-9",
            2: "nguoi-cong-thuong-8",
            3: "cong-nghe-14",
            4: "kinh-te-xanh-13302",
            5: "kinh-te-4",
            6: "hang-hoa-nguyen-lieu-54",
            7: "cartimes-56",
            8: "dia-phuong-8307",
            9: "chinh-sach-3",
            10: "tai-chinh-doanh-nghiep-453",
            11: "gio-thu-9-21974",
            12: "quoc-te-hoi-nhap-2",
            13: "tuyen-sinh-nganh-cong-thuong-21932",                    
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: tapchicongthuong/category/date
            newspaper_name = "tapchicongthuong"
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

            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            h1_tag = soup.select_one('h1.post-title.text-left.font-playfair')
            title = h1_tag.text.strip() if h1_tag else None

            # Lấy tên tác giả
            author_tag = soup.select_one("div.meta-info .source strong")
            author = author_tag.get_text(strip=True) if author_tag else None

            # Lấy description
            desc_tag = soup.select_one('div.sapo.title-1.mb-3')
            description = desc_tag.text.strip() if desc_tag else None
            clean_description = re.sub(r"^TCCT\s+", "", description)

            # Trích xuất ngày viết bài
            publish_date = None
            date_span = soup.select_one('div.post-meta span')
            publish_date = date_span.text.strip() if date_span else None

            content_div = soup.find("div", {"id": "post_content"})

            paragraphs = content_div.find_all(["p", "h2"])
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs)

            content_images = []
            for figure in content_div.find_all("figure"):
                img_tag = figure.find("img")
                caption_tag = figure.find("figcaption")
                if img_tag:
                    image_url = img_tag["src"]
                    content_images.append(image_url)

            return title, clean_description, content, publish_date, author, content_images

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
        page_url = f"https://tapchicongthuong.vn/hashtag/{article_type}/page-{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_divs = soup.select('div.widget-layout-1.pt-4.mb-4, div.list-view')
        if(len(target_divs) == 0):
            return []
        urls = []
        base_url = 'https://tapchicongthuong.vn'
        # Duyệt từng vùng và lấy các <a> có href bắt đầu bằng "/"
        for div in target_divs:
            links = div.select('a[href]')
            for link in links:
                href = link['href']
                if href.startswith('/'):
                    urls.append(base_url + href)

        # Loại bỏ trùng lặp
        urls = list(dict.fromkeys(urls))

        return urls

