from .vnexpress import VNExpressCrawler
from .vietnamnet import VietNamNetCrawler
from .dantri import DanTriCrawler
from .tapchitoaan import TapChiToaAnCrawler
from .quandoinhandan import QuanDoiNhanDanCrawler
from .baovanhoa import BaoVanHoaCrawler
from .tapchidientu import TapChiDienTuCrawler
from .vtcnews import VTCNewsCrawler

WEBNAMES = {"vnexpress": VNExpressCrawler,
            "dantri": DanTriCrawler,
            "vietnamnet": VietNamNetCrawler,
            "tapchitoaan": TapChiToaAnCrawler,
            "quandoinhandan": QuanDoiNhanDanCrawler,
            "baovanhoa": BaoVanHoaCrawler,
            "tapchidientu": TapChiDienTuCrawler
            "vtcnews": VTCNewsCrawler}

def get_crawler(webname, **kwargs):
    crawler = WEBNAMES[webname](**kwargs)
    return crawler
