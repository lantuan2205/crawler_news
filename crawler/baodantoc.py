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

class BaoDanTocCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baodantoc.vn/"
        self.article_type_dict = {
            0: "thoi-su/tin-tuc",
            1: "thoi-su/su-kien-binh-luan",
            2: "thoi-su/van-ban-chinh-sach-moi",
            3: "dan-toc-ton-giao/cong-tac-dan-toc",
            4: "dan-toc-ton-giao/chinh-sach-dan-toc",
            5: "dan-toc-ton-giao/tin-nguong-ton-giao-o-viet-nam",
            6: "dan-toc-ton-giao/nguoi-co-uy-tin",
            7: "dan-toc-ton-giao/dao-va-doi",
            8: "sac-mau-54/tim-trong-di-san",
            9: "sac-mau-54/ban-sac-va-hoi-nhap",
            10: "sac-mau-54/du-lich",
            11: "sac-mau-54/am-thuc",
            12: "kinh-te/san-pham-thi-truong",
            13: "kinh-te/khoi-nghiep",
            14: "kinh-te/doanh-nhan-dan-toc",
            15: "phong-su",
            16: "doi-song-xa-hoi/nghe-nghiep-viec-lam",
            17: "doi-song-xa-hoi/nhip-cau-nhan-ai",
            18: "guong-sang-giua-cong-dong",
            19: "phap-luat/ban-doc",
            20: "phap-luat/chong-dien-bien-hoa-binh",
            21: "khoa-hoc-cong-nghe/ung-dung-sang-tao",
            22: "khoa-hoc-cong-nghe/khuyen-nong-voi-dong-bao-dtts",
            23: "khoa-hoc-cong-nghe/ban-cua-nha-nong",
            24: "giao-duc/giao-duc-dan-toc",
            25: "giao-duc/duong-den-uoc-mo",
            26: "suc-khoe/song-khoe",
            27: "suc-khoe/moi-truong-song",
            28: "suc-khoe/vuon-thuoc-quanh-ta",
            29: "trang-dia-phuong",
            30: "chuyen-de",
            31: "the-thao-giai-tri/the-thao",
            32: "the-thao-giai-tri/giai-tri",                                                                                   
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baodantoc/category/date
            newspaper_name = "baodantoc"
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
            title = soup.find('h1', class_='news-title')['title']

            # Lấy tên tác giả
            author = soup.find('span', class_='author-name').text.strip()

            # Lấy description
            description = soup.find('h2', class_='news-sapo').text.strip()

            # Trích xuất ngày viết bài
            date = soup.find('span', class_='distribution-date')

            # Kiểm tra trường hợp "X giờ trước"
            if date:
                date_text = date.get_text().strip()
                
                if "giờ trước" in date_text:
                        # Trường hợp "X giờ trước"
                        hours_ago = int(date_text.split(' ')[0])
                        current_time = datetime.now()
                        calculated_time = current_time - timedelta(hours=hours_ago)
                        publish_date = calculated_time.strftime('%H:%M, %d/%m/%Y')
                else:
                    # Trường hợp ngày giờ định dạng "HH:MM, DD/MM/YYYY"
                    try:
                        # Định dạng thời gian "HH:MM, DD/MM/YYYY"
                        date_time = datetime.strptime(date_text, "%H:%M, %d/%m/%Y")
                        publish_date = date_time.strftime('%H:%M, %d/%m/%Y')
                    except ValueError:
                        print("Invalid date format")


            # date_tag = soup.find('div', class_='lbPublishedDate')
            # publish_date = date_tag.get_text(strip=True) if date_tag else None

            content_div = soup.find('div', class_='news-body-content')

            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]

            # Lấy nội dung của bài viết (text content)
            content = content_div.get_text(separator="\n").strip()


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
        page_url = f"https://baodantoc.vn/{article_type}-p{page_number}.htm"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        news_timeline = soup.find('div', class_='news-in-timeline')
        a_urls = [
            a.get('href') for a in news_timeline.find_all('a') 
            if a.get('href') and 'tin-tuc.htm' not in a.get('href')
        ]
        
        # Thêm domain vào URL nếu cần thiết
        full_urls = [f"https://baodantoc.vn{url}" if url.startswith('/') else url for url in a_urls]
        return full_urls

