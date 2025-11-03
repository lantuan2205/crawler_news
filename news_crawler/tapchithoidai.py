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

class TapChiThoiDaiCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thoidai.com.vn/"
        self.article_type_dict = {
           0: "huu-nghi/bon-phuong-ket-ban",
            1: "huu-nghi/chan-dung-be-ban",
            2: "huu-nghi/than-gui-viet-nam",

            3: "viet-kieu/tam-long-kieu-bao",
            4: "viet-kieu/tu-hao-viet-nam",
            5: "viet-kieu/cam-nang-ve-nuoc",
            6: "viet-kieu/nhip-song-cong-dong",
             7: "viet-kieu/thu-xa-que",
            8: "viet-kieu/hoc-tieng-viet",

            9: "chuyen-ngoai-giao/doi-song-doi-ngoai",
            10: "chuyen-ngoai-giao/giai-thoai",
            11: "chuyen-ngoai-giao/choi-voi-nguoi",

            12: "nhan-quyen-goc-nhin-thoi-dai/tinh-doi-nghia-dao",
            13: "nhan-quyen-goc-nhin-thoi-dai/chuyen-de",
            14: "nhan-quyen-goc-nhin-thoi-dai/duong-ve-tinh-thien",
            15: "nhan-quyen-goc-nhin-thoi-dai/nhip-song-qua-anh",
            16: "nhan-quyen-goc-nhin-thoi-dai/cam-nang",

            17: "gia-dinh-viet/to-am",
            18: "gia-dinh-viet/hon-nuoc",
            19: "gia-dinh-viet/nho-lang",
            20: "gia-dinh-viet/tap-tuc",

            21: "quoc-te/nhip-song",
            22: "quoc-te/van-hoa-van-minh",
            23: "quoc-te/goc-nhin-cgtn",

            24: "viet-nam-hom-nay/ha-noi-ngay-nay",

            25: "bo-coi-bien-dao/mien-dat-con-nguoi",
            26: "bo-coi-bien-dao/cuoc-song-vung-bien",
            27: "bo-coi-bien-dao/nhip-song-bien-dao",
            28: "bo-coi-bien-dao/lich-su-chu-quyen",
            29: "bo-coi-bien-dao/giao-luu-huu-nghi",

        }

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
            publish_date = None
            date_tag = soup.find("span", class_='article-detail-date')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            content_div = soup.find("div", class_="__MASTERCMS_CONTENT")
            if not content_div:
                if "pdf" in url or "docs" in url or "paper" in url or not "html" in response.headers.get("Content-Type", ""):
                    print(f"⚠️ Bỏ qua file không phải HTML: {url}")
                    return None, None, None, None, None, []

            # Tìm tất cả table tpl_CMS_ARTICLE_EMBED
            excluded_tables = content_div.find_all("table", class_="tpl_CMS_ARTICLE_EMBED")

            # Tạo 1 set chứa các image cần loại bỏ
            excluded_imgs = set()
            for table in excluded_tables:
                for img in table.find_all("img"):
                    if img.get("src"):
                        excluded_imgs.add(img["src"])

            # Tìm toàn bộ img trong content_div nhưng chỉ lấy các ảnh không nằm trong table loại bỏ
            images = content_div.find_all('img')
            content_images = [
                img['src'] for img in images if img.get('src') and img['src'] not in excluded_imgs
            ]

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)

            # Trích xuất tác giả
            author_box = soup.find('h2', class_='author-title')
            author_tag = author_box.find('a')
            author = author_tag.get_text(strip=True).split('(')[0].strip() if author_tag else None

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
        """" Get URLs of articles in a specific type on a given page """
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(options=chrome_options)
        page_number = (page_number - 1) * 16

        page_url = f"https://thoidai.com.vn/{article_type}&s_cond=&BRSR={page_number}"
        driver.get(page_url)
        time.sleep(1)
        seen_links = set()
        last_size = 0
        first_time = True

        try:
            wait = WebDriverWait(driver, 10)

            while True:
                articles = driver.find_elements(By.CSS_SELECTOR, "div._BX_LISTING div.article")

                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "a")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://thoidai.com.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass

                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                    paging_buttons = wait.until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.btn-viewmore a"))
                    )

                    if not paging_buttons:
                        print("✅ Không tìm thấy paging buttons. Dừng lại.")
                        break

                    if first_time:
                        next_button = paging_buttons[0]  # Lần đầu click nút đầu tiên
                        first_time = False
                    else:
                        if len(paging_buttons) > 1:
                            next_button = paging_buttons[1]  # Các lần sau click nút thứ 2
                        else:
                            print("✅ Không còn nút Trang sau. Dừng lại.")
                            break

                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click nút Trang sau")
                    time.sleep(1)

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

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles
