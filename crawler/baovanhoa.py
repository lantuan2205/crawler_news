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

class BaoVanHoaCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baovanhoa.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "bien-dao-to-quoc",
            2: "van-hoa-va-thoi-luan",
            3: "chinh-sach-quan-ly",
            4: "di-san",
            5: "van-hoa-co-so",
            6: "doi-song-van-hoa",
            7: "cong-nghiep-van-hoa",
            8: "chinh-sach-quan-ly-bao-chi",
            9: "toan-canh-bao-chi",
            10: "thong-tin-doi-ngoai",
            11: "van-hoa-so",
            12: "xu-phat-vi-pham-hanh-chinh-ve-bao-chi",
            13: "the-thao-chinh-sach-quan-ly",
            14: "the-thao-trong-nuoc",
            15: "the-thao-quoc-te",
            16: "hau-truong",
            17: "cau-chuyen-the-thao",
            18: "du-lich-chinh-sach-quan-ly",
            19: "diem-den",
            20: "kham-pha",
            21: "gia-dinh-chinh-sach-quan-ly",
            22: "gia-dinh-360-do",
            23: "loi-song",
            24: "van-hoc",
            25: "dien-anh",
            26: "am-nhac",
            27: "san-khau-mua",
            28: "my-thuat-nhiep-anh",
            29: "truyen-hinh",
            30: "thoi-trang",
            31: "showbiz",
            32: "cung-thu-gian",
            33: "giao-duc",
            34: "y-te",
            35: "ban-tre",
            36: "moi-truong-khi-hau",
            37: "do-thi",
            38: "xa-hoi",
            39: "doanh-nghiep",
            40: "chung-khoan",
            41: "dia-phuong",
            42: "thi-truong",
            43: "khoi-nghiep",
            44: "hang-viet",
            45: "bat-dong-san",
            46: "bao-ve-nguoi-tieu-dung",
            47: "dai-doan-ket",
            48: "van-hoa-xa-hoi-vung-mien",
            49: "nong-thon-moi",
            50: "van-hoa-du-lich-dan-toc-thieu-so",
            51: "chuyen-de-dan-toc-thieu-so-va-mien-nui",
            52: "hoc-tap-va-lam-theo-bac",
            53: "viet-nam-ky-nguyen-vuon-minh",
            54: "quy-hoach-mang-luoi-co-so-van-hoa-the-thao-va-du-lich-tam-nhin-2045",
            55: "doi-song-xanh",
            56: "chuong-trinh-muc-tieu-quoc-gia-ve-phat-trien-van-hoa",
            57: "80-nam-ngay-truyen-thong-van-hoa",
            58: "giai-bao-chi-toan-quoc-vi-su-nghiep-phat-trien-van-hoa",
            59: "huong-toi-dai-hoi-thi-dua-yeu-nuoc-bo-vhttdl-2025",
            60: "cau-noi-phap-luat",
            61: "tin-nong",
            62: "dieu-tra",
            63: "thong-tin-tu-ban-doc",
            64: "hoi-am",
            65: "ban-doc-viet",
            66: "chuyen-doi-so",
            67: "cong-nghe",
            68: "san-pham",
            69: "thi-truong-xe",
            70: "trai-nghiem",
            71: "cong-dong",
            72: "su-kien",
            73: "van-hoa-quoc-te",
            74: "nguoi-viet-nam-chau"
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
            newspaper_name = "baovanhoa"
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
            title = soup.find('h1', class_='detail__title').text.strip()

            description = soup.find('h2', class_='detail__summary').text.strip()

            content = soup.find('div', class_='detail__content').text.strip()

            # Trích xuất ngày viết bài
            time_tag = soup.find('time')
            publish_date = time_tag.text.strip() if time_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find('div', class_='detail__content')
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]

            # Trích xuất tác giả
            author = soup.find('span', class_='detail__author').text.strip()

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
        if (page_number > 49):
            return []
        page_url = f"https://baovanhoa.vn/{article_type}/?page={page_number}"
        results = []
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        # titles = soup.find_all("h3", class_="article-title")

        articles = soup.find_all('article', class_='story')

        if (len(articles) == 0):
            return []

        for article in articles:
            title_tag = article.find('h3', class_='story__title')
            title_link = title_tag.find('a') if title_tag else None
            link = title_link['href'] if title_link else None
            if link.startswith(f'/{article_type}/'):
                full_url = f"https://baovanhoa.vn{link}"  # Thêm domain nếu cần
                results.append(full_url)

        return results

