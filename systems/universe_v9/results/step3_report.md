# Step 3 Rule Calibration Report

## Scalars

| Rule | Raw MAF | Scalar |
|------|---------|--------|
| EWMAC_4_16 | 0.995 | 10.05 |
| EWMAC_8_32 | 1.517 | 6.59 |
| EWMAC_16_64 | 2.335 | 4.28 |
| EWMAC_32_128 | 3.601 | 2.78 |
| EWMAC_64_256 | 5.224 | 1.91 |
| SEASONALITY_US500 | 18.460 | 0.54 |
| SEASONALITY_GER40 | 16.643 | 0.60 |
| SEASONALITY_JPN225 | 20.458 | 0.49 |
| SEASONALITY_HK50 | 21.672 | 0.46 |
| SEASONALITY_US10YR | 20.853 | 0.48 |
| SEASONALITY_BUND | 20.647 | 0.48 |
| SEASONALITY_XAU | 21.683 | 0.46 |
| SEASONALITY_XAG | 20.827 | 0.48 |
| SEASONALITY_COPPER | 20.092 | 0.50 |
| SEASONALITY_SpotCrude | 25.446 | 0.39 |
| SEASONALITY_Gasoline | 32.066 | 0.31 |
| SEASONALITY_Coffee | 32.453 | 0.31 |
| SEASONALITY_Sugar | 22.274 | 0.45 |
| SEASONALITY_Corn | 28.584 | 0.35 |
| SEASONALITY_Cotton | 27.586 | 0.36 |
| SEASONALITY_Soybeans | 17.823 | 0.56 |
| SEASONALITY_Wheat | 24.974 | 0.40 |

## Correlation Matrix

| | EWMAC_4_16 | EWMAC_8_32 | EWMAC_16_64 | EWMAC_32_128 | EWMAC_64_256 | SEASONALITY |
|---|---:|---:|---:|---:|---:|---:|
| **EWMAC_4_16** | 1.000 | 0.864 | 0.572 | 0.324 | 0.171 | 0.129 |
| **EWMAC_8_32** | 0.864 | 1.000 | 0.862 | 0.587 | 0.337 | 0.126 |
| **EWMAC_16_64** | 0.572 | 0.862 | 1.000 | 0.873 | 0.599 | 0.087 |
| **EWMAC_32_128** | 0.324 | 0.587 | 0.873 | 1.000 | 0.866 | 0.026 |
| **EWMAC_64_256** | 0.171 | 0.337 | 0.599 | 0.866 | 1.000 | -0.024 |
| **SEASONALITY** | 0.129 | 0.126 | 0.087 | 0.026 | -0.024 | 1.000 |

## Cost Filter

| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |
|------|-----------------|-------------|----------------------------------|
| EWMAC_4_16 | 24.2 | 0.0054 | XAG |
| EWMAC_8_32 | 12.9 | 0.0101 | — |
| EWMAC_16_64 | 9.8 | 0.0133 | — |
| EWMAC_32_128 | 8.3 | 0.0157 | — |
| EWMAC_64_256 | 7.6 | 0.0171 | — |
| SEASONALITY | 10.6 | 0.0122 | — |

## Forecast Weights Template

| Rule | Weight |
|------|--------|
| EWMAC_4_16 | 0.100000 |
| EWMAC_8_32 | 0.100000 |
| EWMAC_16_64 | 0.100000 |
| EWMAC_32_128 | 0.100000 |
| EWMAC_64_256 | 0.100000 |
| SEASONALITY | 0.500000 |
