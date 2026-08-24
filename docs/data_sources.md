# Data Sources

35 instruments, daily (D1) timeframe.

Sources are listed in splice priority order: earlier/coarser → later/finer. Where multiple sources exist, each extends or overrides the previous for the overlapping period.

---

## FX

| Symbol | Start | End | Sources |
|---|---|---|---|
| AUDUSD | 1984-01-03 | 2026-08-22 | FRED DEXUSAL (1971) → yfinance AUDUSD=X → cTrader |
| USDJPY | 1984-01-03 | 2026-08-21 | FRED DEXJPUS (1971) → yfinance USDJPY=X → cTrader |
| USDCAD | 1984-01-03 | 2026-08-22 | FRED DEXCAUS (1971) → yfinance USDCAD=X → cTrader |
| GBPUSD | 1984-01-03 | 2026-08-24 | FRED DEXUSUK (1971) → yfinance GBPUSD=X → cTrader |
| USDX   | 1984-01-03 | 2026-08-21 | Quandl CHRIS/ICE_DX1 → yfinance DX-Y.NYB → cTrader |
| EURUSD | 1999-01-04 | 2026-08-24 | FRED DEXUSEU (1999) → yfinance EURUSD=X → cTrader |
| EURGBP | 1999-01-04 | 2026-08-24 | FRED derived DEXUSEU/DEXUSUK (1999) → yfinance EURGBP=X → cTrader |

## Equity Indices

| Symbol | Start | End | Sources |
|---|---|---|---|
| US500  | 1984-01-03 | 2026-08-21 | yfinance ^GSPC → cTrader |
| JPN225 | 1984-01-04 | 2026-08-21 | yfinance ^N225 → cTrader |
| UK100  | 1984-01-03 | 2026-08-24 | yfinance ^FTSE → cTrader |
| NAS100 | 1985-10-01 | 2026-08-21 | yfinance ^NDX → cTrader |
| GER40  | 1987-12-30 | 2026-08-21 | yfinance ^GDAXI → cTrader |
| HK50   | 1986-12-31 | 2026-08-21 | yfinance ^HSI → cTrader |
| US30   | 2017-12-31 | 2026-08-19 | cTrader only |
| BTC    | 2017-12-31 | 2026-08-19 | cTrader only |
| ETH    | 2017-12-31 | 2026-08-19 | cTrader only |

## Government Bonds

| Symbol | Start | End | Sources |
|---|---|---|---|
| US2YR  | 1984-01-03 | 2026-08-24 | FRED DGS2 yield→price (1976) → Quandl CHRIS/CME_TU1 → yfinance ZT=F |
| US5YR  | 1984-01-03 | 2026-08-24 | FRED DGS5 yield→price (1962) → Quandl CHRIS/CME_FV1 → yfinance ZF=F |
| US10YR | 1984-01-03 | 2026-08-21 | FRED DGS10 yield→price (1962) → Quandl CHRIS/CME_TY1 → yfinance ZN=F |
| US30YR | 1984-01-03 | 2026-08-21 | FRED DGS30 yield→price (1977) → Quandl CHRIS/CME_US1 → yfinance ZB=F |
| BUND   | 1984-01-01 | 2026-08-20 | FRED IRLTLT01DEM156N yield→price monthly (1960) + ECB YC daily (2004) |

## Metals

| Symbol | Start | End | Sources |
|---|---|---|---|
| XAU    | 1984-01-02 | 2026-08-21 | Datahub.io LBMA monthly (1833) → Quandl CHRIS/CME_GC1 → yfinance GC=F → cTrader |
| XAG    | 1984-01-02 | 2026-08-21 | eco3min.fr World Bank monthly (1960) → Quandl CHRIS/CME_SI1 → yfinance SI=F → cTrader |
| COPPER | 1992-01-01 | 2026-08-21 | FRED PCOPPUSDM monthly (1992) → Quandl CHRIS/CME_HG1 → yfinance HG=F → cTrader |

## Energy

| Symbol    | Start | End | Sources |
|---|---|---|---|
| SpotCrude | 1986-01-02 | 2026-08-21 | FRED DCOILWTICO daily (1986) → Quandl CHRIS/CME_CL1 → yfinance CL=F → cTrader |
| NatGas    | 2000-08-30 | 2026-08-21 | Quandl CHRIS/CME_NG1 → yfinance NG=F → cTrader |
| Gasoline  | 2000-11-01 | 2026-08-21 | Quandl CHRIS/NYMEX_RB1 → yfinance RB=F |
| USOIL     | 2017-12-31 | 2026-08-18 | cTrader only |

## Softs & Grains

| Symbol   | Start | End | Sources |
|---|---|---|---|
| Wheat    | 1992-01-01 | 2026-08-21 | FRED PWHEAMTUSDM monthly (1992) → Quandl CHRIS/CME_W1 → yfinance ZW=F |
| Corn     | 1992-01-01 | 2026-08-21 | FRED PMAIZMTUSDM monthly (1992) → Quandl CHRIS/CME_C1 → yfinance ZC=F |
| Soybeans | 1992-01-01 | 2026-08-21 | FRED PSOYBUSDM monthly (1992) → Quandl CHRIS/CME_S1 → yfinance ZS=F |
| Coffee   | 1992-01-01 | 2026-08-21 | FRED PCOFFOTMUSDM monthly (1992) → Quandl CHRIS/ICE_KC1 → yfinance KC=F |
| Cocoa    | 1992-01-01 | 2026-08-21 | FRED PCOCOUSDM monthly (1992) → Quandl CHRIS/ICE_CC1 → yfinance CC=F |
| Sugar    | 1992-01-01 | 2026-08-21 | FRED PSUGAISAUSDM monthly (1992) → Quandl CHRIS/ICE_SB1 → yfinance SB=F |
| Cotton   | 1992-01-01 | 2026-08-21 | FRED PCOTTINDUSDM monthly (1992) → Quandl CHRIS/ICE_CT1 → yfinance CT=F |

---

## Notes

- **Quandl** (Nasdaq Data Link CHRIS continuous futures) requires `NASDAQ_DATA_LINK_API_KEY` in `.env`. Currently returning 403 — yfinance and FRED are the active sources for all affected instruments.
- **BUND** uses FRED monthly spliced with ECB YC daily (`data-api.ecb.europa.eu`, dataset `YC`, series `B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y`) to avoid the ~2 month OECD publication lag. ECB series is euro area AAA-rated bonds (close proxy for Bund).
- **US2YR / US5YR / US10YR / US30YR** use FRED daily yields converted to bond prices via standard bond pricing formula (6% notional coupon, semi-annual). yfinance provides actual futures prices for recent years.
- **BTC, ETH, US30, USOIL** — no historical extension configured; cTrader data only from late 2017.
- All timestamps use 22:00:00 UTC to match cTrader's daily bar convention.
