"""
MongoDB Database Handler for AnonXStreamAPI
Manages dynamic API keys, usage statistics, and user associations.
"""

import os
import time
import secrets
import logging
from typing import Optional, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

logger = logging.getLogger("AnonXStreamAPI.DB")

MONGO_URL = os.getenv(
    "MONGO_URL",
    "mongodb+srv://public:abishnoimf@cluster0.rqk6ihd.mongodb.net/?retryWrites=true&w=majority"
).strip()
DB_NAME = os.getenv("MONGO_DB_NAME", "anonx_stream_api").strip()

client: Optional[AsyncIOMotorClient] = None
db = None
keys_collection = None


async def init_db(mongo_url: Optional[str] = None):
    global client, db, keys_collection
    url = mongo_url or MONGO_URL
    if not url:
        logger.warning("No MONGO_URL provided. Dynamic MongoDB API key management is disabled.")
        return

    try:
        client = AsyncIOMotorClient(url)
        db = client[DB_NAME]
        keys_collection = db["api_keys"]
        # Ensure index on key field
        await keys_collection.create_index("key", unique=True)
        await keys_collection.create_index("user_id")
        logger.info("Connected to MongoDB database: %s", DB_NAME)
    except Exception as exc:
        logger.error("Failed to connect to MongoDB: %s", exc)


def is_connected() -> bool:
    return keys_collection is not None


async def generate_api_key(
    user_id: int,
    user_name: str = "",
    note: str = "",
    prefix: str = "anonx_live_",
) -> str:
    """Generate a random unique API key and store it in MongoDB."""
    random_token = secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    key = f"{prefix}{random_token}"

    doc = {
        "key": key,
        "user_id": user_id,
        "user_name": user_name,
        "note": note,
        "created_at": time.time(),
        "active": True,
        "requests_count": 0,
        "last_used": None,
    }

    if is_connected():
        try:
            await keys_collection.insert_one(doc)
            logger.info("Created new API key for user %s (%s)", user_id, user_name)
        except Exception as exc:
            logger.error("Error inserting API key into MongoDB: %s", exc)
            raise

    return key


async def verify_api_key(key: str) -> bool:
    """Check if an API key is valid and active in MongoDB, and increment request counter."""
    if not is_connected() or not key:
        return False

    try:
        doc = await keys_collection.find_one({"key": key, "active": True})
        if doc:
            # Increment request counter asynchronously in background
            await keys_collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$inc": {"requests_count": 1},
                    "$set": {"last_used": time.time()},
                },
            )
            return True
    except Exception as exc:
        logger.error("Error verifying API key in MongoDB: %s", exc)

    return False


async def get_user_keys(user_id: int) -> List[Dict[str, Any]]:
    """Retrieve all active API keys for a specific user."""
    if not is_connected():
        return []

    try:
        cursor = keys_collection.find({"user_id": user_id, "active": True}).sort("created_at", -1)
        return await cursor.to_list(length=50)
    except Exception as exc:
        logger.error("Error fetching user keys: %s", exc)
        return []


async def revoke_api_key(key: str, user_id: Optional[int] = None) -> bool:
    """Revoke/deactivate an API key."""
    if not is_connected():
        return False

    query = {"key": key}
    if user_id:
        query["user_id"] = user_id

    try:
        result = await keys_collection.update_one(query, {"$set": {"active": False}})
        return result.modified_count > 0
    except Exception as exc:
        logger.error("Error revoking API key: %s", exc)
        return False


async def get_stats() -> Dict[str, Any]:
    """Retrieve overall API usage and key statistics."""
    if not is_connected():
        return {
            "connected": False,
            "total_keys": 0,
            "active_keys": 0,
            "total_requests": 0,
        }

    try:
        total_keys = await keys_collection.count_documents({})
        active_keys = await keys_collection.count_documents({"active": True})
        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$requests_count"}}}]
        agg = await keys_collection.aggregate(pipeline).to_list(1)
        total_requests = agg[0]["total"] if agg else 0

        return {
            "connected": True,
            "total_keys": total_keys,
            "active_keys": active_keys,
            "total_requests": total_requests,
        }
    except Exception as exc:
        logger.error("Error fetching stats: %s", exc)
        return {"connected": False, "error": str(exc)}
