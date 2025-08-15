import requests
import hashlib
import json
import os

class UIChecker:
    def __init__(self, urls, hash_file="ui_hashes.json"):
        self.urls = urls
        self.hash_file = hash_file
        self.prev_hashes = self.load_previous_hashes()

    def load_previous_hashes(self):
        """Load danh sách hash trước đó từ file JSON"""
        if os.path.exists(self.hash_file):
            with open(self.hash_file, "r") as f:
                return json.load(f)
        return {}

    def save_current_hash(self, url, current_hash):
        """Lưu hash hiện tại vào file JSON"""
        self.prev_hashes[url] = current_hash
        with open(self.hash_file, "w") as f:
            json.dump(self.prev_hashes, f, indent=4)

    def check_ui_change(self, url):
        """Kiểm tra UI của từng trang báo"""
        try:
            response = requests.get(url, timeout=5)
            html_content = response.text

            hash_source = html_content[:1000]  # Giữ 1000 ký tự đầu
            current_hash = hashlib.md5(hash_source.encode()).hexdigest()

            # So sánh với hash cũ
            if url in self.prev_hashes and self.prev_hashes[url] != current_hash:
                print(f"UI của {url} đã thay đổi! Cần kiểm tra lại tool crawl.")
                self.save_current_hash(url, current_hash)
                return True

            self.save_current_hash(url, current_hash)
            return False

        except requests.RequestException as e:
            print(f"Không thể kiểm tra UI {url}: {e}")
            return False

    def check_all(self):
        """Kiểm tra tất cả các trang báo"""
        for url in self.urls:
            self.check_ui_change(url)


