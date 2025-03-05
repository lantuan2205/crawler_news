import requests
import sys
import json
from pathlib import Path
import random
import time

from bs4 import BeautifulSoup

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VietNamNetCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietnamnet.vn"
        self.article_type_dict = {
            0: "thoi-su",
            1: "kinh-doanh",
            2: "the-thao",
            3: "van-hoa",
            4: "giai-tri",
            5: "the-gioi",
            6: "doi-song",
            7: "giao-duc",
            8: "suc-khoe",
            9: "thong-tin-truyen-thong",
            10: "phap-luat",
            11: "oto-xe-may",
            12: "bat-dong-san",
            13: "du-lich",
            14: "chinh-tri",
            15: "ban-doc",
        }   
        
    def extract_content(self, url: str) -> tuple:
        content = requests.get(url, headers=headers).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")

        title_tag = soup.find("h1", class_="content-detail-title") 
        desc_tag = soup.find("h2", class_=["content-detail-sapo", "sm-sapo-mb-0"])
        p_tag = soup.find("div", class_=["maincontent", "main-content"])

        date_tag = soup.find("div", class_="bread-crumb-detail__time")
        published_date = date_tag.text.strip() if date_tag else "Không có thông tin"

        img_tag = soup.find("img", class_="img-content")
        if not img_tag:
            img_meta = soup.find("meta", property="og:image")
            image_url = img_meta["content"] if img_meta else "Không có ảnh"
        else:
            image_url = img_tag["src"]

        comment_tags = soup.find_all("div", class_="comment-content")
        comments = [comment.text.strip() for comment in comment_tags] if comment_tags else []

        if [var for var in (title_tag, desc_tag, p_tag) if var is None]:
           return None, None, None, None, None, None
        
        title = title_tag.text
        description = (get_text_from_tag(p) for p in desc_tag.contents)
        paragraphs = (get_text_from_tag(p) for p in p_tag.find_all("p"))

        return title, description, paragraphs, published_date, image_url, comments

    def write_content(self, url: str, output_fpath: str) -> bool:
        title, description, paragraphs, published_date, image_url, comments = self.extract_content(url)
                    
        if title == None:
            return False

        article_data = {
            "url": url,
            "title": title,
            "published_date": published_date,
            "image_url": image_url,
            "description": list(description),
            "content": list(paragraphs),
            "comments": comments
        }

        with open(output_fpath, "w", encoding="utf-8") as file:
            json.dump(article_data, file, ensure_ascii=False, indent=4)

        return True
    
    def get_urls_of_type_thread(self, article_type, page_number):
        page_url = f"https://vietnamnet.vn/{article_type}-page{page_number}"
        content = requests.get(page_url, headers=headers).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")
        titles = soup.find_all(class_=["horizontalPost__main-title", "vnn-title", "title-bold"])

        if (len(titles) == 0):
            self.logger.info(f"Couldn't find any news in {page_url} \nMaybe you sent too many requests, try using less workers")
            
        articles_urls = list()

        for title in titles:
            full_url = title.find_all("a")[0].get("href")
            if self.base_url not in full_url:
                full_url = self.base_url + full_url
            articles_urls.append(full_url)
    
        return articles_urls

    def get_all_articles(self, max_pages):
        all_articles = []
        
        for category in self.article_type_dict.values():
            for page in range(1, max_pages + 1):
                urls = self.get_urls_of_type_thread(category, page)
                all_articles.extend(urls)
        
        return all_articles