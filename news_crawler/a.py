import re

class TestLogoValidator:
    def _validate_logo_url(self, value: str) -> str:
        """Chỉ giữ lại URL ảnh hợp lệ, bỏ hết text hoặc chuỗi không phải ảnh."""
        if not value:
            return ""

        value = value.strip()

        # Regex: chỉ khớp URL ảnh hợp lệ (có đuôi ảnh, có thể kèm query/fragment)
        image_pattern = re.compile(
            r'^https?://[^\s]+\.(png|jpg|jpeg|gif|svg|webp)(\?.*)?$',
            re.IGNORECASE
        )

        # Chỉ giữ nếu khớp pattern URL ảnh
        if image_pattern.match(value):
            return value

        # Các trường hợp còn lại (text, slogan, ký tự đặc biệt...) -> bỏ
        return ""

def main():
    validator = TestLogoValidator()
    test_values = [
        "https://example.com/logo.png",
        "https://domain.vn/image.webp?ver=1.2",
        "http://site.com/assets/logo.svg#hash",
        "Bốn Phương\"Góp lại từ bốn phương, tung ra khắp bốn phương\"",
        "VÌ TỔ QUỐC VIỆT NAM",
        "Logo Báo Tuổi Trẻ",
        "http://domain.com/logo",
        "",
        None
    ]

    print("=== Kết quả kiểm tra _validate_logo_url ===")
    for val in test_values:
        result = validator._validate_logo_url(val)
        print(f"Input: {repr(val)}\nOutput: {repr(result)}\n{'-'*50}")

if __name__ == "__main__":
    main()