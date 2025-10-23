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
        }
        
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

            # Lấy title
            title_tag = soup.select_one("h1.sc-longform-header-title.block-sc-title")
            title = title_tag.get_text(strip=True) if title_tag else None

            # Lấy description
            desc_tag = soup.select_one("p.sc-longform-header-sapo.block-sc-sapo")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            publish_date = None
            date_tag = soup.select_one("span.sc-longform-header-date.block-sc-publish-time")
            publish_date = date_tag.get_text(strip=True) if date_tag else None

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
            author_tag = soup.select_one("span.sc-longform-header-author.block-sc-author")
            author = author_tag.get_text(strip=True) if author_tag else None

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