from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)

db = client["medicine_db"]

users_collection = db["users"]
medicine_collection = db["medicines"]

# ================= MEDICINES =================
def insert_medicine(data):
    medicine_collection.insert_one(data)

def get_all_medicines():
    return list(medicine_collection.find())

def delete_medicine(id):
    medicine_collection.delete_one({"_id": ObjectId(id)})

# ================= USERS =================
def insert_user(data):
    users_collection.insert_one(data)

def get_user(email):
    return users_collection.find_one({"email": email})