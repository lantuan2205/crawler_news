import json
import requests
import sys
import time
import random
import re
import os
import uuid
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime
import paramiko
from io import BytesIO
from pathlib import Path
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from typing import Optional

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.beautifulSoup_utils import  extract_categories_from_soup
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https, time_to_seconds
from utils.mongodb_utils import save_image_metadata

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class BaoAnGiangCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baoangiang.com.vn/"
        self.article_type_dict = {
            0: "an-giang-24-gio",
            1: "chinh-tri-xa-hoi",
            2: "xh-tt",
            3: "kinh-te",
            4: "giao-duc",
            5: "cong-nghe",
            6: "phap-luat",
            7: "quoc-te",
            8: "van-hoa",
            9: "the-thao",
            10: "suc-khoe",
            11: "nhip-song-moi",
            12: "tam-nong",
            13: "thoi-trang",
            14: "du-lich",
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
                logo_img = soup.select_one("div.col-top-logo img.i-logo")
                if logo_img and logo_img.get("src"):
                    info["logo"] = urljoin(url, logo_img["src"])
            except:
                pass
            print("logo after CASE 1:", info["logo"])
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
        chrome_options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,
                "profile.managed_default_content_settings.javascript": 1,
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
                print("⚠️ Load trang quá lâu:", url)
                return info

            # chờ footer
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.bot-item.col-left"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")

            footer = soup.select_one("div.bot-item.col-left")
            if not footer:
                return info

            paragraphs = [
                p.get_text(" ", strip=True)
                for p in footer.find_all("p")
                if p.get_text(strip=True)
            ]

            addresses = []
            content_responsible = []

            for text in paragraphs:
                # -------- License --------
                if "Giấy phép số" in text:
                    info["license"] = text

                # -------- Publisher --------
                elif "Chịu trách nhiệm xuất bản" in text:
                    info["publisher"] = text.replace("Chịu trách nhiệm xuất bản:", "").strip()

                # -------- Address --------
                elif "Địa chỉ Tòa soạn" in text or "Cơ sở 1" in text:
                    addresses.append(text)

                # -------- Phone --------
                elif "Số điện thoại" in text:
                    info["phone"] = text.replace("- Số điện thoại:", "").strip()

                # -------- Email --------
                emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
                if emails:
                    info["email"] = ", ".join(set(emails))

                # -------- Copyright --------
                # elif "Bản quyền" in text or "©" in text:
                #     info.setdefault("infor_copyright", [])
                #     info["infor_copyright"].append(text)

            if addresses:
                info["address"] = "".join(addresses).replace("Địa chỉ Tòa soạn:- Cơ sở 1:", "").strip()

            if content_responsible:
                info["content_responsible"] = " | ".join(content_responsible)

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
        if hasattr(self, 'session'):
            response = self.session.get(url, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        time.sleep(random.uniform(1, 2))

        # -------- Title --------
        title_tag = soup.select_one("div.detail-title h1")
        title = title_tag.get_text(strip=True) if title_tag else None

        # -------- Published date --------
        date_tag = soup.select_one("div.pubdate")
        published_date = date_tag.get_text(strip=True) if date_tag else None

        # -------- Description (sapo) --------
        desc_tag = soup.select_one("div.detail-desc p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # -------- Content --------
        content_div = soup.select_one("#newscontents .content-fck-font-size")
        paragraphs = []
        if content_div:
            for p in content_div.find_all("p", recursive=False):
                # bỏ caption ảnh & author
                if "author" in p.get("class", []):
                    continue
                text = p.get_text(" ", strip=True)
                if text:
                    paragraphs.append(text)

        content = "\n".join(paragraphs)

        author = None
        if content_div:
            p_tags = content_div.find_all("p", recursive=False)
            if p_tags:
                last_p = p_tags[-1]
                author = last_p.get_text(strip=True)

        # -------- Images --------
        image_tags = soup.select("#newscontents img")
        content_image_urls = []
        for img in image_tags:
            src = img.get("src")
            if src:
                content_image_urls.append(urljoin(url, src))

        # -------- Thumbnail --------
        thumbnail_url = content_image_urls[0] if content_image_urls else ""

        # -------- Category --------
        categories = ""
        breadcrumb = soup.select_one("ul.breadcrumb.left")

        if breadcrumb:
            li_tags = breadcrumb.find_all("li")
            if len(li_tags) >= 2:
                categories = li_tags[-1].get_text(strip=True)


        # -------- Location --------
        location = ""

        # -------- Video --------
        video_url = ""

        return title, description, content, published_date, author, content_image_urls, categories, video_url, thumbnail_url, location

    def write_content(self, url: str, article_type: str) -> bool:
        try:
            title, description, content, published_date, author, content_image_urls, categories = self.extract_content(url)
            if not title:  # Nếu không có tiêu đề, bỏ qua bài viết
                return None

            article_data = {
                "dataSource": "/".join(url.split("/")[:3]),
                "url": url,
                "publishedDate": clean_date(published_date),
                "author": author,
                "title": title,
                "description": description,
                "content": content,
                "contentImageUrls": content_image_urls,
                "categories": categories
                # # "localContentImagePaths": content_image_paths
            }

            return article_data

        except Exception as e:
            print(f"Lỗi khi xử lý URL {url}: {e}")
            return None


    def get_urls_of_type_thread(self, article_type, page_number):
        page_url = f"https://baoangiang.com.vn/{article_type}/?p={page_number}&d="
        if(page_number == 2):
            return []
        articles_urls = []

        try:
            # Dùng session nếu có
            if hasattr(self, "session"):
                print("[INFO] Đã sử dụng session từ base class")
                response = self.session.get(page_url, headers=headers, timeout=10)
            else:
                print("[INFO] Đã sử dụng requests")
                response = requests.get(page_url, headers=headers, timeout=10)

            response.raise_for_status()
            time.sleep(random.uniform(1, 2))

            soup = BeautifulSoup(response.content, "html.parser")

            # 👉 ĐÚNG container
            ul = soup.find("ul", class_="cate-content-list-item")
            if not ul:
                self.logger.info(f"Không tìm thấy cate-content-list-item trong {page_url}")
                return []

            items = ul.find_all("li", class_="item")
            if not items:
                self.logger.info(f"Không tìm thấy item bài viết trong {page_url}")
                return []

            for item in items:
                # 👉 Ưu tiên link tiêu đề
                a_tag = item.select_one("div.b-content a[href]")

                # fallback: link ảnh
                if not a_tag:
                    a_tag = item.select_one("a.b-img[href]")

                if a_tag:
                    full_url = urljoin(page_url, a_tag["href"])
                    articles_urls.append(full_url)

        except Exception as e:
            self.logger.warning(f"[!] Error while fetching {page_url}: {e}")
            return []

        print(f"[INFO] Lấy được {len(articles_urls)} URL từ {page_url}")
        return articles_urls
            
    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles
