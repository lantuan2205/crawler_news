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

class BaoThanhNienCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thanhnien.vn/"
        self.article_type_dict = {
            0: "chinh-tri/su-kien",
            1: "chinh-tri/thoi-luan",
            2: "chinh-tri/vuon-minh-trong-ky-nguyen-moi",
            3: "chinh-tri/chung-dong-mau-lac-hong",

            4: "thoi-su/phap-luat",
            5: "thoi-su/lao-dong-viec-lam",
            6: "thoi-su/phong-su--dieu-tra",
            7: "thoi-su/chong-tin-gia",
            8: "thoi-su/dan-sinh",
            9: "thoi-su/quyen-duoc-biet",
            10: "thoi-su/thanh-tuu-y-khoa",
            11: "thoi-su/quoc-phong",

            12: "the-gioi/kinh-te-the-gioi",
            13: "the-gioi/quan-su",
            14: "the-gioi/goc-nhin",
            15: "the-gioi/ho-so",
            16: "the-gioi/nguoi-viet-nam-chau",
            17: "the-gioi/chuyen-la",

            18: "kinh-te/kinh-te-xanh",
            19: "kinh-te/chinh-sach-phat-trien",
            20: "kinh-te/ngan-hang",
            21: "kinh-te/chung-khoan",
            22: "kinh-te/doanh-nghiep",
            23: "kinh-te/doanh-nhan",
            24: "kinh-te/lam-giau",
            25: "kinh-te/dia-oc",

            26: "doi-song/tet-yeu-thuong",
            27: "doi-song/nguoi-song-quanh-ta",
            28: "doi-song/gia-dinh",
            29: "doi-song/am-thuc",
            30: "doi-song/cong-dong",
            31: "doi-song/mot-nua-the-gioi",
            32: "doi-song/khat-vong-nam-rong",

            33: "suc-khoe/khoe-dep-moi-ngay",
            34: "suc-khoe/lam-dep",
            35: "suc-khoe/gioi-tinh",
            36: "suc-khoe/tham-my-an-toan",
            37: "suc-khoe/y-te-thong-minh",

            38: "gioi-tre/song-yeu-an-choi",
            39: "gioi-tre/tiep-suc-gen-z-mua-thi",
            40: "gioi-tre/co-hoi-nghe-nghiep",
            41: "gioi-tre/doan-hoi",
            42: "gioi-tre/ket-noi",
            43: "gioi-tre/khoi-nghiep",
            44: "gioi-tre/the-gioi-mang",
            45: "gioi-tre/guong-mat-tre",

            46: "giao-duc/tuyen-sinh",
            47: "giao-duc/chon-nghe-chon-truong",
            48: "giao-duc/du-hoc",
            49: "giao-duc/nha-truong",
            50: "giao-duc/phu-huynh",
            51: "giao-duc/on-thi-tot-nghiep",
            52: "giao-duc/tuyen-sinh",

            53: "du-lich/tin-tuc-su-kien",
            54: "du-lich/choi-gi-an-dau-di-the-nao",
            55: "du-lich/bat-dong-san-du-lich",
            56: "du-lich/cau-chuyen-du-lich",
            57: "du-lich/kham-pha",

            58: "van-hoa/song-dep",
            59: "van-hoa/cau-chuyen-van-hoa",
            60: "van-hoa/khao-cuu",
            61: "van-hoa/xem-nghe",
            62: "van-hoa/sach-hay",
            63: "van-hoa/mon-ngon-ha-noi",
            64: "van-hoa/nghia-tinh-mien-tay",
            65: "van-hoa/hao-khi-mien-dong",

            66: "giai-tri/phim",
            67: "giai-tri/doi-nghe-si",
            68: "giai-tri/truyen-hinh",

            69: "the-thao/bong-da-thanh-nien-sinh-vien",
            70: "the-thao/bong-da-viet-nam",
            71: "the-thao/bong-da-quoc-te",
            72: "the-thao/the-thao-cong-dong",
            73: "the-thao/cac-mon-khac",

            74: "cong-nghe/tin-tuc-cong-nghe",
            75: "cong-nghe/blockchain",
            76: "cong-nghe/san-pham",
            77: "cong-nghe/xu-huong-chuyen-doi-so",
            78: "cong-nghe/thu-thuat",
            79: "cong-nghe/game",

            80: "xe/thi-truong",
            81: "xe/xe-dien",
            82: "xe/danh-gia-xe",
            83: "xe/tu-van",
            84: "xe/xe-giao-thong",
            85: "xe/xe-doi-song",

            86: "thoi-trang-tre/thoi-trang-247",
            87: "thoi-trang-tre/giu-dang",
            88: "thoi-trang-tre/thoi-trang-nghe-nghiep",
            89: "thoi-trang-tre/tan-huong",

            91: "ban-doc/la-thu-tam-su",
            92: "ban-doc/tu-don-thu-ban-doc",
            93: "ban-doc/ban-doc-viet",
            94: "ban-doc/co-quan-chua-tra-loi-ban-doc",
            95: "ban-doc/tra-loi-ban-doc",
            96: "ban-doc/la-lanh-dum-la-rach",
            90: "ban-doc/tam-long-vang",

            97: "tieu-dung-thong-minh/moi-moi-moi",
            98: "tieu-dung-thong-minh/mua-mot-cham",
            99: "tieu-dung-thong-minh/o-dau-re",
            100: "tieu-dung-thong-minh/goc-nguoi-tieu-dung",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baothanhnien/category/date
            newspaper_name = "baothanhnien"
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
            title = None
            title_wrapper = soup.find("h1", class_="detail-title")
            if title_wrapper:
                span_tag = title_wrapper.find("span", attrs={"data-role": "title"})
                if span_tag:
                    title = span_tag.get_text(strip=True) if span_tag else None

            # Lấy description
            desc_tag = soup.find("h2", class_="detail-sapo")
            description = desc_tag.get_text(strip=True) if desc_tag else None
            
            
            date_tag = soup.select_one("div.detail-time div[data-role='publishdate']")
            if date_tag:
                raw_text = date_tag.get_text(strip=True)
                match = re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", raw_text)
                publish_date = match.group(0) if match else None
            else:
                publish_date = None
            # Lấy tất cả các ảnh trong phần tử này
            content_images = []
            content_div = soup.find("div", class_="detail-content afcbc-body")

            if content_div:
                images = content_div.find_all('img')
                for img in images:
                    src = img.get("src")
                    if src and not src.startswith("data:image") and src.endswith((".jpg", ".jpeg", ".png")):
                        content_images.append(src)
            else:
                print("⚠️ Không tìm thấy thẻ div.detail-content afcbc-body")

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = ""
            content_div = soup.find("div", class_="detail-content afcbc-body", attrs={"data-role": "content"})

            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(
                    p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                )
            else:
                print("❌ Không tìm thấy div.detail-content.afcbc-body có data-role=content")

            # Trích xuất tác giả
            author_box = soup.find('a', class_="name")
            author = author_box.get_text(strip=True).rstrip('-').strip() if author_box else None

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
        # in link lỗi
        try:
            title, description, content, publish_date, author, content_images = self.extract_content(url)
            if not title:
                print(f"⚠️ Bỏ qua bài không có tiêu đề: {url}")
                return None
        except Exception as e:
            print(f"❌ Lỗi trong quá trình phân tích HTML ở bài: {url}")
            print(f"   Chi tiết lỗi: {e}")
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
        page_url = f"https://thanhnien.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        wait = WebDriverWait(driver, 10)
        seen_article_ids = set()  # set theo object id hoặc nội dung text

        try:
            while True:
                previous_count = len(seen_links)

                # Scroll 4 lần
                for i in range(4):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(1.5)
                
                articles = driver.find_elements(By.CSS_SELECTOR, "div.box-category-middle div.box-category-item")

                for article in articles:
                    try:
                        # Lấy text hoặc ID duy nhất để tránh quét lại
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)

                        title_link = article.find_element(By.CSS_SELECTOR, "a")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://thanhnien.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                                # print(" New link:", href)
                                new_found += 1
                    except Exception:
                        continue
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)
    
                try:
                    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.list__viewmore")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(2)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click nút 'Trang sau'")
                    time.sleep(3)

                except Exception:
                        print("✅ Không còn nút Trang sau. Dừng lại.")
                        break

                
        except Exception as e:
            print("⚠️ Lỗi collect links:", e)
        finally:
            driver.quit()
        print(f"📄 Tổng số bài thu thập: {len(seen_links)}")
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles