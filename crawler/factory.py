from .vnexpress import VNExpressCrawler
from .dantri import DanTriCrawler
from .vietnamnet import VietNamNetCrawler
from .tapchitoaan import TapChiToaAnCrawler
from .quandoinhandan import QuanDoiNhanDanCrawler
from .baovanhoa import BaoVanHoaCrawler

WEBNAMES = {"vnexpress": VNExpressCrawler,
            "dantri": DanTriCrawler,
            "vietnamnet": VietNamNetCrawler,
            "tapchitoaan": TapChiToaAnCrawler,
            "quandoinhandan": QuanDoiNhanDanCrawler,
            "baovanhoa": BaoVanHoaCrawler}

def get_crawler(webname, **kwargs):
    crawler = WEBNAMES[webname](**kwargs)
    return crawler