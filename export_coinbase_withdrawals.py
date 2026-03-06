#!/usr/bin/env python3
"""
Export Coinbase withdrawal transactions to CSV for tax/record-keeping purposes.

Shows every crypto send/withdrawal from your Coinbase account, including
the destination address, amount, date, and fees.

Supports two authentication methods:
  1. Legacy API key (from coinbase.com/settings/api) — HMAC auth, no extra deps
  2. CDP API key (from portal.cdp.coinbase.com) — JWT/ES256 auth, needs PyJWT

Usage (legacy key — recommended for personal accounts):
    export COINBASE_API_KEY="your-api-key"
    export COINBASE_API_SECRET="your-api-secret"
    python3 export_coinbase_withdrawals.py

Usage (CDP key):
    pip install PyJWT cryptography
    python3 export_coinbase_withdrawals.py --key-json cdp_api_key.json

Options:
    --key-json FILE     - Path to a CDP JSON key file (JWT auth)
    --key-file FILE     - Path to a PEM private key file (JWT auth, requires COINBASE_API_KEY env var)
    --currency CURRENCY - Filter by currency (e.g. BTC, ETH)
    --output FILE       - Output file path (default: coinbase_withdrawals.csv)
    --json              - Output as JSON instead of CSV
"""

import argparse
import csv
import json
import os
import sys


def _check_jwt_deps():
    """Check that PyJWT and cryptography are installed (only needed for CDP keys)."""
    try:
        import jwt  # noqa: F401
        from cryptography.hazmat.primitives.serialization import load_pem_private_key  # noqa: F401
    except ImportError:
        print(
            "Error: PyJWT and cryptography packages are required for CDP key auth.\n"
            "Install them with:\n\n"
            "    pip install PyJWT cryptography\n",
            file=sys.stderr,
        )
        sys.exit(1)


def build_hmac_headers(method: str, path: str, api_key: str, api_secret: str) -> dict:
    """Build HMAC-SHA256 auth headers for Coinbase legacy API keys."""
    import hashlib
    import hmac
    import time

    timestamp = str(int(time.time()))
    message = timestamp + method.upper() + path
    signature = hmac.new(
        api_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "CB-ACCESS-KEY": api_key,
        "CB-ACCESS-SIGN": signature,
        "CB-ACCESS-TIMESTAMP": timestamp,
        "CB-VERSION": "2023-01-01",
        "Content-Type": "application/json",
    }


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

    # Strip query params from the URI claim — Coinbase rejects JWTs that include them
    clean_path = path.split("?")[0]
    uri = f"{method.upper()} api.coinbase.com{clean_path}"
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


def fetch_withdrawals(api_key: str, api_secret: str, currency: str = None, auth_mode: str = "hmac") -> list:
    """Fetch all withdrawal (send) transactions across all Coinbase accounts."""
    import urllib.request
    import urllib.error

    base_url = "https://api.coinbase.com"

    def authed_get(path):
        if auth_mode == "jwt":
            token = build_coinbase_jwt("GET", path, api_key, api_secret)
            headers = {
                "Authorization": f"Bearer {token}",
                "CB-VERSION": "2023-01-01",
                "Content-Type": "application/json",
            }
        else:
            headers = build_hmac_headers("GET", path, api_key, api_secret)
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

    # Use v2 endpoints for account listing and transaction history
    try:
        accounts = fetch_all_pages("/v2/accounts?limit=100")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(
            f"{e.code} {e.reason} on /v2/accounts\n"
            f"Response: {body}\n"
            "Check that your API key has the correct permissions."
        )

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
    auth_mode = "hmac"  # default to legacy HMAC auth

    if args.key_json:
        # CDP key (JWT auth)
        auth_mode = "jwt"
        try:
            with open(args.key_json, "r") as f:
                key_data = json.load(f)
            api_key = key_data.get("name")
            raw_pk = key_data.get("privateKey", "")
            if "\\n" in raw_pk:
                raw_pk = raw_pk.replace("\\n", "\n")
            api_secret = raw_pk.strip()
            if not api_key or not api_secret:
                print("Error: JSON key file must contain 'name' and 'privateKey' fields.", file=sys.stderr)
                sys.exit(1)
            print(f"Using CDP key (JWT auth): {api_key}", file=sys.stderr)
        except FileNotFoundError:
            print(f"Error: Key file not found: {args.key_json}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in key file: {e}", file=sys.stderr)
            sys.exit(1)
        _check_jwt_deps()
    elif args.key_file:
        # PEM key file (JWT auth)
        auth_mode = "jwt"
        api_key = os.environ.get("COINBASE_API_KEY")
        try:
            with open(args.key_file, "r") as f:
                raw = f.read().strip()
                if "\\n" in raw:
                    raw = raw.replace("\\n", "\n")
                api_secret = raw
        except FileNotFoundError:
            print(f"Error: Key file not found: {args.key_file}", file=sys.stderr)
            sys.exit(1)
        if not api_key:
            print("Error: COINBASE_API_KEY env var required with --key-file", file=sys.stderr)
            sys.exit(1)
        print(f"Using CDP key (JWT auth): {api_key}", file=sys.stderr)
        _check_jwt_deps()
    else:
        # Legacy API key (HMAC auth) — from coinbase.com/settings/api
        api_key = os.environ.get("COINBASE_API_KEY")
        api_secret = os.environ.get("COINBASE_API_SECRET")
        if not api_key or not api_secret:
            print(
                "Error: No API credentials provided.\n\n"
                "Option 1 — Legacy key (for personal accounts, recommended):\n"
                "  Create a key at https://www.coinbase.com/settings/api\n"
                "  export COINBASE_API_KEY='your-key'\n"
                "  export COINBASE_API_SECRET='your-secret'\n\n"
                "Option 2 — CDP key (for developer platform):\n"
                "  python3 export_coinbase_withdrawals.py --key-json cdp_api_key.json\n",
                file=sys.stderr,
            )
            sys.exit(1)
        print("Using legacy key (HMAC auth)", file=sys.stderr)

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"coinbase_withdrawals{ext}"

    try:
        withdrawals = fetch_withdrawals(api_key, api_secret, currency=args.currency, auth_mode=auth_mode)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(withdrawals, output_path)
    else:
        write_csv(withdrawals, output_path)


if __name__ == "__main__":
    main()
