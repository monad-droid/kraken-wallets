#!/usr/bin/env python3
"""Quick diagnostic: test Coinbase API auth against multiple endpoints."""
import json
import sys
import urllib.request
import urllib.error

from coinbase.jwt_generator import build_rest_jwt, format_jwt_uri


def load_key(path):
    with open(path) as f:
        data = json.load(f)
    name = data["name"]
    pk = data["privateKey"]
    if "\\n" in pk:
        pk = pk.replace("\\n", "\n")
    return name, pk.strip()


def try_endpoint(method, path, api_key, api_secret):
    uri = format_jwt_uri(method, path)
    token = build_rest_jwt(uri, api_key, api_secret)
    headers = {
        "Authorization": f"Bearer {token}",
        "CB-VERSION": "2023-01-01",
        "Content-Type": "application/json",
    }
    url = f"https://api.coinbase.com{path}"
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            print(f"  OK {resp.status} — keys: {list(body.keys())[:5]}")
            return body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  FAIL {e.code} {e.reason} — {body}")
        return None


def main():
    key_file = sys.argv[1] if len(sys.argv) > 1 else "cdp_api_key.json"
    api_key, api_secret = load_key(key_file)
    print(f"API key: {api_key}\n")

    endpoints = [
        ("GET", "/api/v3/brokerage/accounts"),
        ("GET", "/api/v3/brokerage/accounts?limit=250"),
        ("GET", "/v2/user"),
        ("GET", "/v2/accounts"),
        ("GET", "/v2/accounts?limit=100"),
    ]

    for method, path in endpoints:
        print(f"{method} {path}")
        try_endpoint(method, path, api_key, api_secret)
        print()


if __name__ == "__main__":
    main()
