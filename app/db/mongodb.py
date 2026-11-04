
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import settings


# Connect to MongoDB Atlas
mongo_client = MongoClient(
    settings.MONGODB_URI,
    serverSelectionTimeoutMS=5000,
)

# Select database
database = mongo_client[settings.MONGODB_DATABASE]

# Collections used by the agent
audit_collection = database["product_audits"]
proposal_collection = database["description_proposals"]


def check_mongodb():
    """Check whether MongoDB is reachable."""
    try:
        mongo_client.admin.command("ping")
        return True
    except PyMongoError:
        return False


def close_mongodb():
    """Close the MongoDB connection."""
    mongo_client.close()
