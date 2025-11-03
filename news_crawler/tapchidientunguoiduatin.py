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

class TapChiDienTuNguoiDuaTinCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://www.nguoiduatin.vn/"
        self.article_type_dict = {
            0: "toan-canh/tieu-diem",
            1: "toan-canh/chinh-sach",
            2: "toan-canh/su-kien",
            3: "toan-canh/doi-thoai",
            4: "toan-canh/the-gioi",

            5: "phap-luat/dong-chay-phap-luat",
            6: "phap-luat/goc-nhin-luat-gia",
            7: "phap-luat/ho-so-dieu-tra",
            8: "phap-luat/tieng-noi-cong-dan",
            9: "phap-luat/an-ninh-hinh-su",

            10: "kinh-te/bat-dong-san",
            11: "kinh-te/tai-chinh-ngan-hang",
            12: "kinh-te/tai-chinh-ngan-hang",
            13: "kinh-te/kinh-te-vi-mo",
            14: "kinh-te/ho-so-doanh-nghiep",
            15: "kinh-te/xu-huong-thi-truong",
            16: "kinh-te/cong-nghe",

            17: "xa-hoi/dan-sinh",
            18: "xa-hoi/giao-duc",
            19: "xa-hoi/van-hoa",
            20: "xa-hoi/moi-truong",
            21: "xa-hoi/giao-thong-do-thi",

            22: "doi-song/gia-dinh",
            23: "doi-song/suc-khoe",
            24: "doi-song/can-biet",
            25: "doi-song/cong-dong-mang",

            26: "da-chieu/quan-diem",
            27: "da-chieu/xi-nhan-trai-phai",
            28: "da-chieu/ban-doc-viet",
            
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
            title = soup.find("h1", class_="title").text.strip()


            # Lấy description
            desc_tag = soup.find("h2", class_="text-title")
            description = desc_tag.get_text(strip=True) if desc_tag else None
            
            date_tag = soup.select_one("div.top span.time")
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_images = []
            content_div = soup.find("div", class_="detail-content afcbc-body")

            if content_div:
                images = content_div.find_all('img')
                for img in images:
                    src = img.get("src")
                    if src and not src.startswith("data:image") and src.endswith((".jpg", ".jpeg", ".png")):
                        content_images.append(src)
        
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = ""
            content_div = soup.find("div", class_="detail-content afcbc-body", attrs={"data-role": "content"})

            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(
                    p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                )
            
            # Bước 1: ưu tiên tìm theo class name nếu có
            author_box = soup.find('p', class_="name")
            author = author_box.get_text(strip=True).rstrip('-').strip() if author_box else None

            # Bước 2: tìm theo style justify và thẻ <b>
            if not author:
                author_paragraphs = soup.find_all('p', style=lambda x: x and "text-align: justify" in x)
                for p in author_paragraphs:
                    b_tag = p.find("b")
                    if b_tag:
                        author_candidate = b_tag.get_text(strip=True)
                        if author_candidate:
                            author = author_candidate
                            break

            # Bước 3: tìm theo thẻ <strong> trong <p> (trường hợp mới)
            if not author:
                strong_paragraphs = soup.find_all('p')
                for p in strong_paragraphs:
                    strong_tag = p.find("strong")
                    if strong_tag:
                        author_candidate = strong_tag.get_text(strip=True)
                        if author_candidate:
                            author = author_candidate
                            break




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
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://www.nguoiduatin.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(1)
        seen_links = set()
        last_size = 0
        wait = WebDriverWait(driver, 10)
        seen_article_ids = set()  # set theo object id hoặc nội dung text

        try:
            while True:
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
                                href = urljoin("https://www.nguoiduatin.vn", href)
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
                    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.views")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click nút 'Trang sau'")
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