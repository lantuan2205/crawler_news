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

class BaoTaiChinhVietNamCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thoibaotaichinhvietnam.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "kinh-te",
            2: "tai-chinh",
            3: "thue-hai-quan",
            4: "chung-khoan",
            5: "ngan-hang",
            6: "bao-hiem",
            7: "kinh-doanh",
            8: "bat-dong-san",
            9: "phap-luat",
            10: "gia-ca",
            11: "xa-hoi",
            12: "quoc-te"                                                             
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: thoibaotaichinhvietnam/category/date
            newspaper_name = "thoibaotaichinhvietnam"
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
            title_tag = soup.find("h1", class_="post-title")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy tên tác giả
            author_tag = soup.find("h2", class_="author-title")
            if author_tag and author_tag.get_text(strip=True):
                author = author_tag.get_text(strip=True)
            else:
                # Nếu không có, lấy từ <div class="post-author">
                fallback_tag = soup.find("div", class_="post-author")
                author = fallback_tag.get_text(strip=True) if fallback_tag else None

            # Lấy description
            desc_div = soup.find("div", class_="post-desc")
            description = desc_div.get_text(strip=True) if desc_div else None

            # Trích xuất ngày viết bài
            time_tag = soup.find("span", class_="article-publish-time")
            if time_tag:
                time_part = time_tag.find("span", class_="format_time")
                date_part = time_tag.find("span", class_="format_date")
                if time_part and date_part:
                    publish_date = f"{time_part.get_text(strip=True)} {date_part.get_text(strip=True)}"

            content_div = soup.find("div", class_="post-content")
            paragraphs = content_div.find_all("p")
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs)

            images = content_div.find_all("img")
            content_images = [img['src'] for img in images if img.get('src')]

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
        page_number = (page_number - 1) * 15
        page_url = f"https://thoibaotaichinhvietnam.vn/{article_type}&s_cond=&BRSR={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_div = soup.find("div", class_="cat-listing bg-dots mt20 pt20 article-bdt-20 thumb-w250 title-22 no-catname")

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

