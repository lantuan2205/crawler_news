import requests
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
import re

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException,TimeoutException,WebDriverException

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

class CongLyCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://congly.vn/"
        self.article_type_dict = {
            0: "chinh-tri",

            1: "toa-an/tieu-diem",
            2: "toa-an/cai-cach-tu-phap",
            3: "toa-an/phong-trao-thi-dua",
            4: "toa-an/toa-an-dia-phuong",
            5: "toa-an/nghiep-vu",

            6: "phap-dinh/ky-su-phap-dinh",
            7: "phap-dinh/toa-tuyen-an",

            8: "phap-luat/ho-so-vu-an",
            9: "phap-luat/an-ninh-trat-tu",
            10: "phap-luat/tu-van-phap-luat",

            11: "xa-hoi/doi-song",
            12: "xa-hoi/moi-truong",
            13: "xa-hoi/suc-khoe",
            14: "xa-hoi/giao-thong",

            15: "van-hoa-the-thao/van-hoa-du-lich",
            16: "van-hoa-the-thao/am-nhac-phim",
            17: "van-hoa-the-thao/the-thao",

            18: "kinh-te/doanh-nghiep-doanh-nhan",
            19: "kinh-te/bat-dong-san",
            20: "kinh-te/tai-chinh-ngan-hang",
            21: "kinh-te/bao-ve-nguoi-tieu-dung",

            22: "the-gioi/chuyen-dong",
            23: "the-gioi/vu-an-noi-tieng",
            24: "the-gioi/chuyen-la-bon-phuong",

            25: "kinh-te/dia-oc",

            26: "ban-doc/nhip-cau-cong-ly",
            27: "ban-doc/van-de-quan-tam",
            28: "ban-doc/nhan-ai",
            29: "ban-doc/hoi-am",

            30: "giao-duc",

            31: "tam-diem-du-luan",

            32: "phong-su-ghi-chep",

            33: "nhan-tin",

            34: "cong-ly-xua-va-nay",
            
            35: "thong-tin-doanh-nghiep",

            36: "cai-chinh",
            37: "video"
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
            
            box = soup.select_one("div.c-logo a img")
            logo_src = ""
            if box:
                logo_src = box.get("src").strip()
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

                # Description = 1 dòng đầu tiên
                if len(lines) >= 1:
                    info["description"] = f"{lines[0]}"

                # License
                if "Giấy phép" in text:
                    license_line = [line for line in lines if "Giấy phép" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép", "").strip()

                # Tổng biên tập
                editor_in_chief = ""
                box = soup.select_one("div.c-footer-main div.b-maincontent")
                if box:
                    p = box.find(lambda tag: tag.name == "p" and "Tổng Biên tập" in tag.get_text())
                    if p:
                        # ưu tiên thẻ b/strong nếu có
                        strong = p.find(["b", "strong"])
                        if strong and strong.get_text(strip=True):
                            editor_in_chief = strong.get_text(strip=True)
                        else:
                            # fallback: tách từ text sau cụm "Tổng Biên tập"
                            txt = p.get_text(" ", strip=True)
                            m = re.search(r"Tổng\s*Biên\s*Tập[:：]?\s*(.+)", txt, flags=re.I)
                            if m:
                                editor_in_chief = m.group(1).strip(' "')

                info["editor_in_chief"] = editor_in_chief

                # Địa chỉ
                if "Trụ sở Tòa soạn:" in text:
                    addr_line = [line for line in lines if "Trụ sở Tòa soạn:" in line]
                    if addr_line:
                        info["address"] = addr_line[0].replace("Trụ sở Tòa soạn:", "").strip()

                # Điện thoại
                if "Điện thoại:" in text:
                    phone_line = [line for line in lines if "Điện thoại:" in line]
                    if phone_line:
                        info["phone"] = phone_line[0].replace("Điện thoại:", "").strip()
                print("phone",info["phone"] )

                # Email
                p = next((tag for tag in footer_copyright.select("p")
                        if "email" in tag.get_text(" ", strip=True).lower()), None)

                if p:
                    # gom toàn bộ chuỗi con trong <p>, bỏ ngoặc kép nếu có
                    parts = [s.strip().strip('"') for s in p.stripped_strings]
                    # lấy phần có dấu '@' (thường là email)
                    candidates = [s for s in parts if "@" in s]
                    email = candidates[-1] if candidates else ""

                info["email"] = email

                # Thông tin bản quyền
                if footer_copyright:
                    # Lấy tất cả p và rút gọn khoảng trắng
                    ps = [p.get_text(" ", strip=True) for p in footer_copyright.find_all("p")]
                    ps = [t for t in ps if t]  # bỏ rỗng

                    if len(ps) >= 2:
                        infor_copyright = " ".join(ps[-2:])   # hoặc "\n".join(ps[-2:]) nếu muốn xuống dòng
                    elif ps:
                        infor_copyright = ps[-1]

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
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title_tag = (
                soup.find('h1', class_='block-sc-title') or
                soup.select_one('div.c-video-detail__title h1')
            )
            title = title_tag.get_text(strip=True) if title_tag else ""

            # Lấy description
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
            date_tag = soup.select_one("span.sc-longform-header-date.block-sc-publish-time") or soup.find("div", class_="c-video-detail__time")
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            for date_tag in soup.find_all("div", class_="c-video-detail__time"):
                text = date_tag.get_text(strip=True)

                # Tìm đoạn ngày giờ ở cuối chuỗi
                match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}\s*-\s*\d{1,2}:\d{2})\s*$", text)

                if match:
                    publish_date = match.group(1).strip()
                else:
                    publish_date = ""

            content_images = []
            entry_div = soup.find('div', class_='entry entry-no-padding')

            # 1. Lấy tất cả các đoạn văn bản <p>
            paragraphs = entry_div.find_all('p')
            contents = [p.get_text(strip=True) for p in paragraphs]

            # 2. Lấy tất cả hình ảnh và chú thích
            content_images = []
            figures = entry_div.find_all('figure')
            for fig in figures:
                img_tag = fig.find('img')
                if img_tag:
                    image_url = img_tag['src']
                    content_images.append(image_url)
            content = "\n".join(contents)

            author = None
            author_box = soup.find("span", class_="sc-longform-header-author")
            if author_box:
                author = author_box.get_text(strip=True).split("/")[0].strip()
            if not author:
                author_box = soup.find("div", class_="c-video-detail__time")
                if author_box:
                    text = author_box.get_text(strip=True)
                    parts = [p.strip() for p in text.split("-") if p.strip()]
                    authors = []

                    for part in parts:
                        if re.search(r"\d{1,2}/\d{1,2}/\d{4}", part):
                            break
                        authors.append(part)

                    author = " - ".join(authors) if authors else ""
            lis = soup.select(".breadcrumb-item")[1:]
            if not lis:
                lis = soup.select_one("div.c-video-detail__cat a")
            # Lấy text bên trong, loại bỏ khoảng trắng
            category = " / ".join(li.get_text(strip=True) for li in lis)
            if category:
                categories = category
            else:
                categories = ""
            video_url = ""
            thumbnail_url = ""
            location = ""
            driver = None

            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-popup-blocking")
                chrome_options.add_argument("--disable-notifications")
                chrome_options.add_argument("--window-size=1200,900")
                chrome_options.add_argument("--log-level=3")

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
            return title, description, content, publish_date, author, content_images,categories, video_url, thumbnail_url, location

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
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://congly.vn/{article_type}"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        ul_element = driver.find_element(By.CSS_SELECTOR, "ul.onecms__loading")
        try:
            while True:
                # Lấy các bài viết hiện tại
                articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.b-grid__title a")
                for article in articles:
                    link = article.get_attribute("href")
                    seen_links.add(link)
                # Thử click nút "Xem thêm"
                try:
                    load_more_button = driver.find_element(By.CSS_SELECTOR, "div.c-more.onecms__loadmore a")
                    if load_more_button.is_displayed():
                        load_more_button.click()
                        print("🔄 Đã click 'Xem thêm'")
                        time.sleep(3)
                    else:
                        break
                except Exception:
                    print("✅ Không còn 'Xem thêm' hoặc gặp lỗi.")
                    break
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
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        resp = requests.get(url, headers=headers)
        soup = BeautifulSoup(resp.text, "html.parser")

        article = soup.select_one("div.section_podcast_detail_newver") or soup

        # 1 AUDIO
        tag = article.find("audio", src=True) or article.find("src", src=True) or article.find("video", src=True)
        if tag:
            audio_url = (tag.get("src") or "").strip()
        else:
            audio_url = ""
        # 2 DESCRIPTION
        s_tag = article.select_one("div.b-grid__desc a")
        description = s_tag.get_text(strip=True) if s_tag else ""

        # 3PUBLISHED DATE
        t_tag = article.select_one("span.b-grid__time")
        time_text = t_tag.get_text(strip=True) if t_tag else ""
        publishedDate = parse_vnexpress_time_ms(time_text)

        # 4AUTHOR
        a_tag = article.select_one("div.b-grid__author")
        author = a_tag.get_text(strip=True) if a_tag else ""

        # 5 END TIME (tổng thời lượng)
        def fmt(sec):
            if not sec: return ""
            sec = int(sec)
            m, s = divmod(sec, 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        opts = webdriver.ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--mute-audio")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")

        driver = webdriver.Chrome(options=opts)
        driver.get(url)

        wait = WebDriverWait(driver, 12)

        # 1) chờ có thẻ audio (hoặc đổi selector theo site của bạn)
        audio = wait.until(EC.presence_of_element_located((By.TAG_NAME, "audio")))

        # 2) tắt âm tuyệt đối cho mọi media trên trang
        driver.execute_script("""
        document.querySelectorAll('audio,video').forEach(m => {
            try { m.muted = true; m.volume = 0.0; } catch(e){}
        });
        """)

        # 3) cố lấy duration chỉ với metadata (không play)
        duration_secs = driver.execute_async_script("""
        const done = arguments[0];
        const a = document.querySelector('audio');
        if (!a) { done(0); return; }

        function finish(){ done(Math.floor(a.duration || 0)); }

        if ((a.readyState >= 1 && a.duration) || !isNaN(a.duration)) { finish(); }
        else {
            a.addEventListener('loadedmetadata', () => finish(), {once:true});
            try { a.load(); } catch(e){}
            // một số site chặn metadata khi chưa tương tác => fallback play rất ngắn (muted)
            setTimeout(() => {
            if (!a.duration || isNaN(a.duration)) {
                a.play().catch(()=>{});                 // đã muted ở trên nên không nghe thấy
                setTimeout(() => { try{ a.pause(); }catch(e){} finish(); }, 200);
            }
            }, 800);
        }
        """)

        end_time_mp3 = fmt(duration_secs)

        # (tuỳ chọn) nếu bạn vẫn muốn đọc từ ô hiển thị của site:
        if not end_time_mp3:
            try:
                play_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".c-podcast-player__control, .jw-icon-play, .vjs-play-control")))
                driver.execute_script("arguments[0].click();", play_btn)
                t = wait.until(lambda d: (d.find_element(By.CSS_SELECTOR, ".c-podcast-player__bar__end, .player__duration, .media-time-count").text.strip()))
                end_time_mp3 = t.strip()
                # dừng phát
                driver.execute_script("document.querySelectorAll('audio,video').forEach(m=>{try{m.pause();}catch(e){}})")
            except Exception:
                pass
        driver.quit()


        
        return {
            "audio_url": audio_url,
            "description": description,
            "author": author,
            "duration": end_time_mp3,
            "publishedDate": publishedDate,
        }

    def crawl_podcast_bs4(self, category_url: str):
        def build_domain_username(domain, author_url):
            return f"{domain}_{author_url.replace(' ', '')}"

        base = "congly"
        ITEM_SELECTOR = "ul.onecms__loading > li"

        # 1) Open & scroll to bottom (lazy-load hết)
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--log-level=3")

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(category_url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ITEM_SELECTOR))
            )
            last_count, stable = 0, 0
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.0)
                # đợi nếu có nội dung mới được bơm vào
                count = len(driver.find_elements(By.CSS_SELECTOR, ITEM_SELECTOR))
                if count > last_count:
                    last_count, stable = count, 0
                else:
                    stable += 1
                if stable >= 3:  # 3 vòng liên tiếp không tăng → dừng
                    break
            print("✅ Đã scroll đến cuối trang")

            # 2) Parse bằng BS4 từ DOM đã render
            soup = BeautifulSoup(driver.page_source, "html.parser")
        finally:
            driver.quit()

        items = soup.select(ITEM_SELECTOR)

        for item in items:
            try:
                # URL bài
                a = item.select_one("a[href]")
                if not a:
                    continue
                url = a.get("href", "").strip()
                url = urljoin(category_url, url)

                # Title (ưu tiên img[title], fallback a.get('title') hoặc text)
                title = ""
                img_title = item.select_one("img[title]")
                if img_title:
                    title = img_title.get("title", "").strip()
                if not title and a.get("title"):
                    title = a.get("title", "").strip()
                if not title:
                    title = (a.get_text(strip=True) or "").strip()

                # Thumbnail
                thumb = ""
                img = item.select_one("img[src]")
                if img:
                    thumb = img.get("src", "").strip()
                    thumb = urljoin(category_url, thumb)

                # Category (nếu cần lấy ở breadcrumb/header khác, bổ sung sau)
                category = ""

                # 3) Lấy meta audio ở trang chi tiết
                meta = self.get_audio_from_article(url)
                audio_url    = meta.get("audio_url", "")
                content_url  = meta.get("description", "")
                author_url   = meta.get("author", "")
                end_time_url = meta.get("duration", "")
                datetime_url = meta.get("publishedDate", "")

                domain_username = build_domain_username(base, author_url) if author_url else ""

                podcast = {
                    "title": title,
                    "url": url,
                    "thumbnail": thumb,
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
                print(f"⚠️ Lỗi trong quá trình crawl {url}: {e}")
                continue

    def crawl_postcast(self):
        podcast_type_dict = {
            0: "",
        }

        BASE_URL = "https://congly.vn/podcast"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url)
