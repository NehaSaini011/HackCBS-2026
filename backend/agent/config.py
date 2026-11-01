import os
from dotenv import load_dotenv

# Locally: AGENT_ENV_FILE=.env.agent-a python -m agent.run_agent
# On DigitalOcean there is no file; the values come from the app's settings.
load_dotenv(os.environ.get("AGENT_ENV_FILE", ".env.agent-a"))

COMPANY = os.environ["COMPANY"]
SHOP = os.environ["SHOP"]
GROUP_API_URL = os.environ["GROUP_API_URL"].rstrip("/")
COMPANY_API_KEY = os.environ["COMPANY_API_KEY"]
# Empty until Person 1 sends the shop addresses. Only evidence.py and fixes.apply() need them.
SHOP_READONLY_URL = os.environ.get("SHOP_READONLY_URL", "")
SHOP_WRITE_URL = os.environ.get("SHOP_WRITE_URL", "")
PROVER_URL = os.environ.get("PROVER_URL", "")
PROVER_TOKEN = os.environ.get("PROVER_TOKEN", "")
FAKE_PROVER = os.environ.get("FAKE_PROVER", "false").lower() == "true"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.8-flash")
POLL_SECONDS = float(os.environ.get("POLL_SECONDS", "3"))
