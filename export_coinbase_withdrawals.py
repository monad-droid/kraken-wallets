#!/usr/bin/env python3
"""
Export Coinbase withdrawal transactions to CSV for tax/record-keeping purposes.

Shows every crypto send/withdrawal from your Coinbase account, including
the destination address, amount, date, and fees.

Uses the Coinbase Developer Platform (CDP) API with JWT authentication.

Usage:
    pip install PyJWT cryptography
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
    except ImportError:
        print(
            "Error: PyJWT and cryptography packages are required.\n"
            "Install them with:\n\n"
            "    pip install PyJWT cryptography\n",
            file=sys.stderr,
        )
        sys.exit(1)


def build_jwt(method: str, path: str, api_key: str, api_secret: str) -> str:
    """Build a signed JWT for Coinbase CDP API authentication."""
    import jwt

    host = API_URL.replace("https://", "").replace("http://", "")
    uri = f"{method.upper()} {host}{path}"
    now = int(time.time())

    payload = {
        "sub": api_key,
        "iss": "cdp",
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


def fetch_withdrawals(api_key: str, api_secret: str, currency: str = None) -> list:
    """Fetch all withdrawal (send) transactions across all Coinbase accounts."""
    accounts = fetch_all_pages("/v2/accounts?limit=100", api_key, api_secret)

    withdrawals = []
    for account in accounts:
        acct_currency = account.get("currency", {})
        currency_code = acct_currency.get("code") if isinstance(acct_currency, dict) else acct_currency

        if currency and currency_code != currency.upper():
            continue

        acct_id = account["id"]
        transactions = fetch_all_pages(
            f"/v2/accounts/{acct_id}/transactions?limit=100",
            api_key,
            api_secret,
        )

        for tx in transactions:
            # "send" = withdrawal to external address
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

    # Sort by date (newest first)
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
        help="Path to the PEM private key file (recommended over env var)",
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

    if "\\n" in api_secret and "-----BEGIN" in api_secret:
        api_secret = api_secret.replace("\\n", "\n")

    _check_jwt_deps()

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"coinbase_withdrawals{ext}"

    try:
        withdrawals = fetch_withdrawals(api_key, api_secret, currency=args.currency)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        print(f"HTTP error {e.code}: {e.reason}\n{body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(withdrawals, output_path)
    else:
        write_csv(withdrawals, output_path)


if __name__ == "__main__":
    main()
