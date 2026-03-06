#!/usr/bin/env python3
"""
Export Coinbase withdrawal transactions to CSV for tax/record-keeping purposes.

Shows every crypto send/withdrawal from your Coinbase account, including
the destination address, amount, date, and fees.

Uses the official Coinbase Advanced API Python SDK for authentication.

Usage:
    pip install PyJWT cryptography
    python export_coinbase_withdrawals.py --key-json cdp_api_key.json

Options:
    --key-json FILE     - Path to the CDP JSON key file (recommended, contains both key name and private key)
    --key-file FILE     - Path to a PEM private key file (requires COINBASE_API_KEY env var)
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
    organizations/... key name. See:
    https://www.technetexperts.com/coinbase-es256-jwt-401-iss-fix/
    """
    import secrets
    import time
    import jwt
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    private_key = load_pem_private_key(api_secret.encode("utf-8"), password=None)

    uri = f"{method.upper()} api.coinbase.com{path}"
    now = int(time.time())

    # Match the official coinbase-advanced-py SDK's build_jwt() exactly
    payload = {
        "sub": api_key,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": uri,
    }

    headers = {
        "kid": api_key,
        "nonce": secrets.token_hex(),
    }

    token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)

    # Debug: decode and print the JWT claims (remove --debug flag check to always show)
    if os.environ.get("DEBUG"):
        import base64
        parts = token.split(".")
        def pad(s): return s + "=" * (4 - len(s) % 4)
        print("JWT header:", base64.urlsafe_b64decode(pad(parts[0])).decode(), file=sys.stderr)
        print("JWT payload:", base64.urlsafe_b64decode(pad(parts[1])).decode(), file=sys.stderr)

    return token


def fetch_withdrawals(api_key: str, api_secret: str, currency: str = None) -> list:
    """Fetch all withdrawal (send) transactions across all Coinbase accounts."""
    import urllib.request
    import urllib.error

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

    # First try v3 Advanced Trade API to verify auth works
    try:
        v3_result = authed_get("/api/v3/brokerage/accounts?limit=250")
        v3_accounts = v3_result.get("accounts", [])
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise RuntimeError(
                "401 Unauthorized on v3 endpoint — your API key or private key may be invalid.\n"
                "Try creating a fresh key at https://portal.cdp.coinbase.com/access/api"
            )
        raise

    # Build a map of account UUID -> currency from v3
    acct_map = {}
    for acct in v3_accounts:
        acct_map[acct.get("uuid", "")] = acct.get("currency", "")

    # Now use v2 endpoints for transaction history
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
        "--key-json",
        help="Path to the CDP JSON key file (contains both key name and private key)",
    )
    parser.add_argument(
        "--key-file",
        help="Path to a PEM private key file (requires COINBASE_API_KEY env var)",
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

    api_key = None
    api_secret = None

    if args.key_json:
        try:
            with open(args.key_json, "r") as f:
                key_data = json.load(f)
            api_key = key_data.get("name")
            raw_pk = key_data.get("privateKey", "")
            # Fix literal \n sequences
            if "\\n" in raw_pk:
                raw_pk = raw_pk.replace("\\n", "\n")
            api_secret = raw_pk.strip()
            if not api_key or not api_secret:
                print("Error: JSON key file must contain 'name' and 'privateKey' fields.", file=sys.stderr)
                sys.exit(1)
            print(f"Loaded API key: {api_key}", file=sys.stderr)
        except FileNotFoundError:
            print(f"Error: Key file not found: {args.key_json}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in key file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        api_key = os.environ.get("COINBASE_API_KEY")
        if args.key_file:
            try:
                with open(args.key_file, "r") as f:
                    raw = f.read().strip()
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
                "Error: API key required. Either:\n"
                "  --key-json cdp_api_key.json   (recommended)\n"
                "  or set COINBASE_API_KEY env var with --key-file",
                file=sys.stderr,
            )
            sys.exit(1)

        if not api_secret:
            print(
                "Error: Private key required. Either:\n"
                "  --key-json cdp_api_key.json   (recommended)\n"
                "  or --key-file with a PEM file",
                file=sys.stderr,
            )
            sys.exit(1)

    _check_deps()

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"coinbase_withdrawals{ext}"

    try:
        withdrawals = fetch_withdrawals(api_key, api_secret, currency=args.currency)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(withdrawals, output_path)
    else:
        write_csv(withdrawals, output_path)


if __name__ == "__main__":
    main()
