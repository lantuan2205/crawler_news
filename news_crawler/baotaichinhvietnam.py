import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from urllib.parse import urljoin, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
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

class BaoTaiChinhVietNamCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thoibaotaichinhvietnam.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "kinh-te",
            2: "tai-chinh",
            3: "thue-hai-quan",
            4: "chung-khoan",
            5: "ngan-hang",
            6: "bao-hiem",
            7: "kinh-doanh",
            8: "bat-dong-san",
            9: "phap-luat",
            10: "gia-ca",
            11: "xa-hoi",
            12: "quoc-te"                                                             
        }   

    def extract_profile_domain(self, url: str):
        job_id = 1
        DOMAIN_URL= "https://thoibaotaichinhvietnam.vn"
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
            container = soup.find("div", class_="logo-bar")
            h1_tag = container.find("h1") if container else None
            logo_src = h1_tag.find("img")["src"] if h1_tag and h1_tag.find("img") else None
            info["logo"] = DOMAIN_URL + logo_src
            
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footer-info"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="footer-info")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                if len(lines) >= 2:
                    info["description"] = f"{lines[0]} - {lines[1]}"

                # License
                if "Giấy phép báo điện tử:" in text:
                    license_line = [line for line in lines if "Giấy phép báo điện tử:" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép báo điện tử:", "").strip()

                # Tổng biên tập
                # trong toàn trang (hoặc giới hạn vào footer nếu muốn)
                name = ""
                node = soup.find(string=lambda s: s and "tổng biên tập" in s.lower())
                if node:
                    strong = node.find_next("strong")
                    name = strong.get_text(strip=True) if strong else ""

                info["editor_in_chief"] = name

                # Địa chỉ
                if "Tòa soạn:" in text:
                    addr_line = [line for line in lines if "Tòa soạn:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Tòa soạn:", "").strip()

                # Điện thoại
                phone_line = footer_copyright.select("strong")[-1]
                if phone_line:
                    info["phone"] = phone_line.get_text(strip=True)

                # Email
                email_tag = footer_copyright.select_one("a[href^=mailto]")
                if email_tag:
                    info["email"] = email_tag.get_text(strip=True).replace("Email:", "").strip()

                # Thông tin bản quyền
                last_p = footer_copyright.select("b")[-1]
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
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = soup.find("h1", class_="post-title")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy tên tác giả
            author_tag = soup.find("h2", class_="author-title")
            if author_tag and author_tag.get_text(strip=True):
                author = author_tag.get_text(strip=True)
            else:
                # Nếu không có, lấy từ <div class="post-author">
                fallback_tag = soup.find("div", class_="post-author")
                author = fallback_tag.get_text(strip=True) if fallback_tag else None

            # Lấy description
            desc_div = soup.find("div", class_="post-desc")
            description = desc_div.get_text(strip=True) if desc_div else None

            # Trích xuất ngày viết bài
            time_tag = soup.find("span", class_="article-publish-time")
            if time_tag:
                time_part = time_tag.find("span", class_="format_time")
                date_part = time_tag.find("span", class_="format_date")
                if time_part and date_part:
                    publish_date = f"{time_part.get_text(strip=True)} {date_part.get_text(strip=True)}"

            content_div = soup.find("div", class_="post-content")
            paragraphs = content_div.find_all("p")
            content = "\n\n".join(p.get_text(strip=True) for p in paragraphs)

            images = content_div.find_all("img")
            content_images = [img['src'] for img in images if img.get('src')]
            a = soup.select_one("div.catname a")
            categories = a.get_text(strip=True) if a else ""
            video_url = ""
            thumbnail_url = ""
            location = ""
            return title, description, content, publish_date, author, content_images,categories, video_url, thumbnail_url, location

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
        if page_number == 5:
            return []
        page_number = (page_number - 1) * 15
        page_url = f"https://thoibaotaichinhvietnam.vn/{article_type}&s_cond=&BRSR={page_number}"
        
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        target_div = soup.find("div", class_="cat-listing bg-dots mt20 pt20 article-bdt-20 thumb-w250 title-22 no-catname")

        urls = []
        if target_div:
            a_tags = target_div.find_all("h3", class_="article-title")
            if(len(a_tags) == 0):
                return []
            for a_tag in a_tags:
                tag = a_tag.find("a")
                if tag and tag.get("href"):
                    urls.append(tag["href"])

        return urls

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
            base_url = "https://thoibaotaichinhvietnam.vn/"

            articles = soup.select("div.cat-content article.article")
            for article in articles:
                a_tag = article.select_one("a.article-thumb")
                if a_tag:
                    relative_url = a_tag.get("href")
                    url = base_url + relative_url.lstrip("/")
                    urls.add(url)
            return list(urls)
        except Exception as e:
            return []
        
    def get_audio_from_article(self, url):
        try:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--blink-settings=imagesEnabled=false")

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)

            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            article = soup.select_one("div.podcast-detail")

            audio_tag = soup.find("audio", src=True)
            if audio_tag:
                audio_url = audio_tag.get("src", "").strip()

             #2 DESCRIPTION
            s_tag = article.select_one("div.podcast-desc")
            description = s_tag.get_text(strip=True) if s_tag else ""


            # 3PUBLISHED DATE
            t_tag = article.select_one("span.podcast-publish-time")
            time_text = t_tag.get_text(strip=True) if t_tag else ""
            publishedDate = parse_vnexpress_time_ms(time_text)

            # 4AUTHOR
            a_tag = article.select_one("div.podcast-author")
            author = a_tag.get_text(strip=True) if a_tag else ""


            duration_tag = article.select("span.pcast-duration.pcast-time")
            if duration_tag:
                end_time_mp3_url = duration_tag[-1].get_text(strip=True)

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
            "description": description,
            "author": author,
            "duration": end_time_mp3_url,
            "publishedDate": publishedDate,
        }

    def crawl_podcast_bs4(self, category_url: str, number_post: int):
        def build_domain_username(domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        # Lấy domain gốc để join URL tuyệt đối
        parsed = urlparse(category_url)
        domain = "thoibaotaichinhvietnam"
        BASE_DOMAIN = f"{parsed.scheme}://{parsed.netloc}"

        seen_urls = set()
        offset = 0
        page_size = None  # sẽ tự suy ra sau trang đầu

        try:
            while True:
                # build URL phân trang: …&BRSR=<offset>
                # nếu category_url đã có query thì nối bằng '&', ngược lại dùng '?'
                sep = '&'
                page_url = f"{category_url}{sep}BRSR={offset}"
                try:
                    resp = requests.get(page_url, headers=headers, timeout=15)
                    resp.raise_for_status()
                except requests.exceptions.RequestException as e:
                    print(f"⚠️ Lỗi tải {page_url}: {e}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # Lấy item bài viết
                items = soup.select("div.cat-content.clearfix article.article")
                if not items:
                    # Không còn dữ liệu => dừng
                    print(f"✅ Hết bài ở {page_url}, dừng.")
                    break

                # Suy ra page_size ở lần đầu (để tăng offset)
                if page_size is None:
                    page_size = len(items)
                    if page_size <= 0:
                        page_size = 12  # fallback

                new_count = 0

                for idx, item in enumerate(items):
                    if idx >= number_post:
                        break
                    # 1) Title + URL
                    title_elem = item.select_one("a[title]")
                    if not title_elem:
                        continue

                    title = title_elem.get("title", "").strip()
                    url = title_elem.get("href", "") or ""

                    # Chuẩn hoá URL tuyệt đối
                    url = urljoin(BASE_DOMAIN, url)

                    # Chống trùng
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    new_count += 1

                    # 2) Thumbnail
                    thumb_elem = item.select_one("img")
                    thumbnail = ""
                    if thumb_elem:
                        thumbnail = thumb_elem.get("src") or thumb_elem.get("data-src") or thumb_elem.get("data-original") or ""

                    # 3) Category (nếu không có trong item thì để rỗng)
                    category = ""
                    cat_tag = item.select_one("a.box-category-category")
                    if cat_tag:
                        category = cat_tag.get_text(strip=True)

                    # 4) Audio URL
                    meta = self.get_audio_from_article(url)
                    audio_url     = meta["audio_url"]
                    content_url   = meta["description"]
                    author_url    = meta["author"]
                    end_time_url  = meta["duration"]
                    datetime_url  = meta["publishedDate"]
                    domain_username = build_domain_username(domain, author_url) if author_url else ""

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
                    }
                    send_podcast_to_kafka(podcast)

                # Nếu trang này không có bài mới nào so với những gì đã thấy → dừng
                if new_count == 0:
                    break

                # tăng offset cho trang kế tiếp
                offset += page_size

                # ngủ ngẫu nhiên tránh bị chặn
                time.sleep(random.uniform(1, 2.5))

        except Exception as e:
            print("❌ Lỗi trong quá trình crawl:", e)

    def crawl_postcast(self,  number_post: int):
        podcast_type_dict = {
            0: "podcasts",
        }

        BASE_URL = "https://thoibaotaichinhvietnam.vn/"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url, number_post)
