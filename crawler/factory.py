from .vnexpress import VNExpressCrawler
from .dantri import DanTriCrawler
from .vietnamnet import VietNamNetCrawler
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
from .baotaichinhvietnam import BaoTaiChinhVietNamCrawler
from .baohaiquanvietnam import BaoHaiQuanVietNamCrawler
from .tapchicongthuong import TapChiCongThuongCrawler
from .tainguyenvamoitruong import TaiNguyenVaMoiTruongCrawler
from .dangcongsan import DangCongSanCrawler
from .kienthuc import KienThucCrawler
from .vietnamdaily import VietNameDailyCrawler
from .phunumoi import PhuNuMoiCrawler
from .congnghevadoisong import CongNgheVaDoiSongCrawler
from .taichinhdoanhnghiep import TaiChinhDoanhNghiepCrawler
from .thuonghieucongluan import ThuongHieuCongLuanCrawler

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
            "thoibaotaichinhvietnam": BaoTaiChinhVietNamCrawler,
            "baohaiquanvietnam": BaoHaiQuanVietNamCrawler,
            "tapchicongthuong": TapChiCongThuongCrawler,
            "tainguyenvamoitruong": TaiNguyenVaMoiTruongCrawler,
            "dangcongsan": DangCongSanCrawler,
            "kienthuc": KienThucCrawler,
            "vietnamdaily": VietNameDailyCrawler,
            "phunumoi": PhuNuMoiCrawler,
            "congnghevadoisong": CongNgheVaDoiSongCrawler,
            "taichinhdoanhnghiep": TaiChinhDoanhNghiepCrawler,
            "thuonghieucongluan": ThuongHieuCongLuanCrawler,
            }

def get_crawler(webname, **kwargs):
    crawler = WEBNAMES[webname](**kwargs)
    return crawler
