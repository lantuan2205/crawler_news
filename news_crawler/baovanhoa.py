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
import json
from io import BytesIO
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
from urllib.parse import urljoin, urlparse, parse_qs
from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class BaoVanHoaCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baovanhoa.vn/"
        self.article_type_dict = {
            0: "thoi-su",
            1: "bien-dao-to-quoc",
            2: "van-hoa-va-thoi-luan",
            3: "chinh-sach-quan-ly",
            4: "di-san",
            5: "van-hoa-co-so",
            6: "doi-song-van-hoa",
            7: "cong-nghiep-van-hoa",
            8: "chinh-sach-quan-ly-bao-chi",
            9: "toan-canh-bao-chi",
            10: "thong-tin-doi-ngoai",
            11: "van-hoa-so",
            12: "xu-phat-vi-pham-hanh-chinh-ve-bao-chi",
            13: "the-thao-chinh-sach-quan-ly",
            14: "the-thao-trong-nuoc",
            15: "the-thao-quoc-te",
            16: "hau-truong",
            17: "cau-chuyen-the-thao",
            18: "du-lich-chinh-sach-quan-ly",
            19: "diem-den",
            20: "kham-pha",
            21: "gia-dinh-chinh-sach-quan-ly",
            22: "gia-dinh-360-do",
            23: "loi-song",
            24: "van-hoc",
            25: "dien-anh",
            26: "am-nhac",
            27: "san-khau-mua",
            28: "my-thuat-nhiep-anh",
            29: "truyen-hinh",
            30: "thoi-trang",
            31: "showbiz",
            32: "cung-thu-gian",
            33: "giao-duc",
            34: "y-te",
            35: "ban-tre",
            36: "moi-truong-khi-hau",
            37: "do-thi",
            38: "xa-hoi",
            39: "doanh-nghiep",
            40: "chung-khoan",
            41: "dia-phuong",
            42: "thi-truong",
            43: "khoi-nghiep",
            44: "hang-viet",
            45: "bat-dong-san",
            46: "bao-ve-nguoi-tieu-dung",
            47: "dai-doan-ket",
            48: "van-hoa-xa-hoi-vung-mien",
            49: "nong-thon-moi",
            50: "van-hoa-du-lich-dan-toc-thieu-so",
            51: "chuyen-de-dan-toc-thieu-so-va-mien-nui",
            52: "hoc-tap-va-lam-theo-bac",
            53: "viet-nam-ky-nguyen-vuon-minh",
            54: "quy-hoach-mang-luoi-co-so-van-hoa-the-thao-va-du-lich-tam-nhin-2045",
            55: "doi-song-xanh",
            56: "chuong-trinh-muc-tieu-quoc-gia-ve-phat-trien-van-hoa",
            57: "80-nam-ngay-truyen-thong-van-hoa",
            58: "giai-bao-chi-toan-quoc-vi-su-nghiep-phat-trien-van-hoa",
            59: "huong-toi-dai-hoi-thi-dua-yeu-nuoc-bo-vhttdl-2025",
            60: "cau-noi-phap-luat",
            61: "tin-nong",
            62: "dieu-tra",
            63: "thong-tin-tu-ban-doc",
            64: "hoi-am",
            65: "ban-doc-viet",
            66: "chuyen-doi-so",
            67: "cong-nghe",
            68: "san-pham",
            69: "thi-truong-xe",
            70: "trai-nghiem",
            71: "cong-dong",
            72: "su-kien",
            73: "van-hoa-quoc-te",
            74: "nguoi-viet-nam-chau"
        }   
        
    def download_image(self, image_url, article_title, category, published_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: dantri/category/date
            newspaper_name = "baovanhoa"
            date_parts = clean_date(published_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"

            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder

            clean_url = image_url.split('?')[0]
            image_filename = Path(clean_url).name
            remote_path = remote_dir / image_filename

            # Tải ảnh
            response = requests.get(image_url, headers=headers, timeout=10)
            response.raise_for_status()
            image_data = BytesIO(response.content)

            # Kết nối SSH/SFTP
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(ssh_host, username=ssh_user, password=ssh_password)
            sftp = ssh.open_sftp()

            # Xử lý URL ảnh
            # Tạo thư mục nếu chưa có (đệ quy)
            path_parts = str(remote_dir).split('/')
            current = ''
            for part in path_parts:
                if not part:
                    continue
                current += f'/{part}'
                try:
                    sftp.stat(current)
                except IOError:
                    sftp.mkdir(current)

            # Lưu ảnh
            with sftp.file(str(remote_path), 'wb') as f:
                f.write(image_data.getvalue())

            # Đóng kết nối
            sftp.close()
            ssh.close()

            return str(remote_path)
            
        except Exception as e:
            self.logger.error(f"Error downloading image {image_url}: {e}")
            return None

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
            header_logo = soup.find("h1", class_="logo")
            img_tag = header_logo.find("img")
            info["logo"] = img_tag["src"].strip()
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "footer.site-footer"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("footer", class_="site-footer")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                info["description"] = ""

                # License
                if "Giấy phép số:" in text:
                    license_line = [line for line in lines if "Giấy phép số:" in line]
                    if license_line:
                        info["license"] = license_line[0].replace("Giấy phép số:", "").strip()

                # Tổng biên tập
                editor_tag = footer_copyright.find(string=lambda s: "Tổng Biên tập" in s if s else False)
                if editor_tag:
                    strong_tag = editor_tag.find_next("strong")
                    if strong_tag:
                        info["editor_in_chief"] = strong_tag.get_text(strip=True)
                # Địa chỉ
                addr_icon = footer_copyright.find("i", class_="fa-location-dot")
                if addr_icon:
                    address_text = addr_icon.find_next(string=True)
                    if address_text:
                        info["address"] = address_text.strip()

                # Điện thoại
                phone_icon = footer_copyright.find("i", class_="fa-phone")
                if phone_icon:
                    phone_line = phone_icon.find_next(string=True)
                    if phone_line:
                        info["phone"] = phone_line.strip()

                # Email
                email_icon = footer_copyright.find("i", class_="fa-envelope")
                if email_icon:
                    email_tag = email_icon.find_next(string=True)
                    if email_tag:
                        info["email"] = email_tag.strip()

                # Thông tin bản quyền
                if "© Bản quyền" in text:
                    copyright_line = [line for line in lines if "© Bản quyền" in line]              
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

    def extract_content(self, url: str) -> tuple:
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
            title = soup.find('h1', class_='detail__title').text.strip()

            description = soup.find('h2', class_='detail__summary').text.strip()

            content = soup.find('div', class_='detail__content').text.strip()

            # Trích xuất ngày viết bài
            time_tag = soup.find('time')
            publish_date = time_tag.text.strip() if time_tag else None

            # Lấy tất cả các ảnh trong phần tử này
            div = soup.find('div', class_='detail__content')
            content = div.get_text(separator="\n").strip() if div else ""
            images = content.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]

            # Trích xuất tác giả
            author = soup.find('span', class_='detail__author').text.strip()
            categories = ""
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
                # comment_id
                comment_id =  ""
                
                # user_id
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
        """" Get URLs of articles in a specific type on a given page"""
        if (page_number > 49):
            return []

        page_url = f"https://baovanhoa.vn/{article_type}/?page={page_number}"
        results = []
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        # titles = soup.find_all("h3", class_="article-title")

        articles = soup.find_all('article', class_='story')

        if (len(articles) == 0):
            return []

        for article in articles:
            title_tag = article.find('h3', class_='story__title')
            title_link = title_tag.find('a') if title_tag else None
            link = title_link['href'] if title_link else None
            full_url = f"https://baovanhoa.vn{link}"  # Thêm domain nếu cần
            results.append(full_url)

        return results

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

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        # 1) Tìm thẻ <audio> có src
        audio_tag = soup.find(attrs={"data-audio-src": True})

        if audio_tag:
            return audio_tag["data-audio-src"]
        return ""
    

    def crawl_podcast_bs4(self, category_url: str):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(category_url, headers=headers, timeout=15)
        response.raise_for_status()
        BASE_URL = "https://baovanhoa.vn"
        url_page = category_url
        seen_urls = set()
        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("article.story.story--podcast.mb-4")  
      
        podcasts = []
        while True:
            # tải trang
            resp = requests.get(url_page, headers=headers, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # quét bài trong trang
            items = soup.select("article.story.story--podcast.mb-4")
            if not items:
                break

            for item in items:
                # 1) Title + URL
                title_elem = item.select_one("a[title]")
                if not title_elem:
                    continue

                title = title_elem.get("title", "").strip()

                url = title_elem.get("href", "") or ""
                if url.startswith("/"):
                    url = BASE_URL + url
                # Chuẩn hoá URL tuyệt đối

                # 2) Thumbnail
                thumb_elem = item.select_one("img")
                thumbnail = ""
                if thumb_elem:
                    thumbnail = thumb_elem.get("src") or thumb_elem.get("data-src") or thumb_elem.get("data-mobile") or ""
                # 3) Category (nếu không có trong item thì để rỗng)
                cat_tag = soup.select_one("span.text-primary")
                category = cat_tag.get_text(strip=True) if cat_tag else ""
                print("cate",category)

                # 4) Audio URL
                audio_url=""
                audio_url = self.get_audio_from_article(url)

                podcast = {
                    "title": title,
                    "url": url,
                    "thumbnail": thumbnail,
                    "category": category,
                    "audio_url": audio_url
                }
                send_podcast_to_kafka(podcast)
              # -> tìm nút Next và sang trang kế
            next_a = soup.select_one('a#nextControl[href]')
            # dừng nếu không có next, hoặc class có 'disabled', hoặc thuộc tính disabled xuất hiện
            if (not next_a) or ('disabled' in (next_a.get('class') or [])) or next_a.has_attr('disabled'):
                print("✅ Không còn trang tiếp theo, dừng.")
                break

            next_href = next_a.get('href', '').strip()
            if not next_href:
                print("✅ Next không có href, dừng.")
                break

            url_page = urljoin(BASE_URL, next_href)
            # ngủ nhẹ tránh bị chặn
            time.sleep(random.uniform(0.8, 1.8))
    def crawl_postcast(self):
        podcast_type_dict = {
            0: "podcast/",
        }

        BASE_URL = "https://baovanhoa.vn/"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url)
