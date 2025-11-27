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

class KinhTeDoUongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://kinhtedouong.vn/"
        self.article_type_dict = {
            0: "tin-tuc-su-kien",
            1: "kinh-te-tieu-dung",
            2: "doi-song",
            3: "thi-truong",
            4: "doanh-nghiep-doanh-nhan",
            5: "do-uong",
            6: "phap-luat",
            7: "khoa-giao",
        }

    def extract_profile_domain(self, url: str):
        job_id = 1
        info = {
            "name": url,
            "description": "",
            "license": None,
            "editor_in_chief": None,
            "address": None,
            "phone": None,
            "email": None,
            "infor_copyright": None,
            "jobId": job_id or str(uuid.uuid4()),
            "logo": None,
        }

        # --- Phase 1: lấy logo bằng requests ---
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # CASE 1: logo trong div.banner
            try:
                banner_div = soup.find("div", class_="banner")
                logo_img = banner_div.find("img") if banner_div else None
                if logo_img and logo_img.get("src"):
                    info["logo"] = urljoin(url, logo_img["src"])
            except:
                pass

            # CASE 2: img trong header
            if not info["logo"]:
                try:
                    header_div = soup.find(["header", "div"], 
                        id=lambda v: v and "header" in v.lower() if v else False,
                        class_=lambda v: v and "header" in v.lower() if v else False)
                    if header_div:
                        logo_img = header_div.find("img")
                        if logo_img and logo_img.get("src"):
                            info["logo"] = urljoin(url, logo_img["src"])
                except:
                    pass

            # CASE 3: img có class/id chứa chữ logo
            if not info["logo"]:
                try:
                    logo_img = soup.find("img", attrs={
                        "class": lambda v: v and "logo" in v.lower(),
                        "id": lambda v: v and "logo" in v.lower()
                    })
                    if logo_img and logo_img.get("src"):
                        info["logo"] = urljoin(url, logo_img["src"])
                except:
                    pass

            # CASE 4: favicon trong <link rel="icon">
            if not info["logo"]:
                try:
                    links = soup.find_all("link", rel=lambda v: v and "icon" in v.lower())
                    for link in links:
                        href = link.get("href")
                        if href:
                            info["logo"] = urljoin(url, href)
                            break
                except:
                    pass

            # CASE 5: og:image
            if not info["logo"]:
                try:
                    og = soup.find("meta", property="og:image")
                    if og and og.get("content"):
                        info["logo"] = urljoin(url, og["content"])
                except:
                    pass

            # CASE 6: twitter:image
            if not info["logo"]:
                try:
                    tw = soup.find("meta", property="twitter:image")
                    if tw and tw.get("content"):
                        info["logo"] = urljoin(url, tw["content"])
                except:
                    pass

        except Exception as e:
            print("⚠️ Lỗi khi lấy logo:", e)

        return (
            info.get("license", ""),
            info.get("description", ""),
            info.get("editor_in_chief", ""),
            info.get("address", ""), 
            info.get("phone", ""),
            info.get("email", ""),
            info.get("infor_copyright", ""),
            info.get("logo", "")
        )

    def extract_author(content_div):
        author = None

        # Ưu tiên 1: <p class="alignright"><strong>...</strong></p>
        tag = content_div.select_one('p.alignright strong')
        if tag:
            author = tag.get_text(strip=True)

        # Ưu tiên 2: <p class="alignright"><em>...</em></p>
        if not author:
            tag = content_div.select_one('p.alignright em')
            if tag:
                author = tag.get_text(strip=True)

        # Ưu tiên 3: <p><strong>...</strong></p> ở cuối (loại các giá trị không hợp lệ như PV)
        if not author:
            for p in reversed(content_div.find_all('p')):
                strong = p.find('strong')
                if strong:
                    text = strong.get_text(strip=True)
                    if 2 <= len(text.split()) <= 5 and text.upper() != "PV":
                        author = text
                        break

        return author
                
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
            title_post = soup.select_one('.title-post')
            title_tag = title_post.select_one('h1.title')
            title = title_tag.get_text(strip=True) if title_tag else None
            # Lấy description từ thẻ div.info-author (lấy text trước thẻ <ul>)
            description_tag = soup.select_one('h2.sum-main')
            description = description_tag.get_text(strip=True) if description_tag else None
            # Lấy ngày tháng từ <li> đầu tiên trong <ul>
            time_tag = title_post.select_one('time')
            publish_date = time_tag['datetime'] if time_tag else None

            content_div = soup.select_one('div.news-content')
            paragraphs = content_div.find_all('p')
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            # Lấy danh sách ảnh từ các thẻ <img> bên trong
            content_images = [img['src'] for img in content_div.find_all('img') if img.get('src')]

            # Tác giả nằm trong div.author-detail
            author = None
            tag = content_div.select_one('p.alignright strong')
            if tag:
                author = tag.get_text(strip=True)
            if not author:
                tag = content_div.select_one('p.alignright em')
                if tag:
                    author = tag.get_text(strip=True)
            if not author:
                for p in reversed(content_div.find_all('p')):
                    strong = p.find('strong')
                    if strong:
                        text = strong.get_text(strip=True)
                        if 2 <= len(text.split()) <= 5 and text.upper() != "PV":
                            author = text
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
        page_url = f"https://kinhtedouong.vn/{article_type}/?trang={page_number}"

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
        url_elements = soup.select(".item-post a[href]")
        if(len(url_elements) == 0):
            return []
        urls = []
        for post in url_elements:
            href = post['href']
            if href.startswith("/"):
                href = "https://kinhtedouong.vn" + href
            urls.append(href)

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
            for a in soup.select('div.item-post a.title'):
                href = a.get('href')
                if href:
                    urls.add('https://kinhtedouong.vn' + href)
            return list(urls)
        except Exception as e:
            return []