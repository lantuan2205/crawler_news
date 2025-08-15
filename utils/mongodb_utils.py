from pymongo import MongoClient
from pathlib import Path
import yaml
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

# Load environment variables
load_dotenv()

def get_iso_datetime():
    """Chuyển đổi datetime hiện tại sang định dạng ISO 8601 với timezone"""
    return datetime.now(timezone.utc).isoformat()

def get_mongodb_config():
    """Lấy cấu hình MongoDB từ file config"""
    config_path = Path(__file__).parent.parent / "config" / "mongodb_config.yml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config['mongodb']

def get_mongodb_client():
    """Tạo kết nối đến MongoDB"""
    config = get_mongodb_config()
    client = MongoClient(config['uri'])
    return client

def get_database():
    """Lấy database"""
    client = get_mongodb_client()
    config = get_mongodb_config()
    return client[config['database']]

def get_collection(collection_name):
    """Lấy collection"""
    db = get_database()
    config = get_mongodb_config()
    return db[config['collections'][collection_name]]

def save_article(article_data):
    """Lưu thông tin bài viết vào MongoDB"""
    articles_collection = get_collection('articles')
    # Thêm trường createdAt với định dạng ISO
    article_data['createdAt'] = get_iso_datetime()
    return articles_collection.insert_one(article_data)

def save_image_metadata(image_data):
    """Lưu metadata của ảnh vào MongoDB"""
    images_collection = get_collection('images')
    # Thêm trường createdAt với định dạng ISO
    image_data['createdAt'] = get_iso_datetime()
    return images_collection.insert_one(image_data)

def save_category(category_data):
    """Lưu thông tin chuyên mục vào MongoDB"""
    categories_collection = get_collection('categories')
    # Thêm trường createdAt với định dạng ISO
    category_data['createdAt'] = get_iso_datetime()
    return categories_collection.insert_one(category_data)

def find_article_by_url(url):
    """Tìm bài viết theo URL"""
    articles_collection = get_collection('articles')
    return articles_collection.find_one({'url': url})

def find_image_by_url(image_url):
    """Tìm ảnh theo URL"""
    images_collection = get_collection('images')
    return images_collection.find_one({'image_url': image_url})

def find_category_by_name(category_name):
    """Tìm chuyên mục theo tên"""
    categories_collection = get_collection('categories')
    return categories_collection.find_one({'category_name': category_name})

def update_article(article_id, update_data):
    """Cập nhật thông tin bài viết"""
    articles_collection = get_collection('articles')
    return articles_collection.update_one(
        {'_id': article_id},
        {'$set': update_data}
    )

def delete_article(article_id):
    """Xóa bài viết"""
    articles_collection = get_collection('articles')
    return articles_collection.delete_one({'_id': article_id})

def get_all_articles():
    """Lấy tất cả bài viết"""
    articles_collection = get_collection('articles')
    return list(articles_collection.find())

def get_articles_by_category(category_name):
    """Lấy bài viết theo chuyên mục"""
    articles_collection = get_collection('articles')
    return list(articles_collection.find({'category': category_name}))

def get_articles_by_date_range(start_date, end_date):
    """Lấy bài viết trong khoảng thời gian"""
    articles_collection = get_collection('articles')
    return list(articles_collection.find({
        'publishedDate': {
            '$gte': start_date,
            '$lte': end_date
        }
    })) 