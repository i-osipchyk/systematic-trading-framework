# Systematic Trading Framework

A systematic trading framework built on Robert Carver's methodology (as described in *Systematic Trading* and *Leveraged Trading*), covering the full pipeline from backtesting to live execution.

---

## Overview

This framework implements a rules-based, fully systematic approach to trading. The core philosophy follows Carver's principles:

- **Volatility targeting** — size every position relative to its risk, not its notional value
- **Diversified trading rules** — combine multiple uncorrelated signals across rule families
- **Forecast scaling** — map raw rule outputs to a standardised ±20 forecast scale
- **Forecast diversification multiplier (FDM)** — correct for imperfect correlation when combining forecasts
- **Instrument diversification multiplier (IDM)** — scale up portfolio position sizes to account for imperfect correlation across instruments
- **Capital preservation** — hard position limits, correlation-aware sizing, and strict leverage caps

---

## Technology Stack

| Component | Technology |
|---|---|
| Core framework | [pysystemtrade](https://github.com/robcarver17/pysystemtrade) |
| Data / execution API | [cTrader Open API](https://help.ctrader.com/open-api/) |
| Broker | Pepperstone (cTrader account) |
| Language | Python |

Data (historical OHLCV and live prices) and order execution are sourced through the **cTrader Open API** connected to a Pepperstone cTrader account. pysystemtrade provides the backtesting engine, rule implementations, forecast combination, and position sizing logic.

---

## Universe

All instruments are traded as **CFDs via Pepperstone (cTrader)**.

| Instrument | Asset Class | Description |
|---|---|---|
| BTC | Crypto | Bitcoin / USD |
| ETH | Crypto | Ethereum / USD |
| US500 | Equity Index | S&P 500 (US large cap) |
| US30 | Equity Index | Dow Jones Industrial Average |
| GER40 | Equity Index | DAX 40 (German large cap) |
| XAU | Commodity | Gold / USD |
| EURUSD | FX | Euro / US Dollar |
| EURGBP | FX | Euro / British Pound |

**Instrument type:** CFDs (no physical delivery, daily overnight funding charges apply)

### Asset class breakdown

```
Equity Indices  ████████████ 3 instruments  (US500, US30, GER40)
FX              ████████     2 instruments  (EURUSD, EURGBP)
Crypto          ████████     2 instruments  (BTC, ETH)
Commodity       ████         1 instrument   (XAU)
```

> **Note on CFD costs:** Overnight funding (swap rates) applies to all CFD positions held past rollover. These costs must be incorporated into backtest P&L to avoid overfitting to gross returns.

---

## Trading Rules

All 10 rules run identically across all 8 instruments. No instrument-specific carve-outs.

### Rule families and weights

| Family | Weight | Rules |
|---|---|---|
| Trend (EWMAC) | 75% | 6 crossover pairs |
| Mean Reversion | 25% | 4 EMA deviation rules |

Within each family, rules are **equal-weighted** (handcrafted method — no in-sample weight optimisation).

### Trend family — EWMAC crossovers

Exponentially weighted moving average crossover: `forecast = (fast_EMA − slow_EMA) / (price × vol)`, scaled to ±20.

| Rule | Fast span | Slow span | Forecast scalar |
|---|---|---|---|
| EWMAC(2,8) | 2 | 8 | 10.6 (Carver) |
| EWMAC(4,16) | 4 | 16 | 7.5 (Carver) |
| EWMAC(8,32) | 8 | 32 | 5.3 (Carver) |
| EWMAC(16,64) | 16 | 64 | 3.75 (Carver) |
| EWMAC(32,128) | 32 | 128 | 2.65 (Carver) |
| EWMAC(64,256) | 64 | 256 | 1.87 (Carver) |

Forecast scalars sourced from Carver's pre-computed values in pysystemtrade — no in-sample estimation.

**Pruning criteria:** Drop (2,8) if transaction cost analysis on daily bars shows negative net SR. Drop any pair with >0.95 forecast correlation to its neighbour.

### Mean reversion family — vol-normalised EMA deviation

`forecast = -(Price − EMA) / (price × vol)`, scaled to ±20.

Negative sign: price above EMA → negative forecast (expect reversion down). Volatility normalisation uses the same EWMA vol estimate as position sizing, keeping the system internally consistent.

| Rule | EMA span |
|---|---|
| MR(16) | 16 |
| MR(64) | 64 |
| MR(100) | 100 |
| MR(200) | 200 |

**Forecast scalar:** ≈ 10 (analytical prior for a vol-normalised half-normal signal). Verified against backtest; adjust only if empirical mean absolute forecast deviates >30% from 10.

**Pruning criteria:** Drop MR(100) and MR(200) if forecasts are noisy or uncorrelated with realised reversions.

### Carry

Excluded from v1. Pepperstone swap rates provide a natural carry signal via cTrader API; revisit if rate environment shifts or as a diversification add in v2.

---

## Forecast Combination

```
combined_forecast = clip(FDM × Σ(weight_i × forecast_i), -20, +20)
```

- Individual rule forecasts capped at ±20 before combination
- FDM computed from the forecast correlation matrix after backtest data is available
- Combined forecast capped at ±20 post-FDM

---

## Position Sizing

```
position = (capital × vol_target × combined_forecast/10) / (price × instrument_vol × IDM)
```

- **Volatility target:** derived post-backtest via Half Kelly on SR with 0.75 overfitting haircut. Working prior for development: **20% annual**.
- **IDM:** computed from instrument return correlation matrix.
- **Vol estimate:** exponentially-weighted standard deviation of daily percentage returns.

---

## Framework Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Data Layer                           │
│   cTrader Open API → historical OHLCV + live prices         │
│   Pepperstone cTrader account                               │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     Trading Rules                           │
│   EWMAC(2,8) … EWMAC(64,256) · MR(16) … MR(200)            │
│   Each rule outputs a raw forecast → scaled to [-20, +20]   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Forecast Combination                       │
│   75% trend / 25% MR · equal weight within families         │
│   × FDM · combined forecast capped at [-20, +20]            │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Position Sizing                           │
│   Half-Kelly vol target (prior: 20%) · IDM                  │
│   Combined forecast scales exposure linearly                │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                Risk & Portfolio Management                  │
│   Correlation matrix · Position limits · Margin checks      │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴──────────────┐
         ▼                              ▼
┌────────────────┐            ┌──────────────────┐
│   Backtesting  │            │  Live Execution  │
│  pysystemtrade │            │  cTrader API     │
└────────────────┘            └──────────────────┘
```

---

## Roadmap

- [ ] **Data pipeline** — cTrader API integration, historical OHLCV ingestion, normalisation into pysystemtrade format
- [ ] **Trading rules** — implement EWMAC and MR rules, verify scalars and forecast distributions
- [ ] **Backtesting engine** — vectorised P&L, CFD cost modelling (spread + overnight funding), performance metrics
- [ ] **Forecast combination** — FDM calculation, combined forecast verification
- [ ] **Position sizing** — vol estimation, IDM, Half-Kelly vol target derivation
- [ ] **Risk management** — correlation monitoring, drawdown controls, margin ceiling checks
- [ ] **Live execution** — cTrader order management, position reconciliation
- [ ] **Monitoring dashboard** — live P&L, position summary, per-rule forecasts

---

## References

- Carver, R. *Systematic Trading*. Harriman House, 2015.
- Carver, R. *Leveraged Trading*. Harriman House, 2019.
- Carver, R. [pysystemtrade](https://github.com/robcarver17/pysystemtrade) — open-source reference implementation
- cTrader [Open API documentation](https://help.ctrader.com/open-api/)
