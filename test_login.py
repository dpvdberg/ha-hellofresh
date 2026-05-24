"""Quick test: login via curl_cffi (Chrome TLS fingerprint) and dump the full response."""
from curl_cffi import requests as cffi_requests
import json
import os

# Load credentials
username = None
password = None

creds_path = os.path.join(os.path.dirname(__file__), ".credentials")
if os.path.exists(creds_path):
    with open(creds_path, "r") as f:
        lines = f.read().strip().splitlines()
        if len(lines) >= 2:
            username = lines[0].strip()
            password = lines[1].strip()

if not username or not password:
    print("Create .credentials with email on line 1, password on line 2")
    exit(1)

# Use a session with Chrome's TLS fingerprint
session = cffi_requests.Session(impersonate="chrome")

# Step 1: Visit the login page first to establish cookies
print("Step 1: Visiting login page to establish session...")
page_resp = session.get("https://www.hellofresh.nl/login")
print(f"  Page status: {page_resp.status_code}")
print(f"  Cookies: {dict(session.cookies)}")
print()

# Step 2: POST login
print("Step 2: Posting login credentials...")
response = session.post(
    "https://www.hellofresh.nl/gw/login",
    params={"country": "NL", "locale": "nl-NL"},
    json={"username": username, "password": password},
    headers={
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://www.hellofresh.nl",
        "Referer": "https://www.hellofresh.nl/login",
    },
)

print(f"  Login status: {response.status_code}")
print()

if response.status_code == 200:
    data = response.json()
    os.makedirs("debug", exist_ok=True)
    with open("debug/login_response.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("Full response dumped to debug/login_response.json")
    print()
    print("Keys in response:", list(data.keys()))
    if "access_token" in data:
        print(f"access_token: {data['access_token'][:20]}...")
    if "refresh_token" in data:
        print(f"refresh_token: {data['refresh_token'][:20]}...")
    if "expires_in" in data:
        print(f"expires_in: {data['expires_in']}")
    if "token_type" in data:
        print(f"token_type: {data['token_type']}")
else:
    print("Response body (first 500 chars):")
    print(response.text[:500])
    exit(1)

# Step 3: Test token refresh - try multiple endpoints
print("\n" + "=" * 50)
print("Step 3: Testing token refresh...")

refresh_endpoints = [
    ("Auth0 direct", "https://hellofresh-live.eu.auth0.com/oauth/token", {
        "grant_type": "refresh_token",
        "client_id": "B1n0Q24hv7e4AHc7yG1WwQyuMvpCAIya",
        "refresh_token": data["refresh_token"],
    }),
    ("GW auth/token", "https://www.hellofresh.nl/gw/auth/token", {
        "grant_type": "refresh_token",
        "refresh_token": data["refresh_token"],
    }),
    ("GW login with grant_type", "https://www.hellofresh.nl/gw/login", {
        "grant_type": "refresh_token",
        "refresh_token": data["refresh_token"],
        "username": username,
        "password": password,
    }),
]

for name, url, payload in refresh_endpoints:
    print(f"\n  Trying: {name} ({url})")
    refresh_response = session.post(
        url,
        params={"country": "NL", "locale": "nl-NL"},
        json=payload,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://www.hellofresh.nl",
            "Referer": "https://www.hellofresh.nl/",
        },
    )
    print(f"  Status: {refresh_response.status_code}")
    if refresh_response.status_code == 200:
        refresh_data = refresh_response.json()
        os.makedirs("debug", exist_ok=True)
        with open("debug/refresh_response.json", "w", encoding="utf-8") as f:
            json.dump(refresh_data, f, indent=2, ensure_ascii=False)
        print(f"  Keys: {list(refresh_data.keys())}")
        print("  SUCCESS! Dumped to debug/refresh_response.json")
        break
    else:
        print(f"  Body: {refresh_response.text[:200]}")
