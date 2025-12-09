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

class BaoChinhPhuCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baochinhphu.vn/"
        self.article_type_dict = {
            0: "chinh-tri/doi-ngoai",
            1: "chinh-tri/to-chuc-nhan-su",
            2: "chinh-tri/hoi-nhap",

            3: "kinh-te/ngan-hang",
            4: "kinh-te/chung-khoan",
            5: "kinh-te/thi-truong",
            6: "kinh-te/doanh-nghiep",
            7: "kinh-te/khoi-nghiep",

            8: "van-hoa/the-thao",
            9: "van-hoa/du-lich",

            10: "xa-hoi/phap-luat",
            11: "xa-hoi/y-te",
            12: "xa-hoi/an-sinh-xa-hoi",
            13: "xa-hoi/nong-thon-moi",
            14: "xa-hoi/doi-song",

            15: "khoa-giao/giao-duc",
            16: "khoa-giao/khoa-hoc-cong-nghe",
            17: "khoa-giao/bien-viet-nam",
            18: "quoc-te/viet-nam-asean"
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
            banner_div = soup.find("div", class_="banner")
            logo_img = banner_div.find("img") if banner_div else None
            logo_src = urljoin(url, logo_img["src"]) if logo_img and logo_img.get("src") else None
            info["logo"] = logo_src
        except Exception as e:
            print("⚠️ Lỗi khi lấy logo:", e)

        # --- Phase 2: lấy footer bằng Selenium ---
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,  # tắt ảnh
                "profile.managed_default_content_settings.javascript": 1,  # bật JS
            }
        )
        chrome_options.set_capability("pageLoadStrategy", "eager")

        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(100)

            try:
                driver.get(url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
                return info

            # Chờ phần footer xuất hiện
            try:
                footer = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div#footer"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            tool_header = soup.find("div", class_="tool-header")
            if tool_header:
                hotline_div = tool_header.find("div", class_="hotline")
                if hotline_div:
                    # Lấy text sau dấu ":"
                    phone_text = hotline_div.get_text(strip=True).split(":")[-1].strip()
                    info["phone"] = phone_text

            footer_copyright = soup.find("div", id="footer-content")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 2:
                    info["description"] = f"{lines[0]} - {lines[1]}"

                # License
                license_line = [line for line in lines if "Giấy phép" in line]
                if license_line:
                    # ví dụ: "Giấy phép số 790/GP-BTTTT do Bộ Thông tin và Truyền thông cấp ngày 02/12/2021."
                    info["license"] = license_line[0].split("số")[-1].split("do")[0].strip()

                # Tổng biên tập
                editor_line = [line for line in lines if "Tổng Biên tập" in line]
                if editor_line:
                    info["editor_in_chief"] = editor_line[0].split(":")[-1].strip()

                # Địa chỉ
                address_line = [line for line in lines if "Tòa soạn" in line]
                if address_line:
                    info["address"] = address_line[0].split(":")[-1].strip()

                # Điện thoại
                if "Điện thoại:" in text:
                    phone_line = [line for line in lines if "Điện thoại:" in line]
                    if phone_line:
                        info["phone"] = phone_line[0].replace("Điện thoại:", "").strip()

                # Email
                email_tag = footer_copyright.select_one("a[href^=mailto]")
                if email_tag:
                    info["email"] = email_tag.get_text(strip=True).replace("Email:", "").strip()

                # Thông tin bản quyền
                copyright_line = [line for line in lines if "Bản quyền" in line]
                if copyright_line:
                    info["infor_copyright"] = copyright_line[0].strip()

        except WebDriverException as e:
            print("⚠️ Lỗi Selenium:", e)
        finally:
            if driver:
                driver.quit()

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


    def extract_content(self, url: str, has_video) -> tuple:
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
            title_tag = soup.find('h1', class_='detail-title')
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Lấy description
            desc_tag = soup.find("h2", class_="detail-sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None            
            # Trích xuất ngày viết bài
            date_tag = soup.find("div", attrs={"data-role": "publishdate"})
            if date_tag:
                # Lấy toàn bộ text trong tag, loại bỏ các ký tự không cần thiết
                full_text = date_tag.get_text(separator=" ", strip=True)
                publish_date = " ".join(full_text.split())  # Gộp lại thành 1 dòng, loại bỏ khoảng trắng thừa
            else:
                publish_date = None
                
            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="detail-content afcbc-body clearfix")
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
            content_div = soup.find("div", class_="detail-content", attrs={"data-role": "content"})
            content = ""
            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                
            # Trích xuất tác giả
            author = None

            # Ưu tiên lấy theo thẻ a nếu có
            author_box = soup.find('a', class_='detail-author-top-name')
            if author_box:
                author = author_box.get_text(strip=True).rstrip('-').strip()
            if not author:
                author_tag = soup.find('p', style=lambda v: v and "text-align:right" in v.replace(" ", ""))
                if author_tag:
                    bold_tag = author_tag.find('b')
                    if bold_tag:
                        author = bold_tag.get_text(strip=True)

            categories= ""
            video_url = ""
            thumbnail_url = ""
            location = ""

            return title, description, content, publish_date, author, content_images, categories, video_url, thumbnail_url, location

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi tải trang: {e}")
            return None, None, None, None, None, [], None, None, None, None
        except Exception as e:
            print(f"Lỗi trong quá trình phân tích HTML: {e}")
            return None, None, None, None, None, [], None, None, None, None
    
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
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_experimental_option("prefs", {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2
        })
        chrome_options.set_capability("pageLoadStrategy", "eager")
        driver = webdriver.Chrome(options=chrome_options)
        
        page_url = f"https://baochinhphu.vn/{article_type}.htm"
        driver.get(page_url)

        seen_links = set()
        wait = WebDriverWait(driver, 10)
        page_count = 0
        max_pages = 2

        try:
            while page_count < max_pages:
                # Lưu số lượng link trước khi quét
                previous_count = len(seen_links)

                # Scroll 4 lần
                for i in range(4):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(1.5)

                # Thu thập link bài viết mới
                articles = driver.find_elements(By.CSS_SELECTOR, "div.box-stream.timeline_list div.box-stream-item")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.CSS_SELECTOR, "a.box-stream-link-with-avatar")
                        href = a_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://baochinhphu.vn", href)
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
                    next_button = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Xem thêm') and contains(@class,'btn')]")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'Xem thêm'")
                    page_count +=1
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

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles