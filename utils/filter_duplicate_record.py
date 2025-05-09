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
    { "$match": { "count": { "$gt": 1 } } },
    {
        "$project": {
            "duplicate_ids": { "$slice": ["$ids", 1, { "$subtract": ["$count", 1] }] },
            "_id": 0
        }
    },
    { "$unwind": "$duplicate_ids" },
    {
        "$lookup": {
            "from": "articles",
            "localField": "duplicate_ids",
            "foreignField": "_id",
            "as": "docs"
        }
    },
    { "$unwind": "$docs" },
    { "$replaceRoot": { "newRoot": "$docs" } }
]

results = list(collection.aggregate(pipeline))

# Ghi kết quả vào file JSON, sử dụng custom converter cho ObjectId
with open("duplicates.json", "w", encoding="utf-8") as f:
    json.dump(results, f, default=json_converter, ensure_ascii=False, indent=2)

print(f"Đã xuất {len(results)} bản ghi trùng vào 'duplicates.json'")
