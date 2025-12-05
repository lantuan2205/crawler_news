import os
import requests
import sys
from pathlib import Path
import re
from bs4 import NavigableString, Tag
import uuid

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
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class CongAnNhanDanCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://cand.com.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "su-kien-binh-luan-thoi-su",
            2: "van-de-hom-nay-thoi-su",
            3: "chong-dien-bien-hoa-binh",
            4: "nhan-quyen",
            5: "cong-an",
            6: "lanh-dao-bo-cong-an",
            7: "gin-giu-hoa-binh-lhq",
            8: "hoat-dong-ll-cand",
            9: "guong-sang",
            10: "xa-hoi",
            11: "giao-duc",
            12: "giao-thong",
            13: "y-te",
            14: "doi-song",
            15: "phong-su-tu-lieu",
            16: "phap-luat",
            17: "ban-tin-113",
            18: "lan-theo-dau-vet-toi-pham",
            19: "thonng-tin-phap-luat",
            20: "quoc-te",
            21: "the-gioi-24h",
            22: "binh-luan-quoc-te",
            23: "tu-lieu-quoc-te",
            24: "vu-khi-chien-tranh",
            25: "van-hoa",
            26: "Chuyen-dong-van-hoa",
            27: "the-thao",
            28: "Tieu-diem-van-hoa",
            29: "van-hoa-24h",
            30: "giai-tri-van-hoa",
            31: "ban-doc-cand",
            32: "dieu-tra-theo-don-ban-doc",
            33: "hop-thu",
            34: "giai-dap-phap-luat",
            35: "tai-chinh-40",
            36: "Kinh-te",
            37: "dia-oc",
            38: "Thi-truong",
            39: "doanh-nghiep",
            40: "cuoc-song-muon-mau",
            41: "hon-nhan-gia-dinh",
            42: "Chuyen-kho-tin-nhung-co-that-goc",
            43: "Khoa-hoc-Quan-su",
            44: "the-gioi-phuong-tien",
            45: "Van-hoa-PT",
            46: "Cong-nghe",
            47: "eMagazine",
            48: "Xa-hoi-tu-thien",
            49: "nhip-cau-nhan-ai",
            50: "Vuot-len-so-phan",

    }

    def extract_profile_domain(self, url: str):
        job_id = 1
        info = {
            "name": url,
            "description": "",
            "license": "",
            "editor_in_chief": "",
            "address": "",
            "phone": "",
            "email": "",
            "infor_copyright": "",
            "jobId": job_id or str(uuid.uuid4()),
            "logo": "",
        }

        # --- Phase 1: lấy logo bằng requests ---
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            container = soup.find("div", class_="logo")
            p_tag = container.find("p") if container else None
            logo_src = p_tag.find("img")["src"] if p_tag and p_tag.find("img") else ""
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "section.footersite"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("section", class_="footersite")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                meta_tag = soup.find("meta", attrs={"name": "description"})
                info["description"] = meta_tag["content"] if meta_tag else ""
                # License
                if "Giấy phép hoạt động báo chí" in text:
                    license_line = [line for line in lines if "Giấy phép hoạt động báo chí" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép hoạt động báo chí", "").strip()

                # Tổng biên tập
                if "Tổng Biên tập: " in text:
                    editor_line = [line for line in lines if "Tổng Biên tập: " in line]
                    if editor_line:
                        info["editor_in_chief"] = editor_line[0].replace("Tổng Biên tập: ", "").strip()

                # Địa chỉ
                addr = ""
                b = soup.find("b", string=lambda s: s and "trụ sở" in s.lower())
                if b:
                    chunks = []
                    for sib in b.next_siblings:
                        if isinstance(sib, Tag) and sib.name == "b":
                            break
                        if isinstance(sib, Tag):
                            if sib.name == "br":
                                continue
                            txt = sib.get_text(" ", strip=True)
                        else:
                            txt = str(sib)
                        txt = txt.replace("\u200b", "").strip(' :"\n\t')
                        if txt:
                            chunks.append(txt)
                    addr = " ".join(chunks)
                    # làm sạch khoảng trắng thừa
                    addr = re.sub(r"\s{2,}", " ", addr)
                info["address"] = addr

                # Điện thoại                
                phone = ""
                b = soup.find("b", string=lambda s: s and "điện thoại" in s.lower())
                if b:
                    parts = []
                    for sib in b.next_siblings:
                        if isinstance(sib, Tag) and sib.name == "b":
                            break
                        txt = sib.get_text(" ", strip=True) if isinstance(sib, Tag) else str(sib)
                        txt = txt.replace("\u200b", "").strip()
                        if txt:
                            parts.append(txt)
                    phone = " ".join(parts).strip(' :"\n\t')
                info["phone"] = phone

                # Email
                email_text = ""
                b = soup.find("b", string=lambda s: s and "email" in s.lower())
                if b:
                    parts = []
                    for sib in b.next_siblings:
                        if isinstance(sib, Tag) and sib.name == "b":
                            break
                        txt = sib.get_text(" ", strip=True) if isinstance(sib, Tag) else str(sib)
                        txt = txt.replace("\u200b", "").strip()
                        if txt:
                            parts.append(txt)
                    email_text  = " ".join(parts).strip(' :"\n\t')
                info["email"] = email_text 
                # Ban quyen
                copyright_div = soup.select_one("div.footer-bottom")
                if copyright_div:
                    text = copyright_div.get_text(" ", strip=True)
                    info["infor_copyright"] = text


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
            title_tag = soup.find('h1', class_='box-title-detail')
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Lấy description
            desc_tag = soup.select_one("div.box-des-detail p")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Trích xuất ngày viết bài
            publish_date = ""
            date_tag = soup.find("div", class_='box-date')
            publish_date = date_tag.get_text(strip=True).rstrip('|').strip() if date_tag else ""

            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="detail-content-body")
            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]
            if not content_div:
                return [], []

            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            images = content_div.find_all("img")
            content_images = [img.get("src") for img in images if img.get("src")]

            # Trích xuất tác giả
            author_box = soup.find('div', class_='box-author')
            author_tag = author_box.find('strong')
            author = author_tag.get_text(strip=True).rstrip('-').strip() if author_tag else ""
            location = ""
            categories = ""
            ul = soup.find("ul", class_="uk-breadcrumb")
            if ul:
                items = ul.find_all("li", class_="bc-item", limit=2)
                names = [i.get_text(strip=True) for i in items if i]
                categories = " > ".join(names)

            video_url = ""
            box = soup.find("div", class_="videoEmbed")
            if box:
                # <video src> hoặc <video><source src>
                v = box.find("video")
                if v:
                    video_url = (v.get("src")
                                or (v.find("source") and v.find("source").get("src"))
                                or "")
                else:
                    # <iframe src> hoặc data-vid
                    iframe = box.find("iframe")
                    video_url = (iframe.get("src") if iframe else (box.get("data-vid") or "")).strip()
            # thumb

            thumbnail_url = ""
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

                try:
                    driver.switch_to.default_content()

                    # 1) tìm đúng iframe YouTube rồi switch vào
                    yt_iframe = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((
                            By.CSS_SELECTOR,
                            'iframe[src*="youtube.com"], iframe[src*="youtube-nocookie.com"]'
                        ))
                    )
                    driver.switch_to.frame(yt_iframe)

                    # 2) lấy background-image của div ytp-cued-thumbnail-overlay-image
                    poster = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div.ytp-cued-thumbnail-overlay-image"))
                    )
                    style_attr = poster.get_attribute("style") or ""
                    m = re.search(r'url\((["\']?)(.*?)\1\)', style_attr)
                    if m:
                        thumbnail_url = m.group(2).strip()
                    else:
                        # computed style fallback
                        bg = driver.execute_script(
                            "return getComputedStyle(arguments[0]).getPropertyValue('background-image');", poster
                        ) or ""
                        m2 = re.search(r'url\((["\']?)(.*?)\1\)', bg)
                        thumbnail_url = m2.group(2).strip() if m2 else ""

                    driver.switch_to.default_content()
                except TimeoutException:
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
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
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

            # ==== Đợi đúng container comment xuất hiện ====
            root_sel = "div.box-content.box-comment-list.bounder-content-data[data-id='comments']"
            try:
                root_el = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, root_sel))
                )
            except TimeoutException:
                print("❌ Không thấy container comment")
                return []

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", root_el)

            # ==== Bấm 'Xem thêm' tới khi hết ====
            def article_count(drv):
                return len(drv.find_elements(
                    By.CSS_SELECTOR,
                    "div.uk-comment-list-bounder ul.uk-comment-list li > article.uk-comment"
                ))

            while True:
                before = article_count(driver)
                try:
                    show_more_btn = WebDriverWait(driver, 2).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "a.btn-next"))
                    )
                except TimeoutException:
                    break  # không có nút

                # nếu nút đang disabled/ẩn thì dừng
                cls = (show_more_btn.get_attribute("class") or "").lower()
                aria = (show_more_btn.get_attribute("aria-disabled") or "").lower()
                style_display = (show_more_btn.value_of_css_property("display") or "").lower()
                if "disabled" in cls or "uk-disabled" in cls or aria == "true" or style_display == "none":
                    break

                # cuộn và click
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", show_more_btn)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", show_more_btn)

                try:
                    WebDriverWait(driver, 5).until(lambda d: article_count(d) > before)
                except TimeoutException:
                    break

            soup = BeautifulSoup(driver.page_source, "html.parser")
            comments = []

            root = soup.select_one(root_sel)
            bounder = root.select_one("div.uk-comment-list-bounder") if root else None
            items = bounder.select("ul.uk-comment-list li > article.uk-comment") if bounder else []

            for item in items:
                nickname = item.select_one("a.author-name")
                username = nickname.get_text(strip=True) if nickname else ""


                content_tag = item.select_one("div.uk-comment-body p") or item.select_one("div.uk-comment-body")
                content = content_tag.get_text(" ", strip=True).replace(username, "") if content_tag else ""

                time_tag = item.select_one("small.uk-comment-date")
                time_text = time_tag.get_text(strip=True) if time_tag else ""
                time_comment = parse_vnexpress_time_ms(time_text)

                reactions = {}
                a = item.select_one("small.uk-comment-like a.btn-like")
                reactions["Like"] = int(a.get("data-like", "0")) if a else 0

                comments.append({
                    "domain": normalize_url_to_root_https(url),
                    "url": url,
                    "commentId": f"{username}_{uuid.uuid4().hex}",
                    "userId": username,
                    "username": username,
                    "userUrl": "",
                    "avatar": "",
                    "content": content,
                    "time": time_comment,
                    "reactions": reactions,
                    "replyCount": 0
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
        chrome_options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,  # tắt ảnh
                "profile.managed_default_content_settings.javascript": 1,  # bật JS
            }
        )
        chrome_options.set_capability("pageLoadStrategy", "eager")
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://cand.com.vn/{article_type}"
        driver.get(page_url)
        seen_links = set()
        last_size = 0
        max_pages = 5
        page_count = 0
        ul_element = driver.find_element(By.CSS_SELECTOR, "div.box-widget-loaded")
        try:
            while page_count < max_pages:
                wait = WebDriverWait(driver, 10)

                container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.box-widget-loaded")))
                articles = container.find_elements(By.TAG_NAME, "article")

                for article in articles:
                    anchors = article.find_elements(By.TAG_NAME, "a")
                    for a in anchors:
                        href = a.get_attribute("href")
                        if href and href.startswith("http") and href not in seen_links:
                            seen_links.add(href)

                # articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.box-category-title-text a")
                # # Lấy các bài viết hiện tại
                # for article in articles:
                #         link = article.get_attribute("href")
                #         seen_links.add(link)
    
                # print(f"📄 Đã lấy được {len(seen_links)} bài.")

                # Nếu không có thêm bài mới → thoát
                if len(seen_links) == last_size:
                    print("✅ Không còn bài mới. Dừng lại.")
                    break
                last_size = len(seen_links)

                # Cuộn xuống một chút sau mỗi lần nhấn
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
                time.sleep(1)

                try:
                        next_button = driver.find_element(By.CSS_SELECTOR, "a.btn-next-page")
                        driver.execute_script("arguments[0].scrollIntoView();", next_button)
                        next_button.click()
                        print("➡️ Đã click nút 'Trang sau'")
                        time.sleep(1)
                        page_count += 1

                except Exception:
                        print("✅ Không còn nút Trang sau. Dừng lại.")
                        break
        finally:    
            driver.quit()

        return seen_links
    
    def get_all_articles(self, category):
        
        all_articles = []

        urls = get_urls_of_type(self, category)
        all_articles.extend(urls)

        return all_articles
