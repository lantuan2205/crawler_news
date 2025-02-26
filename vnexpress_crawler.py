import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

class VnExpressCrawler:
    def __init__(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        self.base_url = "https://vnexpress.net"

    def get_categories(self):
        self.driver.get(self.base_url)
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        categories = soup.select("nav a[href^='/']")
        result = []

        for category in categories:
            name = category.text.strip()
            link = self.base_url + category["href"] if "https" not in category["href"] else category["href"]
            result.append({"name": name, "url": link})

        return result

    def get_articles(self, category_url):
        self.driver.get(category_url)
        time.sleep(2)
        soup = BeautifulSoup(self.driver.page_source, "lxml")
        articles = soup.select(".title-news a")
        result = []

        for article in articles:
            title = article.text.strip()
            link = article["href"]
            result.append({"title": title, "url": link})

        return result

    def get_article_detail(self, article_url):
        self.driver.get(article_url)
        time.sleep(2)

        soup = BeautifulSoup(self.driver.page_source, "lxml")

        title = soup.find("h1", class_="title-detail").text.strip() if soup.find("h1", class_="title-detail") else "N/A"
        date = soup.find("span", class_="date").text.strip() if soup.find("span", class_="date") else "N/A"
        content = "\n".join([p.text.strip() for p in soup.select(".fck_detail p")])
        author = soup.find("p", class_="author_mail").text.strip() if soup.find("p", class_="author_mail") else "N/A"
        thumbnail = soup.find("meta", property="og:image")
        thumbnail_url = thumbnail["content"] if thumbnail else "N/A"
        view_count = soup.find("span", class_="view").text.strip() if soup.find("span", class_="view") else "N/A"
        tags = [tag.text.strip() for tag in soup.select(".tags a")]
        comments = []
        comment_section = soup.find("div", id="list_comment")
        if comment_section:
            comment_items = comment_section.find_all("div", class_="content-comment")
            comments = [c.text.strip() for c in comment_items]

        return {
            "title": title,
            "date": date,
            "author": author,
            "content": content,
            "thumbnail": thumbnail_url,
            "view_count": view_count,
            "tags": tags,
            "comments": comments
        }

    def save_json(self, data, filename="vnexpress_data.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def close(self):
        self.driver.quit()
