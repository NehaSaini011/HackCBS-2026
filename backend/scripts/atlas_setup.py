from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from app.mongo import db, findings, incidents, VECTOR_INDEX

# Collections must exist before a search index can be added
for name in ("findings", "incidents"):
    if name not in db.list_collection_names():
        db.create_collection(name)

findings.create_index([("company_id", 1), ("status", 1), ("last_seen", -1)])
findings.create_index([("company_id", 1), ("fingerprint", 1)])
incidents.create_index([("company_id", 1), ("status", 1)])
print("normal indexes ok")

vector_index = SearchIndexModel(
    name=VECTOR_INDEX,
    type="vectorSearch",
    definition={
        "fields": [
            # 768 numbers per finding, compared by angle (cosine)
            {"type": "vector", "path": "embedding", "numDimensions": 768, "similarity": "cosine"},
            # fields you are allowed to filter on during a vector search
            {"type": "filter", "path": "company_id"},
            {"type": "filter", "path": "group_id"},
            {"type": "filter", "path": "test"},
        ]
    },
)
try:
    findings.create_search_index(vector_index)
    print("vector index requested; it takes a minute to build")
except OperationFailure as e:
    print("vector index NOT created:", e)