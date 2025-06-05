import os
import requests
import sys
from pathlib import Path
import re

import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Optional  


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class ThoiBaoNganHangCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thoibaonganhang.vn/"
        self.article_type_dict = {
            0: "ngan-hang/thi-truong-tien-te",
            1: "ngan-hang/ngan-hang-so",
            2: "ngan-hang/hoat-dong-cua-cac-tctd",
            3: "ngan-hang/dong-chay-tin-dung",
            4: "thoi-su",
            5: "kheo-dung-tien/danh-cho-tre-em",
            6: "kheo-dung-tien/danh-cho-nguoi-truong-thanh",
            7: "kheo-dung-tien/danh-cho-nguoi-cao-tuoi",
            8: "dau-tu-tai-chinh/bat-dong-san",
            9: "dau-tu-tai-chinh/chung-khoan",
            10: "dau-tu-tai-chinh/tai-chinh-quoc-te",
            11: "dau-tu-tai-chinh/du-lich",
            12: "phan-tich-tai-chinh-tien-te/bao-cao-tai-chinh-cac-tctd",
            13: "ngan-hang-doanh-nghiep-doanh-nhan/chuyen-doanh-nghiep",
            14: "ngan-hang-doanh-nghiep-doanh-nhan/ca-phe-voi-ceo",
            15: "ngan-hang-doanh-nghiep-doanh-nhan/doanh-nghiep-voi-hoi-nhap",
            16: "ngan-hang-doanh-nghiep-doanh-nhan/quan-tri-doanh-nghiep",
            17: "ngan-hang-doanh-nghiep-doanh-nhan/nhan-su-va-tuyen-dung",
            18: "mo-khoa-ket",
            19: "ngan-hang-thi-truong/gia-ca-tieu-dung",
            20: "ngan-hang-thi-truong/thiet-bi-san-pham",
            21: "ngan-hang-thi-truong/o-to-xe-may",
            22: "tien-xua-nay/lich-su-tien-te-viet-nam",
            23: "tien-xua-nay/lich-su-tien-te-the-gioi",
            24: "tien-xua-nay/ky-su-ngan-hang",
            25: "tien-xua-nay/hinh-anh-ngan-hang-xua",
            26: "nhip-song-so/giao-duc",
            27: "nhip-song-so/suc-khoe",
            28: "nhip-song-so/the-thao",
            29: "cau-chuyen-canh-giac/canh-bao-ve-lua-dao-thanh-toan",
            30: "cau-chuyen-canh-giac/canh-bao-ve-toi-pham-cac-dich-vu-ngan-hang",
            31: "sac-mau-cuoc-song/sac-mau-cuoc-song",
            32: "sac-mau-cuoc-song/thoi-trang",
            33: "sac-mau-cuoc-song/lam-dep",
            34: "sac-mau-cuoc-song/giai-tri",




        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: thoibaonganhang/category/date
            newspaper_name = "thoibaonganhang"
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
          
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.find('h1',class_='article-detail-title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("div", class_="article-detail-desc")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            time_tag = soup.select_one("span.format_time")
            date_tag = soup.select_one("span.format_date")

            if time_tag and date_tag:
                publish_date = f"{time_tag.get_text(strip=True)} {date_tag.get_text(strip=True)}"
            else:
                publish_date = None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="__MASTERCMS_CONTENT")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('div', class_='tbnh-author-meta')
            author_tag = author_box.find('a')
            author = author_tag.get_text(strip=True).split('/')[0].strip() if author_tag else None

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
        page_url = f"https://thoibaonganhang.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        try:
            wait = WebDriverWait(driver, 10)

            while True:

                articles = driver.find_elements(By.CSS_SELECTOR, "div.bx-cat-content div.article")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "a")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://thoibaonganhang.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.btn-xemthem")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(2)

                except Exception:
                        print("✅ Không còn nút Trang sau. Dừng lại.")
                        break

        except Exception as e:
            print("⚠️ Lỗi collect links:", e)
        finally:
            driver.quit()
        print(f"📄 Tổng số bài thu thập: {len(seen_links)}")
        return seen_links

    def get_all_articles(self):
        
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles
