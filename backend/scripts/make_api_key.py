import hashlib
import secrets
import sys

import psycopg

from app.settings import settings

company_id = sys.argv[1]                         # e.g. c_pinecart
key = "fx_" + secrets.token_urlsafe(32)          # 43 random characters: cannot be guessed
key_hash = hashlib.sha256(key.encode()).hexdigest()

with psycopg.connect(settings.yb_url) as conn:
    conn.execute("INSERT INTO api_keys (key_hash, company_id, label) VALUES (%s, %s, %s)",
                 (key_hash, company_id, "demo"))

print(f"API key for {company_id} (shown once, store it now):")
print(key)