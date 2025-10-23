import os
import requests
import sys
from pathlib import Path
import re

import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import Optional  


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

class TapChiThongTinVaTruyenThongCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://ictvietnam.vn/"
        self.article_type_dict = {
            0: "dien-dan/chinh-sach-va-chien-luoc",
            1: "dien-dan/y-kien-chuyen-gia",
            2: "dien-dan/xu-huong-du-bao",

            3: "make-in-viet-nam",

            4: "chuyen-doi-so/chinh-phu-so",
            5: "chuyen-doi-so/do-thi-thong-minh",
            6: "chuyen-doi-so/xa-hoi-so",

            7: "kinh-te-so/tin-tuc",
            8: "quoc-hoi-va-cu-tri/hoat-dong-cua-doan-dbqh",

            9: "hoi-dong-nhan-dan/hoi-nghi-tt-hdnd",
            10: "kinh-te-so/quan-tri",
            11: "kinh-te-so/doanh-nhan",

            12: "an-toan-thong-tin",

            13: "multimedia/video",

            14: "chuyen-dong-ict/doanh-nghiep-so",
            15: "chuyen-dong-ict/ban-tin-ict",
            16: "chuyen-dong-ict/quoc-te",

            17: "kinh-te/doanh-nghiep",
            18: "kinh-te/tai-chinh",
            19: "kinh-te/bat-dong-san",

            20: "truyen-thong/hoi-nhap",
            21: "truyen-thong/bao-chi",
            22: "truyen-thong/truyen-thong",
            23: "truyen-thong/sach-va-cuoc-song",
            24: "truyen-thong/phat-thanh-truyen-hinh",
            25: "truyen-thong/doi-song-xa-hoi",
            26: "truyen-thong/kinh-te",
            27: "truyen-thong/quoc-te",
            28: "truyen-thong/doi-song",
            29: "truyen-thong/xa-hoi",
            30: "truyen-thong/gia-dinh",
            31: "truyen-thong/the-thao",

        }

    def extract_content(self, url: str) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers)
          
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = (
                soup.find('h1', class_='c-detail-head__title') or 
                soup.find('h1', class_='sc-longform-header-title block-sc-title')
            )

            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            # desc_tag = soup.select_one("div.mota h2")
            desc_tag = (
                soup.find('p', class_='sc-longform-header-sapo') or 
                soup.find('p', class_='desc')
            )
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # if desc_tag:
            #     raw_description = desc_tag.get_text(strip=True)
            #     # Tách sau dấu "-" đầu tiên
            #     split_parts = raw_description.split("-", 1)
            #     description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            # else:
            #     description = None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = (
                soup.find('span', class_='c-detail-head__time') or 
                soup.find('span', class_='sc-longform-header-date')
            )
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.select_one("article", class_="entry-no-padding")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            # Lấy nội dung chỉ từ các thẻ <p> trong <article>
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))


            # Trích xuất tác giả
            author_box = (
                soup.find('span', class_='c-detail-head__author') or 
                soup.find('span', class_='block-sc-author')
            )
            author = author_box.get_text(strip=True).split('/')[0].strip() if author_box else None

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
        # in link lỗi
        try:
            title, description, content, publish_date, author, content_images = self.extract_content(url)
            if not title:
                print(f"⚠️ Bỏ qua bài không có tiêu đề: {url}")
                return None
        except Exception as e:
            print(f"❌ Lỗi trong quá trình phân tích HTML ở bài: {url}")
            print(f"   Chi tiết lỗi: {e}")
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://ictvietnam.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        try:
            wait = WebDriverWait(driver, 10)

            while True:
                 # Scroll và đợi DOM render
                driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                time.sleep(2)
                articles = driver.find_elements(By.CSS_SELECTOR, "ul.onecms__loading li.article__loading")
                new_found = 0
                seen_article_ids = set()  # set theo object id hoặc nội dung text

                for article in articles:
                    try:
                        # Lấy text hoặc ID duy nhất để tránh quét lại
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)

                        title_link = article.find_element(By.CSS_SELECTOR, "a")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://ictvietnam.vn/", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                                # print(" New link:", href)
                                new_found += 1
                    except Exception:
                        continue
                
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.onecms__loadmore a")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(2)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(3)

                except Exception:
                        print("✅ Không còn nút Trang sau. Dừng lại.")
                        break

        except Exception as e:
            print("⚠️ Lỗi collect links:", e)
        finally:
            driver.quit()
        print(f"📄 Tổng số bài thu thập: {len(seen_links)}")
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles