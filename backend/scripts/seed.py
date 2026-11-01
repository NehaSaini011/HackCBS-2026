import getpass

import bcrypt
import psycopg

from app.settings import settings

GROUP = ("g_fund1", "Fund One")
COMPANIES = [
    ("c_pinecart", "Pinecart", "a", "Python, FastAPI, Postgres (Tiger)"),
    ("c_tealbox", "Tealbox", "b", "Python, FastAPI, Postgres (Tiger)"),
]
USERS = [  # id, email, role, company
    ("u_1", "platform@fund1.demo", "group_admin", None),
    ("u_2", "arjun@pinecart.demo", "engineer", "c_pinecart"),
    ("u_3", "priya@tealbox.demo", "engineer", "c_tealbox"),
]

with psycopg.connect(settings.yb_url) as conn:
    conn.execute("INSERT INTO groups (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING", GROUP)
    for c in COMPANIES:
        conn.execute("INSERT INTO companies (id, name, shop, tech_stack, group_id) "
                     "VALUES (%s, %s, %s, %s, 'g_fund1') ON CONFLICT (id) DO NOTHING", c)
    for uid, email, role, company in USERS:
        # Typed, not stored in code. Share the passwords privately with the team.
        pw = getpass.getpass(f"Password for {email}: ")
        h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            "INSERT INTO users (id, email, password_hash, role, group_id, company_id) "
            "VALUES (%s, %s, %s, %s, 'g_fund1', %s) "
            "ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash",
            (uid, email, h, role, company))
print("seeded")