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
from news_crawler.base_crawler import BaseCrawler
from utils.beautifulSoup_utils import get_text_from_tag
from utils.service_utils import clean_date, get_urls_of_type

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

class BaoDanTocCrawler(BaseCrawler):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.logger = log.get_logger(name=__name__)
        self.base_url = "https://baodantoc.vn/"
        self.article_type_dict = {
            0: "thoi-su/tin-tuc",
            1: "thoi-su/su-kien-binh-luan",
            2: "thoi-su/van-ban-chinh-sach-moi",
            3: "dan-toc-ton-giao/cong-tac-dan-toc",
            4: "dan-toc-ton-giao/chinh-sach-dan-toc",
            5: "dan-toc-ton-giao/tin-nguong-ton-giao-o-viet-nam",
            6: "dan-toc-ton-giao/nguoi-co-uy-tin",
            7: "dan-toc-ton-giao/dao-va-doi",
            8: "sac-mau-54/tim-trong-di-san",
            9: "sac-mau-54/ban-sac-va-hoi-nhap",
            10: "sac-mau-54/du-lich",
            11: "sac-mau-54/am-thuc",
            12: "kinh-te/san-pham-thi-truong",
            13: "kinh-te/khoi-nghiep",
            14: "kinh-te/doanh-nhan-dan-toc",
            15: "phong-su",
            16: "doi-song-xa-hoi/nghe-nghiep-viec-lam",
            17: "doi-song-xa-hoi/nhip-cau-nhan-ai",
            18: "guong-sang-giua-cong-dong",
            19: "phap-luat/ban-doc",
            20: "phap-luat/chong-dien-bien-hoa-binh",
            21: "khoa-hoc-cong-nghe/ung-dung-sang-tao",
            22: "khoa-hoc-cong-nghe/khuyen-nong-voi-dong-bao-dtts",
            23: "khoa-hoc-cong-nghe/ban-cua-nha-nong",
            24: "giao-duc/giao-duc-dan-toc",
            25: "giao-duc/duong-den-uoc-mo",
            26: "suc-khoe/song-khoe",
            27: "suc-khoe/moi-truong-song",
            28: "suc-khoe/vuon-thuoc-quanh-ta",
            29: "trang-dia-phuong",
            30: "chuyen-de",
            31: "the-thao-giai-tri/the-thao",
            32: "the-thao-giai-tri/giai-tri",                                                                                   
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
            title = soup.find('h1', class_='news-title')['title']

            # Lấy tên tác giả
            author = soup.find('span', class_='author-name').text.strip()

            # Lấy description
            description = soup.find('h2', class_='news-sapo').text.strip()

            # Trích xuất ngày viết bài
            date = soup.find('span', class_='distribution-date')

            # Kiểm tra trường hợp "X giờ trước"
            if date:
                date_text = date.get_text().strip()
                
                if "giờ trước" in date_text:
                        # Trường hợp "X giờ trước"
                        hours_ago = int(date_text.split(' ')[0])
                        current_time = datetime.now()
                        calculated_time = current_time - timedelta(hours=hours_ago)
                        publish_date = calculated_time.strftime('%H:%M, %d/%m/%Y')
                else:
                    # Trường hợp ngày giờ định dạng "HH:MM, DD/MM/YYYY"
                    try:
                        # Định dạng thời gian "HH:MM, DD/MM/YYYY"
                        date_time = datetime.strptime(date_text, "%H:%M, %d/%m/%Y")
                        publish_date = date_time.strftime('%H:%M, %d/%m/%Y')
                    except ValueError:
                        print("Invalid date format")


            # date_tag = soup.find('div', class_='lbPublishedDate')
            # publish_date = date_tag.get_text(strip=True) if date_tag else None

            content_div = soup.find('div', class_='news-body-content')

            images = content_div.find_all('img')
            content_images = [img['src'] for img in images if img.get('src')]

            # Lấy nội dung của bài viết (text content)
            content = content_div.get_text(separator="\n").strip()
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
        page_url = f"https://baodantoc.vn/{article_type}-p{page_number}.htm"
        if page_number == 5:
            return []
        try:
            response = requests.get(page_url, headers=headers, timeout=10)
            sleep_time = random.uniform(1, 3)
            time.sleep(sleep_time)
            response.raise_for_status()  # Kiểm tra nếu request thất bại
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching {page_url}: {e}")
            return []

        soup = BeautifulSoup(response.content, "html.parser")
        news_timeline = soup.find('div', class_='news-in-timeline')

        links = news_timeline.find_all('a')
        if (len(links) == 0):
            return []

        a_urls = [
            a.get('href') for a in links
            if a.get('href') and 'tin-tuc.htm' not in a.get('href')
        ]
        
        # Thêm domain vào URL nếu cần thiết
        full_urls = [f"https://baodantoc.vn{url}" if url.startswith('/') else url for url in a_urls]
        return full_urls

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
            base_url = "https://baodantoc.vn"

            for a in soup.select("div.news-in-timeline h3 a[href]"):
                href = a["href"]
                if href.startswith("/"):
                    full_url = base_url + href
                    urls.add(full_url)
            return list(urls)
        except Exception as e:
            return []