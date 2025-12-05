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
from selenium.common.exceptions import TimeoutException, WebDriverException


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

class DienTuToQuocCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://toquoc.vn/"
        self.article_type_dict = {
            0: "thoi-su/chinh-tri",
            1: "thoi-su/nguoi-viet-5-chau",
            2: "thoi-su/binh-luan-su-kien",

            3: "van-hoa/su-kien-van-hoa",
            4: "van-hoa/gia-dinh",
            5: "van-hoa/vang-mai-giai-dieu-to-quoc",
            6: "van-hoa/van-hoc-sach",
            7: "van-hoa/dao-duc-xa-hoi", 
            8: "van-hoa/bao-ton-gin-giu-va-phat-huy-ban-sac-dan-toc-ton-giao-viet-nam",

            9: "the-thao/hau-truong",
            10: "the-thao/cac-mon-the-thao",
            11: "the-thao/bong-da",
            12: "the-thao/guong-mat-the-thao",

            13: "du-lich/cam-nang-du-lich",
            14: "du-lich/diem-den",
            15: "du-lich/kham-pha",
            16: "du-lich/quan-lychinh-sach",

            17: "the-gioi/su-kien",
            18: "the-gioi/cua-so-bon-phuong",
            19: "the-gioi/ho-so-quoc-te",
            20: "the-gioi/y-kien-binh-luan",

            21: "kinh-te/chuyen-kinh-doanh",
            22: "kinh-te/tai-chinh-thi-truong",
            23: "kinh-te/thi-truong",
            24: "kinh-te/bat-dong-san",
            25: "kinh-te/xe-co",
            26: "kinh-te/the-gioi-doanh-nhan",

            27: "phap-luat/an-ninh-trat-tu",
            28: "phap-luat/phap-luat-doi-song",
            29: "phong-chong-ma-tuy-t141",
            30: "phong-va-chong-vi-pham-phap-luat-trong-hoat-dong-vhttdl-t144",
            31: "phap-luat/giam-thieu-tinh-trang-tao-hon-va-hon-nhan-can-huyet-vung-dong-bao-dttsmn",
            32: "phap-luat/truyen-thong-chinh-sach",

            33: "giai-tri/am-nhac",
            34: "giai-tri/thoi-trang",
            35: "giai-tri/phim",
            36: "giai-tri/hau-truong",

            37: "giao-duc/thoi-su-giao-duc",
            38: "giao-duc/tuyen-sinh",
            39: "giao-duc/viec-lam",

            40: "suc-khoe/thoi-su-y-te",
            41: "suc-khoe/khoe-dep",
            42: "suc-khoe/benh-cay-con",
            43: "suc-khoe/phong-mach",

            44: "cu-dan-mang",

            45: "cong-nghe/nhip-song-so",
            46: "cong-nghe/khoa-hoc",

            47: "kham-pha/con-nguoi",
            48: "kham-pha/thien-nhien",

            49: "to-quoc-media/phong-su-anh",
            50: "to-quoc-media/ban-tin-phat-thanh",
            51: "to-quoc-media/clip-hot"
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
            logo_tag = soup.find("meta", attrs={"property": "og:image"})
            info["logo"] = logo_tag["content"] if logo_tag else ""

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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.main-footer"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="main-footer")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 2:
                    info["description"] = f"{lines[0]} - {lines[1]}"

                # License
                if "Giấy phép hoạt động" in text:
                    license_line = [line for line in lines if "Giấy phép hoạt động" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép hoạt động", "").strip()

                # Tổng biên tập
                tag = soup.find("a", class_="tag", string=lambda t: t and "Tổng Biên tập" in t)

                if tag and tag.parent:
                    # Lấy toàn bộ text trong <p> (bao gồm cả tên)
                    full_text = tag.parent.get_text(" ", strip=True)
                    # Loại bỏ phần "Tổng Biên tập:" để chỉ còn tên
                    info["editor_in_chief"] = full_text.replace("Tổng Biên tập:", "").strip()

                # Địa chỉ
                if "Toà soạn:" in text:
                    addr_line = [line for line in lines if "Toà soạn:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Toà soạn:", "").strip()

                # Điện thoại
                if "Điện thoại:" in text:
                    phone_line = [line for line in lines if "Điện thoại:" in line]
                    if phone_line:
                        info["phone"] = phone_line[0].replace("Điện thoại:", "").strip()

                # Email
                match = re.search(r'[\w\.-]+@[\w\.-]+', text)
                info["email"] = match.group(0) if match else ""

                # Thông tin bản quyền
                last_p = footer_copyright.select("div.group")[-1]
                if last_p:
                    info["infor_copyright"] = last_p.get_text(strip=True)

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
            title_tag = soup.find('h1',class_='entry-title')
            title = title_tag.get_text(strip=True) if title_tag else ""
            # Lấy description
            desc_tag = soup.find("h2", class_="sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_="publishdate")

            if date_tag:
                # Kiểm tra nếu có chứa ngày giờ ở định dạng cụ thể trong thẻ chính
                raw_date = date_tag.get_text(strip=True)

                # Nếu có ngày ở sau ký tự "|"
                if "|" in raw_date:
                    raw_parts = raw_date.split("|")
                    if len(raw_parts) > 1:
                        publish_date = raw_parts[1].strip()
                else:
                    # Nếu không có "|", giả định nội dung là ngày giờ luôn
                    publish_date = raw_date

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="data-content-body")
            if not content_div:
                content_div = soup.find("div", class_="entry-body")
            if content_div:
                images = content_div.find_all('img')
                content_images = [img['src'] for img in images if img.get('src')]
            else:
                content_images = []

             # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)

            # Trích xuất tác giả
            author_tag = soup.find("p", class_="author")
            if author_tag:
                author = author_tag.get_text(strip=True).split('/')[0].strip()
            else:
                # Nếu không có, tìm trong <span class="publishdate">
                publish_span = soup.find("span", class_="publishdate")
                if publish_span:
                    inner_span = publish_span.find("span")
                    author = inner_span.get_text(strip=True) if inner_span else ""
                else:
                    author = None
            cate_tag = soup.select_one('a.cat')
            categories = cate_tag.get_text(strip=True) if cate_tag else ""

            location = ""

            tag = soup.select_one("div.VCSortableInPreviewMode[type='VideoStream']")
            video_url = tag.get("data-vid", "").strip() if tag else ""
            thumbnail_url = tag.get("data-thumb", "").strip() if tag else ""

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
            "publishedDate": clean_date(publish_date) if publish_date else "",
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
        page_url = f"https://toquoc.vn/{article_type}.htm"
        driver.get(page_url)

        seen_links = set()
        seen_article_ids = set()  # set theo object id hoặc nội dung text
        wait = WebDriverWait(driver, 10)
        page_count = 0
        max_pages = 5
        try:
            while page_count < max_pages:
                # Scroll và đợi DOM render
                driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                time.sleep(1)

                # Tìm tất cả bài viết hiện có
                articles = driver.find_elements(By.CSS_SELECTOR, "div.stream-list ul li.qitem")
                new_found = 0

                for article in articles:
                    try:
                        # Lấy text hoặc ID duy nhất để tránh quét lại
                        article_id = article.text.strip()
                        if article_id in seen_article_ids:
                            continue  # đã xử lý
                        seen_article_ids.add(article_id)

                        title_link = article.find_element(By.CSS_SELECTOR, "a.fl")
                        href = title_link.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://toquoc.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                                # print("🔗 New link:", href)
                                new_found += 1
                    except Exception:
                        continue

                if new_found == 0:
                    print("✅ Không còn bài mới sau khi cuộn/trang mới.")
                    break

                # Tìm và ấn nút Xem thêm nếu còn
                try:
                    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.btn-view-more")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Click nút 'Xem thêm'")
                    page_count  += 1
                except Exception:
                    print("✅ Không còn nút 'Xem thêm'. Kết thúc.")
                    break

        except Exception as e:
            print("❌ Lỗi trong quá trình thu thập:", e)

        finally:
            driver.quit()

        print(f"📄 Tổng số bài thu thập: {len(seen_links)}")
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles