# Kraken Withdrawal Address Exporter

Export your Kraken withdrawal addresses to CSV or JSON using the [WithdrawAddresses](https://docs.kraken.com/api/docs/rest-api/get-withdrawal-addresses/) API endpoint. Useful for tax reporting and record-keeping.

## Prerequisites

- Python 3.7+
- No external dependencies (uses only the Python standard library)
- A Kraken API key with **Funds - Query** and **Funds - Withdraw** permissions.
  Generate one at https://www.kraken.com/u/security/api

## Setup

```bash
export KRAKEN_API_KEY="your-api-key"
export KRAKEN_API_SECRET="your-api-secret"
```

## Usage

```bash
# Export all withdrawal addresses to CSV
python export_withdrawal_addresses.py

# Filter by asset
python export_withdrawal_addresses.py --asset XBT

# Filter by withdrawal method
python export_withdrawal_addresses.py --method Ethereum

# Only verified addresses
python export_withdrawal_addresses.py --verified

# Export as JSON
python export_withdrawal_addresses.py --json

# Custom output file
python export_withdrawal_addresses.py --output my_addresses.csv
```

## Output

The CSV contains these columns: `asset`, `method`, `key`, `address`, `memo`, `verified`, `new` (plus any additional fields returned by the API).
