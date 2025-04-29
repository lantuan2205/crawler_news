import json
import requests
import sys
import time
import random
import os
from pathlib import Path
from datetime import datetime
import paramiko
from io import BytesIO
from pathlib import Path
from bs4 import BeautifulSoup

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from logger import log
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date
from utils.mongodb_utils import save_image_metadata

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VNExpressCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.article_type_dict = {
            0: "thoi-su/chinh-tri",
            1: "thoi-su/huong-toi-ky-nguyen-moi/tinh-gon-bo-may",
            2: "thoi-su/chinh-tri/nhan-su",
            3: "thoi-su/dan-sinh",
            4: "thoi-su/lao-dong-viec-lam",
            5: "thoi-su/giao-thong",
            6: "thoi-su/mekong",
            7: "thoi-su/quy-hy-vong",
            8: "the-gioi/tu-lieu",
            9: "the-gioi/phan-tich",
            10: "the-gioi/nguoi-viet-5-chau",
            11: "the-gioi/cuoc-song-do-day",
            12: "the-gioi/quan-su",
            13: "kinh-doanh/net-zero",
            14: "kinh-doanh/quoc-te",
            15: "kinh-doanh/doanh-nghiep",
            16: "kinh-doanh/chung-khoan",
            17: "kinh-doanh/ebank",
            18: "kinh-doanh/vi-mo",
            19: "kinh-doanh/tien-cua-toi",
            20: "kinh-doanh/hang-hoa",
            21: "khoa-hoc-cong-nghe/bo-khoa-hoc-va-cong-nghe",
            22: "khoa-hoc-cong-nghe/chuyen-doi-so",
            23: "khoa-hoc-cong-nghe/doi-moi-sang-tao",
            24: "khoa-hoc-cong-nghe/ai",
            25: "khoa-hoc-cong-nghe/vu-tru",
            26: "khoa-hoc-cong-nghe/the-gioi-tu-nhien",
            27: "khoa-hoc-cong-nghe/thiet-bi",
            28: "khoa-hoc-cong-nghe/cua-so-tri-thuc",
            29: "bat-dong-san/chinh-sach",
            30: "bat-dong-san/thi-truong",
            31: "bat-dong-san/du-an",
            32: "bat-dong-san/khong-gian-song",
            33: "suc-khoe/tin-tuc",
            34: "suc-khoe/cac-benh",
            35: "suc-khoe/song-khoe",
            36: "suc-khoe/vaccine",
            37: "the-thao/marathon",
            38: "bong-da",
            39: "the-thao/tennis",
            40: "the-thao/cac-mon-khac",
            41: "the-thao/hau-truong",
            42: "giai-tri/gioi-sao",
            43: "giai-tri/sach",
            44: "giai-tri/phim",
            45: "giai-tri/nhac",
            46: "giai-tri/thoi-trang",
            47: "giai-tri/lam-dep",
            48: "giai-tri/san-khau-my-thuat",
            49: "phap-luat/ho-so-pha-an",
            50: "giao-duc/tin-tuc",
            51: "giao-duc/tuyen-sinh/lop-6",
            52: "giao-duc/chan-dung",
            53: "giao-duc/tuyen-sinh/lop-10",
            54: "giao-duc/tuyen-sinh/dai-hoc",
            55: "giao-duc/du-hoc",
            56: "giao-duc/thao-luan",
            57: "giao-duc/hoc-tieng-anh",
            58: "giao-duc/giao-duc-40",
            59: "doi-song/nhip-song",
            60: "doi-song/to-am",
            61: "doi-song/bai-hoc-song",
            62: "doi-song/tieu-dung",
            63: "oto-xe-may/thi-truong",
            64: "oto-xe-may/xe-dien",
            65: "oto-xe-may/cam-lai",
            66: "du-lich/diem-den",
            67: "du-lich/am-thuc",
            68: "du-lich/dau-chan",
            69: "y-kien/thoi-su",
            70: "y-kien/doi-song"
        }

    def download_image(self, image_url, article_title, category, published_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:

            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: vnexpress/category/date
            newspaper_name = "vnexpress"
            date_parts = clean_date(published_date).split(',')[0].strip()  # Lấy phần trước dấu phẩy
            day, month, year = date_parts.split('/')  # Tách ngày, tháng, năm
            date_folder = f"{day}-{month}-{year}"  # Tạo định dạng mới

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

            # Ghi ảnh vào máy B
            with sftp.open(str(remote_path), 'wb') as remote_file:
                remote_file.write(image_data.getbuffer())

            sftp.close()
            ssh.close()
            # Lưu metadata vào MongoDB
            image_data = {
                'image_url': image_url,
                'local_path': str(remote_path),
                'file_size': len(image_data.getbuffer())
            }
            save_image_metadata(image_data)

            return str(remote_path)

        except Exception as e:
            print(f"Lỗi khi tải ảnh {image_url}: {e}")
            return None

    def extract_content(self, url: str) -> tuple:
        content = requests.get(url, headers=headers).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")

        title = soup.find("h1", class_="title-detail")
        if title == None:
            return None, None, None, None, None, None, None, None
        title = title.text

        # some sport news have location-stamp child tag inside description tag
        description = (get_text_from_tag(p) for p in soup.find("p", class_="description").contents)
        paragraph_tags = soup.find_all("p", class_="Normal")
        if paragraph_tags:
            author = paragraph_tags[-1].text.strip()  # Lấy tác giả từ thẻ cuối
            del paragraph_tags[-1]  # Xóa để tránh lặp
        else:
            author = None

        paragraphs = (get_text_from_tag(p) for p in paragraph_tags)

        # Lấy ngày đăng bài
        time_element = soup.find("span", class_="date")
        published_date = time_element.text.strip() if time_element else None

        # Lấy ảnh đại diện
        image_element = soup.find("meta", property="og:image")
        image_url = image_element["content"] if image_element else None

        comments = []
        comment_section = soup.find("div", class_="box_comment")  # Kiểm tra class thật của VnExpress

        if comment_section:
            comment_tags = comment_section.find_all("div", class_="comment_content")  # Kiểm tra thẻ chứa nội dung bình luận
            comments = [c.text.strip() for c in comment_tags]

        # Lấy tất cả các ảnh trong nội dung bài viết
        image_tags = soup.find_all("img", class_="lazy") # VNExpress thường dùng class "lazy" cho ảnh trong nội dung
        content_image_urls = [img.get("data-src") for img in image_tags if img.get("data-src")]

        return title, description, paragraphs, published_date, image_url, comments, author, content_image_urls

    def write_content(self, url: str, article_type: str) -> bool:
        try:
            title, description, paragraphs, published_date, image_url, comments, author, content_image_urls = self.extract_content(url)
            if not title:  # Nếu không có tiêu đề, bỏ qua bài viết
                return None

            # Lấy thể loại từ URL
            category = article_type

            # Tải và lưu ảnh nội dung
            content_image_paths = []
            for img_url in content_image_urls:
                if img_url:
                    img_path = self.download_image(img_url, title, category, published_date)
                    if img_path:
                        content_image_paths.append(img_path)
            article_data = {
                "dataSource": "/".join(url.split("/")[:3]),
                "url": url,
                "publishedDate": clean_date(published_date),
                "author": author,
                "title": title,
                "imageUrl": image_url,
                "description": " ".join(list(description)),
                "content": ",".join(list(paragraphs)),
                "comments": list(comments) if comments else [""],
                "contentImageUrls": content_image_urls,
                "localContentImagePaths": content_image_paths
            }

            return article_data

        except Exception as e:
            print(f"Lỗi khi xử lý URL {url}: {e}")
            return None

    def get_urls_of_type_thread(self, article_type, page_number):
        page_url = f"https://vnexpress.net/{article_type}-p{page_number}"
        content = requests.get(page_url, headers=headers).content
        sleep_time = random.uniform(1, 2)
        time.sleep(sleep_time)
        soup = BeautifulSoup(content, "html.parser")
        titles = soup.find_all(class_="title-news")

        if (len(titles) == 0):
            self.logger.info(f"Couldn't find any news in {page_url} \nMaybe you sent too many requests, try using less workers")

        articles_urls = list()

        for title in titles:
            link = title.find_all("a")[0]
            articles_urls.append(link.get("href"))

        return articles_urls

    def get_all_articles(self, max_pages):
        """Lấy tất cả bài báo từ các danh mục trên VNExpress."""
        all_articles = []

        for category in self.article_type_dict.values():
            for page in range(1, max_pages + 1):
                urls = self.get_urls_of_type_thread(category, page)
                all_articles.extend(urls)

        return all_articles
