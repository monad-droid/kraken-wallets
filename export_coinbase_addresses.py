#!/usr/bin/env python3
"""
Export Coinbase withdrawal addresses to CSV for tax/record-keeping purposes.

Uses the Coinbase Developer Platform (CDP) API with JWT authentication.

Usage:
    pip install PyJWT cryptography
    python export_coinbase_addresses.py --key-file coinbase_key.pem.txt

Environment variables (required unless using --key-file):
    COINBASE_API_KEY    - Your CDP API key name (starts with "organizations/...")
    COINBASE_API_SECRET - Your CDP API private key (PEM format)

Optional flags:
    --key-file FILE     - Path to the PEM private key file (recommended over env var)
    --currency CURRENCY - Filter by currency (e.g. BTC, ETH)
    --output FILE       - Output CSV file path (default: coinbase_addresses.csv)
    --json              - Output as JSON instead of CSV
"""

import argparse
import csv
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

API_URL = "https://api.coinbase.com"
API_VERSION = "2023-01-01"


def _check_jwt_deps():
    """Check that PyJWT and cryptography are installed."""
    try:
        import jwt  # noqa: F401
        return True
    except ImportError:
        print(
            "Error: PyJWT and cryptography packages are required for CDP API keys.\n"
            "Install them with:\n\n"
            "    pip install PyJWT cryptography\n",
            file=sys.stderr,
        )
        sys.exit(1)


def build_jwt(method: str, path: str, api_key: str, api_secret: str) -> str:
    """Build a signed JWT for Coinbase CDP API authentication."""
    import jwt

    # URI format: "METHOD host/path" (no scheme)
    host = API_URL.replace("https://", "").replace("http://", "")
    uri = f"{method.upper()} {host}{path}"
    now = int(time.time())

    payload = {
        "sub": api_key,
        "iss": "coinbase-cloud",
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + 120,
        "uris": [uri],
    }

    headers = {
        "kid": api_key,
        "nonce": secrets.token_hex(16),
        "typ": "JWT",
    }

    return jwt.encode(payload, api_secret, algorithm="ES256", headers=headers)


def coinbase_get(path: str, api_key: str, api_secret: str) -> dict:
    """Make an authenticated GET request to the Coinbase API."""
    token = build_jwt("GET", path, api_key, api_secret)

    headers = {
        "Authorization": f"Bearer {token}",
        "CB-VERSION": API_VERSION,
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(API_URL + path, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_all_pages(path: str, api_key: str, api_secret: str) -> list:
    """Fetch all pages of a paginated Coinbase API endpoint."""
    items = []
    next_uri = path
    while next_uri:
        result = coinbase_get(next_uri, api_key, api_secret)
        items.extend(result.get("data", []))
        pagination = result.get("pagination", {})
        next_uri = pagination.get("next_uri")
    return items


def fetch_coinbase_addresses(api_key: str, api_secret: str, currency: str = None) -> list:
    """Fetch all addresses across all Coinbase accounts."""
    accounts = fetch_all_pages("/v2/accounts?limit=100", api_key, api_secret)

    all_addresses = []
    for account in accounts:
        acct_currency = account.get("currency", {})
        currency_code = acct_currency.get("code") if isinstance(acct_currency, dict) else acct_currency

        if currency and currency_code != currency.upper():
            continue

        acct_id = account["id"]
        addresses = fetch_all_pages(
            f"/v2/accounts/{acct_id}/addresses?limit=100",
            api_key,
            api_secret,
        )

        for addr in addresses:
            all_addresses.append({
                "currency": currency_code,
                "account_name": account.get("name", ""),
                "address": addr.get("address", ""),
                "name": addr.get("name", ""),
                "network": addr.get("network", ""),
                "created_at": addr.get("created_at", ""),
            })

    return all_addresses


def write_csv(addresses: list, output_path: str) -> None:
    """Write addresses to a CSV file."""
    if not addresses:
        print("No addresses found.")
        return

    fieldnames = ["currency", "account_name", "address", "name", "network", "created_at"]
    all_keys = set()
    for addr in addresses:
        all_keys.update(addr.keys())
    for key in sorted(all_keys):
        if key not in fieldnames:
            fieldnames.append(key)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for addr in addresses:
            writer.writerow(addr)

    print(f"Exported {len(addresses)} address(es) to {output_path}")


def write_json(addresses: list, output_path: str) -> None:
    """Write addresses to a JSON file."""
    if not addresses:
        print("No addresses found.")
        return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(addresses, f, indent=2)

    print(f"Exported {len(addresses)} address(es) to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Coinbase addresses to CSV/JSON for tax purposes."
    )
    parser.add_argument(
        "--key-file",
        help="Path to the PEM private key file (recommended over env var)",
    )
    parser.add_argument("--currency", help="Filter by currency (e.g. BTC, ETH)")
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: coinbase_addresses.csv or .json)",
    )
    parser.add_argument(
        "--json", dest="use_json", action="store_true", help="Output as JSON instead of CSV"
    )
    args = parser.parse_args()

    api_key = os.environ.get("COINBASE_API_KEY")
    api_secret = None

    # Load private key from file if --key-file is provided
    if args.key_file:
        try:
            with open(args.key_file, "r") as f:
                api_secret = f.read().strip()
        except FileNotFoundError:
            print(f"Error: Key file not found: {args.key_file}", file=sys.stderr)
            sys.exit(1)
    else:
        api_secret = os.environ.get("COINBASE_API_SECRET")

    if not api_key:
        print(
            "Error: COINBASE_API_KEY environment variable is required.\n"
            "This is the API key name that starts with organizations/...\n"
            "Generate a CDP API key at https://www.coinbase.com/settings/api",
            file=sys.stderr,
        )
        sys.exit(1)

    if not api_secret:
        print(
            "Error: Private key is required. Either:\n"
            "  --key-file coinbase_key.pem.txt   (recommended)\n"
            "  or set COINBASE_API_SECRET env var",
            file=sys.stderr,
        )
        sys.exit(1)

    # The private key may have literal \n — convert to real newlines
    if "\\n" in api_secret and "-----BEGIN" in api_secret:
        api_secret = api_secret.replace("\\n", "\n")

    _check_jwt_deps()

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"coinbase_addresses{ext}"

    try:
        addresses = fetch_coinbase_addresses(api_key, api_secret, currency=args.currency)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"HTTP error {e.code}: {e.reason}\n{body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(addresses, output_path)
    else:
        write_csv(addresses, output_path)


if __name__ == "__main__":
    main()
