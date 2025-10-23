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

class TapChiGiaoDucCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://tapchigiaoduc.edu.vn/"
        self.article_type_dict = {
            0: "215/thong-tin-khoa-hoc",
            1: "214/tin-giao-duc",
            2: "211/chinh-sach-va-thuc-tien-giao-duc",
            3: "170/thong-tin-tuyen-truyen",                                
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
            title = soup.find("h1", class_="page-title").text.strip()

            # Lấy description
            desc_tag = soup.find("div", class_="news-sapo strong")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Trích xuất ngày viết bài
            publish_date = None
            news_heading = soup.find('div', class_='news-heading')
            ul = news_heading.find('ul', class_='list-unstyled list-inline')
            date_li = ul.find('li', class_='list-inline-item')
            publish_date = date_li.get_text(strip=True) if date_li else None

            content_div = soup.find("div", class_="news-content detail", id="news-detail")
            content = content_div.get_text(separator="\n", strip=True)
            # content = "\n".join(content_text)

            content_images = [img['src'] for img in content_div.find_all("img") if img.get("src")]

            author_tag = content_div.find("p", align="right")
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
        page_url = f"https://tapchigiaoduc.edu.vn/cate/{article_type}/page/{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        row_divs = soup.find_all("div", class_="row")
        if(len(row_divs) == 0):
            return []
        urls = []

        for row in row_divs:
            # Trường hợp 1: div.img-content trong category-box2
            img_contents = row.find_all("div", class_="img-content")
            for content in img_contents:
                a_tag = content.find("h6").find("a") if content.find("h6") else None
                if a_tag and a_tag.has_attr("href"):
                    urls.append(a_tag["href"])
            
            # Trường hợp 2: div.category-box-lg
            category_lg_boxes = row.find_all("div", class_="category-box-lg")
            for box in category_lg_boxes:
                a_tag = box.find("h6").find("a") if box.find("h6") else None
                if a_tag and a_tag.has_attr("href"):
                    urls.append(a_tag["href"])
        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles