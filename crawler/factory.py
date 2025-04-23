from .vnexpress import VNExpressCrawler
from .dantri import DanTriCrawler
from .vietnamnet import VietNamNetCrawler
from .tapchitoaan import TapChiToaAnCrawler

WEBNAMES = {"vnexpress": VNExpressCrawler,
            "dantri": DanTriCrawler,
            "vietnamnet": VietNamNetCrawler,
            "tapchitoaan": TapChiToaAnCrawler}

def get_crawler(webname, **kwargs):
    crawler = WEBNAMES[webname](**kwargs)
    return crawler