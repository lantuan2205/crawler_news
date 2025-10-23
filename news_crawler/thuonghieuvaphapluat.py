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

class ThuongHieuPhapLuatCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thuonghieuvaphapluat.vn/"
        self.article_type_dict = {
            0: "dien-dan-thuong-hieu",
            1: "doi-song-xa-hoi",
            2: "thuong-hieu-va-hoi-nhap",
            3: "phap-luat",
            4: "cong-nghe",
            5: "van-hoa",
            6: "nhip-cau-nhan-ai",                                   
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

            title_tag = soup.find('h1', class_='title_detail_news')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find('h2', class_='sapo_detail')
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find('span', class_='time_detail_news')
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            content_div = soup.find('div', id='cotent_detail')

            paragraphs = content_div.find_all('p')
            content = ''
            for p in paragraphs:
                if not p.get_text(strip=True).startswith('Văn Nam'):
                    content += p.get_text(strip=True) + '\n'

            author_tag = content_div.find('p', style=lambda s: s and 'float: right' in s)
            author = author_tag.get_text(strip=True) if author_tag else None

            content_images = [img['src'] for img in content_div.find_all('img') if img.has_attr('src')]

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
        page_url = f"https://thuonghieuvaphapluat.vn/{article_type}/p{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")

        ul = soup.find('ul', class_='list_news_topcate')
        urls = ul.find_all('a', class_='thumb160x120 thumbblock thumb169_notwith fl')
        if(len(urls) == 0 ):
            return []
        links = [a['href'] for a in urls]

        return links

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
            # Lấy toàn bộ thẻ <a> trong vùng <div class="article list">
            for a in soup.select('ul.list_news_topcate li.pkg div.info_cate a.fontbold'):
                href = a.get('href')
                if href:
                    urls.add(href)
            return list(urls)
        except Exception as e:
            return []