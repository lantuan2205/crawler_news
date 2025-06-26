from news_crawler.vnexpress import VNExpressCrawler
from news_crawler.vietnamnet import VietNamNetCrawler
from news_crawler.dantri import DanTriCrawler
from news_crawler.tapchitoaan import TapChiToaAnCrawler
from news_crawler.quandoinhandan import QuanDoiNhanDanCrawler
from news_crawler.baovanhoa import BaoVanHoaCrawler
from news_crawler.tapchidientu import TapChiDienTuCrawler
from news_crawler.vtcnews import VTCNewsCrawler
from news_crawler.baodautu import BaoDauTuCrawler
from news_crawler.baotintuc import BaoTinTucCrawler
from news_crawler.baovephapluat import BaoVePhapLuatCrawler
from news_crawler.baodantoc import BaoDanTocCrawler
from news_crawler.baothanhtra import BaoThanhTraCrawler
from news_crawler.baotaichinhvietnam import BaoTaiChinhVietNamCrawler
from news_crawler.baohaiquanvietnam import BaoHaiQuanVietNamCrawler
from news_crawler.tapchicongthuong import TapChiCongThuongCrawler
from news_crawler.tainguyenvamoitruong import TaiNguyenVaMoiTruongCrawler
from news_crawler.dangcongsan import DangCongSanCrawler
from news_crawler.kienthuc import KienThucCrawler
from news_crawler.vietnamdaily import VietNameDailyCrawler
from news_crawler.phunumoi import PhuNuMoiCrawler
from news_crawler.congnghevadoisong import CongNgheVaDoiSongCrawler
from news_crawler.taichinhdoanhnghiep import TaiChinhDoanhNghiepCrawler
from news_crawler.thuonghieucongluan import ThuongHieuCongLuanCrawler
from news_crawler.vneconomy import VNEconomyCrawler
from news_crawler.suckhoecong import SucKhoeCongCrawler
from news_crawler.kinhtedouong import KinhTeDoUongCrawler
from news_crawler.thuonghieuvaphapluat import ThuongHieuPhapLuatCrawler
from news_crawler.tapchigiaoduc import TapChiGiaoDucCrawler
from news_crawler.quanlythitruong import QuanLyThiTruongCrawler
from news_crawler.congthuong import CongThuongCrawler
from news_crawler.congly import CongLyCrawler
from news_crawler.suckhoedoisong import SucKhoeDoiSongCrawler
from news_crawler.baoxaydung import BaoXayDungCrawler
from news_crawler.congannhandan import CongAnNhanDanCrawler
from news_crawler.vov import VovCrawler
from news_crawler.kiemsat import KiemSatCrawler
from news_crawler.tapchitaichinh import TapChiTaiChinhCrawler
from news_crawler.thoibaonganhang import ThoiBaoNganHangCrawler
from news_crawler.tapchinganhang import TapChiNganHangCrawler
from news_crawler.tapchibaohiemxahoi import TapChiBaoHiemXaHoiCrawler
from news_crawler.tapchithanhtra import TapChiThanhTraCrawler
from news_crawler.nongnghiepmoitruong import NongNghiepMoiTruongCrawler
from news_crawler.daibieunhandan import DaiBieuNhanDanCrawler
from news_crawler.tapchikhoahocvacongnghe import TapChiKhoaHocVaCongNgheCrawler
from news_crawler.vtv import VtvCrawler
from news_crawler.baodaidoanket import DaiDoanKetCrawler
# from news_crawler.baolaodong import BaoLaoDongCrawler
from news_crawler.baonhandan import BaoNhanDanCrawler
from news_crawler.baothanhnien import BaoThanhNienCrawler
from news_crawler.phunuvietnam import PhuNuVietNamCrawler
from news_crawler.baotrithucvacuocsong import TriThucVaCuocSongCrawler
from news_crawler.tapchibongda import TapChiBongDaCrawler
from news_crawler.tapchilaodongcongdoan import TapChiLaoDongCongDoanCrawler
from news_crawler.tapchidientunguoiduatin import TapChiDienTuNguoiDuaTinCrawler
from news_crawler.tapchidiendandoanhnghiep import TapChiDienDanDoanhNghiepCrawler
from news_crawler.tapchimotthegioi import TapChiMotTheGioiCrawler
from news_crawler.tapchidientunhipsongthitruong import TapChiDienTuNhipSongThiTruongCrawler
from news_crawler.baonhabaovacongluan import BaoNhaBaoVaCongLuanCrawler
from news_crawler.thoibaovanhocnghethuat import ThoiBaoVanHocNgheThuatCrawler
from news_crawler.tapchithoidai import TapChiThoiDaiCrawler
from news_crawler.tapchidientukinhtechungkhoanvietnam import TapChiDienTuKinhTeChungKhoanVietNamCrawler
from news_crawler.tapchichatluongcuocsong import TapChiChatLuongCuocSongCrawler
from news_crawler.tapchidientugiaoducvietnam import TapChiDienTuGiaoDucVietNamCrawler
from news_crawler.tapchimekongasean import TapChiMekongAseanCrawler
from news_crawler.tapchidientutrithuc import TapChiDienTuTriThucCrawler
from news_crawler.tapchithuonghieuvasanpham import TapChiThuongHieuVaSanPhamCrawler
from news_crawler.tapchidoanhnghiepvietnam import TapChiDoanhNghiepVietNamCrawler
from news_crawler.tapchidoanhnghiepvahoinhap import TapChiDoanhNghiepVaHoiNhapCrawler
from news_crawler.tapchisuckhoecongdong import TapChiSucKhoeCongDongCrawler
from news_crawler.tapchinhadautu import TapChiNhaDauTuCrawler
from news_crawler.tapchidaututaichinh import TapChiDauTuTaiChinhCrawler
from news_crawler.tapchidoanhnghiepvatiepthi import TapChiDoanhNghiepVaTiepThiCrawler
from news_crawler.baodientudanviet import BaoDienTuDanVietCrawler

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
            "vjst.vn": TapChiKhoaHocVaCongNgheCrawler(),
            "vtv.vn": VtvCrawler(),
            "daidoanket.vn": DaiDoanKetCrawler(),
            # "laodong.vn": BaoLaoDongCrawler(),
            "nhandan.vn": BaoNhanDanCrawler(),
            "thanhnien.vn": BaoThanhNienCrawler(),
            "phunuvietnam.vn": PhuNuVietNamCrawler(),
            "kienthuc.net.vn": TriThucVaCuocSongCrawler(),
            # "tienphong.vn": BaoTienPhongCrawler(),
            "bongdaplus.vn": TapChiBongDaCrawler(),
            "laodongcongdoan.vn": TapChiLaoDongCongDoanCrawler(),
            "nguoiduatin.vn": TapChiDienTuNguoiDuaTinCrawler(),
            "diendandoanhnghiep.vn": TapChiDienDanDoanhNghiepCrawler(),
            "1thegioi.vn": TapChiMotTheGioiCrawler(),
            "markettimes.vn": TapChiDienTuNhipSongThiTruongCrawler(),
            "congluan.vn": BaoNhaBaoVaCongLuanCrawler(),
            "arttimes.vn": ThoiBaoVanHocNgheThuatCrawler(),
            "thoidai.com.vn": TapChiThoiDaiCrawler(),
            "kinhtechungkhoan.vn": TapChiDienTuKinhTeChungKhoanVietNamCrawler(),
            "chatluongvacuocsong.vn": TapChiChatLuongCuocSongCrawler(),
            "giaoduc.net.vn": TapChiDienTuGiaoDucVietNamCrawler(),
            "mekongasean.vn": TapChiMekongAseanCrawler(),
            "znews.vn": TapChiDienTuTriThucCrawler(),
            "thuonghieusanpham.vn": TapChiThuongHieuVaSanPhamCrawler(),
            "doanhnghiepvn.vn": TapChiDoanhNghiepVietNamCrawler(),
            "doanhnghiephoinhap.vn": TapChiDoanhNghiepVaHoiNhapCrawler(),
            "suckhoecongdongonline.vn": TapChiSucKhoeCongDongCrawler(),
            "nhadautu.vn": TapChiNhaDauTuCrawler(),
            "vietnamfinance.vn": TapChiDauTuTaiChinhCrawler(),
            "doanhnghieptiepthi.vn": TapChiDoanhNghiepVaTiepThiCrawler(),
            "danviet.vn": BaoDienTuDanVietCrawler(),
            }

