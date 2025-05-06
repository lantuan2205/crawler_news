import requests
import sys
import json
import os
from pathlib import Path
import random
import time
from urllib.parse import urljoin
import paramiko
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup
from utils.service_utils import clean_date

FILE = Path(__file__).resolve()
ROOT = FILE.parents[1]  # root directory
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))  # add ROOT to PATH

from logger import log
from crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.mongodb_utils import save_image_metadata

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class VietNamNetCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://vietnamnet.vn"
        self.article_type_dict = {
            0: "thoi-su",
            1: "kinh-doanh",
            2: "the-thao",
            3: "van-hoa",
            4: "giai-tri",
            5: "the-gioi",
            6: "doi-song",
            7: "giao-duc",
            8: "suc-khoe",
            9: "thong-tin-truyen-thong",
            10: "phap-luat",
            11: "oto-xe-may",
            12: "bat-dong-san",
            13: "du-lich",
            14: "chinh-tri",
            15: "ban-doc",
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
            newspaper_name = "vietnamnet"
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

        title_tag = soup.find("h1", class_="content-detail-title")
        desc_tag = soup.find("h2", class_=["content-detail-sapo", "sm-sapo-mb-0"])
        main_content_tag = soup.find("div", class_=["maincontent", "main-content"])

        date_tag = soup.find("div", class_="bread-crumb-detail__time")
        published_date = date_tag.text.strip() if date_tag else "Không có thông tin"

        # Lấy ảnh đại diện (ưu tiên ảnh img-content, sau đó meta og:image)
        image_url = "Không có ảnh"
        img_tag = soup.find("img", class_="img-content")
        if img_tag and img_tag.get("src"):
            image_url = img_tag["src"]
        else:
            img_meta = soup.find("meta", property="og:image")
            if img_meta and img_meta.get("content"):
                image_url = img_meta["content"]

        # Lấy tất cả các ảnh trong nội dung bài viết (cập nhật theo cấu trúc HTML Vietnamnet)
        content_images = []
        if main_content_tag:
            img_tags = main_content_tag.find_all("img")
            for img in img_tags:
                img_url_content = img.get("src") or img.get("data-original")
                if img_url_content and not img_url_content.startswith("data:image"):
                    content_images.append(urljoin("https://vietnamnet.vn", img_url_content) if img_url_content.startswith("/") else img_url_content)
                elif img.find_parent("picture"):
                    source = img.find_previous("source")
                    if source and source.get("data-srcset"):
                        srcset = source["data-srcset"].split(',')[0].strip().split()[0].strip()
                        content_images.append(urljoin("https://vietnamnet.vn", srcset))

        comment_tags = soup.find_all("div", class_="comment-content")
        comments = [comment.text.strip() for comment in comment_tags] if comment_tags else []

        if not all([title_tag, desc_tag, main_content_tag]):
            return None, None, None, None, None, None, None, None

        title = title_tag.text
        description = (get_text_from_tag(p) for p in desc_tag.contents)
        paragraphs = (get_text_from_tag(p) for p in main_content_tag.find_all("p"))

        author = ""
        author_box = soup.find("div", class_="article-detail-author")
        if author_box:
            name_span = author_box.find("span", class_="name")
            if name_span:
                author = name_span.text.strip()
            else:
                link_author = author_box.find("a")
                if link_author:
                    author = link_author.text.strip()

        return title, description, paragraphs, published_date, image_url, comments, author, content_images

    def write_content(self, url: str, article_type: str) -> bool:
        try:
            title, description, paragraphs, published_date, image_url, comments, author, content_images = self.extract_content(url)
            if not title:
                return None
            
            # Lấy thể loại từ URL
            category = article_type
                
            # Tải và lưu ảnh nội dung
            content_image_paths = []
            for img_url in content_images:
                if img_url:
                    img_path = self.download_image(img_url, title, category, published_date)
                    if img_path:
                        content_image_paths.append(img_path)
            
            article_data = {
                "dataSource": "/".join(url.split("/")[:3]),
                "url": url,
                "title": title,
                "author": author,
                "publishedDate": clean_date(published_date),
                "imageUrl": image_url,
                "description": " ".join(list(description)),
                "content": ",".join(list(paragraphs)),
                "comments": comments,
                "contentImageUrls": content_images,
                "localContentImagePaths": content_image_paths
            }

            return article_data
            
        except Exception as e:
            print(f"Lỗi khi xử lý URL {url}: {e}")       
            return None
    
    def get_urls_of_type_thread(self, article_type, page_number):
        page_url = f"https://vietnamnet.vn/{article_type}-page{page_number-1}"
        articles_urls = []
        try:
            content = requests.get(page_url, headers=headers).content
            sleep_time = random.uniform(1, 2)
            time.sleep(sleep_time)
            soup = BeautifulSoup(content, "html.parser")
            titles = soup.find_all(class_=["horizontalPost__main-title", "vnn-title", "title-bold"])

            if (len(titles) == 0):
                self.logger.info(f"Couldn't find any news in {page_url} \nMaybe you sent too many requests, try using less workers")
                return []

            for title in titles:
                full_url = title.find_all("a")[0].get("href")
                if self.base_url not in full_url:
                    full_url = self.base_url + full_url
                articles_urls.append(full_url)
        except Exception as e:
            self.logger.warning(f"[!] Error while fetching {page_url}: {e}")
            return []

        return articles_urls

    def get_all_articles(self, max_pages):
        all_articles = []
        
        for category in self.article_type_dict.values():
            for page in range(1, max_pages + 1):
                urls = self.get_urls_of_type_thread(category, page)
                all_articles.extend(urls)
        
        return all_articles

