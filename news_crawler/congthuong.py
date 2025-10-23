import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
import re

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

class CongThuongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://congthuong.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "cong-thuong-24h",
            2: "quan-ly-thi-truong",
            3: "thuong-mai",
            4: "cong-nghiep",
            5: "phap-luat-dieu-tra",
            6: "thi-truong",
            7: "nang-luong",
            8: "hoi-nhap-quoc-te",
            9: "tieu-dung-khuyen-mai",
            10: "ban-doc",
            11: "tai-chinh",
            12: "bat-dong-san",
            13: "doanh-nghiep-doanh-nhan",
            14: "xa-hoi",
            15: "van-hoa-giai-tri",
            16: "dia-phuong",
            17: "dan-toc-thieu-so-mien-nui",
            18: "tu-hao-hang-viet",
            19: "vong-xoay-khoi-nghiep",
            20: "xe-va-cong-nghe"
        }   

    def extract_content(self, url: str) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.find('h1', class_='article-detail-title f5')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find('div', class_='article-detail-desc')
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find('span', class_='format_time')
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            article_body = soup.find("div", id="articleBody", itemprop="articleBody")
            # Lấy text nội dung từ các thẻ <p> hoặc <strong>
            paragraphs = article_body.find_all(["p", "strong"])
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            content_images = [img["src"] for img in article_body.find_all("img") if img.get("src")]

            author = None
            author_tag = soup.find("div", class_="article-detail-author clearfix")
            author = author_tag.get_text(strip=True) if author_tag else None

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
        page_number = (page_number - 1) * 20
        page_url = f"https://congthuong.vn/{article_type}?s_cond=&BRSR={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        urls = []

        # Tìm tất cả các thẻ div có class "article" trong "bx-cat-content"
        container = soup.find('div', class_='bx-cat-content fw lt mb2')
        url_elements = container.select('h3.article-title a')
        if(len(url_elements) == 0):
            return []
        if container:
            # Chỉ tìm các <a> trong <h3 class="article-title">
            titles = url_elements
            for a in titles:
                href = a.get('href')
                if href and href.startswith('http'):
                    urls.append(href)

        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles
