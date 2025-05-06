import requests
import sys
from pathlib import Path
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from datetime import datetime, timedelta
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

class BaoThanhTraCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://thanhtra.com.vn/"
        self.article_type_dict = {
            0: "chinh-tri-1F7B169C8",
            # 1: "thanh-tra-CA492F2B8",
            # 2: "tiep-dan-khieu-to-0FCABC87C",
            # 3: "phong-chong-tham-nhung-A52D004FA",
            # 4: "xa-hoi-C5ACF42DB",
            # 5: "phap-luat-B2DDDF86E",
            # 6: "nha-dat-57A4B2310",
            # 7: "du-lich-E19590D86",                                                                       
        }   
        
    def download_image(self, image_url, article_title, category, publish_date):
        """Tải và lưu ảnh, trả về đường dẫn local và metadata"""
        try:
            # === CẤU HÌNH SSH đến máy B ===
            ssh_host = "192.168.161.230"
            ssh_user = "htsc"
            ssh_password = "Htsc@123"
            remote_base_dir = "/mnt/data/news"
            # Tạo cấu trúc thư mục: thanhtra/category/date
            newspaper_name = "thanhtra"
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
        
    def extract_content(self, url: str) -> tuple:
        """
        Extract title, description, content, publish date, author, and content images from url.
        @param url (str): url to crawl
        @return tuple: (title, description, content, publish_date, author, content_images)
        """
        try:
            response = requests.get(url, headers=headers)

            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Lấy title
            title = soup.find("h1", class_="text-black text-[32px] leading-tight font-bold mb-4").get_text(strip=True)

            # Lấy tên tác giả
            author_div = soup.find("div", class_="flex-shrink-0 font-semibold text-base mr-4")
            # Tìm tác giả từ thẻ <a> (nếu có)
            author_tag_a = author_div.find("a", title=True) if author_div else None
            author = author_tag_a.get_text(strip=True) if author_tag_a else None

            # Nếu không tìm thấy tác giả từ <a>, thử lấy từ thẻ <p>
            if not author:
                author_tag_p = author_div.find("p") if author_div else None
                author = author_tag_p.get_text(strip=True) if author_tag_p else None

            # Lấy description
            desc_tag = soup.find("p", class_="text-lg text-justify font-semibold mb-4")
            description = desc_tag.get_text(strip=True) if desc_tag else None

            # Trích xuất ngày viết bài
            date_tag = soup.find("p", class_="text-[#707070] text-sm")
            publish_date = date_tag.get_text(strip=True) if date_tag else None

            div_mb4 = soup.find("div", class_="mb-4")
            content_images = []
            if div_mb4:
                # Tìm tất cả thẻ img trong div
                imgs = div_mb4.find_all("img")
                for img in imgs:
                    src = img.get("src")
                    if src and "http" in src:  # chỉ lấy ảnh có link đầy đủ
                        content_images.append(src)

            # 2. Lấy content + ảnh từ div#editor-detail
            editor = soup.find("div", id="editor-detail")
            content_paragraphs = []

            if editor:
                for el in editor.find_all(["p", "img", "div"]):
                    # Lấy đoạn văn
                    if el.name == "p":
                        text = el.get_text(strip=True)
                        if text:
                            content_paragraphs.append(text)

                    # Lấy ảnh trong các khối editor-image-wrapper
                    elif el.name == "div" and "editor-image-wrapper" in el.get("class", []):
                        img_tag = el.find("img")
                        content_images.append(img_tag["src"] if img_tag else None)
            content_images = list(set(content_images))
            # Lấy nội dung của bài viết (text content)
            content = " ".join(content_paragraphs)
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
        page_url = f"https://thanhtra.com.vn/{article_type}/trang-{page_number}/loadmore"
        
        try:
            response = requests.get(page_url, headers=headers)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        urls = []
        pagination_div = soup.find("div", id="pagination")
        if pagination_div:
            articles = pagination_div.find_all("article")
            if (len(articles) == 0):
                return []
            for article in articles:
                a_tag = article.find("a", href=True)
                if a_tag:
                    href = a_tag["href"]
                    if href.startswith("/"):
                        href = "https://www.thanhtra.com.vn" + href
                    urls.append(href)
        return urls

