import requests
from bs4 import BeautifulSoup

class WordPressCrawler:
    def __init__(self, url, session=None):
        self.url = url.rstrip('/')
        self.session = session or requests.Session()

    def get_all_articles(self):
        # lấy từ feed RSS hoặc /wp-json/
        feed_url = self.url + "/feed/"
        try:
            r = self.session.get(feed_url, timeout=10)
            soup = BeautifulSoup(r.text, "xml")
            return [item.find("link").text for item in soup.find_all("item")]
        except Exception:
            return []

    def crawl_article(self, article_url):
        r = self.session.get(article_url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("h1").get_text(strip=True)
        content = soup.find("div", class_="entry-content")
        return {"url": article_url, "title": title, "content": content.get_text(strip=True) if content else ""}
