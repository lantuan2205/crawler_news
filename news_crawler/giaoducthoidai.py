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
from selenium.common.exceptions import TimeoutException,WebDriverException, StaleElementReferenceException


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https, time_to_seconds

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class GiaoDucThoiDaiCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://giaoducthoidai.vn/"
        self.article_type_dict = {
            0: "chinh-sach",
            1: "dia-phuong",
            2: "tuyen-sinh-du-hoc",
            3: "giao-duc-bon-phuong",
            4: "chuyen-dong",

            5: "giao-duc-do-thi",
            6: "thoi-su-xa-hoi",
            7: "chinh-tri", 
            8: "kinh-te",

            9: "an-ninh",
            10: "phap-dinh",
            11: "goc-nhin",

            12: "cong-doan",
            13: "dong-hanh",
            14: "khoa-hoc",

            15: "phuong-phap",
            16: "goc-chuyen-gia",

            17: "ky-nang-song",
            18: "du-hoc",
            19: "guong-mat",
            20: "the-chat",

            21: "nhan-ai",

            22: "giao-duc-quoc-phong",
            23: "the-gioi-do-day",
            24: "chuyen-la",

            25: "khoe-dep",
            26: "gia-dinh",
            27: "day-lui-covid",

            28: "tieu-diem",
            29: "sang-tac",
            30: "doi-song-van-hoa",
            31: "the-gioi-sao",
            32: "the-thao-hoc-duong",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: giaoducthoidai/category/date
            newspaper_name = "giaoducthoidai"
            date_parts = clean_date(publish_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"
            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder

            clean_url = image_url.split('?')[0]
            image_filename = Path(clean_url).name
            remote_path = remote_dir / image_filename

            # Tải ảnh
            response = requests.get(image_url, headers=headers)
            response.raise_for_status()
            image_data = BytesIO(response.content)

            # Kết nối SSH/SFTP
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ssh_host, username=ssh_user, password=ssh_password)
            sftp = ssh.open_sftp()

            # Xử lý URL ảnh
            # Tạo thư mục nếu chưa có (đệ quy)
            path_parts = str(remote_dir).split('/')
            current = ''
            for part in path_parts:
                if not part:
                    continue
                current += f'/{part}'
                try:
                    sftp.stat(current)
                except IOError:
                    sftp.mkdir(current)

            # Lưu ảnh
            with sftp.file(str(remote_path), 'wb') as f:
                f.write(image_data.getvalue())

            # Đóng kết nối
            sftp.close()
            ssh.close()

            return str(remote_path)
            
        except Exception as e:
            self.logger.error(f"Error downloading image {image_url}: {e}")
            return None
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
            container = soup.select_one("header.page-header .container.header-primary")
            h1_tag = container.find("h1") if container else None
            a_tag = h1_tag.find("a") if h1_tag else None

            logo_src = a_tag.get("href").strip() if a_tag and a_tag.has_attr("href") else None
            # (tuỳ chọn) chuyển sang URL tuyệt đối
            logo_src = urljoin(url, logo_src) if logo_src else None

            info["logo"] = logo_src or ""
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "footer.page-footer"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("footer", class_="page-footer")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # p = soup.select_one("footer.page-footer .item-primary p")
                # raw = p.get_text(" ", strip=True) if p else ""
                # info["description"] = " ".join(raw.replace("\xa0"," ").split()).strip('\"“”')
                # License
                if "CƠ QUAN CỦA BỘ GIÁO DỤC" in text:
                    des_line = [line for line in lines if "CƠ QUAN CỦA BỘ GIÁO DỤC" in line]
                    if des_line:
                        info["description"] = des_line[0].strip()

                # License
                if "Số giấy phép" in text:
                    license_line = [line for line in lines if "Số giấy phép" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Số giấy phép", "").strip()

                # Tổng biên tập
                if "Tổng Biên tập: " in text:
                    editor_line = [line for line in lines if "Tổng Biên tập: " in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng Biên tập: ", "").strip()

                # Địa chỉ
                if "Tòa soạn: " in text:
                    addr_line = [line for line in lines if "Tòa soạn:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Tòa soạn:", "").strip()

                # Điện thoại
                # if "Điện thoại:" in text:
                #     phone_line = [line for line in lines if "Điện thoại:" in line]
                #     if phone_line:
                #         info["phone"] = phone_line[0].replace("Điện thoại:", "").strip()
                # Email
                phone_tag = footer_copyright.select_one("a[href^='tel:']")
                if phone_tag:
                    info["phone"] = phone_tag.get_text(strip=True).replace("Điện thoại:", "").strip()

                # Email
                email_tag = footer_copyright.select_one("a[href^=mailto]")
                if email_tag:
                    info["email"] = email_tag.get_text(strip=True).replace("Email:", "").strip()

                # Ban quyen
                if "Ghi rõ nguồn" in text:
                    copyright_tag = [line for line in lines if "Ghi rõ nguồn" in line]
                    if copyright_tag:
                        info["infor_copyright"] = copyright_tag[0]


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
            title_tag = soup.find('h1',class_='article__title')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("h2", class_="article__sapo")
            if desc_tag:
                # Ưu tiên thẻ <p> nếu có
                p_tag = desc_tag.find("p")
                if p_tag:
                    raw_description = p_tag.get_text(strip=True)
                else:
                    raw_description = desc_tag.get_text(strip=True)

                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None


            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("time", class_='time')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="article")
            images = content_div.select("table.picture img, figure img") if content_div else []

            # Lọc ảnh
            content_images = []
            for img in images:
                # Kiểm tra và lấy cả src và data-large-src
                for attr in ['src', 'data-large-src']:
                    src = img.get(attr)
                    if not src:
                        continue
                    if src.startswith("data:image"):
                        continue  # ❌ Bỏ base64
                    if any(x in src for x in ["gg-news", "zalo", "logo", "icon"]):
                        continue  # ❌ Bỏ ảnh giao diện
                    if urlparse(src).path.lower().endswith(".jpg") or urlparse(src).path.lower().endswith(".jpg.webp"):
                        content_images.append(src)

             # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            # images = content_div.find_all("img")
            # content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_tag = soup.find(["a","span"], class_="cms-author")
            author = author_tag.get_text(strip=True).split('/')[0].strip() if author_tag else None

            
            a = soup.select_one("div.cate-breadcrumb a.cate-parent")
            categories = a.get_text(strip=True) if a else ""
            
            title_tag = soup.find("h1", class_="article__title cms-title")
            location = ""
            if title_tag and title_tag.text:
                text = title_tag.text.strip()
                if ":" in text:
                    location = text.split(":")[0].strip()
            figure = soup.find('figure',class_='video')

            if figure:
                # tìm thẻ video hoặc source bên trong để lấy src
                video_tag = figure.find("video")
                if video_tag and video_tag.get("src"):
                    video_url = video_tag["src"].strip()
                else:
                    # nếu thẻ <source> bên trong chứa src
                    source_tag = figure.find("source")
                    if source_tag and source_tag.get("src"):
                        video_url = source_tag["src"].strip()

                # lấy thuộc tính poster
                if video_tag and video_tag.get("poster"):
                    thumbnail_url = video_tag["poster"].strip()


            return title, description, content, publish_date, author, content_images,categories, video_url, thumbnail_url, location

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi tải trang: {e}")
            return None, None, None, None, None, []
        except Exception as e:
            print(f"Lỗi trong quá trình phân tích HTML: {e}")
            return None, None, None, None, None, []
    def extract_comment(self, url: str):
        # Sử dụng session từ base class (có thể là proxy session)
        # --- Phase 2: lấy footer bằng Selenium ---
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_experimental_option("prefs", {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2
        })
        chrome_options.set_capability("pageLoadStrategy", "eager")
        driver = None
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(60)

            try:
                driver.get(url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
            # --- Click "Xem thêm ý kiến" để load thêm comment ---
            while True:
                try:
                    show_more_btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "a#show_more_coment"))
                    )
                    # Cuộn tới nút
                    driver.execute_script("arguments[0].scrollIntoView(true);", show_more_btn)
                    time.sleep(0.2)
                    # Click bằng JS (bypass quảng cáo che)
                    driver.execute_script("arguments[0].click();", show_more_btn)
                    time.sleep(0.5)  # chờ comment load
                except (TimeoutException, NoSuchElementException):
                    break  # hết nút để click

            soup = BeautifulSoup(driver.page_source, "html.parser")
            comments = []

            for item in soup.select("div.comment_item"):
                comment_id =  ""
                user_id = ""
                user_url = ""
                username = ""      
                avatar = ""
                content = ""
                time_comment = ""
                reaction_map = {
                    "Thích": "Like",
                    "Yêu thích": "Love",
                    "Haha": "Haha",
                    "Wow": "Wow",
                    "Buồn": "Sad",
                    "Phẫn nộ": "Angry",
                }

                reactions = {}
                reply_count = 0
                
                comments.append({
                    "domain": normalize_url_to_root_https(url),
                    "url": url,
                    "commentId": comment_id,
                    "userId": user_id,
                    "username": username,
                    "userUrl": user_url,
                    "avatar": avatar,
                    "content": content,
                    "time": time_comment,
                    "reactions": reactions,
                    "replyCount": reply_count
                })
            return comments
        except WebDriverException as e:
            print("⚠️ Lỗi Selenium:", e)
        finally:
            if driver:
                driver.quit()
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
            "publishedDate": clean_date(publish_date) if publish_date else None,
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
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless 
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://giaoducthoidai.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0  
        wait = WebDriverWait(driver, 10)

        try:
            while True:
                articles = driver.find_elements(By.CSS_SELECTOR, "div.many-pack article.story")
                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "h3 > a")
                        href = title_link.get_attribute("href")
                        # print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://giaoducthoidai.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)
    
                try:
                    # Kéo xuống một nửa trang
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(2)

                    try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.load-more")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(2)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(3)

                    except Exception:
                            print("✅ Không còn nút Trang sau. Dừng lại.")
                            break

                except Exception as e:
                    print(f"❌ Lỗi khi click nút 'Xem thêm': {e}")

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