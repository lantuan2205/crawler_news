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

class TapChiBongDaCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://bongdaplus.vn/"
        self.article_type_dict = {
            0: "v-league",
            1: "hang-nhat-quoc-gia",
            2: "cup-quoc-gia",
            3: "doi-tuyen-quoc-gia-viet-nam",
            4: "bong-da-nu-viet-nam",
            5: "u17-viet-nam",
            6: "futsal",
            7: "bong-da-phong-trao",
            8: "cac-doi-tuyen-tre-viet-nam",
            9: "tin-moi",
            10: "u19-viet-nam",

            11: "champions-league-cup-c1",

            12: "la-liga",
            13: "cup-nha-vua-tay-ban-nha",
            14: "doi-tuyen-tay-ban-nha",

            15: "bundesliga",
            16: "cup-quoc-gia-duc",
            17: "doi-tuyen-duc",

            18: "ligue-1",
            19: "cup-quoc-gia-phap",
            20: "doi-tuyen-phap",

            21: "serie-a",
            22: "coppa-italia",
            23: "doi-tuyen-y",

            24: "giao-huu-bong-da",
            25: "world-cup",
            26: "diem-tin",
            27: "fifa-club-world-cup",

            28: "the-thao",

            29: "doi-tuyen-anh",
            30: "ngoai-hang-anh",
            31: "fa-cup",
            32: "cup-lien-doan-anh",

            33: "europa-league",
            34: "fifa-club-world-cup-tags",
            35: "europa-conference-league",

            36: "world-cup",
            37: "nations-league",
            38: "copa-america",
            39: "can",
            40: "olympic",

            41: "asian-cup",
            42: "asian-games",
            43: "aff-cup",
            44: "sea-games",

            45: "tin-chuyen-nhuong",
            46: "hau-truong-bong-da",
            47: "diem-tin",
            48: "ngoi-sao-showbiz",
            49: "goc-check-var",
            50: "dam-me",

            51: "bigstory",
            52: "x-file",
            53: "nhan-dinh-bong-da-tags"

        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: tapchibongda/category/date
            newspaper_name = "tapchibongda"
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
            title_tag = soup.select_one('div.lead-title h1a')
            title = title_tag.get_text(strip=True) if title_tag else None

             # Lấy description
            desc_tag = soup.select_one("div.summary b")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None 

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("div.emobar div.rgt")
            if date_tag:
                publish_date = date_tag.get_text(strip=True).strip()
                import re
                m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})\s*\|\s*(\d{1,2}):(\d{2})', publish_date)
                if m:
                    day, month, year, hour, minute = m.groups()
                    publish_date = f"{int(day):02d}/{int(month):02d}/{str(year)[-2:]} {int(hour):02d}:{int(minute):02d}"
                else:
                    m = re.search(r'(\d{1,2}):(\d{2})\s*ngày\s*(\d{1,2})/(\d{1,2})/(\d{4})', publish_date)
                    if m:
                        hour, minute, day, month, year = m.groups()
                        publish_date = f"{int(day):02d}/{int(month):02d}/{str(year)[-2:]} {int(hour):02d}:{int(minute):02d}"
                    else:
                        m = re.search(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', publish_date)
                        if m:
                            year, month, day, hour, minute = m.groups()
                            publish_date = f"{int(day):02d}/{int(month):02d}/{str(year)[-2:]} {int(hour):02d}:{int(minute):02d}"
                        else:
                            m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', publish_date)
                            if m:
                                day, month, year = m.groups()
                                publish_date = f"{int(day):02d}/{int(month):02d}/{str(year)[-2:]} 00:00"

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="content")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('div', class_='editor')
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
        # chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://bongdaplus.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0

        try:
            wait = WebDriverWait(driver, 10)

            while True:
                articles = driver.find_elements(By.CSS_SELECTOR, "div.row.flex div.col.m12.w3")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "div.news > a.thumb")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://bongdaplus.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                max_clicks = 8  # Giới hạn số lần click
                click_count = 0

                while click_count < max_clicks:
                    try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.view-more > a")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        print(f"➡️ Đã click nút 'Trang sau'")
                        time.sleep(2)
                        click_count += 1
                    except Exception:
                        print("✅ Không còn nút Trang sau. Dừng lại.")
                        break

                



                # try:
                #  # Tìm div chứa nội dung chính
                #     cont_wrap = driver.find_element(By.CSS_SELECTOR, "div.cont-wrap")

                #     # Tìm nút "Xem thêm" bên trong cont-wrap
                #     next_button = cont_wrap.find_element(By.CSS_SELECTOR, "div.view-more > a")

                #     # Cuộn đến nút và click
                #     driver.execute_script("arguments[0].scrollIntoView();", next_button)
                #     time.sleep(1)
                #     driver.execute_script("arguments[0].click();", next_button)
                #     print("➡️ Đã click nút 'Trang sau'")
                #     time.sleep(2)

                # except Exception:
                #     print("✅ Không còn nút Trang sau trong cont-wrap. Dừng lại.")
                #     break

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