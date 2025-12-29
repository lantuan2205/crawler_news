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

class BaoCaoBangCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baocaobang.vn/"
        self.article_type_dict = {
            0: "Xa-hoi",
            1: "Van-hoa",
            2: "Giao-duc",
            3: "kinh-te",
            4: "Suc-khoe-Doi-song",
            5: "Khoa-hoc-cong-nghe",
            6: "The-gioi",
            7: "The-thao",
            8: "Chinh-tri",
            9: "Thoi-su",
            10: "Quoc-phong-An-ninh"
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
                banner_div = soup.find("div", class_="banner")
                logo_img = banner_div.find("img") if banner_div else None
                if logo_img and logo_img.get("src"):
                    info["logo"] = urljoin(url, logo_img["src"])
            except:
                pass

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
                    # --- Phase 2: lấy footer bằng Selenium ---

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
                print("⚠️ Load trang quá lâu, bỏ qua:", url)
                return info

            # Chờ footer load (chỉ cần 1 trong 2 cột)
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.col-md-5, div.col-md-7"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")

            # =========================
            # COL LEFT (col-md-5)
            # =========================
            left_col = soup.select_one(
                "div.col-md-5:has(div.footer-text), div.col-md-5:has(div.footer-white)"
            )
            if left_col:
                # -------- Address --------
                addr_p = left_col.select_one("div.footer-text p")
                if addr_p and "Trụ sở" in addr_p.get_text():
                    info["address"] = (
                        addr_p.get_text(strip=True)
                        .replace("Trụ sở:", "")
                        .strip()
                    )

                # -------- Phone & Fax --------
                phone_block = left_col.select_one("div.footer-white")
                if phone_block:
                    phone_text = phone_block.get_text(" ", strip=True)

                    if "Điện thoại:" in phone_text:
                        info["phone"] = (
                            phone_text.split("Điện thoại:")[1]
                            .split("Fax:")[0]
                            .strip(" -")
                        )

                    if "Fax:" in phone_text:
                        info["fax"] = phone_text.split("Fax:")[1].strip()

                # -------- Emails (nhiều email) --------
                emails = [
                    a.get_text(strip=True)
                    for a in left_col.select("a[href^=mailto]")
                ]
                if emails:
                    info["email"] = ", ".join(emails)

            # =========================
            # COL RIGHT (col-md-7)
            # =========================
            right_col = soup.select_one("div.col-md-7 div.license")
            if right_col:
                full_text = right_col.get_text("\n", strip=True)
                lines = [l.strip() for l in full_text.split("\n") if l.strip()]

                # Description (dòng đầu tiên)
                if lines:
                    info["description"] = lines[0]

                for line in lines:
                    if "Giấy phép số:" in line:
                        info["license"] = line.replace("Giấy phép số:", "").strip()

                    elif "Giám đốc:" in line:
                        info["director"] = line.replace("Giám đốc:", "").strip()

                    elif "Phó Giám đốc:" in line:
                        info["deputy_director"] = line.replace("Phó Giám đốc:", "").strip()

                    elif "Bản quyền" in line:
                        info["infor_copyright"] = line

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

    def extract_content(self, url: str, has_video=False) -> tuple:
        if hasattr(self, 'session'):
            response = self.session.get(url, headers=headers, timeout=10)
        else:
            response = requests.get(url, headers=headers, timeout=10)

        soup = BeautifulSoup(response.content, "html.parser")

        # --- Title ---
        title_tag = soup.select_one("h1.name")
        title = title_tag.get_text(strip=True) if title_tag else None

        # --- Published date ---
        date_div = soup.select_one("div.date")
        published_date = None
        if date_div:
            published_date = date_div.get_text(" ", strip=True).split("[")[0].strip()

        # --- Content ---
        content_div = soup.select_one(
            "div#content-detail, div.detail.auto-gallery"
        )

        paragraphs = []

        if content_div:
            for p in content_div.find_all("p"):
                text = p.get_text(strip=True)
                if text:
                    paragraphs.append(text)
        else:
            print("⚠️ content_div not found:", url)

        content_text = "\n".join(paragraphs)

        # --- Description ---
        description = paragraphs[0] if paragraphs else ""

        # --- Author ---
        author = None
        if content_div:
            author_tag = content_div.select_one("div.pseudonym")
            if author_tag:
                author = author_tag.get_text(strip=True)

        # --- Images ---
        content_image_urls = []
        if content_div:
            for img in content_div.find_all("img"):
                src = img.get("src")
                if src:
                    content_image_urls.append(src)

        # --- Categories (HTML không có) ---
        category_tag = soup.select_one("div.breadcrumbs ol.breadcrumb li a")
        categories = category_tag.get_text(strip=True) if category_tag else ""

        # --- Thumbnail ---
        thumbnail_url = content_image_urls[0] if content_image_urls else ""

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

    CATEGORY_MAP = {
        "Xa-hoi": 61,
        "Van-hoa": 62,
        "Giao-duc": 63,
        "kinh-te": 59,
        "Suc-khoe-Doi-song": 66,
        "Khoa-hoc-cong-nghe": 65,
        "The-gioi": 60,
        "The-thao": 64,
        "Chinh-tri":58 ,
        "Thoi-su": 57,
        "Quoc-phong-An-ninh": 67,
    }

    def get_urls_of_type_thread(self, article_type, page_number):
        if(page_number == 3):
            return []

        category_id = self.CATEGORY_MAP.get(article_type)
        if not category_id:
            print(f"[WARN] Không map được category_id cho {article_type}")
            return []
        params = {
            "page": page_number,
            "limit": 12,
            "category_id": category_id,
            "show_thumb": "true",
            "show_desc": "true",
        }

        API_URL = "https://baocaobang.vn/list-post-by-category"

        HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9",
            "Referer": "https://baocaobang.vn/",
            "X-Requested-With": "XMLHttpRequest",
            "Connection": "keep-alive",
        }

        try:
            resp = requests.get(
                API_URL,
                headers=HEADERS,
                params=params,
                timeout=10
            )

            if resp.status_code != 200 or not resp.text.strip():
                return []

            data = resp.json()
            items = data.get("data", [])

            if not items:
                return []

            links = []
            for item in items:
                link = item.get("link")
                if not link:
                    continue

                if link.startswith("/"):
                    link = "https://baocaobang.vn" + link

                links.append(link)
            return links

        except Exception:
            # Bất kỳ lỗi nào → coi như hết page
            return []

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

    # def crawl_podcast(self, number_post: int, crawl_id: Optional[str] = None):
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
