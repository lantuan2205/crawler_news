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

class BaoDienTuDanVietCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://danviet.vn/"
        self.article_type_dict = {
            5: "kinh-da-trong/",
            6: "dv-chinh-tri/",
            7: "ho-so-tu-lieu-doc-quyen/",
            8: "xa-hoi/",
            9: "ky-nguyen-vuon-minh/",

            0: "doc-la-the-gioi/",
            1: "cong-dong-viet/",
            2: "diem-nong/",
            3: "goc-chuyen-gia/",
            4: "vu-khi-quan-su/",

            10: "tin-nong-nghiep/",
            11: "muon-cach-lam-giau/",
            12: "giai-bao-chi-nong-nghiep-nong-dan-nong-thon/",
            13: "ngon-sach-la/",
            14: "kinh-te-nong-nghiep/",
            15: "nong-thon-moi/",
            16: "khuyen-nong/",
            17: "moi-truong-xanh/",

            18: "dv-nong-dan-gui-tam-tu-toi-thu-tuong/",
            19: "tin-hoat-dong-hoi/",
            20: "lang-nghe-nong-dan/",
            21: "doi-song-nong-thon/",
            22: "chan-dung-can-bo-hoi/",
            23: "kinh-te-tap-the/",
            24: "thi-viet-tim-hieu-truyen-thong-95-nam-hoi-nong-dan-viet-nam/",

            25: "dv-dau-tu-tai-chinh/",
            26: "dv-thi-truong/",
            27: "nang-luong-moi/",
            28: "dv-giao-thong-xay-dung/",
            29: "dv-tin-tuc/",

            30: "chinh-sach/",
            31: "dia-oc/",
            32: "du-an/",
            33: "kien-truc/",
            34: "vat-lieu-moi/",

            35: "bong-chuyen/",
            36: "fifa-club-world-cup-2025/",
            37: "bong-da/",
            38: "chuyen-nhuong/",
            39: "ben-le/",
            40: "cac-mon-khac/",
            41: "phia-sau-san-co/",
            42: "dv-tin-tuc/",

            43: "phap-dinh/",
            44: "an-ninh-trat-tu/",

            45: "chuyen-cua-sao/",
            46: "thoi-trang/",
            47: "phim-anh/",
            48: "am-nhac/",
            49: "doi-song-van-hoa/",

            50: "y-te/",
            51: "giao-duc/",
            52: "lao-dong-viec-lam/",
            53: "nhip-song-tre/",
            54: "du-lich/",

            55: "y-kien-ban-doc/",
            56: "duong-day-nong/",
            57: "giai-dap-phap-luat/",
            58: "dieu-tra/",
            59: "cai-chinh/",
            60: "ha-noi-hom-nay/",
            61: "nhan-ai/",

            62: "dan-sinh/",
            63: "kinh-doanh/",
            64: "song-vui/",

            65: "dv-gia-dinh/",

            66: "danh-nhan-lich-su/",
            67: "bi-an-khoa-hoc/",
            68: "quan-su/",
            69: "tham-cung-bi-su/",

            70: "giam-ngheo-thong-tin/",
            71: "giam-ngheo-da-chieu/",
            72: "day-nghe-viec-lam/",

            73: "nhip-song-nong-thon-moi/",
            74: "nong-dan-moi/",
            75: "ve-lang/",
            76: "ky-uc-lang/",

            77: "bao-ve-nen-tang-tu-tuong-cua-dang/",
            78: "dv-doanh-nghiep/",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: baodientudanviet/category/date
            newspaper_name = "baodientudanviet"
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
            title_tag = soup.find('h1', class_='detail-title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("div", attrs={"data-role": "sapo"})
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None     

            # Trích xuất ngày viết bài

            date_tag = soup.find("span", attrs={"data-role": "publishdate"})
            if date_tag:
                full_text = date_tag.get_text(separator=" ", strip=True)

                # Dùng regex để trích xuất ngày và giờ
                match = re.search(r'(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})', full_text)
                if match:
                    date_part, time_part = match.groups()
                    publish_date = f"{date_part} {time_part}"
                else:
                    publish_date = None  # fallback nếu không tìm thấy
            else:
                publish_date = None


                
            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", id="explus-editor")
            content_images = []
            if content_div:
                # 2. Lấy toàn bộ ảnh <img> trong content_div
                images = content_div.find_all("img")

                for img in images:
                    # 3. Kiểm tra ảnh này có nằm trong div bị loại trừ không
                    parent_div = img.find_parent("div", class_="VCSortableInPreviewMode alignCenter type-6")
                    if not parent_div:
                        img_url = img.get("src")
                        if img_url:
                            content_images.append(img_url)

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            # content_div = soup.find("div", class_="detail-content", attrs={"data-role": "content"})
            content = ""
            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                
            # Trích xuất tác giả
            author_tag = soup.find("span", class_="anots")
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
        page_url = f"https://danviet.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)

        seen_links = set()
        wait = WebDriverWait(driver, 10)

        try:
            while True:
                # Lưu số lượng link trước khi quét
                previous_count = len(seen_links)

                # Thu thập link bài viết mới
                articles = driver.find_elements(By.CSS_SELECTOR, "div.home-articles div.home-article")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.CSS_SELECTOR, "h3.article-heading > a")
                        href = a_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://danviet.vn", href)
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
                    next_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.readmore")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(2)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'Xem thêm'")
                    time.sleep(3)
                except Exception as e:
                    print("❌ Không tìm thấy hoặc không click được nút 'Xem thêm':", e)
                    break
        finally:
            driver.quit()

        print(f"📄 Tổng số link thu thập được: {len(seen_links)}")
        return seen_links

    def get_all_articles(self):
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles