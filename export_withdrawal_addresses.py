#!/usr/bin/env python3
"""
Export Kraken withdrawal addresses to CSV for tax/record-keeping purposes.

Usage:
    python export_withdrawal_addresses.py

Environment variables (required):
    KRAKEN_API_KEY    - Your Kraken API public key
    KRAKEN_API_SECRET - Your Kraken API private key

Optional flags:
    --asset ASSET     - Filter by asset (e.g. XBT, ETH)
    --method METHOD   - Filter by withdrawal method
    --verified        - Only show verified addresses
    --output FILE     - Output CSV file path (default: withdrawal_addresses.csv)
    --json            - Output as JSON instead of CSV
"""

import argparse
import base64
import csv
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

API_URL = "https://api.kraken.com"
WITHDRAW_ADDRESSES_PATH = "/0/private/WithdrawAddresses"


def get_kraken_signature(url_path: str, data: dict, secret: str) -> str:
    """Generate the API-Sign header value for Kraken private endpoints."""
    post_data = urllib.parse.urlencode(data)
    encoded = (str(data["nonce"]) + post_data).encode("utf-8")
    message = url_path.encode("utf-8") + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode("utf-8")


def kraken_request(url_path: str, data: dict, api_key: str, api_secret: str) -> dict:
    """Make an authenticated request to a Kraken private endpoint."""
    data["nonce"] = str(int(time.time() * 1000))
    signature = get_kraken_signature(url_path, data, api_secret)

    headers = {
        "API-Key": api_key,
        "API-Sign": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    req = urllib.request.Request(
        API_URL + url_path,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_withdrawal_addresses(
    api_key: str,
    api_secret: str,
    asset: str = None,
    method: str = None,
    verified: bool = False,
) -> list:
    """Fetch withdrawal addresses from Kraken API."""
    params = {}
    if asset:
        params["asset"] = asset
    if method:
        params["method"] = method
    if verified:
        params["verified"] = "true"

    result = kraken_request(WITHDRAW_ADDRESSES_PATH, params, api_key, api_secret)

    if result.get("error"):
        errors = result["error"]
        raise RuntimeError(f"Kraken API error: {', '.join(errors)}")

    return result.get("result", [])


def write_csv(addresses: list, output_path: str) -> None:
    """Write addresses to a CSV file."""
    if not addresses:
        print("No withdrawal addresses found.")
        return

    fieldnames = ["asset", "method", "key", "address", "memo", "verified", "new"]
    # Include any extra fields present in the response
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
        print("No withdrawal addresses found.")
        return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(addresses, f, indent=2)

    print(f"Exported {len(addresses)} address(es) to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export Kraken withdrawal addresses to CSV/JSON for tax purposes."
    )
    parser.add_argument("--asset", help="Filter by asset (e.g. XBT, ETH)")
    parser.add_argument("--method", help="Filter by withdrawal method")
    parser.add_argument(
        "--verified", action="store_true", help="Only show verified addresses"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: withdrawal_addresses.csv or .json)",
    )
    parser.add_argument(
        "--json", dest="use_json", action="store_true", help="Output as JSON instead of CSV"
    )
    args = parser.parse_args()

    api_key = os.environ.get("KRAKEN_API_KEY")
    api_secret = os.environ.get("KRAKEN_API_SECRET")

    if not api_key or not api_secret:
        print(
            "Error: KRAKEN_API_KEY and KRAKEN_API_SECRET environment variables are required.\n"
            "Generate an API key at https://www.kraken.com/u/security/api\n"
            "Required permissions: Funds - Query, Funds - Withdraw",
            file=sys.stderr,
        )
        sys.exit(1)

    ext = ".json" if args.use_json else ".csv"
    output_path = args.output or f"withdrawal_addresses{ext}"

    try:
        addresses = fetch_withdrawal_addresses(
            api_key,
            api_secret,
            asset=args.asset,
            method=args.method,
            verified=args.verified,
        )
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if args.use_json:
        write_json(addresses, output_path)
    else:
        write_csv(addresses, output_path)


if __name__ == "__main__":
    main()
