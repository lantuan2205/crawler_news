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
from io import BytesIO

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

class BaoTinTucCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baotintuc.vn/"
        self.article_type_dict = {
            0: "thoi-su-472ct0",
            1: "chinh-tri-321ct472",
            2: "chinh-sach-va-cuoc-song-603ct472",
            3: "chinh-phu-voi-nguoi-dan-589ct472",
            4: "viet-nam-ky-nguyen-moi-1622ct472",
            5: "phan-hoi-phan-bien-473ct472",
            6: "the-gioi-130ct0",
            7: "phan-tichnhan-dinh-525ct130",
            8: "chuyen-la-the-gioi-162ct130",
            9: "nguoi-viet-4-phuong-478ct130",
            10: "kinh-te-128ct0",
            11: "thi-truong-tien-te-587ct128",
            12: "doanh-nghiep-doanh-nhan-145ct128",
            13: "bat-dong-san-144ct128",
            14: "tai-chinh-ngan-hang-606ct128",
            15: "nguoi-tieu-dung-147ct128",
            16: "xa-hoi-129ct0",
            17: "van-de-quan-tam-149ct129",
            18: "phong-su-dieu-tra-581ct129",
            19: "nguoi-tot-viec-tot-588ct129",
            20: "mang-xa-hoi-604ct129",
            21: "chinh-sach-bhxh-bhyt-591ct129",
            22: "phap-luat-475ct0",
            23: "van-ban-moi-577ct475",
            24: "an-ninh-trat-tu-579ct475",
            25: "chong-buon-lau-hang-gia-590ct475",
            26: "don-thu-ban-doc-607ct475",
            27: "van-hoa-158ct0",
            28: "doi-song-van-hoa-272ct158",
            29: "giai-tri-sao-274ct158",
            30: "du-lich-132ct158",
            31: "sang-tac-487ct158",
            32: "am-thuc-576ct158",
            33: "giao-duc-135ct0",
            34: "tuyen-sinh-325ct135",
            35: "du-hoc-480ct135",
            36: "ban-tron-giao-duc-311ct135",
            37: "tu-van-608ct135",
            38: "the-thao-273ct0",
            39: "bong-da-547ct273",
            40: "tennis-549ct273",
            41: "the-thao-24h-548ct273",
            42: "chuyen-the-thao-582ct273",
            43: "ho-so-133ct0",
            44: "giai-mat-541ct133",
            45: "the-gioi-bi-an-561ct133",
            46: "nhan-vat-su-kien-562ct133",
            47: "vu-an-noi-tieng-563ct133",
            48: "quan-su-514ct0",
            49: "ho-so-quan-su-556ct514",
            50: "tap-tran-dien-tap-592ct514",
            51: "vu-khi-khi-tai-557ct514",
            52: "khoa-hoc-cong-nghe-131ct0",
            53: "o-to-xe-may-491ct131",
            54: "dien-tu-vien-thong-492ct131",
            55: "khoa-hoc-doi-song-515ct131",
            56: "bien-dao-viet-nam-537ct0",
            57: "bao-ve-chu-quyen-538ct537",
            58: "kinh-te-bien-dao-574ct537",
            59: "hoi-dap-luat-canh-sat-bien-596ct537",
            60: "suc-khoe-564ct0",
            61: "chinh-sach-609ct564",
            62: "dich-benh-610ct564",
            63: "benh-vien-bac-si-611ct564",
            64: "gioi-tinh-566ct564",
            65: "dia-phuong-529ct0",
            66: "ha-noi-612ct529",
            67: "tp-ho-chi-minh-613ct529",
            68: "da-nang-614ct529",
            69: "tay-bac-tay-nguyen-tay-nam-bo-550ct529",
                                                                                                
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
            title = soup.find('h1', class_='detail-title').get_text(strip=True)

            # Trích xuất ngày viết bài
            publish_date = soup.select_one('div.date span.txt').get_text(strip=True)
            description = soup.find('h2', class_='sapo').get_text(strip=True)

            content_div = soup.select_one(".boxdetail .contents")
            content = ""
            if content_div:
                # Loại bỏ các thẻ không phải là nội dung chính (nếu cần)
                for tag in content_div.select("script, style, .share"):
                    tag.decompose()
                content = content_div.get_text(separator="\n", strip=True)

            # Lấy các URL ảnh và alt text từ các thẻ img trong thẻ figure
            content_images = []
            for figure in content_div.select("figure.image"):
                img_tag = figure.find("img")
                caption = figure.find("figcaption")
                if img_tag and img_tag.get("src"):
                    content_images.append(img_tag["src"])

            author_tag = soup.find("div", class_="author")
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
        if (page_number > 100):
            return []
        page_url = f"https://baotintuc.vn/{article_type}/trang-{page_number}.htm"
        urls = []

        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        base_url = "https://baotintuc.vn"
        items = soup.select("li.item a.thumb")

        if (len(items) == 0):
            return []

        for item in items:
            href = item.get("href")
            if href:
                full_url = base_url + href
                urls.append(full_url)
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
            domain = "https://baotintuc.vn"
            for li in soup.select("#search_result ul.list-newsest li.item"):
                a_tag = li.find("a", class_="thumb")
                if a_tag and a_tag.get("href"):
                    href = a_tag["href"]
                    if href.startswith("/"):
                        href = domain + href
                    urls.add(href)

            return list(urls)
        except Exception as e:
            return []