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
import time


FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class TapChiDienDanDoanhNghiepCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://diendandoanhnghiep.vn/"
        self.article_type_dict = {
            0: "chinh-tri-xa-hoi/chinh-tri",
            1: "chinh-tri-xa-hoi/kinh-te",
            2: "chinh-tri-xa-hoi/xa-hoi",
            3: "chinh-tri-xa-hoi/van-de-hom-nay",
            4: "chinh-tri-xa-hoi/tam-diem",

            5: "vcci/phat-trien-ben-vung",
            6: "vcci/tieng-noi-cua-hiep-hoi-doanh-nghiep",
            7: "vcci/doanh-nghiep-hang-dau-viet-nam",
            8: "vcci/xuc-tien-dau-tu-thuong-mai",
            9: "vcci/dai-hoi-vcci-lan-thu-vii",
            10: "vcci/tham-muu-chinh-sach",

            11: "doanh-nghiep/quan-tri",
            12: "doanh-nghiep/chuyen-dong",
            13: "doanh-nghiep/giao-thuong",

            14: "phong-su-anh",
            15: "bai-bao-in",
            16: "tin-luu-tru",

            17: "doanh-nhan/chuyen-lam-an",
            18: "doanh-nhan/trach-nhiem-xa-hoi",
            19: "doanh-nhan/ca-phe-doanh-nhan",
            20: "doanh-nhan/phong-cach-song",

            21: "phap-luat/nghien-cuu-trao-doi",
            22: "phap-luat/ban-doc",
            23: "phap-luat/kien-nghi",
            24: "phap-luat/24h",
            25: "phap-luat/nhin-thang-noi-that",
            26: "phap-luat/chong-hang-gia",
            27: "phap-luat/ho-so",
            28: "phap-luat/phap-dinh",
            
            29: "bat-dong-san/thi-truong",
            30: "bat-dong-san/doanh-nghiep-du-an",
            31: "bat-dong-san/chinh-sach-quy-hoach",
            32: "bat-dong-san/cafe-dia-oc",
            33: "bat-dong-san/tien-do-du-an",

            34: "quoc-te/doi-ngoai",
            35: "quoc-te/kinh-te-the-gioi",
            36: "quoc-te/phan-tich-binh-luan",
             
            37: "ngan-hang-chung-khoan/chung-khoan",
            38: "ngan-hang-chung-khoan/tin-dung-ngan-hang",
            39: "ngan-hang-chung-khoan/tai-chinh-doanh-nghiep",
            40: "ngan-hang-chung-khoan/thi-truong-vang",
            41: "ngan-hang-chung-khoan/dich-vu-tai-chinh",
            42: "ngan-hang-chung-khoan/tai-chinh-so",
            43: "ngan-hang-chung-khoan/chuyen-de",

            44: "du-lich/trai-nghiem",
            45: "du-lich/hoat-dong-du-lich",
            46: "du-lich/hoi-nhap",

            47: "kinh-te-dia-phuong",

            48: "cong-nghe/kinh-te-so",
            49: "cong-nghe/ung-dung",
            50: "cong-nghe/chuyen-doi-so",
            
            51: "o-to-xe-may/dien-dan",
            52: "o-to-xe-may/thong-tin-thi-truong",
            53: "o-to-xe-may/san-pham",
            54: "o-to-xe-may/tu-van-ky-thuat",

            55: "doanh-nghiep-thi-truong/thong-tin-doanh-nghiep",
            56: "doanh-nghiep-thi-truong/san-pham-thi-truong",
            
            57: "nguoi-tot-viec-tot",

            58: "khoi-nghiep/khoi-nghiep-quoc-gia",
            59: "khoi-nghiep/y-tuong-kinh-doanh",
            60: "khoi-nghiep/kinh-doanh-liem-chinh",
            61: "khoi-nghiep/cau-chuyen-khoi-nghiep",
            62: "khoi-nghiep/co-van-huan-luyen",
            63: "khoi-nghiep/so-tay-khoi-nghiep",


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

        except Exception as e:
            print("⚠️ Lỗi khi lấy logo:", e)

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
            title_tag = soup.select_one("h1.sc-longform-header-title.block-sc-title")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("p.sc-longform-header-sapo")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("span.sc-longform-header-date.block-sc-publish-time")
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            content_images = []
            entry_div = soup.find('div', class_='entry entry-no-padding')
            paragraphs = entry_div.find_all('p')

            contents = []
            for p in paragraphs:
                # Kiểm tra tổ tiên (parents) của thẻ <p>
                if not p.find_parent(class_='sc-longform-header'):
                    contents.append(p.get_text(strip=True))

            # Nếu muốn gộp nội dung

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
            author_tag = soup.select_one("span.sc-longform-header-author.block-sc-author")
            author = author_tag.get_text(strip=True) if author_tag else None

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
        page_url = f"https://diendandoanhnghiep.vn/{article_type}"
        driver.get(page_url)
        time.sleep(1)
        seen_links = set()
        ul_element = driver.find_element(By.CSS_SELECTOR, "ul.onecms__loading ")
        page = 0
        max_page = 5
        try:
            while page < max_page:
                # Lấy các bài viết hiện tại
                articles = ul_element.find_elements(By.CSS_SELECTOR, "h3.b-grid__title a")
                for article in articles:
                    link = article.get_attribute("href")
                    seen_links.add(link)
                # Thử click nút "Xem thêm"
                try:
                    load_more_button = driver.find_element(By.CSS_SELECTOR, "div.c-more a")
                    if load_more_button.is_displayed():
                        load_more_button.click()
                        print("🔄 Đã click 'Xem thêm'")
                        time.sleep(1)
                        page += 1
                    else:
                        break
                except Exception:
                    print("✅ Không còn 'Xem thêm' hoặc gặp lỗi.")
                    break
        finally:
            driver.quit()
        return seen_links

    def get_all_articles(self, category):
        
        all_articles = []

        for category in self.article_type_dict.values():
            urls = get_urls_of_type(self, category)
            all_articles.extend(urls)

        return all_articles