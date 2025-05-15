import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time


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

class SucKhoeDoiSongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://suckhoedoisong.vn/"
        self.article_type_dict = {
            0: "y-te",
            1: "thoi-su",
            2: "tra-cuu-benh",
            3: "suc-khoe-tv",
            4: "y-hoc-360",
            5: "duoc",
            6: "y-hoc-co-truyen",
            7: "gioi-tinh",
            8: "dinh-duong",
            9: "khoe-dep",
            10: "phong-mach-online",
            11: "thi-truong",
            12: "nhip-cau-nhan-ai",
            13: "van-hoa-giai-tri",
            14: "doi-song",
        }
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: suckhoedoisong/category/date
            newspaper_name = "suckhoedoisong"
            date_parts = clean_date(publish_date).split(',')[0].strip()
            day, month, year = date_parts.split('-')
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
            title_tag = soup.find("h1", class_="detail-title", attrs={"data-role": "title"})
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("h2", class_="detail-sapo", attrs={"data-role": "sapo"})
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_="publish-date", attrs={"data-role": "publishdate"})
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            content_images = []
            content_div = soup.find('div', class_='detail-content afcbc-body', attrs={'data-role': 'content'})
            if not content_div:
                return [], []

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            paragraphs = content_div.find_all('p')
            contents = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
            content = "\n".join(contents)
            for img_tag in content_div.find_all('img'):
                src = img_tag.get('data-original') or img_tag.get('src')
                if src and src.startswith('http'):
                    content_images.append(src)

            author = None
            author_div = soup.find('div', class_='detail-author', attrs={'data-role': 'author'})
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://suckhoedoisong.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        ul_elements = driver.find_elements(By.CSS_SELECTOR, "div.box-category-middle")

        while True:
            # Lấy các bài viết hiện tại
            for ul_element in ul_elements:
                articles = ul_element.find_elements(By.CSS_SELECTOR, "h3 a")
                for article in articles:
                    link = article.get_attribute("href")
                    seen_links.add(link)
            # Thử click nút "Xem thêm"
            try:
                load_more_button = driver.find_element(By.CSS_SELECTOR, "div.loadmore")
                if load_more_button.is_displayed():
                    load_more_button.click()
                    print("🔄 Đã click 'Xem thêm'")
                    time.sleep(3)
                else:
                    break
            except Exception:
                print("✅ Không còn 'Xem thêm' hoặc gặp lỗi.")
                break
        return seen_links

