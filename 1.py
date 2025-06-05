import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from urllib.parse import urlparse
from urllib.parse import urlparse, urlunparse

def find_menu_blocks_only(soup, min_links=3):
    """
    Tìm các block HTML chứa menu (dựa vào class/id, từ khóa mở rộng, số lượng link).
    """
    menu_keywords = ["nav", "navbar", "category"]
    candidate_blocks = []

    for tag in soup.find_all(["div", "nav", "ul", "section", "header", "aside"]):
        class_attr = " ".join(tag.get("class", [])).lower()
        id_attr = (tag.get("id") or "").lower()
        # Bổ sung thêm điều kiện riêng cho từ 'menu'
        if ("menu" in class_attr or "menu" in id_attr) or \
           any(kw in class_attr for kw in menu_keywords) or \
           any(kw in id_attr for kw in menu_keywords):
            links = [a for a in tag.find_all("a", href=True) if a['href'] != "/"]
            if len(links) >= min_links:
                candidate_blocks.append(tag)

    return candidate_blocks

def extract_links_from_blocks(blocks, base_url=None):
    """
    Trích xuất title + url từ các block lọc, loại bỏ các link trùng (theo url).
    """
    seen_urls = set()
    for block in blocks:
        for a in block.find_all("a", href=True):
            title = a.get_text(strip=True)
            url = a["href"]
            if not title:
                continue
            if base_url and url.startswith("/"):
                url = urljoin(base_url, url)
            if url in seen_urls:
                continue
            seen_urls.add(url)
    return seen_urls

def extract_menu_links(url, domain):
    """
    Hàm chính để chạy toàn bộ luồng trích xuất menu.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, timeout=10, headers=headers)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, "html.parser")

        blocks = find_menu_blocks_only(soup)
        links = extract_links_from_blocks(blocks, base_url=url)
        urls = []
        for url in links:
            if is_valid_category_url(url):
                url = clean_url(url)
                urls.append(url)
        # filter link cha chi lấy link con
        result = filter_urls_keep_only_child_or_all(urls, domain)
        return result

    except Exception as e:
        print(f"Lỗi khi lấy menu từ {url}: {e}")
        return []

def extract_categories(urls, max_depth=2):
    categories = []
    for url in urls:
        path = urlparse(url).path  # Lấy phần sau domain
        path = path.strip("/")     # Bỏ dấu / đầu và cuối
        if path.endswith(".htm"):
            path = path[:-4]  # Bỏ đuôi .htm
        parts = path.split("/")
        if len(parts) >= max_depth:
            categories.append("/".join(parts[:max_depth]))
    return categories

def is_valid_category_url(url: str) -> bool:
    """
    Kiểm tra xem URL có phải là link chuyên mục của dantri.com.vn không.
    """
    # Loại bỏ các kiểu link không phải chuyên mục

    is_article = any([
        re.search(r'\d{6,}\.htm[l]?$', url),
        re.search(r'/[^/]+-\d+\.htm[l]?$', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/\d{2}/', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/', url),
        re.search(r'-i\d+/?$', url)
    ])
    if is_article:
        return False

    exclude_patterns = [
        "mailto:", "tel:", "facebook.com", "youtube.com", "tiktok.com",
        "photo-", "interactive", "infographic", "dmagazine", "d-buzz",
        "photo-news", "photo-story", "dtinews", "fica", "catalog"
    ]

    for pattern in exclude_patterns:
        if pattern in url:
            return False

    return True

def filter_urls_keep_only_child_or_all(urls, domain):
    filtered = []
    valid_urls = []

    # Lọc các URL hợp lệ và cùng domain
    for url in urls:
        if not url.startswith("https://" + domain):
            continue
        parsed = urlparse(url)
        if domain not in parsed.netloc:
            continue
        valid_urls.append(url)

    # Giữ lại toàn bộ nếu không có URL cha-con
    parents = set()
    for parent_candidate in valid_urls:
        for child_candidate in valid_urls:
            if child_candidate != parent_candidate and child_candidate.startswith(parent_candidate.rstrip('/') + '/'):
                parents.add(parent_candidate)
                break
    # Loại bỏ cha (parents), chỉ giữ lại url không phải cha
    filtered = [url for url in valid_urls if url not in parents]
    return filtered


def clean_url(url):
    parsed = urlparse(url)
    path = parsed.path

    # Bỏ đuôi .html hoặc .htm
    if path.endswith(".html"):
        path = path[:-5]
    elif path.endswith(".htm"):
        path = path[:-4]

    # Bỏ dấu / cuối cùng nếu path dài hơn 1 ký tự (để tránh bỏ dấu / ở root)
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]

    cleaned_url = urlunparse(parsed._replace(path=path))
    return cleaned_url

# def extract_categories(urls):
#     categories = []
#     for url in urls:
#         path = urlparse(url).path.strip("/")
#         if path:
#             category = path.split("/")[0]
#             categories.append(category)
#     return categories

def is_article_url(url: str) -> bool:
    is_article = any([
        re.search(r'\d{6,}\.htm[l]?$', url),
        re.search(r'/[^/]+-\d+\.htm[l]?$', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/\d{2}/', url),
        re.search(r'/[^/]+/\d{4}/\d{2}/', url),
        re.search(r'-i\d+/?$', url)
    ])
    if(is_article):
        return True
    return False

def extract_article_urls_from_menu(menu_links):
    article_urls = set()

    for link in menu_links:
        try:
            resp = requests.get(link, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            domain = f"{resp.url.split('/')[0]}//{resp.url.split('/')[2]}"  # lấy domain gốc từ URL thực tế

            # 1. Lấy <a> trong các thẻ có class chứa 'content', 'container', 'list'
            keywords = ['content', 'container', 'list']
            for tag in soup.find_all(class_=lambda c: c and any(k in c for k in keywords)):
                for a in tag.find_all("a", href=True):
                    if(is_article_url(a['href'])):
                        article_urls.add(urljoin(domain, a['href']))

            # 2. Lấy <a> trong <h3>
            for h3 in soup.find_all("h3"):
                for a in h3.find_all("a", href=True):
                    if(is_article_url(a['href'])):
                        article_urls.add(urljoin(domain, a['href']))

        except Exception as e:
            print(f"❌ Lỗi khi xử lý {link}: {e}")

    return list(article_urls)

if __name__ == "__main__":
    # Ví dụ
    test_url = "https://vietnamnet.vn/"
    domain = test_url.split("/")[2]
    menu_links = extract_menu_links(test_url, domain)
    # categories = extract_categories(menu_links)
    # results = extract_categories(menu_links)
    urls = extract_article_urls_from_menu(menu_links)
    print("-------urls-------", urls)
    # for item in results:
    #     print(item)
    # Ghi ra file sau khi lọc trùng theo URL
    output_file = "urls11.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for i, item in enumerate(urls):
            # print("-------item-------", item)
            line = f"{item}\n"
            print(line.strip())
            f.write(line)
