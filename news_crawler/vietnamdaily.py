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

class VietNameDailyCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietnamdaily.kienthuc.net.vn/"
        self.article_type_dict = {
            0: "tai-chinh-ngan-hang",
            1: "bat-dong-san",
            2: "golf-doanh-nhan",
            3: "doanh-nghiep",
            4: "tin-247",
            5: "hitech-xe",
            6: "tieu-dung-ban-doc",
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
            title = soup.find('h1', class_='cms-title article-title').get_text(strip=True)
            # Lấy description
            description = soup.find('div', class_='summary cms-desc').get_text(strip=True)
            # Trích xuất ngày viết bài
            publish_date = soup.select_one('div.meta.clearfix time').get_text(strip=True)
            # Lấy nội dung text trong các thẻ <p>
            content_div = soup.find('div', id='abody', class_='cms-body clearfix')
            content = []
            content_images = []
            if content_div:
                # Lấy tất cả đoạn văn bản
                for div in content_div.find_all('div', recursive=False):
                    text = div.get_text(strip=True)
                    if text:
                        content.append(text)

                    # Tìm ảnh bên trong mỗi div
                    imgs = div.find_all('img')
                    for img in imgs:
                        src = img.get('src')
                        if src:
                            content_images.append(src)
            content = '\n'.join(content)
            # Lấy tên tác giả
            author_tag = soup.find('div', class_='author')
            author = ''
            if author_tag:
                name_span = author_tag.find('span', class_='name')
                if name_span:
                    author = name_span.get_text(strip=True)

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
        page_url = f"https://vietnamdaily.kienthuc.net.vn/{article_type}/?page={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        base_url = "https://vietnamdaily.kienthuc.net.vn"

        # Tìm section chứa danh sách bài viết
        ul_zone = soup.find('ul', class_='zone category-listing-story')
        urls = []
        if ul_zone:
            articles = ul_zone.select('article.story')
            if(len(articles) == 0):
                return []
            for article in articles:
                a_tag = article.find('a', href=True)
                if a_tag:
                    relative_url = a_tag['href']
                    full_url = base_url + relative_url
                    urls.append(full_url)


        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles