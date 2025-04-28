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

class BaoVePhapLuatCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baovephapluat.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            # 1: "kiem-sat-24h/van-de-su-kien",
            # 2: "kiem-sat-24h/ban-tin-kiem-sat",
            # 3: "kiem-sat-24h/nhan-su-moi",
            # 4: "kiem-sat-24h/chinh-sach-moi",
            # 5: "cong-to-kiem-sat-tu-phap/theo-dong",
            # 6: "cong-to-kiem-sat-tu-phap/khoi-to",
            # 7: "cong-to-kiem-sat-tu-phap/khoi-to",
            # 8: "cong-to-kiem-sat-tu-phap/an-ninh-trat-tu",
            # 9: "phap-dinh/toa-tuyen-an",
            # 10: "phap-dinh/ky-an",
            # 11: "phap-dinh/cau-chuyen-phap-luat",
            # 12: "cai-cach-tu-phap/dien-dan",
            # 13: "cai-cach-tu-phap/thuc-tien-kinh-nghiem",
            # 14: "cai-cach-tu-phap/nhan-to-dien-hinh",
            # 15: "kinh-te/kinh-doanh-phap-luat",
            # 16: "kinh-te/do-thi-xay-dung",
            # 17: "giao-thong",
            # 18: "kinh-te/tai-chinh-ngan-hang",
            # 19: "kinh-te/dung-hang-viet",
            # 20: "van-hoa-xa-hoi/giao-duc",
            # 21: "van-hoa-xa-hoi/y-te",
            # 22: "van-hoa-xa-hoi/lao-dong-viec-lam",
            # 23: "van-hoa-xa-hoi/vong-tay-nhan-ai",
            # 24: "van-hoa-xa-hoi/goc-van-hoa",
            # 25: "van-hoa-xa-hoi/doi-song-xa-hoi",
            # 26: "quoc-te/tin-tuc",
            # 27: "quoc-te/phap-luat-5-chau",
            # 28: "quoc-te/chuyen-la-bon-phuong",
            # 29: "phap-luat-ban-doc/tin-duong-day-nong",
            # 30: "phap-luat-ban-doc/dieu-tra-theo-don-thu",
            # 31: "phap-luat-ban-doc/hoi-am",
            # 32: "phap-luat-ban-doc/bao-chi-cong-dan",                                                                                   
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baovephapluat/category/date
            newspaper_name = "baovephapluat"
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

            # Trích xuất tiêu đề
            title_tag = soup.find('h1', class_='post-title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Trích xuất ngày viết bài
            date_tag = soup.find('div', class_='lbPublishedDate')
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            desc_tag = soup.find('div', class_='post-summary')
            description = desc_tag.h2.get_text(strip=True) if desc_tag and desc_tag.h2 else None

            content_tag = soup.find('div', class_='noidung')
            content = ''
            if content_tag:
                paragraphs = content_tag.find_all('p')
                content = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)

            post_content_div = soup.find('div', class_='post-content')
            content_images = []
            if post_content_div:
                for img in post_content_div.find_all('img'):
                    src = img.get('src')
                    # Chỉ lấy ảnh có src bắt đầu bằng http hoặc chứa tên miền chính
                    if src and ('baovephapluat.vn' in src):
                        content_images.append(src)

            # Lấy tác giả (nằm trong div class="tacgia")
            author_tag = soup.find('div', class_='tacgia')
            author = author_tag.get_text(strip=True) if author_tag else None

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
        page_url = f"https://baovephapluat.vn/{article_type}/p/{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        ctrangc3_div = soup.find('div', class_='ctrangc3')
        link_tags = ctrangc3_div.find_all('a', href=True) if ctrangc3_div else []
        urls = [tag['href'] for tag in link_tags]
        return urls

