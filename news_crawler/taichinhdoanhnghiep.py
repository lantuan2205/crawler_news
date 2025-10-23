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

class TaiChinhDoanhNghiepCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://taichinhdoanhnghiep.net.vn/"
        self.article_type_dict = {
            0: "tin-tuc",
            1: "thue-cuoc-song",
            2: "tai-chinh",
            3: "bat-dong-san",
            4: "chung-khoan",
            5: "thi-truong",
            6: "phap-luat-tai-chinh",
            7: "tai-chinh-quoc-te"
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
            article = soup.find("article", class_="article")
            h1_tag = article.find("h1") if article else None
            title = h1_tag.get_text(strip=True) if h1_tag else None
            # Trích xuất ngày viết bài
            time_span = soup.find("span", class_="bx-time lt")
            publish_date = time_span.get_text(strip=True) if time_span else None
            # Lấy nội dung text trong các thẻ <p>
            content_div = soup.find("div", id="noidung")
            raw_description = content_div.find("h2").get_text(strip=True)
            description = re.sub(r'\s+', ' ', raw_description).strip()
            paragraphs = content_div.find_all("p")
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs)

            content_images = []
            content_images = [img['src'] for img in content_div.find_all("img") if img.get("src")]

            # Lấy tên tác giả
            cite_tag = soup.find('blockquote', class_='blockquote-reverse').find('cite')
            author = cite_tag.get_text(strip=True) if cite_tag else None

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
        if( page_number == 1):
            page_url = f"https://taichinhdoanhnghiep.net.vn/{article_type}/"
        else:
            page_url = f"https://taichinhdoanhnghiep.net.vn/{article_type}/p{page_number}"

        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")

        # Tìm div có id là dle-content
        content_div = soup.find("div", id="dle-content")
        article_elements = content_div.find_all("a", class_="article-title")
        if(len(article_elements) == 0 ):
            return []

        # Tìm tất cả các thẻ <a> trong các thẻ <article> bên trong div đó
        urls = [a['href'] for a in article_elements]
        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles