import requests
import time
import json

API_URL = "https://baocaobang.vn/list-post-by-category"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": "https://baocaobang.vn/",
    "X-Requested-With": "XMLHttpRequest",
    "Connection": "keep-alive",
}

CATEGORY_ID = 57  # ví dụ: Chính trị

def call_api(page: int):
    params = {
        "page": page,
        "limit": 12,
        "category_id": CATEGORY_ID,
        "show_thumb": "true",
        "show_desc": "true"
    }

    resp = requests.get(
        API_URL,
        headers=HEADERS,
        params=params,
        timeout=10
    )

    print("=" * 80)
    print(f"[PAGE {page}] status={resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    print(f"Length: {len(resp.text)}")

    if not resp.text.strip():
        print("❌ EMPTY BODY")
        return False

    try:
        data = resp.json()

    except json.JSONDecodeError:
        print("❌ NOT JSON")
        return False

    items = data.get("data", [])
    print(f"✅ JSON OK | items={len(items)}")

    if items:
        links = []
        for item in items:
            link = item.get("link")
            if not link:
                continue

            if link.startswith("/"):
                link = "https://baocaobang.vn" + link

            links.append(link)

        print(f"Total links: {len(links)}")
        for l in links:
            print(l)

    return True


def main():
    success = 0
    fail = 0

    for page in range(1, 6):
        ok = call_api(page)
        if ok:
            success += 1
        else:
            fail += 1

        # QUAN TRỌNG: delay giống browser
        time.sleep(1.2)

    print("\nRESULT")
    print("Success:", success)
    print("Fail:", fail)


if __name__ == "__main__":
    main()
