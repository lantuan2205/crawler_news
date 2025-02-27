from .vnexpress import VNExpressCrawler
from .vietnamnet import VietNamNetCrawler

WEBNAMES = {"vnexpress": VNExpressCrawler,
            "vietnamnet": VietNamNetCrawler}

def get_crawler(webname, **kwargs):
    crawler = WEBNAMES[webname](**kwargs)
    return crawler