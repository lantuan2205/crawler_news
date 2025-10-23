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
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class TapChiDoanhNghiepVaHoiNhapCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://doanhnghiephoinhap.vn/"
        self.article_type_dict = {
            0: "hoat-dong-hoi",
            1: "thoi-cuoc",

            2: "kinh-doanh",

            3: "thuong-hieu",
            4: "doanh-nghiep-doanh-nhan",
            5: "bat-dong-san",
            6: "thi-truong",

            7: "tai-chinh",
            8: "doanh-nhan-toan-cau",
            9: "khat-vong-viet-nam",

            10: "goc-nhin-chuyen-gia",
            11: "kinh-te-so",

            12: "phap-luat",
            13: "loi-song",
            14: "nghien-cuu-du-lieu",
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
            title_tag = soup.find('h1', class_='detail-title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find('div',class_='detail-desc')
            description = desc_tag.get_text(strip=True) if desc_tag else None


            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_='format_time')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="__MASTERCMS_CONTENT")
            content_images = []

            if not content_div:
                return [], []

            # Tìm toàn bộ table cần loại bỏ
            tables_to_exclude = content_div.find_all("table", class_="__mb_article_in_image")

            # Lấy tất cả ảnh
            images = content_div.find_all('img')

            for img in images:
                src = img.get('src')
                if not src:
                    continue

                # Kiểm tra ảnh này có thuộc table bị loại bỏ không
                in_excluded_table = any(table in img.parents for table in tables_to_exclude)

                if not in_excluded_table:
                    content_images.append(src)

            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            # Lấy nội dung chỉ từ các thẻ <p> trong <article>
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            author = None
            # Trường hợp 1
            author_tag = soup.find("div", class_="text-right font-weight-bold no-hidden")
            if author_tag:
                author = author_tag.get_text(strip=True).split('/')[0].strip()

            # Trường hợp 2
            if not author:
                author_tag = soup.find("span", class_="link-source-text-name")
                if author_tag:
                    author = author_tag.get_text(strip=True).split('/')[0].strip()

            # Trường hợp 3: p align right chứa strong
            if not author:
                right_aligned_p = soup.find("p", attrs={"align": "right"})
                if right_aligned_p:
                    strong_tag = right_aligned_p.find("strong")
                    if strong_tag:
                        author = strong_tag.get_text(strip=True)

            # Trường hợp 5: p chứa b (hoặc font > b), lấy b cuối cùng
            if not author:
                p_tags = soup.find_all("p")
                for p in p_tags[::-1]:  # duyệt ngược từ dưới lên để ưu tiên lấy b cuối cùng
                    b_tags = p.find_all("b")
                    if b_tags:
                        author = b_tags[-1].get_text(strip=True)
                        break

                if not author:
                    font_tags = soup.find_all("font")
                    for font in font_tags[::-1]:
                        b_tags = font.find_all("b")
                        if b_tags:
                            author = b_tags[-1].get_text(strip=True)
                            break

            # Nếu vẫn không có thì None
            if not author:
                author = None



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
       
        page_number = (page_number - 1) * 20
        page_url = f"https://doanhnghiephoinhap.vn/{article_type}&s_cond=&BRSR={page_number}"
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            time.sleep(3)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"❌ Lỗi khi tải {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_div = soup.find("div", class_="box-list")

        urls = []
        if target_div:
            a_tags = target_div.find_all("h3", class_="article-title")
            if(len(a_tags) == 0):
                return []
            for a_tag in a_tags:
                tag = a_tag.find("a")
                if tag and tag.get("href"):
                    urls.append(tag["href"])

        return urls
    def get_all_articles(self, category):
        
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles