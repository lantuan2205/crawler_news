import os
import requests
import sys
from pathlib import Path
import re
import json
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
from selenium.common.exceptions import TimeoutException, WebDriverException

from typing import Optional  
from utils.service_utils import clean_date, get_urls_of_type, send_podcast_to_kafka, parse_vnexpress_time_ms, normalize_url_to_root_https


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag

from utils.service_utils import clean_date

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VtvCrawler(BaseCrawler):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vtv.vn/"
        self.article_type_dict = {
            0: "chinh-tri",
            1: "xa-hoi",
            2: "phap-luat",

            3: "the-gioi/tin-tuc",
            4: "the-gioi/the-gioi-do-day",
            5: "dong-su-kien/da-chieu-cau-chuyen-quoc-te-238",

            6: "kinh-te/bat-dong-san",
            7: "kinh-te/tai-chinh",
            8: "kinh-te/thi-truong",
            9: "kinh-te/goc-doanh-nghiep",

            10: "truyen-hinh/phim-vtv",
            11: "truyen-hinh/hau-truong",
            12: "truyen-hinh/nhan-vat",
            13: "truyen-hinh/goc-khan-gia",
            14: "truyen-hinh/giai-sao-mai",

            15: "nguoi-viet-bon-phuong",

            16: "truyen-hinh/goc-khan-gia",

            17: "van-hoa-giai-tri/dien-anh",
            18: "van-hoa-giai-tri/am-nhac",

            19: "doi-song/du-lich",
            20: "doi-song/lam-dep",
            21: "dong-su-kien/chat-luong-cuoc-song-268",

            22: "suc-khoe",

            23: "tam-long-viet",

            24: "the-thao/bong-da-trong-nuoc",
            25: "the-thao/bong-da-quoc-te",
            26: "the-thao/tennis",
            27: "the-thao/cac-mon-khac",
            28: "the-thao/ben-le",

            29: "chuong-trinh-dac-sac/su-kien-va-binh-luan",
            30: "chuong-trinh-dac-sac/toan-canh-the-gioi",
            31: "chuong-trinh-dac-sac/tap-chi-kinh-te-cuoi-tuan",

            32: "truc-tuyen",

            33: "cong-nghe/san-pham",
            34: "cong-nghe/thi-truong",
            35: "cong-nghe/tu-van",
            36: "cong-nghe/hitech-cong-nghe-tuong-lai",

            37: "giao-duc/tu-van",
            38: "giao-duc/hoc-truc-tuyen",
            39: "cong-nghe/tin-cong-nghe",
        }
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: vtv/category/date
            newspaper_name = "vtv"
            date_parts = clean_date(publish_date).split(',')[0].strip()
            day, month, year = date_parts.split('/')
            date_folder = f"{day}-{month}-{year}"
            # Tạo đường dẫn thư mục đầy đủ
            remote_dir = Path(remote_base_dir) / newspaper_name / category / date_folder

            clean_url = image_url.split('?')[0]
            image_filename = Path(clean_url).name
            remote_path = remote_dir / image_filename

            # Tải ảnh
            response = requests.get(image_url, headers=headers)
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
            container = soup.find("div", class_="header")
            h1_tag = container.find("h1") if container else None
            logo_src = h1_tag.find("img")["src"] if h1_tag and h1_tag.find("img") else None
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
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.footer div.container"))
                )
            except TimeoutException:
                print("⚠️ Không tìm thấy footer.")
                return info

            soup = BeautifulSoup(driver.page_source, "html.parser")
            footer_copyright = soup.find("div", class_="footer")
            if footer_copyright:
                text = footer_copyright.get_text("\n", strip=True)
                lines = text.split("\n")

                # Description = 2 dòng đầu tiên
                org = soup.select_one("div.col-organ")
                descr = ""

                if org:
                    # 2 <p> đầu (con trực tiếp)
                    ps = org.find_all("p", limit=2, recursive=False)
                    texts = [" ".join(p.stripped_strings) for p in ps]  # gom cả text trong <span>, <br>
                    descr = " - ".join(texts)
                info["description"] = descr


                # License
                p = soup.select_one("div.col-organ p.des:nth-of-type(3)")
                info["license"] = p.get_text(separator="\n", strip=True).split("\n")[-1] if p else ""

                # Tổng biên tập
                editor = next((editor for editor in soup.select("div.col-total p.des span.bold")
                    if "tổng biên tập" in ((editor.previous_sibling or "").strip().lower())), None)
                info["editor_in_chief"] = editor.get_text(strip=True) if editor else ""

                # Địa chỉ
                info["address"] = ""
                     
                # Điện thoại
                p_tel = next((p for p in soup.select("div.col-total p.des")
                            if "tổng đài" in p.get_text(strip=True).lower()), None)
                phones_text = p_tel.select_one("span.bold").get_text(" ", strip=True) if p_tel else ""
                # tách ra danh sách số (giữ dấu . hoặc - nếu muốn, bỏ nếu không)
                phones = re.findall(r"\d[\d.\-\s]*\d", phones_text) if phones_text else []
                info["phone"] = ", ".join(s.strip() for s in phones) if phones else phones_text

                # Email
                p_mail = next((p for p in soup.select("div.col-total p.des")
                            if "email" in p.get_text(strip=True).lower()), None)
                info["email"] = p_mail.select_one("span.bold").get_text(strip=True) if p_mail else ""

                # Thông tin bản quyền
                last_p = footer_copyright.select("p")[-1]
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

    def extract_content(self, url: str) -> tuple:
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
            title_tag = soup.find('h1', class_='title_detail')
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.find("h2", class_="sapo")
            if desc_tag:
                raw_description = desc_tag.get_text(strip=True)
                # Tách phần mô tả sau dấu "-"
                split_parts = raw_description.split("-", 1)
                description = split_parts[1].strip() if len(split_parts) > 1 else raw_description
            else:
                description = None
            # Trích xuất ngày viết bài
            import re

            publish_date = None
            date_tag = soup.find("span", class_="time")

            if date_tag:
                text = date_tag.get_text(strip=True)
                # Tìm chuỗi dạng dd/mm/yyyy hh:mm bằng regex
                match = re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", text)
                if match:
                    publish_date = match.group(0)


            # Lấy tất cả các ảnh trong phần tử này
            content_div = soup.find("div", class_="ta-justify")
            if not content_div:
                return [], []

            # Tìm tất cả ảnh
            images = content_div.find_all('img')

            # Bỏ ảnh cụ thể: like-fanpage-vtv.jpg
            content_images = [
                img['src'] for img in images
                if img.get('src') and not img['src'].endswith("like-fanpage-vtv.jpg")
            ]
            
            # Lấy toàn bộ văn bản (không lấy script, ads, liên kết liên quan)
            content = content_div.get_text(separator="\n", strip=True)
            paragraphs = content_div.find_all("p")
            content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

            # Trích xuất tác giả
            author = None
            author_tag = soup.find('p', class_='author')

            if author_tag:
                # Xóa thẻ <span class="time"> nếu có
                span_time = author_tag.find('span', class_='time')
                if span_time:
                    span_time.extract()  # loại bỏ khỏi cây DOM

                # Sau đó lấy text còn lại (tên)
                author = author_tag.get_text(strip=True)

            return title, description, content, publish_date, author, content_images

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
        chrome_options.add_argument("--headless")  # Chạy trình duyệt ở chế độ headless
        chrome_options.add_argument("--disable-gpu")  # Tăng độ ổn định khi headless
        chrome_options.add_argument("--no-sandbox")   # Bắt buộc khi chạy ở môi trường Linux
        chrome_options.add_argument("--window-size=1920,1080")  # Kích thước cửa sổ giả lập
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        page_url = f"https://vtv.vn/{article_type}.htm"
        driver.get(page_url)
        time.sleep(2)
        seen_links = set()
        last_size = 0
        wait = WebDriverWait(driver, 10)

        try:
            while True:
                # Lưu số lượng link trước khi quét
                previous_count = len(seen_links)

                # Scroll 4 lần
                # for i in range(4):
                #     driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
                #     time.sleep(1.5)

                # Thu thập link bài viết mới
                articles = driver.find_elements(By.CSS_SELECTOR, "div.list_news ul li.tlitem")
                for article in articles:
                    try:
                        a_tag = article.find_element(By.CSS_SELECTOR, "a")
                        href = a_tag.get_attribute("href")
                        if href:
                            if href.startswith("/"):
                                href = urljoin("https://vtv.vn", href)
                            if href not in seen_links:
                                seen_links.add(href)
                    except Exception:
                        continue

                # So sánh số lượng link sau khi quét
                current_count = len(seen_links)
                new_links_found = current_count - previous_count
                # Nếu không có link mới → dừng
                if new_links_found == 0:
                    print("✅ Không còn link mới. Kết thúc.")
                    break

                # Nếu có link mới, click nút "Xem thêm"
                try:
                    next_button = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(text(),'Xem thêm')]")))
                    driver.execute_script("arguments[0].scrollIntoView();", next_button)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_button)
                    print("➡️ Đã click 'Xem thêm'")
                    time.sleep(2)
                except Exception as e:
                    print("❌ Không tìm thấy hoặc không click được nút 'Xem thêm':", e)
                    break

        finally:
            driver.quit()

        print(f"📄 Tổng số link thu thập được: {len(seen_links)}")
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

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        audio_tag = soup.find("audio", src=True)
        if audio_tag:
            return audio_tag["src"]
        return ""

    def crawl_podcast_bs4(self, category_url: str):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(category_url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        items = soup.select("div.flex-latest-news.br-bot div.box-liti-news div.box-category-middle div.box-category-item")
        BASE_DOMAIN = "https://vtv.vn"
        podcasts = []
        try:
            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(60)
            try:
                driver.get(category_url)
            except TimeoutException:
                print("⚠️ Load trang quá lâu, bỏ qua:", category_url)
                driver.quit()
                return

            # click "Xem thêm" nhiều lần
            while True:
                try:
                    btn = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.btn-views[title="Xem thêm"]'))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
                except (TimeoutException, NoSuchElementException):
                    break
            soup = BeautifulSoup(driver.page_source, "html.parser")
            driver.quit()

            items = soup.select(
                "div.flex-latest-news.br-bot div.box-liti-news div.box-category-middle div.box-category-item"
            )
            for item in items:
                # 1. Title + URL
                title_elem = item.select_one("a[title]")
                if not title_elem:
                    continue
                title = title_elem.get("title", "").strip()
                url = title_elem.get("href", "")
                if url.startswith("/"):
                    url = BASE_DOMAIN + url
                print("title", title)
                # 2. Thumbnail (từ <img> hoặc <source data-srcset>)
                thumb_elem = item.select_one("img")
                thumbnail = thumb_elem.get("src", "") if thumb_elem else ""
                # 3. Category (nếu cần)
                # Lấy category ở đầu trang
                cat_tag = item.select_one("a.box-category-category")
                category = cat_tag.get_text(strip=True) if cat_tag else ""

                # 4. Audio URL 
                audio_url = ""
                audio_url = self.get_audio_from_article(url)

                podcast = {
                    "title": title,
                    "url": url,
                    "thumbnail": thumbnail,
                    "category": category,
                    "audio_url": audio_url
                }
                send_podcast_to_kafka(podcast)
                # podcasts.append({
                #     "title": title,
                #     "url": url,
                #     "thumbnail": thumbnail,
                #     "category": category,
                #     "audio_url": audio_url
                # })
            # return podcasts
        except Exception as e:
            print("❌ Lỗi trong quá trình crawl:", e)
            try:
                driver.quit()
            except:
                pass
    def crawl_postcast(self):
        podcast_type_dict = {
            0: "hat-giong-tam-hon.htm",
            1: "oi-nghe-ne.htm",
            2: "doi-thoai-truc-tuyen.htm",
            3: "nhip-song-24h.htm",
            4: "thoi-su-hang-ngay.htm",
            5: "tam-su-dem.htm",
        }

        BASE_URL = "https://vtv.vn/podcast/"

        for idx, slug in podcast_type_dict.items():
            category_url = BASE_URL + slug
            print(f"🔎 Crawl category {slug} => {category_url}")
            self.crawl_podcast_bs4(category_url)
