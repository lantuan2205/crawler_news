from .vnexpress import VNExpressCrawler
from .vietnamnet import VietNamNetCrawler
from .dantri import DanTriCrawler
from .tapchitoaan import TapChiToaAnCrawler
from .quandoinhandan import QuanDoiNhanDanCrawler
from .baovanhoa import BaoVanHoaCrawler
from .tapchidientu import TapChiDienTuCrawler
from .vtcnews import VTCNewsCrawler
from .baodautu import BaoDauTuCrawler
from .baotintuc import BaoTinTucCrawler
from .baovephapluat import BaoVePhapLuatCrawler
from .baodantoc import BaoDanTocCrawler
from .baothanhtra import BaoThanhTraCrawler

WEBNAMES = {"vnexpress": VNExpressCrawler,
            "dantri": DanTriCrawler,
            "vietnamnet": VietNamNetCrawler,
            "tapchitoaan": TapChiToaAnCrawler,
            "quandoinhandan": QuanDoiNhanDanCrawler,
            "baovanhoa": BaoVanHoaCrawler,
            "tapchidientu": TapChiDienTuCrawler,
            "vtcnews": VTCNewsCrawler,
            "baodautu": BaoDauTuCrawler,
            "baotintuc": BaoTinTucCrawler,
            "baovephapluat": BaoVePhapLuatCrawler,
            "baodantoc": BaoDanTocCrawler,
            "thanhtra": BaoThanhTraCrawler,
            }

def get_crawler(webname, **kwargs):
    crawler = WEBNAMES[webname](**kwargs)
    return crawler
