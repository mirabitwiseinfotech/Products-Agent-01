
import os
from pathlib import Path

import requests
from dotenv import load_dotenv, set_key

# Load .env from the project root
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path, override=True)

shop = os.getenv("SHOPIFY_STORE_DOMAIN", "").strip()
client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
client_secret = os.getenv("SHOPIFY_CLIENT_SECRET", "").strip()

if not all([shop, client_id, client_secret]):
    raise SystemExit(
        "Missing SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID "
        "or SHOPIFY_CLIENT_SECRET in .env"
    )

shop = shop.replace("https://", "").replace("http://", "").strip("/")

url = f"https://{shop}/admin/oauth/access_token"

try:
    response = requests.post(
        url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        },
        timeout=30,
    )

    if not response.ok:
        raise SystemExit(
            f"Shopify token request failed: HTTP {response.status_code}\n"
            f"{response.text}"
        )

    data = response.json()
    token = data.get("access_token")

    if not token:
        raise SystemExit("Shopify did not return an access token.")

    # Save the token without displaying it
    set_key(str(env_path), "SHOPIFY_ADMIN_ACCESS_TOKEN", token)

    print("SUCCESS: Shopify access token generated.")
    print("Token saved securely in your project .env file.")
    print("Token type:", data.get("token_type", "not provided"))
    print("Expires in:", data.get("expires_in"), "seconds")
    print("Granted scopes:", data.get("scope", "not provided"))

except requests.RequestException as exc:
    raise SystemExit(f"Shopify connection failed: {exc}")
