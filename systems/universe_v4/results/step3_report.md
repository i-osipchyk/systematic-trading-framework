# Step 3 Rule Calibration Report

## Scalars

| Rule | Raw MAF | Scalar |
|------|---------|--------|
| EWMAC_4_16 | 1.011 | 9.89 |
| EWMAC_8_32 | 1.563 | 6.40 |
| EWMAC_16_64 | 2.434 | 4.11 |
| EWMAC_32_128 | 3.774 | 2.65 |
| EWMAC_64_256 | 5.484 | 1.82 |
| SEASONALITY_US500 | 20.846 | 0.48 |
| SEASONALITY_NAS100 | 21.981 | 0.46 |
| SEASONALITY_GER40 | 19.695 | 0.51 |
| SEASONALITY_JPN225 | 23.626 | 0.42 |
| SEASONALITY_HK50 | 24.542 | 0.41 |
| SEASONALITY_UK100 | 26.328 | 0.38 |
| SEASONALITY_US2YR | 16.968 | 0.59 |
| SEASONALITY_US5YR | 16.581 | 0.60 |
| SEASONALITY_US10YR | 17.519 | 0.57 |
| SEASONALITY_US30YR | 18.123 | 0.55 |
| SEASONALITY_BUND | 22.637 | 0.44 |
| SEASONALITY_XAU | 37.139 | 0.27 |
| SEASONALITY_XAG | 19.425 | 0.52 |
| SEASONALITY_COPPER | 17.149 | 0.58 |
| SEASONALITY_SpotCrude | 16.596 | 0.60 |
| SEASONALITY_Gasoline | 26.238 | 0.38 |
| SEASONALITY_Coffee | 33.424 | 0.30 |
| SEASONALITY_Cocoa | 19.358 | 0.52 |
| SEASONALITY_Sugar | 21.438 | 0.47 |
| SEASONALITY_Corn | 25.216 | 0.40 |
| SEASONALITY_Cotton | 20.195 | 0.49 |
| SEASONALITY_Soybeans | 23.140 | 0.43 |
| SEASONALITY_Wheat | 22.143 | 0.45 |

## Correlation Matrix

| | EWMAC_4_16 | EWMAC_8_32 | EWMAC_16_64 | EWMAC_32_128 | EWMAC_64_256 | SEASONALITY |
|---|---:|---:|---:|---:|---:|---:|
| **EWMAC_4_16** | 1.000 | 0.867 | 0.580 | 0.335 | 0.179 | 0.146 |
| **EWMAC_8_32** | 0.867 | 1.000 | 0.864 | 0.594 | 0.343 | 0.141 |
| **EWMAC_16_64** | 0.580 | 0.864 | 1.000 | 0.876 | 0.601 | 0.093 |
| **EWMAC_32_128** | 0.335 | 0.594 | 0.876 | 1.000 | 0.867 | 0.020 |
| **EWMAC_64_256** | 0.179 | 0.343 | 0.601 | 0.867 | 1.000 | -0.033 |
| **SEASONALITY** | 0.146 | 0.141 | 0.093 | 0.020 | -0.033 | 1.000 |

## Cost Filter

| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |
|------|-----------------|-------------|----------------------------------|
| EWMAC_4_16 | 23.7 | 0.0055 | XAU, XAG, Cocoa |
| EWMAC_8_32 | 12.7 | 0.0102 | XAG, Cocoa |
| EWMAC_16_64 | 9.7 | 0.0135 | — |
| EWMAC_32_128 | 8.2 | 0.0159 | — |
| EWMAC_64_256 | 7.5 | 0.0172 | — |
| SEASONALITY | 9.9 | 0.0131 | XAG |

## Forecast Weights Template

| Rule | Weight |
|------|--------|
| EWMAC_4_16 | 0.100000 |
| EWMAC_8_32 | 0.100000 |
| EWMAC_16_64 | 0.100000 |
| EWMAC_32_128 | 0.100000 |
| EWMAC_64_256 | 0.100000 |
| SEASONALITY | 0.500000 |
