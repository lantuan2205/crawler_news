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
from utils.service_utils import clean_date, get_urls_of_type


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

class VtvCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vtv.vn/"
        self.article_type_dict = {
            0: "chinh-tri",
            1: "xa-hoi",
            2: "phap-luat",

            3: "the-gioi/tin-tuc",
            4: "the-gioi/the-gioi-do-day",
            5: "dong-su-kien/da-chieu-cau-chuyen-quoc-te-238",

            6: "kinh-te/bat-dong-san",
            7: "kinh-te/tai-chinh",
            8: "kinh-te/thi-truong",
            9: "kinh-te/goc-doanh-nghiep",

            10: "truyen-hinh/phim-vtv",
            11: "truyen-hinh/hau-truong",
            12: "truyen-hinh/nhan-vat",
            13: "truyen-hinh/goc-khan-gia",
            14: "truyen-hinh/giai-sao-mai",

            15: "nguoi-viet-bon-phuong",

            16: "truyen-hinh/goc-khan-gia",

            17: "van-hoa-giai-tri/dien-anh",
            18: "van-hoa-giai-tri/am-nhac",

            19: "doi-song/du-lich",
            20: "doi-song/lam-dep",
            21: "dong-su-kien/chat-luong-cuoc-song-268",

            22: "suc-khoe",

            23: "tam-long-viet",

            24: "the-thao/bong-da-trong-nuoc",
            25: "the-thao/bong-da-quoc-te",
            26: "the-thao/tennis",
            27: "the-thao/cac-mon-khac",
            28: "the-thao/ben-le",

            29: "chuong-trinh-dac-sac/su-kien-va-binh-luan",
            30: "chuong-trinh-dac-sac/toan-canh-the-gioi",
            31: "chuong-trinh-dac-sac/tap-chi-kinh-te-cuoi-tuan",

            32: "truc-tuyen",

            33: "cong-nghe/san-pham",
            34: "cong-nghe/thi-truong",
            35: "cong-nghe/tu-van",
            36: "cong-nghe/hitech-cong-nghe-tuong-lai",

            37: "giao-duc/tu-van",
            38: "giao-duc/hoc-truc-tuyen",
            39: "cong-nghe/tin-cong-nghe",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: vtv/category/date
            newspaper_name = "vtv"
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
            title_tag = soup.find('h1', class_='title_detail')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("h2", class_="sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None
            # Trích xuất ngày viết bài
            import re

            publish_date = None
            date_tag = soup.find("span", class_="time")

            if date_tag:
                text = date_tag.get_text(strip=True)
                # Tìm chuỗi dạng dd/mm/yyyy hh:mm bằng regex
                match = re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", text)
                if match:
                    publish_date = match.group(0)


            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="ta-justify")
            if not content_div:
                return [], []

            # Tìm tất cả ảnh
            images = content_div.find_all('img')

            # Bỏ ảnh cụ thể: like-fanpage-vtv.jpg
            content_images = [
                img['src'] for img in images
                if img.get('src') and not img['src'].endswith("like-fanpage-vtv.jpg")
            ]
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            # Trích xuất tác giả
            author = None
            author_tag = soup.find('p', class_='author')

            if author_tag:
                # Xóa thẻ <span class="time"> nếu có
                span_time = author_tag.find('span', class_='time')
                if span_time:
                    span_time.extract()  # loại bỏ khỏi cây DOM

                # Sau đó lấy text còn lại (tên)
                author = author_tag.get_text(strip=True)

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
        page_url = f"https://vtv.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        wait = WebDriverWait(driver, 10)

        try:
            while True:
                # Lưu số lượng link trước khi quét
                previous_count = len(seen_links)

                # Scroll 4 lần
                # for i in range(4):
                #     driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                #     time.sleep(1.5)

                # Thu thập link bài viết mới
                articles = driver.find_elements(By.CSS_SELECTOR, "div.list_news ul li.tlitem")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.CSS_SELECTOR, "a")
                        href = a_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://vtv.vn", href)
                            if href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        continue

                # So sánh số lượng link sau khi quét
                current_count = len(seen_links)
                new_links_found = current_count - previous_count
                # Nếu không có link mới → dừng
                if new_links_found == 0:
                    print("✅ Không còn link mới. Kết thúc.")
                    break

                # Nếu có link mới, click nút "Xem thêm"
                try:
                    next_button = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Xem thêm')]")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'Xem thêm'")
                    time.sleep(2)
                except Exception as e:
                    print("❌ Không tìm thấy hoặc không click được nút 'Xem thêm':", e)
                    break

        finally:
            driver.quit()

        print(f"📄 Tổng số link thu thập được: {len(seen_links)}")
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles