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

class TapChiDienDanDoanhNghiepCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://diendandoanhnghiep.vn/"
        self.article_type_dict = {
            0: "chinh-tri-xa-hoi/chinh-tri",
            1: "chinh-tri-xa-hoi/kinh-te",
            2: "chinh-tri-xa-hoi/xa-hoi",
            3: "chinh-tri-xa-hoi/van-de-hom-nay",
            4: "chinh-tri-xa-hoi/tam-diem",

            5: "vcci/phat-trien-ben-vung",
            6: "vcci/tieng-noi-cua-hiep-hoi-doanh-nghiep",
            7: "vcci/doanh-nghiep-hang-dau-viet-nam",
            8: "vcci/xuc-tien-dau-tu-thuong-mai",
            9: "vcci/dai-hoi-vcci-lan-thu-vii",
            10: "vcci/tham-muu-chinh-sach",

            11: "doanh-nghiep/quan-tri",
            12: "doanh-nghiep/chuyen-dong",
            13: "doanh-nghiep/giao-thuong",

            14: "phong-su-anh",
            15: "bai-bao-in",
            16: "tin-luu-tru",

            17: "doanh-nhan/chuyen-lam-an",
            18: "doanh-nhan/trach-nhiem-xa-hoi",
            19: "doanh-nhan/ca-phe-doanh-nhan",
            20: "doanh-nhan/phong-cach-song",

            21: "phap-luat/nghien-cuu-trao-doi",
            22: "phap-luat/ban-doc",
            23: "phap-luat/kien-nghi",
            24: "phap-luat/24h",
            25: "phap-luat/nhin-thang-noi-that",
            26: "phap-luat/chong-hang-gia",
            27: "phap-luat/ho-so",
            28: "phap-luat/phap-dinh",
            
            29: "bat-dong-san/thi-truong",
            30: "bat-dong-san/doanh-nghiep-du-an",
            31: "bat-dong-san/chinh-sach-quy-hoach",
            32: "bat-dong-san/cafe-dia-oc",
            33: "bat-dong-san/tien-do-du-an",

            34: "quoc-te/doi-ngoai",
            35: "quoc-te/kinh-te-the-gioi",
            36: "quoc-te/phan-tich-binh-luan",
             
            37: "ngan-hang-chung-khoan/chung-khoan",
            38: "ngan-hang-chung-khoan/tin-dung-ngan-hang",
            39: "ngan-hang-chung-khoan/tai-chinh-doanh-nghiep",
            40: "ngan-hang-chung-khoan/thi-truong-vang",
            41: "ngan-hang-chung-khoan/dich-vu-tai-chinh",
            42: "ngan-hang-chung-khoan/tai-chinh-so",
            43: "ngan-hang-chung-khoan/chuyen-de",

            44: "du-lich/trai-nghiem",
            45: "du-lich/hoat-dong-du-lich",
            46: "du-lich/hoi-nhap",

            47: "kinh-te-dia-phuong",

            48: "cong-nghe/kinh-te-so",
            49: "cong-nghe/ung-dung",
            50: "cong-nghe/chuyen-doi-so",
            
            51: "o-to-xe-may/dien-dan",
            52: "o-to-xe-may/thong-tin-thi-truong",
            53: "o-to-xe-may/san-pham",
            54: "o-to-xe-may/tu-van-ky-thuat",

            55: "doanh-nghiep-thi-truong/thong-tin-doanh-nghiep",
            56: "doanh-nghiep-thi-truong/san-pham-thi-truong",
            
            57: "nguoi-tot-viec-tot",

            58: "khoi-nghiep/khoi-nghiep-quoc-gia",
            59: "khoi-nghiep/y-tuong-kinh-doanh",
            60: "khoi-nghiep/kinh-doanh-liem-chinh",
            61: "khoi-nghiep/cau-chuyen-khoi-nghiep",
            62: "khoi-nghiep/co-van-huan-luyen",
            63: "khoi-nghiep/so-tay-khoi-nghiep",


        }
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: tapchidiendandoanhnghiep/category/date
            newspaper_name = "tapchidiendandoanhnghiep"
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
            desc_tag = soup.select_one("p.sc-longform-header-sapo")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("span.sc-longform-header-date.block-sc-publish-time")
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            content_images = []
            entry_div = soup.find('div', class_='entry entry-no-padding')
            paragraphs = entry_div.find_all('p')

            contents = []
            for p in paragraphs:
                # Kiểm tra tổ tiên (parents) của thẻ <p>
                if not p.find_parent(class_='sc-longform-header'):
                    contents.append(p.get_text(strip=True))

            # Nếu muốn gộp nội dung

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
        page_url = f"https://diendandoanhnghiep.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        ul_element = driver.find_element(By.CSS_SELECTOR, "ul.onecms__loading ")
        try:
            while True:
                # Lấy các bài viết hiện tại
                articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.b-grid__title a")
                for article in articles:
                    link = article.get_attribute("href")
                    seen_links.add(link)
                # Thử click nút "Xem thêm"
                try:
                    load_more_button = driver.find_element(By.CSS_SELECTOR, "div.c-more a")
                    if load_more_button.is_displayed():
                        load_more_button.click()
                        print("🔄 Đã click 'Xem thêm'")
                        time.sleep(2)
                    else:
                        break
                except Exception:
                    print("✅ Không còn 'Xem thêm' hoặc gặp lỗi.")
                    break
        finally:
            driver.quit()
        return seen_links

    def get_all_articles(self):
        
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles