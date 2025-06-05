from crawler.vnexpress import VNExpressCrawler
from crawler.vietnamnet import VietNamNetCrawler
from crawler.dantri import DanTriCrawler
from crawler.tapchitoaan import TapChiToaAnCrawler
from crawler.quandoinhandan import QuanDoiNhanDanCrawler
from crawler.baovanhoa import BaoVanHoaCrawler
from crawler.tapchidientu import TapChiDienTuCrawler
from crawler.vtcnews import VTCNewsCrawler
from crawler.baodautu import BaoDauTuCrawler
from crawler.baotintuc import BaoTinTucCrawler
from crawler.baovephapluat import BaoVePhapLuatCrawler
from crawler.baodantoc import BaoDanTocCrawler
from crawler.baothanhtra import BaoThanhTraCrawler
from crawler.baotaichinhvietnam import BaoTaiChinhVietNamCrawler
from crawler.baohaiquanvietnam import BaoHaiQuanVietNamCrawler
from crawler.tapchicongthuong import TapChiCongThuongCrawler
from crawler.tainguyenvamoitruong import TaiNguyenVaMoiTruongCrawler
from crawler.dangcongsan import DangCongSanCrawler
from crawler.kienthuc import KienThucCrawler
from crawler.vietnamdaily import VietNameDailyCrawler
from crawler.phunumoi import PhuNuMoiCrawler
from crawler.congnghevadoisong import CongNgheVaDoiSongCrawler
from crawler.taichinhdoanhnghiep import TaiChinhDoanhNghiepCrawler
from crawler.thuonghieucongluan import ThuongHieuCongLuanCrawler
from crawler.vneconomy import VNEconomyCrawler
from crawler.suckhoecong import SucKhoeCongCrawler
from crawler.kinhtedouong import KinhTeDoUongCrawler
from crawler.thuonghieuvaphapluat import ThuongHieuPhapLuatCrawler
from crawler.tapchigiaoduc import TapChiGiaoDucCrawler
from crawler.quanlythitruong import QuanLyThiTruongCrawler
from crawler.congthuong import CongThuongCrawler
from crawler.congly import CongLyCrawler
from crawler.suckhoedoisong import SucKhoeDoiSongCrawler
from crawler.baoxaydung import BaoXayDungCrawler
from crawler.congannhandan import CongAnNhanDanCrawler
from crawler.vov import VovCrawler
from crawler.kiemsat import KiemSatCrawler
from crawler.tapchitaichinh import TapChiTaiChinhCrawler
from crawler.thoibaonganhang import ThoiBaoNganHangCrawler
from crawler.tapchinganhang import TapChiNganHangCrawler
from crawler.tapchibaohiemxahoi import TapChiBaoHiemXaHoiCrawler
from crawler.tapchithanhtra import TapChiThanhTraCrawler
from crawler.nongnghiepmoitruong import NongNghiepMoiTruongCrawler
from crawler.daibieunhandan import DaiBieuNhanDanCrawler
from crawler.baohaiquanonline import BaoHaiQuanOnlineCrawler
from crawler.baodientutoquoc import DienTuToQuocCrawler
from crawler.baodauthau import BaoDauThauCrawler
from crawler.thethaovanhoa import TheThaoVanHoaCrawler
from crawler.baokinhtevadubao import KinhTeVaDuBaoCrawler
from crawler.tapchigiaothongvantai import TapChiGiaoThongVanTaiCrawler
from crawler.tapchithongtinvatruyenthong import TapChiThongTinVaTruyenThongCrawler
from crawler.baoanhdantocvamiennui import BaoDanTocMienNuiCrawler
from crawler.baovietnamplus import BaoVietnamPlusCrawler
from crawler.baoquocte import BaoQuocTeCrawler
from crawler.baochinhphu import BaoChinhPhuCrawler
from crawler.tapchixaydung import TapChiXayDungCrawler
from crawler.tochucnhanuoc import ToChucNhaNuocCrawler
from crawler.kiemtoan import BaoKiemToanCrawler

