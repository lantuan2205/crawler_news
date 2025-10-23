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

class VNEconomyCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vneconomy.vn/"
        self.article_type_dict = {
            0: "tieu-diem",
            1: "dau-tu",
            2: "tai-chinh",
            3: "kinh-te-so",
            4: "kinh-te-xanh",
            5: "thi-truong",
            6: "nhip-cau-doanh-nghiep",
            7: "dia-oc",
            8: "kinh-te-the-gioi",
            9: "dan-sinh"
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
            header = soup.find('header', class_='detail__header')
            # Lấy title
            publish_date =  header.find('div', class_='detail__meta').text.strip()
            title = header.find('h1', class_='detail__title').text.strip()
            description = header.find('h2', class_='detail__summary').text.strip()
            author = header.find('div', class_='detail__author').text.strip()

            content_div = soup.find('div', class_='detail__content')

            # Lấy nội dung bài viết từ các thẻ <p>
            paragraphs = [p.get_text(strip=True) for p in content_div.find_all('p') if p.get_text(strip=True)]
            content = "\n\n".join(paragraphs)
            # Lấy danh sách ảnh
            content_images = []
            for figure in content_div.find_all('figure'):
                img = figure.find('img')
                if img:
                    src = img['src']
                    content_images.append(src)
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
        page_url = f"https://vneconomy.vn/{article_type}.htm?trang={page_number}"

        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        # Tìm thẻ div chứa danh sách bài viết
        container = soup.find('div', class_='col-12 col-lg-9 column-border')

        # Tìm tất cả các article trong div
        articles = container.find_all('article')
        if(len(articles) == 0):
            return []

        # Lấy URL từ thẻ <a> đầu tiên trong mỗi article
        base_url = 'https://vneconomy.vn'
        urls = []

        for article in articles:
            a_tag = article.find('a', href=True)
            if a_tag: 
                href = a_tag['href']
                full_url = href if href.startswith('http') else base_url + href
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
            base_url = "https://vneconomy.vn"
            for h3 in soup.select('div.contentSearch h3.story__title'):
                a_tag = h3.find('a')
                if a_tag and a_tag.get('href'):
                    href = a_tag['href']
                    if href.startswith('/'):
                        href = base_url + href
                    urls.add(href)

            return list(urls)
        except Exception as e:
            return []