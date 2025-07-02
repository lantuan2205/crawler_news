from urllib.parse import urlencode, quote_plus

def build_vietnamnet_url(keyword):
    return f"https://vietnamnet.vn/tim-kiem?{urlencode({'q': keyword})}"

def build_vnexpress_url(keyword):
    return f"https://timkiem.vnexpress.net/?{urlencode({'q': keyword})}"

def build_dantri_url(keyword):
    return f"https://dantri.com.vn/tim-kiem/{quote_plus(keyword)}.htm"


SEARCH_URL_BUILDERS = {
    "vietnamnet.vn": build_vietnamnet_url,
    "vnexpress.net": build_vnexpress_url,
    "dantri.com.vn": build_dantri_url,
}
