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

class BaoNhanDanCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://nhandan.vn/"
        self.article_type_dict = {
            0: "xa-luan",
            1: "binh-luan-phe-phan",
            2: "xay-dung-dang",

            3: "chungkhoan",
            4: "thong-tin-hang-hoa",

            5: "nguoi-tot-viec-tot",

            6: "bhxh-va-cuoc-song",
            7: "vanhoa",

            8: "phapluat",

            9: "du-lich",

            10: "binh-luan-quoc-te",
            11: "asean",
            12: "chau-phi",
            13: "chau-my",
            14: "chau-au",
            15: "trung-dong",
            16: "chau-a-tbd",

            17: "thethao",

            18: "giaoduc",

            19: "goc-tu-van",

            20: "khoahoc-congnghe",

            21: "moi-truong",

            22: "duong-day-nong",
            23: "dieu-tra-qua-thu-ban-doc",

            24: "factcheck",
            25: "trung-du-va-mien-nui-bac-bo",

            26: "dong-bang-song-hong",
            27: "trang-bac-trung-bo-va-duyen-hai-trung-bo",
            28: "trang-tay-nguyen",

            29: "trang-dong-bang-song-cuu-long",
            30: "tphcm",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baonhandan/category/date
            newspaper_name = "baonhandan"
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
            title_tag = soup.find('h1', class_='article__title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            # desc_tag = soup.select_one("div.mota h2")
            desc_tag = soup.find("div",class_= "article__sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách sau dấu "-" đầu tiên
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("div.article__meta time.time")
            if date_tag:
                raw_text = date_tag.get_text(strip=True)  # VD: "Thứ Ba, ngày 14/01/2025 - 06:01"
                
                # Regex tách phần ngày và giờ
                match = re.search(r"ngày (\d{2}/\d{2}/\d{4}) - (\d{2}:\d{2})", raw_text)
                if match:
                    publish_date = f"{match.group(1)} {match.group(2)}"


            # Lấy tất cả các ảnh trong phần tử này
            # content_div = soup.find("div", class_="main-col")
            # images = content_div.find_all('img')
            # content_images = [img['src'] for img in images if img.get('src')]
            # if not content_div:
            #     return [], []
            content_div = soup.find("div", class_="main-col")
            

            images = content_div.find_all('img')

            # Bỏ ảnh base64 dạng "data:image/..."
            content_images = [
                img['src'] for img in images
                if img.get('src') and not img['src'].strip().startswith("data:image")
            ]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            # Lấy nội dung chỉ từ các thẻ <p> trong <article>
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))


            # Trích xuất tác giả
            author_box = soup.find('p', class_='name')
            author = author_box.get_text(strip=True).split('/')[0].strip() if author_box else None

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
        page_url = f"https://nhandan.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        seen_article_ids = set()  # set theo object id hoặc nội dung text

        try:
            wait = WebDriverWait(driver, 10)

            while True:
                articles = driver.find_elements(By.CSS_SELECTOR, "div.content-list article.story")
                new_found = 0

                for article in articles:
                    try:
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)
                        title_link = article.find_element(By.CSS_SELECTOR, "a.cms-link")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://nhandan.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                                new_found += 1

                    except Exception:
                        continue
                if new_found == 0:
                    print("✅ Không còn bài mới sau khi cuộn/trang mới.")
                    break

                # try:
                #         next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.see-more")))
                #         driver.execute_script("arguments[0].scrollIntoView();", next_button)
                #         time.sleep(1)
                #         driver.execute_script("arguments[0].click();", next_button)
                #         print("➡️ Đã click nút 'Trang sau'")
                #         time.sleep(3)

                # except Exception:
                #         print("✅ Không còn nút Trang sau. Dừng lại.")
                #         break

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
