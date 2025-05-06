import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime
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

class TapChiDienTuCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietq.vn/"
        self.article_type_dict = {
            0: "tin-trong-nuoc-sub9",
            1: "quoc-te-sub10",
            2: "van-de-sub11",
            3: "tieu-chuan-chat-luong-c86",
            4: "an-toan-thuc-pham-sub12",
            5: "hang-kem-chat-luong-sub13",
            6: "phat-hien-sub34",
            7: "thi-truong-sub14",
            8: "san-pham-dich-vu-sub16",
            9: "chat-luong-vang-sub20",
            10: "dien-dan-sub71",
            11: "khoa-hoc-cong-nghe-sub6",
            12: "dau-tu-sub96",
            13: "khieu-nai-sub75",
            14: "tu-van-tieu-dung-sub15",
        }   
        
    def download_image(self, image_url, article_title, category, published_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: dantri/category/date
            newspaper_name = "tapchidientu"
            date_parts = clean_date(published_date).split(',')[0].strip()
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
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Trích xuất tiêu đề
            title = soup.find("h1", class_="detail-title").get_text(strip=True)

            intro_p = soup.select_one(".detail-intro .caption")
            description = intro_p.get_text(strip=True) if intro_p else None

            main_content = soup.find("div", id="main-detail")
            content = [p.get_text(strip=True) for p in main_content.find_all("p")] if main_content else []

            # Trích xuất ngày viết bài
            datetime_div = soup.find("div", class_="datetimeup")
            publish_date = datetime_div.get_text(strip=True) if datetime_div else None

            # Trích xuất tất cả các ảnh trong phần nội dung
            content_images = []
            if main_content:
                for img in main_content.find_all("img"):
                    src = img.get("src")
                    if src:
                        content_images.append(src)

            # Trích xuất tác giả
            ps = soup.find_all("p", style="text-align: right;")
            author = None
            for p in reversed(ps):  # Duyệt từ cuối lên đầu
                strong = p.find("strong")
                if strong:
                    author = strong.get_text(strip=True)
                    break

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
        page_url = f"https://vietq.vn/{article_type}/p{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        article_links = soup.find_all('a', class_='thumb300x170')

        if (len(article_links) == 0):
            return []

        results =  [a['href'] for a in article_links]

        return results

