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

class KienThucCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://kienthuc.net.vn/"
        self.article_type_dict = {
            0: "tuyen-sinh",
            1: "doc-30s",
            2: "soi-xet",
            3: "song-4-mau",
            4: "hoi-dap",
            5: "nguoi-tot-viec-tot",
            6: "cai-chinh-xin-loi",
            7: "tham-cung",
            8: "di-san",
            9: "ta-tay",
            10: "giai-ma",
            11: "phong-thuy",
            12: "tri-thuc-viet-toan-cau",
            13: "thien",
            14: "khoa-hoc",
            15: "cong-nghe",
            16: "tien-vang",
            17: "nha-dat",
            18: "doanh-nhan",
            19: "tieu-dung",
            20: "hang-hot",

            21: "tin-tuc-quan-su",
            22: "vu-khi",
            23: "quan-doi",
            24: "quan-su-viet-nam",

            25: "the-gioi-24h",
            26: "nong-sau",
            27: "ho-so",
            28: "doi-song-the-gioi",

            29: "xe",
            30: "phu-kien-xe",
            31: "dan-choi-xe",

            32: "doi-song",
            33: "lam-dep-giam-can",
            34: "me-be",
            35: "an-ngon",
            36: "dinh-duong-thuoc",
            37: "yeu-tam",

            38: "chat-sao",
            39: "showbiz",
            40: "showbiz-ngoai",
            41: "phong-cach-sao",
            42: "phim-nhac",
            43: "nhip-song",
            
            44: "sot-mang",
            45: "yeu-online",
            46: "the-thao",
            47: "choi-phuot",
            48: "ban-doc-dieu-tra",
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
            title = soup.find('h1', class_='cms-title').get_text()
            # Lấy description
            description = soup.find('h2', class_='sapo cms-desc').text.strip()
            # Trích xuất ngày viết bài
            publish_date = soup.find('time').text.strip()
            # Lấy nội dung text trong các thẻ <p>
            body = soup.find('div', id='abody')
            # Lấy content text (giữ định dạng đoạn văn)
            content = []
            if body:
                for tag in body.find_all(['p', 'div'], style=lambda x: x and 'text-align: justify' in x):
                    content.append(tag.get_text(strip=True))


            content = '\n\n'.join(content)
            # Lấy ảnh
            content_images = [img['src'] for img in body.find_all('img') if img.get('src')]

            # Lấy tên tác giả
            author = soup.find('span', class_='name').text.strip()

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
        page_url = f"https://kienthuc.net.vn/{article_type}/?page={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        base_url = "https://kienthuc.net.vn"

        # Tìm section chứa danh sách bài viết
        section = soup.select_one('section.cat-listnews.hzol-clear')

        # Tìm tất cả các thẻ <a> trong <h2 class="title">
        urls = []
        if section:
            articles = section.select('h2.title a')
            for a in articles:
                href = a.get('href')
                if href and href.startswith('/'):
                    urls.append(base_url + href)

        return urls

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles