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

class DangCongSanCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://dangcongsan.vn/"
        self.article_type_dict = {
            0: "Tinhoatdong",
            # 1: "XaydungDang",
            # 2: "Vandequantam",
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
            title = soup.find('h1', id='contenttitle').get_text()
            # Lấy description
            description = soup.find('div', id='description').get_text(strip=True)
            # Trích xuất ngày viết bài
            publish_date = soup.find('div', id='ngaytao').get_text(strip=True)
            # Lấy nội dung text trong các thẻ <p>
            content_div = soup.find('div', class_='noidungtt')
            content = []
            for p in content_div.find_all('p'):
                text = p.get_text(strip=True)
                if text:
                    content.append(text)
            content = '\n\n'.join(content)

            # Lấy tên tác giả
            author = None
            tacgia_text = soup.find('b', id='tacgia').get_text(strip=True)

            # Loại bỏ "Theo " nếu có
            if tacgia_text.lower().startswith("theo "):
                author = tacgia_text[5:]
            else:
                author = tacgia_text

            content_images = []
            content_images = [
                img['src'] for img in content_div.select('img.imgtelerik')
                if img.get('src')
            ]


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
        page_url = f"https://dangcongsan.vn/noidung/tintuc/Lists/{article_type}/View.aspx?Page={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        container = soup.find('div', id='KhuVuc_3')

        # Tìm tất cả thẻ a bên trong
        links = container.find_all('a', href=True)
        if(len(links) == 0):
            return []
        # Lấy URL đầy đủ
        base_url = 'https://dangcongsan.vn'
        urls = []
        urls = [base_url + a['href'] for a in links]

        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles
    


    def get_all_articles_by_keyword(self, page_url):
        print(f"page_url: {page_url}")

        try:
            content = requests.get(page_url, headers=headers, timeout=10).content
            sleep_time = random.uniform(1, 2)
            time.sleep(sleep_time)
            soup = BeautifulSoup(content, "html.parser")
            urls = set()
            domain = "https://dangcongsan.vn"

            for a in soup.select('div.search-byType a.item-title'):
                href = a.get('href', '').strip()
                # Bỏ qua nếu là chuyên mục hoặc rỗng
                if href and href != '#' and not href.startswith('/tin-tuc.htm'):
                    if href.startswith('/'):
                        href = domain + href
                    urls.add(href)

            return list(urls)
        except Exception as e:
            return []



