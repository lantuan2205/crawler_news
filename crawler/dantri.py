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
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class DanTriCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://dantri.com.vn"
        self.article_type_dict = {
            0: "kinh-doanh/tai-chinh",
            1: "kinh-doanh/chung-khoan",
            2: "kinh-doanh/doanh-nghiep",
            3: "kinh-doanh/khoi-nghiep",
            4: "kinh-doanh/tieu-dung",
            5: "kinh-doanh/esg-phat-trien-ben-vung",

            6: "xa-hoi/chinh-tri",
            7: "xa-hoi/hoc-tap-bac",
            8: "xa-hoi/ky-nguyen-moi",
            9: "xa-hoi/moi-truong",
            10: "xa-hoi/giao-thong",
            11: "xa-hoi/nong-tren-mang",

            12: "the-gioi/quan-su",
            13: "the-gioi/phan-tich-binh-luan",
            14: "the-gioi/the-gioi-do-day",
            15: "the-gioi/kieu-bao",

            16: "giai-tri/hau-truong",
            17: "giai-tri/sach-hay/tin-tuc",
            18: "giai-tri/sach-hay/sach-hay-tren-ke",
            19: "giai-tri/dien-anh",
            20: "giai-tri/am-nhac",
            21: "giai-tri/thoi-trang",
            22: "giai-tri/hat-giong-tam-hon",
            23: "giai-tri/my-thuat-san-khau",

            24: "bat-dong-san/du-an",
            25: "bat-dong-san/thi-truong",
            26: "bat-dong-san/nha-dat/thi-truong",
            27: "bat-dong-san/nha-dat/cau-chuyen-dau-tu",
            28: "bat-dong-san/nha-dat/nghe-moi-gioi-bat-dong-san",
            29: "bat-dong-san/nha-dat/cuoc-thi-nha-moi-gioi-bds-uy-tin",
            30: "bat-dong-san/nhip-song-do-thi",
            31: "bat-dong-san/song-xanh/tin-tuc",
            32: "bat-dong-san/song-xanh/tam-nhin-do-thi",
            33: "bat-dong-san/song-xanh/nhip-song-xanh",
            34: "bat-dong-san/song-xanh/khong-gian-song",
            35: "bat-dong-san/song-xanh/khoanh-khac",
            36: "bat-dong-san/song-xanh/co-hoi-dau-tu",
            37: "bat-dong-san/noi-that",

            38: "the-thao/bong-da",
            39: "the-thao/bong-da/bong-da-quoc-te",
            40: "the-thao/bong-da/v-league",
            41: "the-thao/bong-da/bong-da-anh",
            42: "the-thao/bong-da/bong-da-tay-ban-nha",
            43: "the-thao/bong-da/bong-da-y-duc-phap",
            44: "the-thao/bong-da/champions-league",
            45: "the-thao/bong-da/europa-league",

            46: "the-thao/pickleball",
            47: "the-thao/tennis",
            48: "the-thao/golf",
            49: "the-thao/vo-thuat-cac-mon-khac",
            50: "the-thao/hau-truong",

            51: "suc-khoe/ung-thu/tin-tuc",
            52: "suc-khoe/ung-thu/kien-thuc-ung-thu",
            53: "suc-khoe/song-khoe/loi-song-van-dong",
            54: "suc-khoe/song-khoe/dinh-duong-toan-dien",
            55: "suc-khoe/song-khoe/ung-thu.htm",
            56: "suc-khoe/song-khoe/tim-mach.htm",
            57: "suc-khoe/ngoai-than-kinh-cot-song/y-te-chat-luong-cao.htm",
            58: "suc-khoe/ngoai-than-kinh-cot-song/ngoai-than-kinh-cot-song.htm",
            59: "suc-khoe/ngoai-than-kinh-cot-song/chan-thuong-chinh-hinh.htm",
            60: "suc-khoe/ngoai-than-kinh-cot-song/ngoai-tong-hop.htm",
            61: "suc-khoe/ngoai-than-kinh-cot-song/noi-tong-hop.htm",
            62: "suc-khoe/kien-thuc-gioi-tinh.htm",
            63: "suc-khoe/tu-van.htm",
            64: "suc-khoe/khoe-dep.htm",

            65: "noi-vu/chinh-sach.htm",
            66: "noi-vu/to-chuc-bo-may.htm",
            67: "noi-vu/tien-luong.htm",
            68: "noi-vu/cong-so.htm",

            69: "o-to-xe-may/thi-truong-xe.htm",
            70: "o-to-xe-may/xe-dien.htm",
            71: "o-to-xe-may/cam-lai.htm",
            72: "o-to-xe-may/danh-gia.htm",
            73: "o-to-xe-may/kinh-nghiem-tu-van.htm",
            74: "o-to-xe-may/cong-dong-xe.htm",

            75: "cong-nghe/ai-internet.htm",
            76: "cong-nghe/an-ninh-mang.htm",
            77: "cong-nghe/gia-dung-thong-minh.htm",
            78: "cong-nghe/san-pham-cong-dong.htm",

            79: "giao-duc/tuyen-sinh/bi-quyet-hoc-va-thi.htm",
            80: "giao-duc/tuyen-sinh/de-thi-dap-an.htm",
            81: "giao-duc/tuyen-sinh/gap-go-cac-truong.htm",

            82: "giao-duc/goc-phu-huynh.htm",
            83: "giao-duc/khuyen-hoc.htm",
            84: "giao-duc/guong-sang.htm",
            85: "giao-duc/giao-duc-nghe-nghiep.htm",
            86: "giao-duc/du-hoc/co-hoi-du-hoc.htm",
            87: "giao-duc/du-hoc/the-gioi-du-hoc.htm",
            88: "giao-duc/du-hoc/tai-tri-viet.htm",

            89: "lao-dong-viec-lam/nhan-luc-moi.htm",
            90: "lao-dong-viec-lam/lam-giau.htm",
            91: "lao-dong-viec-lam/an-sinh.htm",
            92: "lao-dong-viec-lam/chuyen-nghe.htm",
            93: "lao-dong-viec-lam/chinh-sach.htm",

            94: "phap-luat/ho-so-vu-an.htm",
            95: "phap-luat/phap-dinh.htm",

            96: "du-lich/tin-tuc.htm",
            97: "du-lich/kham-pha.htm",
            98: "du-lich/mon-ngon-diem-dep.htm",
            99: "du-lich/tour-hay-khuyen-mai.htm",

            100: "doi-song/cong-dong.htm",
            101: "doi-song/thuong-luu.htm",
            102: "doi-song/nha-dep.htm",
            103: "doi-song/gioi-tre.htm",
            104: "doi-song/cho-online.htm",

            105: "tinh-yeu-gioi-tinh/chuyen-cua-toi.htm",
            106: "tinh-yeu-gioi-tinh/gia-dinh.htm",
            107: "tinh-yeu-gioi-tinh/tinh-yeu.htm",
            108: "khoa-hoc/the-gioi-tu-nhien.htm",
            109: "khoa-hoc/vu-tru.htm",
            110: "khoa-hoc/kham-pha.htm",
            111: "khoa-hoc/khoa-hoc-doi-song.htm",


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
            newspaper_name = "dantri"
            date_parts = clean_date(published_date).split(',')[0].strip()
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
        
    def extract_content(self, url: str) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title_tag = soup.find("h1", class_="title-page detail")
            title = title_tag.text.strip() if title_tag else None

            sapo_tag = soup.find("h2", class_="singular-sapo")
            description = sapo_tag.get_text(strip=True) if sapo_tag else "Không tìm thấy mô tả"

            content_div = soup.find("div", class_="singular-content")
            paragraph_tags = content_div.find_all("p") if content_div else []
            content = "\n".join(p.get_text(strip=True) for p in paragraph_tags) if paragraph_tags else None

            time_tag = soup.find("time", class_="author-time")
            publish_date = time_tag.get_text(strip=True) if time_tag else "Không tìm thấy ngày đăng"

            content_images = []
            if content_div:
                img_tags = content_div.find_all("img")
                for img in img_tags:
                    if "data-src" in img.attrs:
                        content_images.append(img["data-src"])

            author_tag = soup.find("div", class_="author-name")
            author = author_tag.get_text(strip=True) if author_tag else "Không rõ tác giả"

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
        content_image_paths = []
        for img_url in content_images:
            if img_url:
                img_path = self.download_image(img_url, title, article_type, publish_date)
                if img_path:
                    content_image_paths.append(img_path)
                    
        article_data = {
            "dataSource": "/".join(url.split("/")[:3]),
            "url": url,
            "publishedDate": clean_date(publish_date),
            "author": author,
            "title": title,
            "description": description,
            "content": content,
            "contentImageUrls": content_images,
            "localContentImagePaths": content_image_paths
        }

        return article_data
    
    def get_urls_of_type_thread(self, article_type, page_number):
        """" Get URLs of articles in a specific type on a given page"""
        page_url = f"https://dantri.com.vn/{article_type}/trang-{page_number}.htm"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        titles = soup.find_all("h3", class_="article-title")

        if not titles:
            self.logger.warning(f"Couldn't find any news in {page_url}. Maybe too many requests?")
            return []

        articles_urls = []
        for title in titles:
            link_tag = title.find("a")  # Tìm thẻ <a>
            if link_tag and link_tag.has_attr("href"):  # Kiểm tra nếu có link
                articles_urls.append(link_tag["href"])

        return articles_urls

