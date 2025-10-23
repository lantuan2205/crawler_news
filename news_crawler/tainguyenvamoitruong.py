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

class TaiNguyenVaMoiTruongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://www.tainguyenvamoitruong.vn/"
        self.article_type_dict = {
            0: "tin-tuc-id12",
            1: "nong-nghiep-id159",
            2: "tai-nguyen-id14",
            3: "moi-truong-id15",
            4: "khoa-hoc-id110",
            5: "chinh-sach-id17",
            7: "dien-dan-id13",
            8: "the-gioi-id19",
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
            title = soup.find("h2", class_="headingDetail").text.strip()
            # Lấy description
            p = soup.find("p", class_="descDetail")
            if p:
                # Loại bỏ thẻ span (như <span class="tnmt">TN&MT</span>)
                for span in p.find_all("span"):
                    span.decompose()
                description = p.get_text(strip=True)

            # Trích xuất ngày viết bài
            publish_date = soup.find("span", class_="time icon-time").text.strip()

            html_content = soup.find('div', class_='html-content')

            # Lấy nội dung text trong các thẻ <p>
            paragraphs = html_content.find_all('p') if html_content else []
            content = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            # Lấy tên tác giả
            author = None
            for p in reversed(paragraphs):
                if p.get('style') and 'text-align: right' in p['style']:
                    author = p.get_text(strip=True)
                    break
            base_url = "https://www.tainguyenvamoitruong.vn"
            content_images = []
            if html_content:
                for img in html_content.find_all('img'):
                    src = img.get('src')
                    if src:
                        full_src = urljoin(base_url, src)
                        content_images.append(full_src)


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
        page_url = f"https://www.tainguyenvamoitruong.vn/{article_type}.html?page={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        base_url = "https://www.tainguyenvamoitruong.vn"
        div_elements = soup.select("div.list_news-page h3.title-24 a")

        if(len(div_elements) == 0):
            return []

        urls = []
        for h3 in soup.select("div.list_news-page h3.title-24 a"):
            href = h3.get("href")
            if href:
                full_url = base_url + href if href.startswith("/") else href
                urls.append(full_url)

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
            # Lấy toàn bộ thẻ <a> trong vùng <div class="article list">
            for h3 in soup.select('div.list_news-page h3 a'):
                href = h3.get('href', '')
                if href and href.startswith('/'):
                    urls.append('https://www.tainguyenvamoitruong.vn' + href)
                elif href.startswith('http'):
                    urls.add(href)
            return list(urls)
        except Exception as e:
            return []