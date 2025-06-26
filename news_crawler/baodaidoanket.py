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
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class DaiDoanKetCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://daidoanket.vn/"
        self.article_type_dict = {
            0: "chinh-tri/lanh-dao-dang",
            1: "chinh-tri/chu-tich-nuoc",
            2: "chinh-tri/quoc-hoi",
            3: "chinh-tri/chinh-phu",

            4: "mat-tran/cac-cuoc-van-dong",
            5: "mat-tran/tieng-noi-co-so",
            6: "mat-tran/nguoi-mat-tran",
            7: "mat-tran/giam-sat-phan-bien",
            8: "mat-tran/kieu-bao",
            9: "mat-tran/dan-toc",
            10: "mat-tran/ton-giao",
            11: "mat-tran/tu-van",

            12: "tieng-dan/dieu-tra",
            13: "tieng-dan/chung-toi-len-tieng",

            14: "xa-hoi/an-sinh-xa-hoi",
            15: "xa-hoi/moi-truong",
            16: "xa-hoi/chuyen-tu-te",

            17: "phap-luat/quy-dinh-moi",

            18: "giao-duc",

            19: "do-thi",

            20: "giao-thong",

            21: "van-hoa/giai-tri",

            22: "suc-khoe/cac-benh-dich",

            23: "the-thao",

            24: "bat-dong-san",

            25: "cong-nghe/san-pham-so",

            26: "goc-nhin-dai-doan-ket",
            27: "quoc-te",
            28: "tinh-hoa-viet",
            29: "du-lich",
            30: "thong-tin-doanh-nghiep",
            
        }
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baodaidoanket/category/date
            newspaper_name = "baodaidoanket"
            date_parts = clean_date(publish_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"
            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder

            clean_url = image_url.split('?')[0]
            image_filename = Path(clean_url).name
            remote_path = remote_dir / image_filename

            # Tải ảnh
            response = requests.get(image_url, headers=headers, timeout=10)
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
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.select_one("h1.sc-longform-header-title.block-sc-title")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("p.sc-longform-header-sapo.block-sc-sapo")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("span.sc-longform-header-date.block-sc-publish-time")
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            content_images = []
            entry_div = soup.find('div', class_='entry entry-no-padding')

            # 1. Lấy tất cả các đoạn văn bản <p>
            paragraphs = entry_div.find_all('p')
            contents = [p.get_text(strip=True) for p in paragraphs]

            # 2. Lấy tất cả hình ảnh và chú thích
            content_images = []
            figures = entry_div.find_all('figure')
            for fig in figures:
                img_tag = fig.find('img')
                if img_tag:
                    image_url = img_tag['src']
                    content_images.append(image_url)
            content = "\n".join(contents)

            author = None
            author_tag = soup.select_one("span.sc-longform-header-author.block-sc-author")
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://daidoanket.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        ul_element = driver.find_element(By.CSS_SELECTOR, "ul.onecms__loading")
        try:
            while True:
                # Lấy các bài viết hiện tại
                articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.b-grid__title a")
                for article in articles:
                    link = article.get_attribute("href")
                    seen_links.add(link)
                # Thử click nút "Xem thêm"
                try:
                    load_more_button = driver.find_element(By.CSS_SELECTOR, "div.c-more.onecms__loadmore a")
                    if load_more_button.is_displayed():
                        load_more_button.click()
                        print("🔄 Đã click 'Xem thêm'")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    print("✅ Không còn 'Xem thêm' hoặc gặp lỗi.")
                    break
        finally:
            driver.quit()
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles