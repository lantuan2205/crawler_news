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

class TapChiCongThuongCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://tapchicongthuong.vn/"
        self.article_type_dict = {
            0: "bao-ve-nen-tang-tu-tuong-cua-dang-10818",
            1: "doanh-nghiep-9",
            2: "nguoi-cong-thuong-8",
            3: "cong-nghe-14",
            4: "kinh-te-xanh-13302",
            5: "kinh-te-4",
            6: "hang-hoa-nguyen-lieu-54",
            7: "cartimes-56",
            8: "dia-phuong-8307",
            9: "chinh-sach-3",
            10: "tai-chinh-doanh-nghiep-453",
            11: "gio-thu-9-21974",
            12: "quoc-te-hoi-nhap-2",
            13: "tuyen-sinh-nganh-cong-thuong-21932",                    
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
            h1_tag = soup.select_one('h1.post-title.text-left.font-playfair')
            title = h1_tag.text.strip() if h1_tag else None

            # Lấy tên tác giả
            author_tag = soup.select_one("div.meta-info .source strong")
            author = author_tag.get_text(strip=True) if author_tag else None

            # Lấy description
            desc_tag = soup.select_one('div.sapo.title-1.mb-3')
            description = desc_tag.text.strip() if desc_tag else None
            clean_description = re.sub(r"^TCCT\s+", "", description)

            # Trích xuất ngày viết bài
            publish_date = None
            date_span = soup.select_one('div.post-meta span')
            publish_date = date_span.text.strip() if date_span else None

            content_div = soup.find("div", {"id": "post_content"})

            paragraphs = content_div.find_all(["p", "h2"])
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs)

            content_images = []
            for figure in content_div.find_all("figure"):
                img_tag = figure.find("img")
                caption_tag = figure.find("figcaption")
                if img_tag:
                    image_url = img_tag["src"]
                    content_images.append(image_url)

            return title, clean_description, content, publish_date, author, content_images

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
        page_url = f"https://tapchicongthuong.vn/hashtag/{article_type}/page-{page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_divs = soup.select('div.widget-layout-1.pt-4.mb-4, div.list-view')
        if(len(target_divs) == 0):
            return []
        urls = []
        base_url = 'https://tapchicongthuong.vn'
        # Duyệt từng vùng và lấy các <a> có href bắt đầu bằng "/"
        for div in target_divs:
            links = div.select('a[href]')
            for link in links:
                href = link['href']
                if href.startswith('/'):
                    urls.append(base_url + href)

        # Loại bỏ trùng lặp
        urls = list(dict.fromkeys(urls))

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
            base_url="https://tapchicongthuong.vn"
            # Lấy toàn bộ thẻ <a> trong vùng <div class="article list">
            for h3 in soup.select("ul.list-post h3.title a"):
                href = h3.get("href", "")
                if href and href.startswith("/"):
                    urls.add(base_url + href)

            return list(urls)
        except Exception as e:
            return []