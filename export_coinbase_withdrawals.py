#!/usr/bin/env python3
"""
Export Coinbase withdrawal transactions to CSV for tax/record-keeping purposes.

Shows every crypto send/withdrawal from your Coinbase account, including
the destination address, amount, date, and fees.

Uses the official Coinbase Advanced API Python SDK for authentication.

Usage:
    pip install coinbase-advanced-py
    python export_coinbase_withdrawals.py --key-file coinbase_key.pem.txt

Environment variables (required):
    COINBASE_API_KEY    - Your CDP API key name (starts with "organizations/...")

Optional flags:
    --key-file FILE     - Path to the PEM private key file (recommended)
    --currency CURRENCY - Filter by currency (e.g. BTC, ETH)
    --output FILE       - Output file path (default: coinbase_withdrawals.csv)
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
        from coinbase.rest import RESTClient  # noqa: F401
    except ImportError:
        print(
            "Error: coinbase-advanced-py package is required.\n"
            "Install it with:\n\n"
            "    pip install coinbase-advanced-py\n",
            file=sys.stderr,
        )
        sys.exit(1)


def make_client(api_key: str, api_secret: str):
    """Create a Coinbase REST client."""
    from coinbase.rest import RESTClient
    return RESTClient(api_key=api_key, api_secret=api_secret)


def fetch_withdrawals(client, currency: str = None) -> list:
    """Fetch all withdrawal (send) transactions across all Coinbase accounts."""
    import urllib.request
    import urllib.error

    # The SDK is mainly for Advanced Trade, but we can use its JWT generator
    # to auth against the v2 endpoints
    from coinbase import jwt_generator

    api_key = client.API_KEY
    api_secret = client.API_SECRET
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

    withdrawals = []
    for account in accounts:
        acct_currency = account.get("currency", {})
        currency_code = acct_currency.get("code") if isinstance(acct_currency, dict) else acct_currency

        if currency and currency_code != currency.upper():
            continue

        acct_id = account["id"]
        transactions = fetch_all_pages(f"/v2/accounts/{acct_id}/transactions?limit=100")

        for tx in transactions:
            if tx.get("type") != "send":
                continue

            amount = tx.get("amount", {})
            native_amount = tx.get("native_amount", {})
            network_info = tx.get("network", {})
            to_info = tx.get("to", {})

            withdrawals.append({
                "date": tx.get("created_at", ""),
                "currency": amount.get("currency", currency_code),
                "amount": amount.get("amount", ""),
                "native_currency": native_amount.get("currency", ""),
                "native_amount": native_amount.get("amount", ""),
                "to_address": to_info.get("address", "") if isinstance(to_info, dict) else "",
                "to_name": to_info.get("name", "") if isinstance(to_info, dict) else "",
                "network_name": network_info.get("name", "") if isinstance(network_info, dict) else "",
                "tx_hash": network_info.get("hash", "") if isinstance(network_info, dict) else "",
                "fee": network_info.get("transaction_fee", {}).get("amount", "") if isinstance(network_info, dict) else "",
                "fee_currency": network_info.get("transaction_fee", {}).get("currency", "") if isinstance(network_info, dict) else "",
                "status": tx.get("status", ""),
                "description": tx.get("details", {}).get("title", ""),
            })

    withdrawals.sort(key=lambda w: w["date"], reverse=True)
    return withdrawals


def write_csv(rows: list, output_path: str) -> None:
    """Write withdrawals to a CSV file."""
    if not rows:
        print("No withdrawals found.")
        return

    fieldnames = [
        "date", "currency", "amount", "native_currency", "native_amount",
        "to_address", "to_name", "network_name", "tx_hash",
        "fee", "fee_currency", "status", "description",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Exported {len(rows)} withdrawal(s) to {output_path}")


def write_json(rows: list, output_path: str) -> None:
    """Write withdrawals to a JSON file."""
    if not rows:
        print("No withdrawals found.")
        return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    print(f"Exported {len(rows)} withdrawal(s) to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Coinbase withdrawal transactions to CSV/JSON for tax purposes."
    )
    parser.add_argument(
        "--key-file",
        help="Path to the PEM private key file (recommended)",
    )
    parser.add_argument("--currency", help="Filter by currency (e.g. BTC, ETH)")
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: coinbase_withdrawals.csv or .json)",
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

    client = make_client(api_key, api_secret)

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"coinbase_withdrawals{ext}"

    try:
        withdrawals = fetch_withdrawals(client, currency=args.currency)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(withdrawals, output_path)
    else:
        write_csv(withdrawals, output_path)


if __name__ == "__main__":
    main()