CRAWLERS = {
            "vnexpress.net": VNExpressCrawler(),
            "dantri.com.vn": DanTriCrawler(),
            "vietnamnet.vn": VietNamNetCrawler(),
            "tapchitoaan.vn": TapChiToaAnCrawler(),
            "www.qdnd.vn": QuanDoiNhanDanCrawler(),
            "baovanhoa.vn": BaoVanHoaCrawler(),
            "vietq.vn": TapChiDienTuCrawler(),
            "vtcnews.vn": VTCNewsCrawler(),
            "baodautu.vn": BaoDauTuCrawler(),
            "baotintuc.vn": BaoTinTucCrawler(),
            "baovephapluat.vn": BaoVePhapLuatCrawler(),
            "baodantoc.vn": BaoDanTocCrawler(),
            "thanhtra.com.vn": BaoThanhTraCrawler(),
            "thoibaotaichinhvietnam.vn": BaoTaiChinhVietNamCrawler(),
            "baohaiquanvietnam.vn": BaoHaiQuanVietNamCrawler(),
            "tapchicongthuong.vn": TapChiCongThuongCrawler(),
            "www.tainguyenvamoitruong.vn": TaiNguyenVaMoiTruongCrawler(),
            "dangcongsan.vn": DangCongSanCrawler(),
            "kienthuc.net.vn": KienThucCrawler(),
            "vietnamdaily.kienthuc.net.vn": VietNameDailyCrawler(),
            "phunumoi.net.vn": PhuNuMoiCrawler(),
            "congnghevadoisong.vn": CongNgheVaDoiSongCrawler(),
            "taichinhdoanhnghiep.net.vn": TaiChinhDoanhNghiepCrawler(),
            "thuonghieucongluan.com.vn": ThuongHieuCongLuanCrawler(),
            "vneconomy.vn": VNEconomyCrawler(),
            "suckhoecong.vn": SucKhoeCongCrawler(),
            "kinhtedouong.vn": KinhTeDoUongCrawler(),
            "thuonghieuvaphapluat.vn": ThuongHieuPhapLuatCrawler(),
            "tapchigiaoduc.edu.vn": TapChiGiaoDucCrawler(),
            "qltt.vn": QuanLyThiTruongCrawler(),
            "congthuong.vn": CongThuongCrawler(),
            "congly.vn": CongLyCrawler(),
            "suckhoedoisong.vn": SucKhoeDoiSongCrawler(),
            "baoxaydung.vn": BaoXayDungCrawler(),
            "cand.com.vn": CongAnNhanDanCrawler(),
            "vov.vn": VovCrawler(),
            "kiemsat.vn": KiemSatCrawler(),
            "tapchitaichinh.vn": TapChiTaiChinhCrawler(),
            "thoibaonganhang.vn": ThoiBaoNganHangCrawler(),
            "tapchinganhang.gov.vn": TapChiNganHangCrawler(),
            "tapchibaohiemxahoi.gov.vn": TapChiBaoHiemXaHoiCrawler(),
            "thanhtravietnam.vn": TapChiThanhTraCrawler(),
            "nongnghiepmoitruong.vn": NongNghiepMoiTruongCrawler(),
            "daibieunhandan.vn": DaiBieuNhanDanCrawler(),
            "haiquanonline.com.vn": BaoHaiQuanOnlineCrawler(),
            "toquoc.vn": DienTuToQuocCrawler(),
            "baodauthau.vn": BaoDauThauCrawler(),
            "thethaovanhoa.vn": TheThaoVanHoaCrawler(),
            "kinhtevadubao.vn": KinhTeVaDuBaoCrawler(),
            "giaothong.tapchixaydung.vn": TapChiGiaoThongVanTaiCrawler(),
            "ictvietnam.vn": TapChiThongTinVaTruyenThongCrawler(),
            "dantocmiennui.baotintuc.vn": BaoDanTocMienNuiCrawler(),
            "www.vietnamplus.vn": BaoVietnamPlusCrawler(),
            "baoquocte.vn": BaoQuocTeCrawler(),
            "baochinhphu.vn": BaoChinhPhuCrawler(),
            "tapchixaydung.vn": TapChiXayDungCrawler(),
            "tcnnld.vn": ToChucNhaNuocCrawler(),
            "baokiemtoan.vn": BaoKiemToanCrawler()
            }
