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
    """Check that the Coinbase SDK is installed."""
    try:
        from coinbase import jwt_generator  # noqa: F401
    except ImportError:
        print(
            "Error: coinbase-advanced-py package is required.\n"
            "Install it with:\n\n"
            "    pip install coinbase-advanced-py\n",
            file=sys.stderr,
        )
        sys.exit(1)


def fetch_coinbase_addresses(api_key: str, api_secret: str, currency: str = None) -> list:
    """Fetch all addresses across all Coinbase accounts."""
    import urllib.request

    from coinbase import jwt_generator

    base_url = "https://api.coinbase.com"

    def authed_get(path):
        uri = jwt_generator.format_jwt_uri("GET", path)
        token = jwt_generator.build_rest_jwt(uri, api_key, api_secret)
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
