import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime
import paramiko
from io import BytesIO

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

class TapChiDienTuCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietq.vn/"
        self.article_type_dict = {
            0: "tin-trong-nuoc-sub9",
            1: "quoc-te-sub10",
            2: "van-de-sub11",
            3: "tieu-chuan-chat-luong-c86",
            4: "an-toan-thuc-pham-sub12",
            5: "hang-kem-chat-luong-sub13",
            6: "phat-hien-sub34",
            7: "thi-truong-sub14",
            8: "san-pham-dich-vu-sub16",
            9: "chat-luong-vang-sub20",
            10: "dien-dan-sub71",
            11: "khoa-hoc-cong-nghe-sub6",
            12: "dau-tu-sub96",
            13: "khieu-nai-sub75",
            14: "tu-van-tieu-dung-sub15",
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

            # Trích xuất tiêu đề
            title = soup.find("h1", class_="detail-title").get_text(strip=True)

            intro_p = soup.select_one(".detail-intro .caption")
            description = intro_p.get_text(strip=True) if intro_p else None

            main_content = soup.find("div", id="main-detail")
            content_list = [p.get_text(strip=True) for p in main_content.find_all("p")] if main_content else []
            content = "\n".join(content_list)
            # Trích xuất ngày viết bài
            datetime_div = soup.find("div", class_="datetimeup")
            publish_date = datetime_div.get_text(strip=True) if datetime_div else None

            # Trích xuất tất cả các ảnh trong phần nội dung
            content_images = []
            if main_content:
                for img in main_content.find_all("img"):
                    src = img.get("src")
                    if src:
                        content_images.append(src)

            # Trích xuất tác giả
            ps = soup.find_all("p", style="text-align: right;")
            author = None
            for p in reversed(ps):  # Duyệt từ cuối lên đầu
                strong = p.find("strong")
                if strong:
                    author = strong.get_text(strip=True)
                    break

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
        page_url = f"https://vietq.vn/{article_type}/p{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        article_links = soup.find_all('a', class_='thumb300x170')

        if (len(article_links) == 0):
            return []

        results =  [a['href'] for a in article_links]

        return results

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles