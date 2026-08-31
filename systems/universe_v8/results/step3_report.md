# Step 3 Rule Calibration Report

## Scalars

| Rule | Raw MAF | Scalar |
|------|---------|--------|
| EWMAC_4_16 | 0.956 | 10.46 |
| EWMAC_8_32 | 1.474 | 6.78 |
| EWMAC_16_64 | 2.301 | 4.35 |
| EWMAC_32_128 | 3.583 | 2.79 |
| EWMAC_64_256 | 5.152 | 1.94 |
| BREAKOUT_20 | 0.892 | 11.21 |
| SEASONALITY_XAU | 21.626 | 0.46 |
| SEASONALITY_XAG | 20.914 | 0.48 |
| SEASONALITY_COPPER | 20.082 | 0.50 |
| SEASONALITY_SpotCrude | 25.456 | 0.39 |
| SEASONALITY_Coffee | 32.143 | 0.31 |
| SEASONALITY_Cocoa | 16.544 | 0.60 |
| SEASONALITY_Sugar | 22.335 | 0.45 |
| SEASONALITY_Corn | 28.556 | 0.35 |
| SEASONALITY_Cotton | 27.647 | 0.36 |
| SEASONALITY_Soybeans | 17.882 | 0.56 |
| SEASONALITY_Wheat | 25.969 | 0.39 |

## Correlation Matrix

| | EWMAC_4_16 | EWMAC_8_32 | EWMAC_16_64 | EWMAC_32_128 | EWMAC_64_256 | BREAKOUT_20 | SEASONALITY |
|---|---:|---:|---:|---:|---:|---:|---:|
| **EWMAC_4_16** | 1.000 | 0.858 | 0.555 | 0.307 | 0.157 | 0.884 | 0.116 |
| **EWMAC_8_32** | 0.858 | 1.000 | 0.855 | 0.578 | 0.327 | 0.724 | 0.103 |
| **EWMAC_16_64** | 0.555 | 0.855 | 1.000 | 0.873 | 0.594 | 0.445 | 0.059 |
| **EWMAC_32_128** | 0.307 | 0.578 | 0.873 | 1.000 | 0.861 | 0.238 | 0.007 |
| **EWMAC_64_256** | 0.157 | 0.327 | 0.594 | 0.861 | 1.000 | 0.121 | -0.029 |
| **BREAKOUT_20** | 0.884 | 0.724 | 0.445 | 0.238 | 0.121 | 1.000 | 0.118 |
| **SEASONALITY** | 0.116 | 0.103 | 0.059 | 0.007 | -0.029 | 0.118 | 1.000 |

## Cost Filter

| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |
|------|-----------------|-------------|----------------------------------|
| EWMAC_4_16 | 22.6 | 0.0058 | XAG, Cocoa |
| EWMAC_8_32 | 11.7 | 0.0111 | — |
| EWMAC_16_64 | 9.8 | 0.0132 | — |
| EWMAC_32_128 | 8.8 | 0.0148 | — |
| EWMAC_64_256 | 8.2 | 0.0159 | — |
| BREAKOUT_20 | 39.6 | 0.0033 | XAU, XAG, Cocoa |
| SEASONALITY | 11.4 | 0.0114 | — |

## Forecast Weights Template

| Rule | Weight |
|------|--------|
| EWMAC_4_16 | 0.066667 |
| EWMAC_8_32 | 0.066667 |
| EWMAC_16_64 | 0.066667 |
| EWMAC_32_128 | 0.066667 |
| EWMAC_64_256 | 0.066667 |
| BREAKOUT_20 | 0.333333 |
| SEASONALITY | 0.333332 |
