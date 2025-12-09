import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime
import paramiko
from io import BytesIO
from selenium import webdriver
import re
FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class BaoVePhapLuatCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baovephapluat.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "kiem-sat-24h/van-de-su-kien",
            2: "kiem-sat-24h/ban-tin-kiem-sat",
            3: "kiem-sat-24h/nhan-su-moi",
            4: "kiem-sat-24h/chinh-sach-moi",
            5: "cong-to-kiem-sat-tu-phap/theo-dong",
            6: "cong-to-kiem-sat-tu-phap/khoi-to",
            7: "cong-to-kiem-sat-tu-phap/khoi-to",
            8: "cong-to-kiem-sat-tu-phap/an-ninh-trat-tu",
            9: "phap-dinh/toa-tuyen-an",
            10: "phap-dinh/ky-an",
            11: "phap-dinh/cau-chuyen-phap-luat",
            12: "cai-cach-tu-phap/dien-dan",
            13: "cai-cach-tu-phap/thuc-tien-kinh-nghiem",
            14: "cai-cach-tu-phap/nhan-to-dien-hinh",
            15: "kinh-te/kinh-doanh-phap-luat",
            16: "kinh-te/do-thi-xay-dung",
            17: "giao-thong",
            18: "kinh-te/tai-chinh-ngan-hang",
            19: "kinh-te/dung-hang-viet",
            20: "van-hoa-xa-hoi/giao-duc",
            21: "van-hoa-xa-hoi/y-te",
            22: "van-hoa-xa-hoi/lao-dong-viec-lam",
            23: "van-hoa-xa-hoi/vong-tay-nhan-ai",
            24: "van-hoa-xa-hoi/goc-van-hoa",
            25: "van-hoa-xa-hoi/doi-song-xa-hoi",
            26: "quoc-te/tin-tuc",
            27: "quoc-te/phap-luat-5-chau",
            28: "quoc-te/chuyen-la-bon-phuong",
            29: "phap-luat-ban-doc/tin-duong-day-nong",
            30: "phap-luat-ban-doc/dieu-tra-theo-don-thu",
            31: "phap-luat-ban-doc/hoi-am",
            32: "phap-luat-ban-doc/bao-chi-cong-dan",                                                                                   
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
            logo_tag = soup.select_one("a.logo-avatar img.imglogo")
            info["logo"] = logo_tag.get("src", "").strip() if logo_tag else ""
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footer-down"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="footer-down")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")
                license_tag = footer_copyright.find("div", class_="col-md-12")

                # Description
                info["description"] = soup.find("meta", id="MetaDescription")["content"]

                # License
                if "Giấy phép" in text:
                    license_line = [line for line in lines if "Giấy phép" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép", "").strip()

                # Tổng biên tập
                editor_in_chief = ""
                box = soup.select_one("div.footer-down div.col-md-12")
                if box:
                    # ưu tiên tên nằm trong <strong>
                    s = box.find("strong")
                    if s and s.get_text(strip=True):
                        editor_in_chief = s.get_text(strip=True)
                    else:
                        # fallback: lấy sau cụm "Tổng biên tập:"
                        txt = box.get_text(" ", strip=True)
                        m = re.search(r"Tổng\s*biên\s*tập[:\-]?\s*(.+)", txt, flags=re.I)
                        if m:
                            editor_in_chief = m.group(1).strip().strip('"')
                info["editor_in_chief"] = editor_in_chief

                # Địa chỉ
                addr = ""
                box = soup.select_one("div.footer-down div.col-md-12")
                if box:
                    txt = box.get_text(" ", strip=True).replace("\xa0", " ").replace("&nbsp;", " ")
                    m = re.search(r"Tòa\s*soạn:\s*(.*?)\s*Điện\s*thoại:", txt, flags=re.I | re.S)
                    if m:
                        addr = m.group(1).strip(' ".,;:-')

                info["address"] = addr

                # Điện thoại
                phone = ""
                box = soup.select_one("div.footer-down div.col-md-12")
                if box:
                    txt = box.get_text(" ", strip=True).replace("\xa0", " ")
                    m = re.search(r"Điện\s*thoại:\s*(.*?)(?:Email|Fax|$)", txt, flags=re.I | re.S)
                    if m:
                        phone = m.group(1).strip(' ".,;:-')

                info["phone"] = phone

                # Email
                email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", license_tag.get_text())
                if email_match:
                    email_text = email_match.group(0).strip()
                info["email"] = email_text

                # Thông tin bản quyền
                infor_copyright = ""
                box = soup.select_one("div.footer-down div.box-div div.col-md-12")
                if box:
                    parts = list(box.stripped_strings)  # ['®', 'Bản quyền thuộc...', 'Tổng biên tập :', ... , 'Cấm sao chép ...']
                    if parts:
                        # ghép "®" với câu "Bản quyền..." nếu cần
                        head = parts[0]
                        if head == "®" and len(parts) > 1:
                            head = (parts[0] + " " + parts[1]).strip()

                        tail = parts[-1]  # dòng cuối
                        infor_copyright = f"{head} {tail}".strip()

                info["infor_copyright"] = infor_copyright


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

    def extract_content(self, url: str,has_video) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Trích xuất tiêu đề
            title_tag = soup.find('h1', class_='post-title')
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Trích xuất ngày viết bài
            date_tag = soup.find('div', class_='lbPublishedDate')
            publish_date = date_tag.get_text(strip=True) if date_tag else ""

            desc_tag = soup.find('div', class_='post-summary')
            description = desc_tag.h2.get_text(strip=True) if desc_tag and desc_tag.h2 else ""

            content_tag = soup.find('div', class_='noidung')
            content = ''
            if content_tag:
                paragraphs = content_tag.find_all('p')
                content = '\n\n'.join(p.get_text(strip=True) for p in paragraphs)

            post_content_div = soup.find('div', class_='post-content')
            content_images = []
            if post_content_div:
                for img in post_content_div.find_all('img'):
                    src = img.get('src')
                    # Chỉ lấy ảnh có src bắt đầu bằng http hoặc chứa tên miền chính
                    if src and ('baovephapluat.vn' in src):
                        content_images.append(src)

            # Lấy tác giả (nằm trong div class="tacgia")
            author_tag = soup.find('div', class_='tacgia')
            author = author_tag.get_text(strip=True) if author_tag else ""
            categories = ""
            box = soup.select_one("div.v3home-block-title span.head")
            if box:
                categories = " > ".join(a.get_text(strip=True) for a in box.select("a") if a.get_text(strip=True))
            thumbnail_url = ""

            video_url = ""
            video_tag = soup.find("video")
            if video_tag:
                # ưu tiên <source src="...">
                src_tag = video_tag.find("source", src=True)
                if src_tag:
                    video_url = src_tag["src"].strip()
                else:
                    # fallback nếu <video> gắn trực tiếp src
                    video_url = (video_tag.get("src") or "").strip()
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
        base_url = "https://baovephapluat.vn"

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
                "profile.managed_default_content_settings.images": 2,  # tắt ảnh
                "profile.managed_default_content_settings.javascript": 1,  # bật JS
            }
        )
        chrome_options.set_capability("pageLoadStrategy", "eager")

        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"{base_url}/{article_type}"
        driver.get(page_url)

        seen_links = set()
        page_count = 0
        max_pages = 2
        wait = WebDriverWait(driver, 10)

        try:
            while page_count < max_pages:
                previous_count = len(seen_links)

                # Scroll xuống cuối page để load bài viết
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)

                # Lấy tất cả bài viết
                articles = driver.find_elements(By.CSS_SELECTOR, "div.pcontent3.contentCategory")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.TAG_NAME, "a")
                        href = a_tag.get_attribute("href")
                        if href:
                            href = urljoin(base_url, href)
                            seen_links.add(href)
                    except Exception:
                        continue

                # Nếu không có link mới → dừng
                new_links_found = len(seen_links) - previous_count
                if new_links_found == 0:
                    print("✅ Không còn link mới. Kết thúc.")
                    break

                # Click nút "XEM TIẾP" nếu còn
                try:
                    next_button = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.btnViewMoreData"))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'XEM TIẾP'")
                except Exception as e:
                    print("❌ Không tìm thấy hoặc không click được nút 'XEM TIẾP':", e)
                    break

                page_count += 1

        finally:
            driver.quit()

        print(f"📄 Tổng số link thu thập được: {len(seen_links)}")
        return seen_links

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
            results_div = soup.find("div", class_="row row-mb dsearch")

            if results_div:
                items = results_div.find_all("a", class_="item-title", href=True)
                for a_tag in items:
                    url = a_tag["href"].strip()
                    urls.add(url)

            return list(urls)
        except Exception as e:
            return []