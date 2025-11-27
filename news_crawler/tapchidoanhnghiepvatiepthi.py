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

class TapChiDoanhNghiepVaTiepThiCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://doanhnghieptiepthi.vn/"
        self.article_type_dict = {
            0: "tiep-thi/tiep-thi-so",
            1: "tiep-thi/dien-dan",
            2: "tiep-thi/dia-phuong",
            3: "tiep-thi/quoc-te",

            4: "thi-truong/nhip-dap-thi-truong",
            5: "thi-truong/thi-truong-tieu-dung",
            6: "thi-truong/xuat-nhap-khau",

            7: "dau-tu-va-tiep-thi/kinh-doanh",
            8: "dau-tu-va-tiep-thi/tai-chinh-dau-tu",
            9: "dau-tu-va-tiep-thi/ngan-hang",
            10: "dau-tu-va-tiep-thi/chung-khoan",
            11: "dau-tu-va-tiep-thi/chinh-sach",

            12: "bat-dong-san-va-tiep-thi/nhip-cau-bds",
            13: "bat-dong-san-va-tiep-thi/du-an",
            14: "bat-dong-san-va-tiep-thi/tu-van",

            15: "tieu-dung-va-tiep-thi/san-pham-dich-vu",
            16: "tieu-dung-va-tiep-thi/bao-ve-nguoi-tieu-dung",
            17: "tieu-dung-va-tiep-thi/tu-van-tieu-dung",

            18: "doanh-nghiep-doanh-nhan/doanh-nghiep",
            19: "doanh-nghiep-doanh-nhan/doanh-nhan",
            20: "doanh-nghiep-doanh-nhan/khoi-nghiep",
            
            21: "ky-nguyen-vuon-minh",
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
            title_tag = soup.find('h1', class_='detail__title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("h2", class_="detail__sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None     

            # Trích xuất ngày viết bài
            date_tag = soup.find("span", attrs={"data-role": "publishdate"})
            if date_tag:
                full_text = date_tag.get_text(separator=" ", strip=True)

                # Tách phần thời gian và timezone nếu có
                parts = full_text.split(" ", 2)  # chia thành 3 phần: time, date, GMT
                if len(parts) >= 2:
                    time_part, date_part = parts[0], parts[1]
                    timezone_part = parts[2] if len(parts) == 3 else ""

                    # Đổi thứ tự thành: ngày + giờ + timezone
                    publish_date = f"{date_part} {time_part} {timezone_part}".strip()
                else:
                    publish_date = full_text  # fallback nếu không đúng định dạng
            else:
                publish_date = None

                
            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="detail__content afcbc-body")
            content_images = []
            if content_div:
                # 2. Lấy toàn bộ ảnh <img> trong content_div
                images = content_div.find_all("img")

                for img in images:
                    # 3. Kiểm tra ảnh này có nằm trong div bị loại trừ không
                    parent_div = img.find_parent("div", class_="VCSortableInPreviewMode alignCenter type-6")
                    if not parent_div:
                        img_url = img.get("src")
                        if img_url:
                            content_images.append(img_url)

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            # content_div = soup.find("div", class_="detail-content", attrs={"data-role": "content"})
            content = ""
            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                
            # Trích xuất tác giả
            author = None

            # Ưu tiên lấy theo thẻ a nếu có
            author_box = soup.find('b', class_='detail__author')
            if author_box:
                author = author_box.get_text(strip=True).rstrip('-').strip()
            if not author:
                author_tag = soup.find('p', style=lambda v: v and "text-align:right" in v.replace(" ", ""))
                if author_tag:
                    bold_tag = author_tag.find('b')
                    if bold_tag:
                        author = bold_tag.get_text(strip=True)

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
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=chrome_options)
        
        page_url = f"https://doanhnghieptiepthi.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(1)

        seen_links = set()
        wait = WebDriverWait(driver, 10)

        try:
            while True:
                # Lưu số lượng link trước khi quét
                previous_count = len(seen_links)

                # Scroll 4 lần
                for i in range(4):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(1)

                # Thu thập link bài viết mới
                articles = driver.find_elements(By.CSS_SELECTOR, "div#loadListData div.box__item-row")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.CSS_SELECTOR, "h3 > a")
                        href = a_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://doanhnghieptiepthi.vn", href)
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
                    next_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.box__viewmore")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'Xem thêm'")
                    time.sleep(4)
                except Exception as e:
                    print("❌ Không tìm thấy hoặc không click được nút 'Xem thêm':", e)
                    break

                for i in range(4):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(1)

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