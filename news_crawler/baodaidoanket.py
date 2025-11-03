import requests, re
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime, timedelta
import paramiko
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException,WebDriverException, StaleElementReferenceException

from selenium.webdriver.support import expected_conditions as EC
import time


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https,time_to_seconds

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class DaiDoanKetCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://daidoanket.vn/"
        self.article_type_dict = {
            0: "chinh-tri/lanh-dao-dang",
            1: "chinh-tri/chu-tich-nuoc",
            2: "chinh-tri/quoc-hoi",
            3: "chinh-tri/chinh-phu",

            4: "mat-tran/cac-cuoc-van-dong",
            5: "mat-tran/tieng-noi-co-so",
            6: "mat-tran/nguoi-mat-tran",
            7: "mat-tran/giam-sat-phan-bien",
            8: "mat-tran/kieu-bao",
            9: "mat-tran/dan-toc",
            10: "mat-tran/ton-giao",
            11: "mat-tran/tu-van",

            12: "tieng-dan/dieu-tra",
            13: "tieng-dan/chung-toi-len-tieng",

            14: "xa-hoi/an-sinh-xa-hoi",
            15: "xa-hoi/moi-truong",
            16: "xa-hoi/chuyen-tu-te",

            17: "phap-luat/quy-dinh-moi",

            18: "giao-duc",

            19: "do-thi",

            20: "giao-thong",

            21: "van-hoa/giai-tri",

            22: "suc-khoe/cac-benh-dich",

            23: "the-thao",

            24: "bat-dong-san",

            25: "cong-nghe/san-pham-so",

            26: "goc-nhin-dai-doan-ket",
            27: "quoc-te",
            28: "tinh-hoa-viet",
            29: "du-lich",
            30: "thong-tin-doanh-nghiep",
            
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
            # --- ƯU TIÊN: Selenium lấy đúng "Current source" ---
            opts = Options()
            opts.add_argument("--headless=new")
            opts.add_argument("--disable-gpu")
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            opts.add_argument("--disable-software-rasterizer")
            opts.add_argument("--remote-debugging-port=9222")
            opts.add_argument("--disable-extensions")
            opts.add_argument("--window-size=1920,1080")

            driver = webdriver.Chrome(options=opts)
            driver.get(url)

            # ảnh logo nằm trong thẻ <a> ở header (điều chỉnh selector nếu site thay đổi)
            img = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "header .main_header a > img"))
            )
            logo_url = driver.execute_script(
                "return arguments[0].currentSrc || arguments[0].src || '';", img
            ).strip()

            info["logo"] = logo_url or ""

        except Exception as e:
            print("⚠️ Selenium logo error:", e)
            # --- FALLBACK: BS4 lấy src rồi chuẩn hoá absolute URL ---
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "html.parser")
                img = soup.select_one("header .main_header a > img")
                raw = (img.get("src") or "").strip() if img else ""
                info["logo"] = urljoin(url, raw) if raw else ""
            except Exception as e2:
                print("⚠️ BS4 logo fallback error:", e2)
                info["logo"] = ""

        finally:
            try:
                if driver:
                    driver.quit()
            except:
                pass

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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "footer.container"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("footer", class_="container")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                info["description"] = ""

                # License

                lines = [l.strip() for l in text.split("\n") if l.strip()]
                candidates = [l for l in lines if "Số" in l and ("GP-" in l or "GP/" in l or "GP" in l)]
                if not candidates:
                    candidates = [l for l in lines if "giấy phép" in l.lower()]
                if candidates:
                    info["license"] = candidates[0]

                info["editor_in_chief"] = ""
                p = soup.select_one("footer p:-soup-contains('Tổng Biên tập')")
                if p:
                    s = p.find("strong")
                    name = s.get_text(strip=True) if s else re.sub(r"^Tổng Biên tập\s*:?\s*", "", p.get_text(" ", strip=True), flags=re.I)
                    info["editor_in_chief"] = " ".join(w.capitalize() for w in name.split())

                # Địa chỉ
                span = soup.select_one("footer .icon_location")
                if span:
                    wrap = span.find_parent("div", class_="flex") or span.parent
                    addr_div = wrap.find("div")
                    raw = addr_div.get_text(separator="\n", strip=True) if addr_div else ""
                    lines = [re.sub(r'^[\'"]|[\'"]$', '', s).strip() for s in raw.split("\n") if s.strip()]
                    info["address"] = "; ".join(lines)

                phone_tag = footer_copyright.select_one("a[href^='tel:']")
                if phone_tag:
                    info["phone"] = phone_tag.get_text(strip=True).replace("Hotline:", "").strip()

                # Email
                email_tag = footer_copyright.select_one("a[href^=mailto]")
                if email_tag:
                    info["email"] = email_tag.get_text(strip=True).replace("Email:", "").strip()
                else :
                    info["email"] = ""
                # Ban quyen
                p1 = soup.select_one("footer p:-soup-contains('Bản quyền')")
                if p1:
                    p2 = p1.find_next_sibling("p")
                    lines = [p1.get_text(" ", strip=True)]
                    if p2:
                        lines.append(p2.get_text(" ", strip=True))
                    info["infor_copyright"] = "\n".join(lines)  


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
            title_tag = soup.select_one('article.article-content h1, article[itemprop="articleBody"] h1')
            title = title_tag.get_text(strip=True) if title_tag else ""
            # Lấy description
            desc_tag = soup.select_one("h2.article-content__description, h2.font-medium.font-poppins")
            description = desc_tag.get_text(strip=True) if desc_tag else ""

            # Trích xuất ngày viết bài
            publish_date = ""
            date_tag = soup.select_one("div.flex.flex-row.justify-between time, article[itemprop='articleBody'] time")
            publish_date = date_tag.get_text(strip=True) if date_tag else ""

            content = []
            content_images = []
            entry_div = soup.find('article', class_='article-content')
            if entry_div:

                # 1. Lấy tất cả các đoạn văn bản <p>
                paragraphs = entry_div.find_all('p')
                contents = [p.get_text(strip=True) for p in paragraphs]
                content = "\n".join(contents) if contents else ""

                # 2. Lấy tất cả hình ảnh và chú thích
                figures = entry_div.find_all('figure')
                for fig in figures:
                    img_tag = fig.find('img')
                    if img_tag:
                        image_url = img_tag['src']
                        content_images.append(image_url)
                content = "\n".join(contents)
            else:
                # Không có article-content
                content = ""
                content_images = []
                # đảm bảo nếu không có gì thì vẫn là chuỗi rỗng
            content = content or ""
            content_images = content_images or []
            author = ""
            author_tag = soup.select_one("p.text-lg.font-medium.text-black.font-sans.icon_author")
            author = author_tag.get_text(strip=True) if author_tag else ""

            categories_tag = soup.select_one("section.breadcrumbs h4 a ")
            categories = categories_tag.get_text(strip=True) if categories_tag else ""
           
            title_tag = soup.select_one("article.article-content h1")
            location = ""
            if title_tag:
                title_text = (title_tag.get_text() or "").strip()
                if ":" in title_text:
                    location = title_text.split(":", 1)[0].strip()

            video_url = ""
            thumbnail_url = ""
            
            # 1 Trường hợp video bình thường
            video_tag = soup.find("video")
            if video_tag:
                thumbnail_url = video_tag.get("data-poster", "").strip()
                source_tag = video_tag.find("source")
                if source_tag and source_tag.get("src"):
                    video_url = source_tag["src"].strip()
            if not video_url:
                iframe = soup.select_one('iframe[src*="youtube.com"], iframe[src*="youtu.be"]')
                if iframe and iframe.has_attr("src"):
                    video_url = urljoin(url, iframe["src"].strip())  # gán luôn src 
            # 2 Trường hợp YouTube nhúng — thumbnail nằm trong style
            if not thumbnail_url:
                opts = Options()
                opts.add_argument("--headless=new")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-gpu")
                # ❌ đừng tắt ảnh khi cần poster: bỏ --disable-images & blink image off

                driver = webdriver.Chrome(options=opts)
                try:
                    driver.get(url)
                    wait = WebDriverWait(driver, 12)

                    # 1) Nếu có iframe YouTube, switch vào
                    try:
                        iframe = wait.until(EC.presence_of_element_located((
                            By.CSS_SELECTOR, 'iframe[src*="youtube.com"], iframe[src*="youtu.be"]'
                        )))
                        driver.switch_to.frame(iframe)
                    except Exception:
                        # không có iframe -> giữ nguyên context
                        pass

                    # 2) Chờ thumbnail overlay rồi lấy background-image
                    thumb = wait.until(EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.ytp-cued-thumbnail-overlay-image")
                    ))

                    style = thumb.get_attribute("style") or ""
                    if not style or "url(" not in style:
                        # fallback: computed style
                        bg = driver.execute_script(
                            "return getComputedStyle(arguments[0]).getPropertyValue('background-image');",
                            thumb
                        )
                        style = f"background-image: {bg};"

                    m = re.search(r'url\((["\']?)(.*?)\1\)', style)
                    thumbnail_url = (m.group(2).strip() if m else "")
                except:
                    pass
                finally:
                    driver.quit()
            
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
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=chrome_options)
        page_url = f"https://daidoanket.vn/{article_type}"
        driver.get(page_url)
        seen_links = set()
        max_pages = 20
        page_count = 0
        try:
            while page_count < max_pages:
                # 1️⃣ Chờ danh sách bài viết
                try:
                    container = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "#latest-articles"))
                    )
                except Exception:
                    print("❌ Không tìm thấy danh sách bài viết (#latest-articles).")
                    break

                # 2️⃣ Lấy link các bài trong danh sách
                articles = container.find_elements(By.CSS_SELECTOR, "article h2 a")
                before_count = len(seen_links)

                for a_tag in articles:
                    href = a_tag.get_attribute("href")
                    if href and not href.startswith("http"):
                        href = "https://daidoanket.vn" + href
                    seen_links.add(href)

                print(f"📄 Trang {page_count+1}: tổng {len(seen_links)} link")

                # 3️⃣ Tìm nút "Xem thêm"
                try:
                    load_more_btn = driver.find_element(
                        By.XPATH,
                        "//button[contains(text(), 'Xem thêm') or @onclick='loadMoreArticles()']"
                    )

                    if load_more_btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", load_more_btn)
                        driver.execute_script("arguments[0].click();", load_more_btn)
                        print(f"🔄 Đã click 'Xem thêm' lần {page_count+1}")

                        # Chờ thêm bài mới (vì JS loadMoreArticles() là async)
                        time.sleep(3)

                        # Nếu không thấy thêm bài mới thì dừng
                        if len(seen_links) == before_count:
                            print("⚠️ Không có bài mới được thêm — dừng lại.")
                            break

                        page_count += 1
                    else:
                        print("✅ Hết nút 'Xem thêm'.")
                        break
                except Exception:
                    print("✅ Không tìm thấy hoặc không thể click 'Xem thêm'.")
                    break

        finally:
            driver.quit()

        print(f"✅ Tổng cộng thu được {len(seen_links)} bài.")
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
            chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
            chrome_options.add_argument("--no-sandbox")   
            chrome_options.add_argument("--headless=new")  # chạy ẩn

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(url)
            html = driver.page_source
            soup = BeautifulSoup(html,"html.parser")

            audio_tag = soup.find("audio", src=True)
            if audio_tag:
                audio_url = audio_tag.get("src", "").strip()
            
            # 2 DESCRIPTION
            s_tag = soup.select_one("h2.article-content__description")
            description = s_tag.get_text(strip=True) if s_tag else ""

            title_tag = soup.select_one("h1.text-3xl")
            title = title_tag.get_text(strip=True) if title_tag else ""

            # 3PUBLISHED DATE
            t_tag = soup.select_one("time.text-iris-400")
            time_text = t_tag.get_text(strip=True) if t_tag else ""
            publishedDate = parse_vnexpress_time_ms(time_text)

            # 4AUTHOR
            a_tag = soup.select_one("p.text-sm.font-medium.text-black.font-sans")
            author = a_tag.get_text(strip=True) if a_tag else ""


            duration_tag = soup.select("span#duration")
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
            "description": content_url,
            "author": author_url,
            "duration": end_time_mp3_url,
            "publishedDate": datetime_url
        }

    def crawl_podcast_bs4(self, category_url: str):
        def build_domain_username(domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(category_url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("article.flex") 
        domain = "daidoanket"
        BASE_DOMAIN = "https://daidoanket.vn"
        podcasts = []
        try :
            for item in items:
                # 1. Title + URL

                # Lấy href của thẻ <a> chứa tiêu đề
                a_tag = item.select_one("a.loading-link")
                url = a_tag.get("href", "") if a_tag else ""

                if url.startswith("/"):
                    url = BASE_DOMAIN + url

                # 2. Thumbnail (từ <img> hoặc <source data-srcset>)
                thumb_elem = item.select_one("a.loading-link picture img")
                thumbnail = thumb_elem.get("src", "") if thumb_elem else ""
                # 3. Category (nếu cần)
                category = ""

                # 4. Audio URL (trong data-player)
                meta = self.get_audio_from_article(url)
                audio_url     = meta["audio_url"]
                content_url   = meta["description"]
                author_url    = meta["author"]
                end_time_url  = meta["duration"]
                datetime_url  = meta["publishedDate"]
                domain_username = build_domain_username(domain, author_url) if author_url else ""
                title = meta["title"]

                podcast = {
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
        except Exception as e:
            print("❌ Lỗi trong quá trình crawl:", e)

    def crawl_postcast(self):
        podcast_type_dict = {
            0: "podcast.html",

        }

        BASE_URL = "https://daidoanket.vn/chuyen-muc/"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url)
