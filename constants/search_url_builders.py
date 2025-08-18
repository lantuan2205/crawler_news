from urllib.parse import urlencode, quote_plus, quote

def build_vietnamnet_url(keyword):
    return f"https://vietnamnet.vn/tim-kiem?{urlencode({'q': keyword})}"

def build_vnexpress_url(keyword):
    return f"https://timkiem.vnexpress.net/?{urlencode({'q': keyword})}"

def build_dantri_url(keyword):
    return f"https://dantri.com.vn/tim-kiem/{quote_plus(keyword)}.htm"

def build_thoibaotaichinh_url(keyword):
    return f"https://thoibaotaichinhvietnam.vn/search_enginer.html?{urlencode({'p': 'search', 'q': keyword})}"

def build_thanhtra_url(keyword):
    return f"https://thanhtra.com.vn/tim-kiem.html?{urlencode({'q': keyword})}"

def build_qdnd_url(keyword):
    return f"https://www.qdnd.vn/tim-kiem/q/{quote(keyword)}"

def build_qltt_url(keyword):
    return f"https://qltt.vn/search_enginer.html?{urlencode({'p': 'tim-kiem', 'q': keyword})}"

def build_baotintuc_url(keyword):
    return f"https://baotintuc.vn/Search.aspx?KeySearch={quote(keyword)}&ar=1&op=1"

def build_baovephapluat_url(keyword):
    return f"https://baovephapluat.vn/tim-kiem/q/{quote_plus(keyword)}"

def build_baodantoc_url(keyword):
    return f"https://baodantoc.vn/tim-kiem.htm?{urlencode({'type': 0, 'keyword': keyword})}"

def build_tapchicongthuong_url(keyword):
    return f"https://tapchicongthuong.vn/tim-kiem?{urlencode({'q': keyword})}"

def build_tainguyenvamoitruong_url(keyword):
    return f"https://www.tainguyenvamoitruong.vn/tim-kiem.html?{urlencode({'keyword': keyword})}"

def build_dangcongsan_url(keyword):
    return f"https://dangcongsan.vn/page/search?{urlencode({'keyword': keyword})}"

def build_phunumoi_url(keyword):
    return f"https://phunumoi.net.vn/tim-kiem.html?{urlencode({'q': keyword})}"

def build_vneconomy_url(keyword):
    return f"https://vneconomy.vn/tim-kiem.htm?q={quote(keyword)}"

def build_kinhtedouong_url(keyword):
    return f"https://kinhtedouong.vn/tim-kiem.html?{urlencode({'q': keyword})}"

def build_thuonghieuvaphapluat_url(keyword):
    return f"https://thuonghieuvaphapluat.vn/search/{quote(keyword)}/"

SEARCH_URL_BUILDERS = {
    "vietnamnet": build_vietnamnet_url,
    "vnexpress": build_vnexpress_url,
    "dantri": build_dantri_url,
    "thoibaotaichinhvietnam": build_thoibaotaichinh_url,
    "thanhtra": build_thanhtra_url,
    "qdnd": build_qdnd_url,
    "qltt": build_qltt_url,
    "baotintuc": build_baotintuc_url,
    "baovephapluat": build_baovephapluat_url,
    "baodantoc": build_baodantoc_url,
    "tapchicongthuong": build_tapchicongthuong_url,
    "tainguyenvamoitruong": build_tainguyenvamoitruong_url,
    "dangcongsan": build_dangcongsan_url,
    "phunumoi": build_phunumoi_url,
    "vneconomy": build_vneconomy_url,
    "kinhtedouong": build_kinhtedouong_url,
    "thuonghieuvaphapluat": build_thuonghieuvaphapluat_url,
}