#!/usr/bin/env python3
"""
Export Coinbase deposit addresses to CSV for tax/record-keeping purposes.

Uses the official Coinbase Advanced API Python SDK for authentication.

Usage:
    pip install coinbase-advanced-py
    python export_coinbase_addresses.py --key-file coinbase_key.pem.txt

Environment variables (required):
    COINBASE_API_KEY    - Your CDP API key name (starts with "organizations/...")

Optional flags:
    --key-file FILE     - Path to the PEM private key file (recommended)
    --currency CURRENCY - Filter by currency (e.g. BTC, ETH)
    --output FILE       - Output CSV file path (default: coinbase_addresses.csv)
    --json              - Output as JSON instead of CSV
"""

import argparse
import csv
import json
import os
import sys


def _check_deps():
    """Check that PyJWT and cryptography are installed."""
    try:
        import jwt  # noqa: F401
        from cryptography.hazmat.primitives.serialization import load_pem_private_key  # noqa: F401
    except ImportError:
        print(
            "Error: PyJWT and cryptography packages are required.\n"
            "Install them with:\n\n"
            "    pip install PyJWT cryptography\n",
            file=sys.stderr,
        )
        sys.exit(1)


def build_coinbase_jwt(method: str, path: str, api_key: str, api_secret: str) -> str:
    """Build a JWT for Coinbase CDP API authentication.

    Key detail: 'iss' must be the raw API key UUID, while 'sub' is the full
    organizations/... key name.
    """
    import secrets
    import time
    import jwt
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    private_key = load_pem_private_key(api_secret.encode("utf-8"), password=None)

    # Extract the UUID from "organizations/.../apiKeys/<uuid>"
    key_id = api_key.split("/")[-1] if "/" in api_key else api_key

    uri = f"{method.upper()} api.coinbase.com{path}"
    now = int(time.time())

    payload = {
        "sub": api_key,
        "iss": key_id,
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + 120,
        "uri": uri,
    }

    headers = {
        "kid": api_key,
        "nonce": secrets.token_hex(16),
        "typ": "JWT",
    }

    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


def fetch_coinbase_addresses(api_key: str, api_secret: str, currency: str = None) -> list:
    """Fetch all addresses across all Coinbase accounts."""
    import urllib.request

    base_url = "https://api.coinbase.com"

    def authed_get(path):
        token = build_coinbase_jwt("GET", path, api_key, api_secret)
        headers = {
            "Authorization": f"Bearer {token}",
            "CB-VERSION": "2023-01-01",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(base_url + path, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_all_pages(path):
        items = []
        next_uri = path
        while next_uri:
            result = authed_get(next_uri)
            items.extend(result.get("data", []))
            pagination = result.get("pagination", {})
            next_uri = pagination.get("next_uri")
        return items

    accounts = fetch_all_pages("/v2/accounts?limit=100")

    all_addresses = []
    for account in accounts:
        acct_currency = account.get("currency", {})
        currency_code = acct_currency.get("code") if isinstance(acct_currency, dict) else acct_currency

        if currency and currency_code != currency.upper():
            continue

        acct_id = account["id"]
        addresses = fetch_all_pages(f"/v2/accounts/{acct_id}/addresses?limit=100")

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
        help="Path to the PEM private key file (recommended)",
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

    if args.key_file:
        try:
            with open(args.key_file, "r") as f:
                raw = f.read().strip()
                # Fix literal \n (common when copying from Coinbase UI)
                if "\\n" in raw:
                    raw = raw.replace("\\n", "\n")
                api_secret = raw
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

    _check_deps()

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"coinbase_addresses{ext}"

    try:
        addresses = fetch_coinbase_addresses(api_key, api_secret, currency=args.currency)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(addresses, output_path)
    else:
        write_csv(addresses, output_path)


if __name__ == "__main__":
    main()
