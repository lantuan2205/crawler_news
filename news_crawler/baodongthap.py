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

class BaoDongThapCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://www.baodongthap.vn/"
        self.article_type_dict = {
            0: "chinh-tri?cate=342",
            1: "kinh-te?cate=343",
            2: "xa-hoi?cate=344",
            3: "phap-luat-an-ninh-trat-tu?cate=345",
            4: "van-hoa-nghe-thuat?cate=353",
            5: "the-thao?cate=361",
            6: "giao-duc?cate=360",
            7: "suc-khoe-y-te?cate=369",
            8: "quoc-te?cate=362",
            9: "khoa-hoc-doi-song?cate=365",
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
        # Sử dụng session từ base class (có thể là proxy session)
        if hasattr(self, 'session'):
            response = self.session.get(url, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)
            
        content = response.content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")

        title = soup.find("h1", class_="title-detail")
        if title == None:
            return None, None, None
        title = title.text

        desc_tag = soup.find("p", class_="description")
        location = ""
        description = ""
        if desc_tag:
            # Lấy thẻ <span class="location-stamp">
            location_tag = desc_tag.find("span", class_="location-stamp")
            if location_tag:
                location = location_tag.get_text(strip=True)
                location_tag.extract()
            description = desc_tag.get_text(strip=True)


        paragraph_tags = soup.find_all("p", class_="Normal")
        if paragraph_tags:
            author = paragraph_tags[-1].text.strip() 
            del paragraph_tags[-1]
        else:
            author = None

        paragraphs = (get_text_from_tag(p) for p in paragraph_tags)
        content = "\n".join(paragraphs)

        # Lấy ngày đăng bài
        time_element = soup.find("span", class_="date")
        published_date = time_element.text.strip() if time_element else None

        categories_array = extract_categories_from_soup(soup)
        if categories_array and isinstance(categories_array[0], list):
            categories_array = categories_array[0]

        # Lấy tags
        tags_array = [tag.get_text(strip=True) for tag in soup.select("div.tags h4.item-tag a")]
        all_categories = categories_array + tags_array
        categories = ", ".join(all_categories)

        # Lấy tất cả các ảnh trong nội dung bài viết
        image_tags = soup.find_all("img", class_="lazy")
        content_image_urls = [img.get("data-src") for img in image_tags if img.get("data-src")]

        thumbnail_url = ""
        video_box = soup.select_one("div.box_img_video img")
        if video_box:
            thumbnail_url = video_box.get("src")

        # --- Lấy video URL bằng Selenium nếu có ---
        video_url = ""
        if has_video:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.set_capability("pageLoadStrategy", "eager")

            driver = None
            try:
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(120)
                driver.set_script_timeout(120)
                driver.get(url)
                try:
                    video_elem = driver.find_element(By.CSS_SELECTOR, "div.video-js")
                    video_url = video_elem.get_attribute("src")
                except NoSuchElementException:
                    pass
            except WebDriverException as e:
                print("⚠️ Lỗi Selenium khi lấy video:", e)
            finally:
                if driver:
                    driver.quit()


        return title, description, content, published_date, author, content_image_urls, categories, video_url, thumbnail_url, location

    def extract_content(self, url: str, has_video) -> tuple:
        # Sử dụng session từ base class (có thể là proxy session)
        if hasattr(self, 'session'):
            response = self.session.get(url, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)
            
        content = response.content
        time.sleep(random.uniform(1, 2))
        soup = BeautifulSoup(content, "html.parser")

        # --- Tiêu đề ---
        title_tag = soup.find("h1", id="title")
        title = title_tag.text.strip() if title_tag else None

        # --- Nội dung ---
        content_div = soup.find("div", id="content")
        paragraphs = []
        if content_div:
            for p in content_div.find_all(["p", "div"], recursive=False):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
        content_text = "\n".join(paragraphs)

        # --- Mô tả ngắn ---
        description = paragraphs[0] if paragraphs else ""

        # --- Tác giả ---
        author = None
        if content_div:
            # Tìm thẻ cuối cùng có style "text-align: right"
            author_tag = content_div.find_all(style=re.compile("text-align:\s*right", re.I))
            if author_tag:
                last_tag = author_tag[-1]  # thường thẻ cuối là tác giả
                author = last_tag.get_text(strip=True)

        # --- Ngày đăng ---
        date_div = soup.find("div", id="current-date")
        published_date = date_div.get_text(strip=True) if date_div else None

        # --- Categories ---
        category_tag = soup.select_one("div#nav a.parent_cate")
        categories = category_tag.get_text(strip=True) if category_tag else ""

        # --- Ảnh bài viết ---
        image_tags = content_div.find_all("img") if content_div else []
        content_image_urls = [urljoin("https://www.baodongthap.vn", img.get("src")) for img in image_tags if img.get("src")]
        print("content_image_urls:", content_image_urls)
        # --- Thumbnail ---
        thumbnail_url = ""
        # --- Location ---
        location = ""

        # --- Video ---
        video_url = ""
        if has_video:
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-popup-blocking")
            chrome_options.add_argument("--disable-notifications")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.set_capability("pageLoadStrategy", "eager")

            driver = None
            try:
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(120)
                driver.set_script_timeout(120)
                driver.get(url)
                try:
                    video_elem = driver.find_element(By.CSS_SELECTOR, "div.video-js")
                    video_url = video_elem.get_attribute("src")
                except NoSuchElementException:
                    pass
            except WebDriverException as e:
                print("⚠️ Lỗi Selenium khi lấy video:", e)
            finally:
                if driver:
                    driver.quit()

        return title, description, content_text, published_date, author, content_image_urls, categories, video_url, thumbnail_url, location

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
        page_url = f"https://www.baodongthap.vn/{article_type}&page={page_number}"
        if(page_number == 20):
            return []
        articles_urls = []
        try:
            # Sử dụng session từ base class nếu có
            if hasattr(self, 'session'):
                print(f"[INFO] Đã sử dụng session từ base class")
                response = self.session.get(page_url, headers=headers, timeout=10)
            else:
                print(f"[INFO] Đã sử dụng requests")
                response = requests.get(page_url, headers=headers, timeout=10)

            content = response.content
            time.sleep(random.uniform(1, 2))

            soup = BeautifulSoup(content, "html.parser")
            cate_content = soup.find("div", id="cate-content")
            if not cate_content:
                self.logger.info(f"Không tìm thấy danh sách bài viết trong {page_url}")
                return []

            items = cate_content.find_all("div", class_="item")
            if not items:
                self.logger.info(f"Không tìm thấy bài viết trong {page_url}")
                return []

            for item in items:
                a_tag = item.find("a", class_="title")
                if a_tag and a_tag.get("href"):
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

    def get_all_articles_by_keyword(self, page_url):
        print(f"page_url: {page_url}")
        try:
            # Sử dụng session từ base class (có thể là proxy session)
            if hasattr(self, 'session'):
                response = self.session.get(page_url, headers=headers, timeout=10)
            else:
                response = requests.get(page_url, headers=headers, timeout=10)
                
            content = response.content
            sleep_time = random.uniform(1, 2)
            time.sleep(sleep_time)
            soup = BeautifulSoup(content, "html.parser")
            urls = set()
            # Tìm tất cả thẻ <article> có data-url
            for article in soup.find_all("article"):
                data_url = article.get("data-url")
                if data_url and data_url.startswith("https://vnexpress.net/"):
                    urls.add(data_url)

            return list(urls)
        except Exception as e:
            return []

    # def get_audio_from_article(self, url):
    #     chrome_options = Options()
    #     chrome_options.add_argument("--headless=new")
    #     chrome_options.add_argument("--disable-gpu")
    #     chrome_options.add_argument("--no-sandbox")
    #     chrome_options.add_argument("--remote-debugging-port=9222")
    #     chrome_options.add_argument("--disable-images")
    #     # chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    #     chrome_options.add_argument("--disable-extensions")
    #     chrome_options.add_argument("--disable-popup-blocking")
    #     chrome_options.add_argument("--disable-notifications")
    #     chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    #     chrome_options.set_capability("pageLoadStrategy", "eager")
    #     driver = webdriver.Chrome(options=chrome_options)
    #     try:
    #         driver.get(url)
    #         headers = {
    #             "User-Agent": "Mozilla/5.0"
    #         }
    #         resp = requests.get(url, headers=headers)
    #         soup = BeautifulSoup(resp.text, "html.parser")

    #         article = soup.select_one("div.section_podcast_detail_newver") or soup

    #         # 1 AUDIO
    #         tag = article.find("audio", src=True) or article.find("source", src=True) or article.find("video", src=True)
    #         if tag:
    #             audio_url = (tag.get("src") or "").strip()
    #         else:
    #             players = article.find_all(attrs={"data-player": True})
    #             for p in players:
    #                 raw = p.get("data-player", "")
    #                 if not raw:
    #                     continue
    #                 try:
    #                     data_clean = raw.replace("&quot;", '"').replace("&#34;", '"').replace("'", '"')
    #                     data_json = json.loads(data_clean)
    #                     playlist = data_json.get("playlist", [])
    #                     if playlist:
    #                         first = playlist[0]
    #                         if not audio_url and "src" in first:
    #                             audio_url = (first.get("src") or "").strip()
    #                         dur = first.get("duration") or first.get("time") or ""
    #                         if dur:
    #                             end_time_mp3 = str(dur).strip()
    #                         break
    #                 except Exception:
    #                     pass

    #         # 2 DESCRIPTION
    #         s_tag = article.select_one("p.description")
    #         description = s_tag.get_text(strip=True) if s_tag else ""

    #         # 3PUBLISHED DATE
    #         t_tag = article.select_one("span.date")
    #         time_text = t_tag.get_text(strip=True) if t_tag else ""
    #         publishedDate = parse_vnexpress_time_ms(time_text)

    #         # 4AUTHOR
    #         a_tag = article.select_one("span.author-in-player")
    #         author = a_tag.get_text(strip=True) if a_tag else ""

    #         # 5 END TIME (tổng thời lượng)
    #         end_time_mp3 = ""
    #         try:
    #             # Đợi có ít nhất 2 thẻ span.afp-duration xuất hiện
    #             WebDriverWait(driver, 10).until(
    #                 lambda d: len(d.find_elements(By.CSS_SELECTOR, "span.afp-duration")) >= 2
    #             )

    #             spans = driver.find_elements(By.CSS_SELECTOR, "span.afp-duration")
    #             if len(spans) >= 2:
    #                 # Đợi cho span thứ 2 khác 00:00
    #                 WebDriverWait(driver, 10).until(
    #                     lambda d: spans[1].text.strip() != "00:00"
    #                 )
    #                 end_time_mp3 = spans[1].text.strip()
    #         except Exception as e:
    #             print("⚠️ Không lấy được end_time_mp3:", e)
    #             end_time_mp3 = ""
    #     finally:
    #         if driver:
    #             driver.quit()
        
    #     return {
    #         "audio_url": audio_url,
    #         "description": description,
    #         "author": author,
    #         "duration": end_time_mp3,
    #         "publishedDate": publishedDate,
    #     }

    # def crawl_podcast_bs4(self, category_url: str, number_post: int, crawl_id: Optional[str] = None):
    #     def build_domain_username(domain, author_url):
    #         return f"{domain}_{author_url.replace(' ', '')}"
    #     base = "vnexpress"
    #     headers = {
    #         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    #     }
    #     response = requests.get(category_url, headers=headers, timeout=15)
    #     response.raise_for_status()

    #     soup = BeautifulSoup(response.text, "html.parser")
    #     items = soup.select("article")  # hoặc "article.item-ev" nếu muốn chính xác hơn

    #     podcasts = []

    #     for idx, item in enumerate(items):
    #         if idx >= number_post:
    #             break
    #         try:
    #             # 1. Title + URL
    #             title_elem = item.select_one("a[title]")
    #             if not title_elem:
    #                 continue
    #             title = title_elem.get("title", "").strip()
    #             url = title_elem.get("href", "")

    #             # 2. Thumbnail (từ <img> hoặc <source data-srcset>)
    #             thumb_elem = item.select_one("img")
    #             thumbnail = thumb_elem.get("src", "") if thumb_elem else ""

    #             # 3. Category (nếu cần)
    #             # Lấy category ở đầu trang
    #             cat_tag = soup.select_one("h1.name-s")
    #             category = cat_tag.get_text(strip=True) if cat_tag else ""


    #             meta = self.get_audio_from_article(url)
    #             audio_url     = meta["audio_url"]
    #             content_url   = meta["description"]
    #             author_url    = meta["author"]
    #             end_time_url  = meta["duration"]
    #             datetime_url  = meta["publishedDate"]
    #             domain_username = build_domain_username(base, author_url) if author_url else ""

    #             podcast = {
    #                 "domain": normalize_url_to_root_https(url),
    #                 "title": title,
    #                 "url": url,
    #                 "thumbnail": thumbnail,
    #                 "category": category,
    #                 "audio_url": audio_url,
    #                 "author": author_url,
    #                 "description": content_url,
    #                 "duration": time_to_seconds(end_time_url),
    #                 "publishedDate": datetime_url,
    #                 "authorId": domain_username,
    #                 "crawlId": crawl_id or str(uuid.uuid4())
    #             }
    #             send_podcast_to_kafka(podcast)
    #         except Exception as e:
    #             print(f"⚠️ Lỗi trong quá trình crawl {url}: {e}")
    #             continue

    # def crawl_postcast(self, number_post: int, crawl_id: Optional[str] = None):
    #     podcast_type_dict = {
    #         0: "toi-ke",
    #         1: "vnexpress-hom-nay",
    #         2: "giai-ma",
    #         3: "hop-den",
    #         4: "ho-so-toi-ac",
    #         5: "tai-chinh-ca-nhan",
    #         6: "tham-thi",
    #         7: "ho-noi-gi",
    #         8: "news-explainer",
    #         9: "nguoi-tro-ve",
    #         10: "ban-on-khong",
    #         11: "tien-lam-gi",
    #         12: "ly-hon",
    #         13: "toi-trong-guong",
    #         14: "nguy-co",
    #         15: "diem-tin"
    #     }
    #     n_category = len(podcast_type_dict)
    #     per_category = max(1, number_post // n_category)
    #     BASE_URL = "https://vnexpress.net/vne-go/podcast/"

    #     for idx, slug in podcast_type_dict.items():
    #         category_url = BASE_URL + slug
    #         print(f"🔎 Crawl category {slug} => {category_url}")
    #         self.crawl_podcast_bs4(category_url, number_post=per_category, crawl_id=crawl_id)
