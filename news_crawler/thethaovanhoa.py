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
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class TheThaoVanHoaCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thethaovanhoa.vn/"
        self.article_type_dict = {
            0: "bong-da-viet-nam/v-league",
            1: "bong-da-viet-nam/doi-tuyen-viet-nam",
            2: "bong-da-viet-nam/hang-nhat",

            3: "bong-da-anh",
            4: "bong-da-tay-ban-nha",
            5: "bong-da-quoc-te/duc",
            6: "bong-da-quoc-te/italy",
            7: "bong-da-quoc-te/phap",
            8: "bong-da-quoc-te/champions-league",
            9: "bong-da-quoc-te/europa-league",

            10: "truc-tiep-bong-da",
            11: "du-doan-bong-da/lich-thi-dau",
            12: "du-doan-bong-da/ket-qua",
            13: "du-doan-bong-da/bang-xep-hang",

            14: "the-thao/bong-chuyen",
            15: "the-thao/pickleball",
            16: "the-thao/the-thao-toc-do",
            17: "the-thao/the-thao-tennis",
            18: "the-thao/billiards-snooker",

            19: "the-gioi-sao/hau-truong",
            20: "the-gioi-sao/ben-le",
            21: "the-gioi-sao/sao",

            22: "van-hoa/doc-xem",
            23: "van-hoa/dien-dan-van-hoa",

            24: "giai-tri/phim",
            25: "giai-tri/am-nhac",
            26: "giai-tri/kbiz",

            27: "genz",
            28: "doi-song/suc-khoe-gioi-tinh",

            29: "tin-tuc-24h/tin-tuc-trong-nuoc",
            30: "tin-tuc-24h/tin-tuc-the-gioi",

            31: "hightech/mobile",
            32: "hightech/xe",
            33: "hightech/cong-nghe",

            34: "multimedia"
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: thethaovanhoa/category/date
            newspaper_name = "thethaovanhoa"
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
            title_tag = soup.find('h1', attrs={'data-role': 'title'})
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("div", class_="entry-body normal clearafter", attrs={"data-role": "content"})
            description = None
            if desc_tag:
                first_p = desc_tag.find("p")
                if first_p:
                    b_tag = first_p.find("b")
                    if b_tag:
                        description = b_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            date_tag = soup.find("span", attrs={"data-role": "publishdate"})
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None
            if date_tag:
                # Lấy nội dung, loại bỏ GMT+7 nếu có
                full_text = date_tag.get_text(strip=True)
                # Tách trước chuỗi 'GMT' nếu xuất hiện
                publish_date = full_text.split('GMT')[0].strip()
            else:
                publish_date = None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("figure", class_="VCSortableInPreviewMode")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            content_div = soup.find("div", class_="entry-body normal clearafter", attrs={"data-role": "content"})
            content = []
            if content_div:
                content = [p.get_text(strip=True) for p in content_div.find_all("p")]
            content = "\n".join(p.get_text(strip=True) for p in content_div if p.get_text(strip=True))

            # Trích xuất tác giả
            author_box = soup.find('p', class_='author')
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
        title, description, content, publish_date, author, content_images = self.extract_content(url)
        if not title:
            return None
            
        # Tải và lưu ảnh nội dung
        '''content_image_paths = []
        for img_url in content_images:
            if img_url:
                img_path = self.download_image(img_url, title, article_type, publish_date)      
                if img_path:
                    content_image_paths.append(img_path)'''
                    
        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date),
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            # "localContentImagePaths": content_image_paths
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
        page_url = f"https://thethaovanhoa.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        wait = WebDriverWait(driver, 10)

        try:
            while True:
                container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.news-stream")))
                articles = container.find_elements(By.TAG_NAME, "li")

                for article in articles:
                    anchors = article.find_elements(By.TAG_NAME, "a")
                    for a in anchors:
                        href = a.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href and href.startswith("http") and href not in seen_links:
                            seen_links.add(href)

                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)
    
                try:
                    # Kéo xuống một nửa trang
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(2)

                    try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.readmore")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(2)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(3)

                    except Exception:
                            print("✅ Không còn nút Trang sau. Dừng lại.")
                            break

                except Exception as e:
                    print(f"❌ Lỗi khi click nút 'Xem thêm': {e}")

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