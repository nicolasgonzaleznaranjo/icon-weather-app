# ICON Weather App

ICON Weather App is a dark, trading-focused monitoring dashboard for Kalshi weather markets.

It is built for operational decision support around:
- Kalshi weather contracts
- NWS forecast data
- official station references
- trade-log-driven performance tracking
- daily high and low temperature monitoring

## Pages

- `Performance Overview`
- `High Temp Monitor`
- `Low Temp Monitor`
- `Market Map`
- `Trade Log`
- `Data Diagnostics`
- `Settings`

## Project Structure

```text
app.py
config/
  cities.csv
  markets.csv
src/
  kalshi_client.py
  nws_client.py
  data_models.py
  rules_engine.py
  trade_log.py
  charts.py
  utils.py
pages/
  2_High_Temp_Monitor.py
  3_Low_Temp_Monitor.py
  4_Market_Map.py
  5_Trade_Log.py
  6_Data_Diagnostics.py
  7_Settings.py
data/
  trade_log.csv
  cached_forecasts.csv
```

## Local Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Required Streamlit Secrets

Production account:

```toml
KALSHI_ENVIRONMENT = "production"
KALSHI_API_KEY_ID = "your_key_id"
KALSHI_PRIVATE_KEY = '''
-----BEGIN RSA PRIVATE KEY-----
your_private_key_lines
-----END RSA PRIVATE KEY-----
'''
```

Demo account:

```toml
KALSHI_ENVIRONMENT = "demo"
KALSHI_DEMO_API_KEY_ID = "your_demo_key_id"
KALSHI_DEMO_PRIVATE_KEY = '''
-----BEGIN RSA PRIVATE KEY-----
your_demo_private_key_lines
-----END RSA PRIVATE KEY-----
'''
```

## Notes

- Public Kalshi market data can still load without authenticated credentials.
- Authenticated balance checks require valid Kalshi secrets.
- NWS data is pulled from public NOAA/NWS endpoints.
- `trade_log.csv` is currently seeded from your workbook reference and should be replaced with your live source-of-truth workflow when ready.
