# Crypto Withdrawal Address Exporter

Export your withdrawal addresses from **Kraken** and **Coinbase** to CSV or JSON. Useful for tax reporting and record-keeping.

## Prerequisites

- Python 3.7+
- Kraken script: no external dependencies (standard library only)
- Coinbase script: `pip install PyJWT cryptography`

## Kraken

### Setup

Generate an API key at https://www.kraken.com/u/security/api with **Funds - Query** and **Funds - Withdraw** permissions.

```bash
export KRAKEN_API_KEY="your-api-key"
export KRAKEN_API_SECRET="your-api-secret"
```

### Usage

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

### Output

The CSV contains these columns: `asset`, `method`, `key`, `address`, `memo`, `verified`, `new` (plus any additional fields returned by the API).

## Coinbase

### Setup

Generate a CDP API key at https://www.coinbase.com/settings/api with **View (read-only)** permission.

```bash
pip install PyJWT cryptography

export COINBASE_API_KEY="organizations/..."        # the API key name
export COINBASE_API_SECRET="-----BEGIN EC PRIVATE KEY-----
...
-----END EC PRIVATE KEY-----"
```

### Usage

```bash
# Export all addresses to CSV
python export_coinbase_addresses.py

# Filter by currency
python export_coinbase_addresses.py --currency BTC

# Export as JSON
python export_coinbase_addresses.py --json

# Custom output file
python export_coinbase_addresses.py --output my_coinbase_addresses.csv
```

### Output

The CSV contains these columns: `currency`, `account_name`, `address`, `name`, `network`, `created_at`.
