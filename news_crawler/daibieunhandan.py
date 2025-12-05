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
from selenium.common.exceptions import NoSuchElementException,TimeoutException,WebDriverException
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
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https, time_to_seconds

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class DaiBieuNhanDanCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://daibieunhandan.vn/"
        self.article_type_dict = {
            0: "chinh-tri/thoi-su-quoc-hoi",
            1: "chinh-tri/bao-ve-nen-tang-tu-tuong-dang",
            2: "chinh-tri/viet-nam-voi-ky-nguyen-moi",
            3: "chinh-tri/theo-dong-su-kien",

            4: "quoc-hoi-va-cu-tri/dien-dan-quoc-hoi",
            5: "quoc-hoi-va-cu-tri/lap-phap",
            6: "quoc-hoi-va-cu-tri/chinh-sach-va-cuoc-song",
            7: "quoc-hoi-va-cu-tri/y-kien-dai-bieu",
            8: "quoc-hoi-va-cu-tri/hoat-dong-cua-doan-dbqh",

            9: "hoi-dong-nhan-dan/hoi-nghi-tt-hdnd",
            10: "hoi-dong-nhan-dan/chuyen-dong",
            11: "hoi-dong-nhan-dan/dien-dan",
            12: "hoi-dong-nhan-dan/dai-bieu-cu-tri",

            13: "phong-chong-tham-nhung-lang-phi/van-ban-chi-dao",
            14: "phong-chong-tham-nhung-lang-phi/kiem-tra-giam-sat",
            15: "phong-chong-tham-nhung-lang-phi/don-thu-ban-doc",

            16: "kinh-te/thi-truong",
            17: "kinh-te/doanh-nghiep",
            18: "kinh-te/tai-chinh",
            19: "kinh-te/bat-dong-san",

            20: "xa-hoi/doi-song",
            21: "xa-hoi/giao-thong",
            22: "xa-hoi/moi-truong",

            23: "quoc-phong-an-ninh/an-ninh-trat-tu",
            24: "quoc-phong-an-ninh/quoc-phong-toan-dan",
            25: "quoc-phong-an-ninh/tin-tuc-phap-luat",

            26: "giao-duc/nhip-cau-giao-duc",
            27: "giao-duc/tuyen-sinh",
            28: "giao-duc/trao-doi",

            29: "suc-khoe/tin-tuc",
            30: "suc-khoe/tu-van",
            31: "suc-khoe/song-khoe",

            32: "van-hoa-the-thao/van-hoa",
            33: "van-hoa-the-thao/the-thao-du-lich",
            34: "van-hoa-the-thao/van-nghe",

            35: "khoa-hoc-cong-nghe/khoa-hoc",
            36: "khoa-hoc-cong-nghe/cong-nghe",
            
            37: "dia-phuong/hoat-dong-chinh-quyen",
            38: "dia-phuong/tren-duong-phat-trien",
            39: "dia-phuong/an-ninh-co-so",

            40: "quoc-te/viet-nam-va-the-gioi",
            41: "quoc-te/the-gioi-24h",
            42: "quoc-te/nghi-vien-the-gioi",
            
            43: "dai-bieu-nhan-dan-video/thoi-su-quoc-hoi",
            43: "dai-bieu-nhan-dan-video/dai-bieu-voi-cu-tri",
            43: "dai-bieu-nhan-dan-video/ban-tin-thoi-su-qh",
            43: "dai-bieu-nhan-dan-video/kinh-te-xa-hoi",
            43: "dai-bieu-nhan-dan-video/toa-dam-talkshow"

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

            box = soup.select_one("h1.c-logo a img")
            logo_src = ""
            if box:
                logo_src = ( box.get("data-src") or "").strip()

            info["logo"] = urljoin(url, logo_src) if logo_src else ""
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.c-footer-main"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="c-footer-main")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 1:
                    info["description"] = f"{lines[0]}"

                # License
                if "Giấy phép" in text:
                    license_line = [line for line in lines if "Giấy phép" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép", "").strip()

                # Tổng biên tập
                if "Tổng Biên tập:" in text:
                    editor_line = [line for line in lines if "Tổng Biên tập:" in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng Biên tập:", "").strip()

                # Địa chỉ
                if "Trụ sở tòa soạn:" in text:
                    addr_line = [line for line in lines if "Trụ sở tòa soạn:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Trụ sở tòa soạn:", "").strip()

                # Điện thoại
                b = footer_copyright.select_one("li a span b")
                info["phone"] = b.get_text(strip=True) if b else ""

                # Email
                email_b = soup.select_one("li:has(span:-soup-contains('Email')) b")
                info["email"] = email_b.get_text(strip=True) if email_b else ""
                # Thông tin bản quyền
                last_p = footer_copyright.select("p")[-1]
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
            title_tag = (
                soup.find('h1', class_='block-sc-title') or
                soup.select_one('div.c-video-detail__title h1')
            )
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Lấy description
            # desc_tag = soup.select_one("div.mota h2")
            desc_tag = soup.find("p",class_= "block-sc-sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách sau dấu "-" đầu tiên
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                desc_tag = soup.find("div", class_="c-video-detail__desc")
                description = desc_tag.get_text(strip=True) if desc_tag else ""
            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.find("span", class_="sc-longform-header-date")

            # TH2: dạng div.c-video-detail__time (chứa cả tên + ngày)
            if not date_tag:
                date_tag = soup.find("div", class_="c-video-detail__time")

            if date_tag:
                text = date_tag.get_text(strip=True)
                # Loại bỏ phần tên tác giả, chỉ giữ lại phần có ngày tháng
                match = re.search(r"\d{1,2}/\d{1,2}/\d{4}\s*\d{1,2}:\d{2}", text)
                publish_date = match.group(0) if match else ""
            else:
                publish_date = ""

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="b-maincontent")
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
            author = None

            # TH1: bài viết dạng longform
            author_box = soup.find("span", class_="sc-longform-header-author")
            if author_box:
                author = author_box.get_text(strip=True).split("/")[0].strip()

            # TH2: video hoặc bài có tác giả chung với ngày
            if not author:
                author_box = soup.find("div", class_="c-video-detail__time")
                if author_box:
                    text = author_box.get_text(strip=True)

                    # Nếu có ngày ở cuối (dd/mm/yyyy), cắt bỏ phần đó
                    parts = [p.strip() for p in text.split("-") if p.strip()]
                    authors = []

                    for part in parts:
                        # Nếu phần này chứa ngày -> dừng lại
                        if re.search(r"\d{1,2}/\d{1,2}/\d{4}", part):
                            break
                        authors.append(part)

                    author = " - ".join(authors) if authors else ""

            cat_tag = soup.select_one("li.breadcrumb-item.active a")
            if not cat_tag:
                cat_tag = soup.select_one("div.c-video-detail__cat a")
            categories = cat_tag.get_text(strip=True) if cat_tag else ""
            
            video_url = ""
            location = ""

            thumbnail_url = ""
            driver = None

            try:
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
                chrome_options.set_capability("pageLoadStrategy", "eager")

                driver = webdriver.Chrome(options=chrome_options)
                driver.get(url)

                # Lấy video src (nếu có)
                try:
                    iframe_switched = False
                    # nếu player nằm trong iframe thì thử switch
                    for f in driver.find_elements(By.CSS_SELECTOR, "iframe"):
                        driver.switch_to.frame(f)
                        if driver.find_elements(By.CSS_SELECTOR, "video.vjs-tech, .video-js"):
                            iframe_switched = True
                            break
                        driver.switch_to.default_content()
                    if not iframe_switched:
                        driver.switch_to.default_content()

                    try:
                        video_el = driver.find_element(By.CSS_SELECTOR, "video.vjs-tech")
                        video_url = video_el.get_attribute("src") or ""
                        thumbnail_url = video_el.get_attribute("poster") or ""

                    except NoSuchElementException:
                        video_url = ""
                        thumbnail_url =""
                except Exception:
                    video_url = ""
                    thumbnail_url = ""

            except WebDriverException as e:
                print("⚠️ Selenium error:", e)
            finally:
                try:
                    if driver:
                        driver.quit()
                except:
                    pass

            return title, description, content, publish_date, author, content_images, categories, video_url, thumbnail_url, location

        except requests.exceptions.RequestException as e:
            print(f"Lỗi khi tải trang: {e}")
            return None, None, None, None, None, [], None, None, None, None
        except Exception as e:
            print(f"Lỗi trong quá trình phân tích HTML: {e}")
            return None, None, None, None, None, [], None, None, None, None
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
        page_url = f"https://daibieunhandan.vn/{article_type}"
        driver.get(page_url)
        seen_links = set()
        last_size = 0
        page_count = 0
        max_pages = 2
        try:
            wait = WebDriverWait(driver, 10)

            while page_count < max_pages:
                articles = driver.find_elements(By.CSS_SELECTOR, "ul.onecms_loading li")
                for article in articles:
                    try:
                        title_link = article.find_element(By.CSS_SELECTOR, "a")
                        href = title_link.get_attribute("href")
                        print("🧪 Found link:", href)  # ✅ In ra để debug
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://daibieunhandan.vn", href)
                            if href.startswith("http") and href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        pass
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                try:
                        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "div.view-more-article a")))
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        print("➡️ Đã click nút 'Trang sau'")
                        page_count += 1

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
