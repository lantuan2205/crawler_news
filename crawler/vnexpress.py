import json
import requests
import sys
import time
import random
from pathlib import Path

from bs4 import BeautifulSoup

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VNExpressCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.article_type_dict = {
            0: "thoi-su",
            # 1: "the-gioi",
            # 2: "kinh-doanh",
            # 3: "cong-nghe",
            # 4: "khoa-hoc",
            # 5: "video",
            # 6: "podcasts",
            # 7: "goc-nhin",
            # 8: "bat-dong-san",
            # 9: "suc-khoe",
            # 10: "the-thao",
            # 11: "giai-tri",
            # 12: "phap-luat",
            # 13: "giao-duc",
            # 14: "doi-song",
            # 15: "xe",
            # 16: "du-lich",
            # 17: "y-kien",
            # 18: "tam-su",
        }

    def extract_content(self, url: str) -> tuple:
        content = requests.get(url, headers=headers).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")

        title = soup.find("h1", class_="title-detail") 
        if title == None:
            return None, None, None
        title = title.text

        # some sport news have location-stamp child tag inside description tag
        description = (get_text_from_tag(p) for p in soup.find("p", class_="description").contents)
        paragraphs = (get_text_from_tag(p) for p in soup.find_all("p", class_="Normal"))

        # Lấy ngày đăng bài
        time_element = soup.find("span", class_="date")
        published_date = time_element.text.strip() if time_element else None

        # Lấy ảnh đại diện
        image_element = soup.find("meta", property="og:image")
        image_url = image_element["content"] if image_element else None

        comments = []
        comment_section = soup.find("div", class_="box_comment")  # Kiểm tra class thật của VnExpress

        if comment_section:
            comment_tags = comment_section.find_all("div", class_="comment_content")  # Kiểm tra thẻ chứa nội dung bình luận
            comments = [c.text.strip() for c in comment_tags]
        return title, description, paragraphs, published_date, image_url, comments

    def write_content(self, url: str) -> bool:
        title, description, paragraphs, published_date, image_url, comments = self.extract_content(url)
                    
        if title == None:
            return False

        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": published_date,
            "title": title,
            "imageUrl": image_url,
            "description": " ".join(list(description)),
            "content": ",".join(list(paragraphs)),
            "comments": list(comments) if comments else [""]
        }

        return article_data

    def get_urls_of_type_thread(self, article_type, page_number):
        page_url = f"https://vnexpress.net/{article_type}-p{page_number}"
        content = requests.get(page_url, headers=headers).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")
        titles = soup.find_all(class_="title-news")

        if (len(titles) == 0):
            self.logger.info(f"Couldn't find any news in {page_url} \nMaybe you sent too many requests, try using less workers")

        articles_urls = list()

        for title in titles:
            link = title.find_all("a")[0]
            articles_urls.append(link.get("href"))
    
        return articles_urls

    def get_all_articles(self, max_pages):
        """Lấy tất cả bài báo từ các danh mục trên VNExpress."""
        all_articles = []
        
        for category in self.article_type_dict.values():
            for page in range(1, max_pages + 1):
                urls = self.get_urls_of_type_thread(category, page)
                all_articles.extend(urls)
        
        return all_articles