from pymongo import MongoClient
import json

from bson import ObjectId  # Import ObjectId từ bson
# mongodb:
#   uri: "mongodb://192.168.161.230:27018/"
#   database: "news_scraper"
#   collections:
#     articles: "articles"
#     images: "images"
#     categories: "categories" 


def json_converter(obj):
    if isinstance(obj, ObjectId):
        return str(obj)  # Chuyển ObjectId thành chuỗi
    raise TypeError("Type not serializable")

# Kết nối tới MongoDB
client = MongoClient("mongodb://192.168.161.230:27018/")
db = client["news_scraper"]
collection = db["articles"]

# Aggregation pipeline
pipeline = [
    {
        "$group": {
            "_id": {
                "dataSource": "$dataSource",
                "article_type": "$article_type",
                "publishedDate": "$publishedDate",
                "title": "$title"
            },
            "ids": { "$push": "$_id" },
            "count": { "$sum": 1 }
        }
    },
    { "$match": { "count": { "$gt": 1 } } },  # Chỉ tìm các nhóm có nhiều hơn 1 bản ghi
    {
        "$project": {
            "duplicate_ids": { "$slice": ["$ids", 1, { "$subtract": ["$count", 1] }] },
            "_id": 0
        }
    }
]

# Chạy aggregation để tìm các bản ghi trùng lặp
results = list(collection.aggregate(pipeline))

# Duyệt qua kết quả và xóa các bản ghi trùng lặp
for result in results:
    duplicate_ids = result['duplicate_ids']
    
    # Xóa các bản ghi trùng lặp, chỉ giữ lại bản đầu tiên (đã được giữ trong 'duplicate_ids')
    if duplicate_ids:
        collection.delete_many({"_id": {"$in": duplicate_ids}})

print("Đã xóa các bản ghi trùng lặp, chỉ giữ lại bản ghi duy nhất.")
