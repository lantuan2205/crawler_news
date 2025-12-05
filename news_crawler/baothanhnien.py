import os
import requests
import sys
from pathlib import Path
import re, json

import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta, timezone
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

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
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https, time_to_seconds
 
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class BaoThanhNienCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thanhnien.vn/"
        self.article_type_dict = {
            0: "chinh-tri/su-kien",
            1: "chinh-tri/thoi-luan",
            2: "chinh-tri/vuon-minh-trong-ky-nguyen-moi",
            3: "chinh-tri/chung-dong-mau-lac-hong",

            4: "thoi-su/phap-luat",
            5: "thoi-su/lao-dong-viec-lam",
            6: "thoi-su/phong-su--dieu-tra",
            7: "thoi-su/chong-tin-gia",
            8: "thoi-su/dan-sinh",
            9: "thoi-su/quyen-duoc-biet",
            10: "thoi-su/thanh-tuu-y-khoa",
            11: "thoi-su/quoc-phong",

            12: "the-gioi/kinh-te-the-gioi",
            13: "the-gioi/quan-su",
            14: "the-gioi/goc-nhin",
            15: "the-gioi/ho-so",
            16: "the-gioi/nguoi-viet-nam-chau",
            17: "the-gioi/chuyen-la",

            18: "kinh-te/kinh-te-xanh",
            19: "kinh-te/chinh-sach-phat-trien",
            20: "kinh-te/ngan-hang",
            21: "kinh-te/chung-khoan",
            22: "kinh-te/doanh-nghiep",
            23: "kinh-te/doanh-nhan",
            24: "kinh-te/lam-giau",
            25: "kinh-te/dia-oc",

            26: "doi-song/tet-yeu-thuong",
            27: "doi-song/nguoi-song-quanh-ta",
            28: "doi-song/gia-dinh",
            29: "doi-song/am-thuc",
            30: "doi-song/cong-dong",
            31: "doi-song/mot-nua-the-gioi",
            32: "doi-song/khat-vong-nam-rong",

            33: "suc-khoe/khoe-dep-moi-ngay",
            34: "suc-khoe/lam-dep",
            35: "suc-khoe/gioi-tinh",
            36: "suc-khoe/tham-my-an-toan",
            37: "suc-khoe/y-te-thong-minh",

            38: "gioi-tre/song-yeu-an-choi",
            39: "gioi-tre/tiep-suc-gen-z-mua-thi",
            40: "gioi-tre/co-hoi-nghe-nghiep",
            41: "gioi-tre/doan-hoi",
            42: "gioi-tre/ket-noi",
            43: "gioi-tre/khoi-nghiep",
            44: "gioi-tre/the-gioi-mang",
            45: "gioi-tre/guong-mat-tre",

            46: "giao-duc/tuyen-sinh",
            47: "giao-duc/chon-nghe-chon-truong",
            48: "giao-duc/du-hoc",
            49: "giao-duc/nha-truong",
            50: "giao-duc/phu-huynh",
            51: "giao-duc/on-thi-tot-nghiep",
            52: "giao-duc/tuyen-sinh",

            53: "du-lich/tin-tuc-su-kien",
            54: "du-lich/choi-gi-an-dau-di-the-nao",
            55: "du-lich/bat-dong-san-du-lich",
            56: "du-lich/cau-chuyen-du-lich",
            57: "du-lich/kham-pha",

            58: "van-hoa/song-dep",
            59: "van-hoa/cau-chuyen-van-hoa",
            60: "van-hoa/khao-cuu",
            61: "van-hoa/xem-nghe",
            62: "van-hoa/sach-hay",
            63: "van-hoa/mon-ngon-ha-noi",
            64: "van-hoa/nghia-tinh-mien-tay",
            65: "van-hoa/hao-khi-mien-dong",

            66: "giai-tri/phim",
            67: "giai-tri/doi-nghe-si",
            68: "giai-tri/truyen-hinh",

            69: "the-thao/bong-da-thanh-nien-sinh-vien",
            70: "the-thao/bong-da-viet-nam",
            71: "the-thao/bong-da-quoc-te",
            72: "the-thao/the-thao-cong-dong",
            73: "the-thao/cac-mon-khac",

            74: "cong-nghe/tin-tuc-cong-nghe",
            75: "cong-nghe/blockchain",
            76: "cong-nghe/san-pham",
            77: "cong-nghe/xu-huong-chuyen-doi-so",
            78: "cong-nghe/thu-thuat",
            79: "cong-nghe/game",

            80: "xe/thi-truong",
            81: "xe/xe-dien",
            82: "xe/danh-gia-xe",
            83: "xe/tu-van",
            84: "xe/xe-giao-thong",
            85: "xe/xe-doi-song",

            86: "thoi-trang-tre/thoi-trang-247",
            87: "thoi-trang-tre/giu-dang",
            88: "thoi-trang-tre/thoi-trang-nghe-nghiep",
            89: "thoi-trang-tre/tan-huong",

            91: "ban-doc/la-thu-tam-su",
            92: "ban-doc/tu-don-thu-ban-doc",
            93: "ban-doc/ban-doc-viet",
            94: "ban-doc/co-quan-chua-tra-loi-ban-doc",
            95: "ban-doc/tra-loi-ban-doc",
            96: "ban-doc/la-lanh-dum-la-rach",
            90: "ban-doc/tam-long-vang",

            97: "tieu-dung-thong-minh/moi-moi-moi",
            98: "tieu-dung-thong-minh/mua-mot-cham",
            99: "tieu-dung-thong-minh/o-dau-re",
            100: "tieu-dung-thong-minh/goc-nguoi-tieu-dung",
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
            container = soup.find("div", class_="header__top-flex")
            h1_tag = container.find("h1") if container else None
            logo_src = h1_tag.find("img")["src"] if h1_tag and h1_tag.find("img") else ""
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footer__bottom"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="footer__bottom")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                meta_tag = soup.find("meta", attrs={"name": "description"})
                info["description"] = meta_tag["content"] if meta_tag else ""
                # License
                if "Giấy phép" in text:
                    license_line = [line for line in lines if "Giấy phép" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép", "").strip()

                # Tổng biên tập
                if "Tổng biên tập:" in text:
                    editor_line = [line for line in lines if "Tổng biên tập:" in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng biên tập:", "").strip()

                # Địa chỉ
                info["address"] = ""

                # Điện thoại
                vals = footer_copyright.select("div.footer__contact p.value")
                phones = [v.get_text(strip=True) for v in vals if v.get_text(strip=True)]

                # nếu muốn chỉ 2 số đầu:
                phones = phones[:2]

                info["phone"] = ", ".join(phones) if phones else ""

                # Email
                ld_json_scripts = soup.find_all("script", type="application/ld+json")

                for script in ld_json_scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict) and data.get("@type") == "Organization":
                            email = data.get("email")
                            if email:
                                info["email"] = email.replace("mailto:", "")
                                break
                    except Exception as e:
                        print(f"❌ Lỗi khi parse JSON-LD: {e}")

                # Thông tin bản quyền
                box = footer_copyright.select_one("div.copy-right")
                infor_copyright = ""
                if box:
                    txt = (box.get_text(" ", strip=True) or "").replace("\xa0", " ")
                    i = txt.lower().find("bản quyền")
                    if i != -1:
                        infor_copyright = txt[i:].strip(' "“”')
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
            title = ""
            title_wrapper = soup.find("h1", class_="detail-title")
            if title_wrapper:
                span_tag = title_wrapper.find("span", attrs={"data-role": "title"})
                if span_tag:
                    title = span_tag.get_text(strip=True) if span_tag else ""

            # Lấy description
            desc_tag = soup.find("h2", class_="detail-sapo")
            description = desc_tag.get_text(strip=True) if desc_tag else ""
            
            
            date_tag = soup.select_one("div.detail-time div[data-role='publishdate']")
            if date_tag:
                raw_text = date_tag.get_text(strip=True)
                match = re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", raw_text)
                publish_date = match.group(0) if match else ""
            else:
                publish_date = ""
            # Lấy tất cả các ảnh trong phần tử này
            content_images = []
            content_div = soup.find("div", class_="detail-content afcbc-body")

            if content_div:
                images = content_div.find_all('img')
                for img in images:
                    src = img.get("src")
                    if src and not src.startswith("data:image") and src.endswith((".jpg", ".jpeg", ".png")):
                        content_images.append(src)
            else:
                print("⚠️ Không tìm thấy thẻ div.detail-content afcbc-body")

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = ""
            content_div = soup.find("div", class_="detail-content afcbc-body", attrs={"data-role": "content"})

            if content_div:
                paragraphs = content_div.find_all("p")
                content = "\n".join(
                    p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
                )
            else:
                print("❌ Không tìm thấy div.detail-content.afcbc-body có data-role=content")

            # Trích xuất tác giả
            author_box = soup.find('a', class_="name")
            author = author_box.get_text(strip=True).rstrip('-').strip() if author_box else ""

            a = soup.select_one("div.detail-cate a[data-role='cate-name'], div.detail-cate a.category-page_name")
            categories = a.get_text(strip=True) if a else ""
            
            location = ""
            pairs = []
            video_url = []
            thumbnail_url = []

            for box in soup.select('div.VCSortableInPreviewMode'):
                v  = (box.get("data-vid") or "").strip()
                th = (box.get("data-thumb") or "").strip()
                if v:
                    v = urljoin(url, v)
                    video_url.append(v)
                if th:
                    th = urljoin(url, th)
                    thumbnail_url.append(th)

                if v or th:
                    pairs.append((v, th))
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
        page_url = f"https://thanhnien.vn/{article_type}.htm"
        driver.get(page_url)
        seen_links = set()
        last_size = 0
        max_pages = 5
        page_count = 0
        wait = WebDriverWait(driver, 10)
        seen_article_ids = set()  # set theo object id hoặc nội dung text

        try:
            while page_count < max_pages:
                previous_count = len(seen_links)

                # Scroll 4 lần
                for i in range(4):
                    driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                    time.sleep(1.5)
                
                articles = driver.find_elements(By.CSS_SELECTOR, "div.box-category-middle div.box-category-item")

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
                                href = urljoin("https://thanhnien.vn", href)
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
                    next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.list__viewmore")))
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
    
    def get_audio_from_article(self, url):
        driver = None
        try:

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
            chrome_options.set_capability("pageLoadStrategy", "eager")

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            headers = {
                "User-Agent": "Mozilla/5.0"
            }
            resp = requests.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, "html.parser")

            article = soup.select_one("div.detail__video-section") or soup
            # 1 AUDIO
            audio_url = ""
            try:
                # đợi có thẻ audio xuất hiện
                audio_el = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "audio"))
                )
                # 1) audio có src trực tiếp
                audio_url = (audio_el.get_attribute("src") or "").strip()
                # 2) fallback: audio > source[src]
                if not audio_url:
                    try:
                        src_el = audio_el.find_element(By.CSS_SELECTOR, "source[src]")
                        audio_url = (src_el.get_attribute("src") or "").strip()
                    except Exception:
                        pass
            except Exception:
                audio_url = ""
    
            # 2 DESCRIPTION
            s_tag = article.select_one("h2.detail-sapo")
            description = s_tag.get_text(strip=True) if s_tag else ""

            # 3PUBLISHED DATE
            t_tag = article.select_one("div.detail-time div")
            time_text = t_tag.get_text(strip=True) if t_tag else ""
            publishedDate = parse_vnexpress_time_ms(time_text)

            # 4AUTHOR
            author = ""
            # CATEGORY
            category = [a.get("title", "").strip() for a in soup.select("div.detail-cate a[title]")]

            # 5 END TIME (tổng thời lượng)
            end_time_mp3 = ""
            try:
                # Đợi có ít nhất 2 thẻ span.afp-duration xuất hiện
                WebDriverWait(driver, 10).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "div.audioPodcastPlayer-time ")) >= 2
                )

                spans = driver.find_elements(By.CSS_SELECTOR, "div.audioPodcastPlayer-time ")
                if len(spans) >= 2:
                    # Đợi cho span thứ 2 khác 00:00
                    WebDriverWait(driver, 10).until(
                        lambda d: spans[1].text.strip() != "00:00"
                    )
                    end_time_mp3 = spans[1].text.strip()
            except Exception as e:
                end_time_mp3 = ""
        except Exception as e:
            print(f"❌ Lỗi trong quá trình crawl {url}: {e}")
            return {
                "audio_url": "",
                "description": "",
                "author": "",
                "duration": "",
                "publishedDate":"",
            }

        finally:
            if driver:
                driver.quit()

        return {
            "audio_url": audio_url,
            "description": content_url,
            "author": author_url,
            "duration": end_time_mp3_url,
            "publishedDate": datetime_url
        }

    def crawl_podcast_bs4(self, category_url: str, number_post: int, crawl_id: Optional[int] = None):
        def build_domain_username(domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"
        base = "thanhnien"
        BASE_DOMAIN = "https://thanhnien.vn/"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(category_url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("div.box-category-item")  # hoặc "article.item-ev" nếu muốn chính xác hơn

        podcasts = []

        for idx, item in enumerate(items):
            if idx >= number_post:
                break
            try:
                # 1. Title + URL
                title_elem = item.select_one("a[title]")
                if not title_elem:
                    continue
                title = title_elem.get("title", "").strip()
                url = title_elem.get("href", "")
                if url.startswith("/"):
                    url = BASE_DOMAIN + url
                # 2. Thumbnail (từ <img> hoặc <source data-srcset>)
                thumb_elem = item.select_one("img")
                thumbnail = thumb_elem.get("src", "") if thumb_elem else ""

                # 3. Category (nếu cần)
                # Lấy category ở đầu trang
                print("u------rl",url)


                meta = self.get_audio_from_article(url)
                audio_url     = meta["audio_url"]
                content_url   = meta["description"]
                author_url    = meta["author"]
                end_time_url  = meta["duration"]
                datetime_url  = meta["publishedDate"]
                category = meta["category"]
                domain_username = build_domain_username(base, author_url) if author_url else ""
                crawled_at = int(datetime.now(timezone.utc).timestamp())
                podcast = {
                    "domain": normalize_url_to_root_https(url),
                    "title": title,
                    "url": url,
                    "thumbnail": thumbnail,
                    "category": category,
                    "audio_url": audio_url,
                    "author": author_url,
                    "description": content_url,
                    "duration": time_to_seconds(end_time_url),
                    "publishedDate": datetime_url,
                    "authorId": domain_username,
                    "crawlId": crawl_id or str(uuid.uuid4()),
                    "crawledAt": crawled_at
                }
                tracking_status = {
                    "id": url,
                    "platform": "news",
                    "data_type": "podcast",
                    "crawled_at": crawled_at,
                    "pre_status": None,
                    "pre_processed_at": None,
                    "pre_message": None,
                    "post_status": None,
                    "post_processed_at": None,
                    "post_message": None,
                    "crawl_id": crawl_id or str(uuid.uuid4()),
                }
                send_tracking_status_to_kafka(tracking_status)
                send_podcast_to_kafka(podcast)
            except Exception as e:
                print(f"⚠️ Lỗi trong quá trình crawl {url}: {e}")
                continue

    def crawl_postcast(self, number_post: int, crawl_id: Optional[int] = None):
        podcast_type_dict = {
            0: "genz.htm",
            1: "showbiz.htm",
        }

        n_category = len(podcast_type_dict)
        per_category = max(1, number_post // n_category)

        BASE_URL = "https://thanhnien.vn/podcast.htm"
        base = re.sub(r'\.html?$', '', BASE_URL.strip())
        base = base.rstrip('/')

        for idx, slug in podcast_type_dict.items():
            category_url = f"{base}/{slug.lstrip('/')}"
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url, number_post=per_categor, crawl_id=crawl_id)
