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

class TapChiDienTuKinhTeChungKhoanVietNamCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://kinhtechungkhoan.vn/"
        self.article_type_dict = {
            0: "vi-mo/chu-truong-chinh-sach",
            1: "vi-mo/hoat-dong-vasb",
            2: "vi-mo/kinh-te-doi-ngoai",
            3: "vi-mo/van-ban-phap-luat",

            4: "quoc-te/tieu-diem-quoc-te",
            5: "quoc-te/the-gioi-24h",
            6: "quoc-te/bao-chi-cong-nghe",
            
            7: "bao-chi-truyen-thong/nghe-bao",
            8: "bao-chi-truyen-thong/cong-tac-hoi",

            9: "kinh-te/thi-truong-doanh-nghiep",
            10: "kinh-te/bat-dong-san",
            11: "kinh-te/kinh-te-vi-mo",
            12: "kinh-te/tu-hao-hang-vn-tinh-hoa-hang-vn",

            13: "dau-tu-tai-chinh/du-an-dau-tu",
            14: "dau-tu-tai-chinh/kinh-doanh-tai-chinh",

            15: "phap-luat/dieu-tra",
            16: "phap-luat/vu-an",

            17: "xa-hoi/giao-duc",
            18: "xa-hoi/giao-thong",
            19: "xa-hoi/suc-khoe",
            20: "xa-hoi/doi-song",

            21: "moi-truong/bien-doi-khi-hau",
            22: "moi-truong/moi-truong-va-cuoc-song",

            23: "van-hoa/giai-tri",
            24: "van-hoa/the-thao",
            25: "van-hoa/doi-song-van-hoa",
            26: "van-hoa/du-lich",

            27: "xe",
            28: "van-hoa/cau-chuyen-van-hoa",       
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
            response = requests.get(url, headers=headers)
          
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.find('h1',class_="sc-longform-header-title")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("p", class_="sc-longform-header-sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split(")", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_='sc-longform-header-date')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("article", class_="entry-no-padding")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            # content = content_div.get_text(separator="\n", strip=True)
            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            else:
                content = None
            # Tìm theo class cũ trước
            author_tag = soup.select_one("span.sc-longform-header-author")
            author = author_tag.get_text(strip=True) if author_tag else None

            # Nếu chưa có author -> fallback tìm thẻ strong cuối cùng trong article.entry.entry-no-padding
            if not author:
                article_entry = soup.find("article", class_="entry entry-no-padding")
                if article_entry:
                    strong_tags = article_entry.find_all("strong")
                    if strong_tags:
                        last_strong = strong_tags[-1]  # lấy thẻ strong cuối cùng
                        name_candidate = last_strong.get_text(strip=True).strip("()")
                        if name_candidate and len(name_candidate) >= 3:
                            author = name_candidate


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
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://kinhtechungkhoan.vn/{article_type}"
        driver.get(page_url)
        time.sleep(1)
        seen_links = set()
        wait = WebDriverWait(driver, 10)
        try: 
            # Scroll 4 lần
            for i in range(4):
                driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                time.sleep(1.5)
            while True:
                # Lưu số lượng link trước khi quét
                previous_count = len(seen_links)

                # Thu thập link bài viết mới
                articles = driver.find_elements(By.CSS_SELECTOR, "ul.onecms_loading li")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.CSS_SELECTOR, "div.b-grid__img > a")
                        href = a_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://kinhtechungkhoan.vn", href)
                            if href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        continue

                # So sánh số lượng link sau khi quét
                current_count = len(seen_links)
                new_links_found = current_count - previous_count
                # Nếu không có link mới → dừng
                if new_links_found == 0:
                    print("✅ Không còn link mới. Kết thúc.")
                    break

                # Nếu có link mới, click nút "Xem thêm"
                try:
                    next_button = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Xem thêm')]")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'Xem thêm'")
                    time.sleep(1)
                except Exception as e:
                    print("❌ Không tìm thấy hoặc không click được nút 'Xem thêm':", e)
                    break

        finally:
            driver.quit()

        print(f"📄 Tổng số link thu thập được: {len(seen_links)}")
        return seen_links
    
    def get_all_articles(self, category):
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles
