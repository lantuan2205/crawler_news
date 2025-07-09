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
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException


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

class BaoDauThauCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baodauthau.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "quoc-te",

            2: "tai-san-tai-chinh",
            3: "nha-dat",
            4: "hang-hoa-dich-vu",
            5: "ket-qua-dau-gia",

            6: "lich-dau-gia/tai-san-tai-chinh",
            7: "lich-dau-gia/nha-dat", 
            8: "lich-dau-gia/hang-hoa-dich-vu",

            9: "kinh-doanh",
            10: "doanh-nghiep",
            11: "tai-chinh",

            12: "dau-tu",
            13: "bat-dong-san",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baodauthau/category/date
            newspaper_name = "baodauthau"
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
            title_tag = soup.find('h1',class_='article__title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("div", class_="article__sapo")
            if desc_tag:
                # Ưu tiên thẻ <p> nếu có
                p_tag = desc_tag.find("p")
                if p_tag:
                    raw_description = p_tag.get_text(strip=True)
                else:
                    raw_description = desc_tag.get_text(strip=True)

                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None


            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("time", class_='time')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            content_div = soup.find("div", class_="article__body")
            images = content_div.find_all('img')
            # Lọc ảnh
            content_images = []
            for img in images:
                # Kiểm tra và lấy cả src và data-large-src
                for attr in ['src', 'data-src']:
                    src = img.get(attr)
                    if not src:
                        continue
                    if src.startswith("data:image"):
                        continue  # ❌ Bỏ base64
                    if any(x in src for x in ["gg-news", "zalo", "logo", "icon"]):
                        continue  # ❌ Bỏ ảnh giao diện
                    if urlparse(src).path.lower().endswith(".jpg") or urlparse(src).path.lower().endswith(".png"):
                        content_images.append(src)
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))


            # Trích xuất tác giả
            author_tag = soup.find(["a","span"], class_=["name","cms-author"])
            # author_tag = soup.find("span", class_="cms-author")
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
        '''content_image_paths = []
        for img_url in content_images:
            if img_url:
                img_path = self.download_image(img_url, title, article_type, publish_date)      
                if img_path:
                    content_image_paths.append(img_path)'''
                    
        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date) if publish_date else None,
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            # "localContentImagePaths": content_image_paths
        }

        return article_data
    def get_urls_of_type_thread(self, article_type, page_number):
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless 
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux                                                
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://baodauthau.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        seen_article_ids = set()  # set theo object id hoặc nội dung text

        last_size = 0  
        try:
            wait = WebDriverWait(driver, 10)

            while True:
                # Scroll và đợi DOM render
                driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                time.sleep(2)

                # Tìm tất cả bài viết hiện có
                articles = driver.find_elements(By.CSS_SELECTOR, "div.content-list article.story")
                new_found = 0

                for article in articles:
                    try:
                        # Lấy text hoặc ID duy nhất để tránh quét lại
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)

                        title_link = article.find_element(By.CSS_SELECTOR, "figure.story__thumb > a")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://baodauthau.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                                # print("🔗 New link:", href)
                                new_found += 1
                    except Exception:
                        continue

                if new_found == 0:
                    print("✅ Không còn bài mới sau khi cuộn/trang mới.")
                    break
                
                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.control__loadmore")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
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