from vnexpress_crawler import VnExpressCrawler
from dantri_crawler import DanTriCrawler

def crawl_vnexpress():
    vnexpress = VnExpressCrawler()
    categories = vnexpress.get_categories()
    data = []
    for cat in categories[:3]:
        print(f"Crawling {cat['name']}...")
        articles = vnexpress.get_articles(cat["url"])
        details = [vnexpress.get_article_detail(a["url"]) for a in articles[:10]]
        data.append({"category": cat["name"], "articles": details})

    vnexpress.save_json(data, "vnexpress_data.json")
    vnexpress.close()

def crawl_dantri():
    dantri = DanTriCrawler()
    categories = dantri.get_categories()

    data = []
    for cat in categories:  
        print(f"Crawling {cat['name']}...")
        articles = dantri.get_articles(cat["url"])
        details = [dantri.get_article_detail(a["url"]) for a in articles[:5]]
        data.append({"category": cat["name"], "articles": details})

    dantri.save_json(data, "dantri_data.json")
    dantri.close()

if __name__ == "__main__":
    crawl_vnexpress()
