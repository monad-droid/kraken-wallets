# Crypto Withdrawal Address Exporter

Export your withdrawal addresses from **Kraken** and **Coinbase** to CSV or JSON. Useful for tax reporting and record-keeping.

## Prerequisites

- Python 3.7+
- Kraken script: no external dependencies (standard library only)
- Coinbase scripts: `pip install coinbase-advanced-py`

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

Generate a CDP API key at https://www.coinbase.com/settings/api with **View (read-only)** permission. Save the private key to a `.pem.txt` file.

```bash
pip install coinbase-advanced-py

export COINBASE_API_KEY="organizations/..."        # the API key name
```

### Usage

```bash
# Export all withdrawal transactions (sends) to CSV
python export_coinbase_withdrawals.py --key-file coinbase_key.pem.txt

# Filter by currency
python export_coinbase_withdrawals.py --key-file coinbase_key.pem.txt --currency BTC

# Export as JSON
python export_coinbase_withdrawals.py --key-file coinbase_key.pem.txt --json

# Export account addresses instead
python export_coinbase_addresses.py --key-file coinbase_key.pem.txt
```

### Output

`export_coinbase_withdrawals.py` — every crypto withdrawal you made:

| Column | Description |
|---|---|
| `date` | When the withdrawal happened |
| `currency` | Asset sent (BTC, ETH, etc.) |
| `amount` | How much was sent |
| `native_amount` | Value in your local currency at the time |
| `to_address` | Destination wallet address |
| `tx_hash` | On-chain transaction hash |
| `fee` | Network fee |
| `status` | completed, pending, etc. |

`export_coinbase_addresses.py` — your Coinbase deposit addresses: `currency`, `account_name`, `address`, `name`, `network`, `created_at`.
