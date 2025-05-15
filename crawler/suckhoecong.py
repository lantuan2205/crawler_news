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

class SucKhoeCongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://suckhoecong.vn/"
        self.article_type_dict = {
            0: "kien-thuc-song-khoe-d1",
            1: "thuc-pham-chuc-nang-d2",
            2: "tai-chinh",
            3: "hoi-dap-d8",
            4: "goc-nhin-quan-ly-d5",
            5: "tro-chuyen-d6",
            6: "ban-doc-viet-d7",
            7: "van-hoa-xa-hoi-d3",
            8: "phong-benh-chu-dong-d4",
            9: "cong-dong-len-tieng-d11",
            10: "tin-tuc-thoi-su-d12",
            11: "suc-khoe-moi-truong-d51"
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: suckhoecong/category/date
            newspaper_name = "suckhoecong"
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
            section = soup.find('section', class_='box-author')
            # Lấy title
            title = section.find('h1').get_text(strip=True)
            # Lấy description từ thẻ div.info-author (lấy text trước thẻ <ul>)
            info_author = section.find('div', class_='info-author')
            cleaned_description = info_author.get_text(separator=' ', strip=True).split(' 03/')[0].strip()
            description = re.sub(r'^[^|]+\|\s*', '', cleaned_description)
            # Lấy ngày tháng từ <li> đầu tiên trong <ul>
            publish_date = section.find('ul').find('li').get_text(strip=True)
            detail_div = soup.find('div', class_='detail text-justify')

            # Lấy nội dung bài viết: tất cả thẻ <p> bên trong (trừ liên quan)
            paragraphs = detail_div.find_all('p')
            content = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)

            # Lấy danh sách ảnh từ các thẻ <img> bên trong
            content_images = [img['src'] for img in detail_div.find_all('img') if img.get('src')]

            # Tác giả nằm trong div.author-detail
            author_div = detail_div.find('div', class_='author-detail')
            author = author_div.get_text(strip=True) if author_div else None
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
        page_url = f"https://suckhoecong.vn/{article_type}/p{page_number}"

        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        # Tìm thẻ div chứa danh sách bài viết
        main_div = soup.find('div', class_='list-new-cate')

        # Tìm tất cả thẻ <a> có class="link-title" bên trong main_div
        title_links = main_div.find_all('a', class_='link-title')
        if(len(title_links) == 0):
            return []
        # Trích xuất href và tiêu đề
        results = [a['href'] for a in title_links]

        return results

