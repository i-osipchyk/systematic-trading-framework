# Step 3 Rule Calibration Report

## Scalars

| Rule | Raw MAF | Scalar |
|------|---------|--------|
| EWMAC_8_32 | 1.530 | 6.53 |
| EWMAC_16_64 | 2.384 | 4.20 |
| EWMAC_32_128 | 3.721 | 2.69 |
| EWMAC_64_256 | 5.441 | 1.84 |
| SEASONALITY_US500 | 19.392 | 0.52 |
| SEASONALITY_GER40 | 15.699 | 0.64 |
| SEASONALITY_JPN225 | 20.331 | 0.49 |
| SEASONALITY_HK50 | 22.362 | 0.45 |
| SEASONALITY_US10YR | 19.382 | 0.52 |
| SEASONALITY_BUND | 19.873 | 0.50 |
| SEASONALITY_XAU | 22.716 | 0.44 |
| SEASONALITY_COPPER | 21.246 | 0.47 |
| SEASONALITY_SpotCrude | 23.307 | 0.43 |
| SEASONALITY_Coffee | 34.557 | 0.29 |
| SEASONALITY_Sugar | 24.268 | 0.41 |
| SEASONALITY_Corn | 27.566 | 0.36 |
| SEASONALITY_Cotton | 25.884 | 0.39 |
| SEASONALITY_Soybeans | 18.568 | 0.54 |
| SEASONALITY_Wheat | 18.873 | 0.53 |

## Correlation Matrix

| | EWMAC_8_32 | EWMAC_16_64 | EWMAC_32_128 | EWMAC_64_256 | SEASONALITY |
|---|---:|---:|---:|---:|---:|
| **EWMAC_8_32** | 1.000 | 0.862 | 0.592 | 0.347 | 0.120 |
| **EWMAC_16_64** | 0.862 | 1.000 | 0.876 | 0.608 | 0.078 |
| **EWMAC_32_128** | 0.592 | 0.876 | 1.000 | 0.870 | 0.017 |
| **EWMAC_64_256** | 0.347 | 0.608 | 0.870 | 1.000 | -0.026 |
| **SEASONALITY** | 0.120 | 0.078 | 0.017 | -0.026 | 1.000 |

## Cost Filter

| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |
|------|-----------------|-------------|----------------------------------|
| EWMAC_8_32 | 12.7 | 0.0102 | — |
| EWMAC_16_64 | 9.8 | 0.0133 | — |
| EWMAC_32_128 | 8.3 | 0.0157 | — |
| EWMAC_64_256 | 7.7 | 0.0169 | — |
| SEASONALITY | 10.6 | 0.0123 | — |

## Forecast Weights Template

| Rule | Weight |
|------|--------|
| EWMAC_8_32 | 0.125000 |
| EWMAC_16_64 | 0.125000 |
| EWMAC_32_128 | 0.125000 |
| EWMAC_64_256 | 0.125000 |
| SEASONALITY | 0.500000 |
