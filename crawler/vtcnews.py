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

class VTCNewsCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietq.vn/"
        self.article_type_dict = {
            0: "chinh-tri-47",
            # 1: "quan-su-49",
            # 2: "bao-ve-nguoi-tieu-dung-51",
            # 3: "thoi-su-quoc-te-53",
            # 4: "tin-tuc-bien-dong-55",
            # 5: "tin-tuc-su-kien-56",
            # 6: "ban-tin-113-online-58",
            # 7: "chuyen-vu-an-59",
            # 8: "hoa-hau-60",
            # 9: "nhac-62",
            # 10: "sao-the-gioi-63",
            # 11: "sao-viet-64",
            # 12: "bong-da-anh-66",
            # 13: "benh-va-thuoc-68",
            # 14: "dinh-duong-69",
            # 15: "nguoi-dep-va-xe-72",
            # 16: "tu-van-73",
            # 17: "gioi-tinh-90",
            # 18: "gioi-tre-85",
            # 19: "thi-truong-100",
            # 20: "lich-thi-dau-bong-da-101",
            # 21: "tin-tuc-trong-ngay-105",
            # 22: "bat-dong-san-112",
            # 23: "tin-gia-vang-113",
            # 24: "bong-da-viet-nam-115",
            # 25: "du-lich-195",
            # 26: "tin-tuc-202",
            # 27: "khoe-dep-203",
            # 28: "tu-van-204",
            # 29: "dien-dan-207",
            # 30: "du-hoc-208",
            # 31: "chuyen-bon-phuong-209",
            # 32: "y-kien-211",
            # 33: "gia-dinh-212",
            # 34: "tuyen-sinh-220",
            # 35: "an-sinh-239",
            # 36: "thu-thuat-267",
            # 37: "hom-thu-phap-luat-268",
            # 38: "chuyen-doi-so-271",
            # 39: "phong-chong-chay-no-272",
            # 40: "v-league-274",
            # 41: "ky-nguyen-vuon-minh-285",
            # 42: "nguoi-viet-bon-phuong-292",
            # 43: "tin-xe-247-293",
            # 44: "trai-nghiem-294",
            # 45: "thi-truong-295",
            # 46: "xe-dien-296"

            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",
            # 22: "tu-van-tieu-dung-sub15",

                                                                                                
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
            title_tag = soup.find("header", class_="mb5").find("h1")
            title = title_tag.get_text(strip=True) if title_tag else None

            description = soup.select_one('h2')
            description = description.get_text(strip=True) if description else ''

            content_elements = soup.select('.edittor-content p')
            content = '\n'.join(p.get_text(strip=True) for p in content_elements if p.get_text(strip=True))

            # Trích xuất ngày viết bài
            date_tag = soup.find('span', class_='time-update')
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            # Lấy các URL ảnh và alt text từ các thẻ img trong thẻ figure
            figures = soup.select("figure.expNoEdit img")
            content_images = [img.get("data-src") for img in figures if img.get("data-src")]

            # Trích xuất tác giả
            author = soup.select_one('.author-make span')
            author = author.get_text(strip=True) if author else ''

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
        page_url = f"https://vtcnews.vn/{article_type}/trang-{page_number}.html"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        articles = soup.find_all("article")
        urls = []

        for article in articles:
            # Tìm <h3> hoặc <h2>
            heading = article.find(["h3", "h2"])
            if heading:
                a_tag = heading.find("a")
                if a_tag and a_tag.get("href"):
                    url = a_tag["href"]
                    full_url = "https://vtcnews.vn/" + url
                    urls.append(full_url)

        return urls

