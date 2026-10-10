# Kairos — SerpApi Alt-Data Terminal

Kairos turns SerpApi's search engines into a scheduled sensor network that tracks listed Indian companies, and flags when what the public is doing diverges from what the stock price says. 

Every search engine becomes a sensor, every eligible capture becomes a traceable observation, repeated captures become a time series, every alert links back to the search result that caused it.

![Kairos Dashboard Mockup](docs/dashboard_mockup.png) <!-- Replace with actual screenshot later -->

## Why search data is alternative data
Funds pay data vendors heavily for alternative data: app reviews, hiring activity, web demand, pricing. Small research teams in India get none of it. The raw signals are public, but they are scattered across dozens of search surfaces. Kairos is the layer that turns those APIs into time-series sensors.

## Quickstart (Offline Mode)

You can run Kairos without any SerpApi keys using committed mock data/fixtures.

```bash
# Clone the repository
git clone https://github.com/catherinearulanand/Kairos.git
cd Kairos

# Install dependencies
pip install -e .

# Run the UI in offline mode
KAIROS_OFFLINE=1 streamlit run app/streamlit_app.py
```

## How Kairos uses SerpApi

| Sensor | Engine | Metrics extracted |
|---|---|---|
| Demand | `google_trends` | Weekly interest index; share of search vs competitors |
| App health | `google_play_product` | Mean rating of recent reviews, recent review sample vs displayed rating |
| Ad activity | `google_ads_transparency_center` | Active creatives per window |
| Price | `google_finance` | Ground truth price, weekly closes |
| News context| `google_news` | Article headlines |

*(Includes additional resolution engines: `google_trends_autocomplete`, `google_play`, etc.)*

## Rules

Kairos evaluates rules to find divergences. Example:
- **R1 (High)**: Search interest share vs price disconnect. Fires when the 4-week mean search share vs prior 8 weeks moves >15% one way, while price moves >8% the other way.
- **R2 (Medium)**: Recent reviews below displayed rating.

## Limitations & Honesty Notes
- **Signals, not predictions.** Kairos flags divergences; it does not predict prices.
- **Samples, not totals.** Sampled stores and recent reviews are samples, not totals.
- **No buy/sell language.** We do not provide investment advice.

## AI Tools Used
- Claude for specification and code generation.
- [Model Name] for implementation and rule design assistance.

## Disclaimer
Data via SerpApi. Not investment advice.

## License
MIT
