# Step 3 Rule Calibration Report

## Scalars

| Rule | Raw MAF | Scalar |
|------|---------|--------|
| EWMAC_4_16 | 1.001 | 9.99 |
| EWMAC_8_32 | 1.520 | 6.58 |
| EWMAC_16_64 | 2.328 | 4.29 |
| EWMAC_32_128 | 3.564 | 2.81 |
| EWMAC_64_256 | 5.145 | 1.94 |
| SEASONALITY_US500 | 19.926 | 0.50 |
| SEASONALITY_GER40 | 17.369 | 0.58 |
| SEASONALITY_JPN225 | 20.467 | 0.49 |
| SEASONALITY_HK50 | 21.606 | 0.46 |
| SEASONALITY_US10YR | 20.832 | 0.48 |
| SEASONALITY_BUND | 20.799 | 0.48 |
| SEASONALITY_XAU | 21.475 | 0.47 |
| SEASONALITY_COPPER | 20.103 | 0.50 |
| SEASONALITY_SpotCrude | 25.403 | 0.39 |
| SEASONALITY_Gasoline | 31.893 | 0.31 |
| SEASONALITY_Coffee | 33.766 | 0.30 |
| SEASONALITY_Cocoa | 16.869 | 0.59 |
| SEASONALITY_Sugar | 22.355 | 0.45 |
| SEASONALITY_Corn | 28.239 | 0.35 |
| SEASONALITY_Cotton | 27.923 | 0.36 |
| SEASONALITY_Soybeans | 17.916 | 0.56 |
| SEASONALITY_Wheat | 25.440 | 0.39 |

## Correlation Matrix

| | EWMAC_4_16 | EWMAC_8_32 | EWMAC_16_64 | EWMAC_32_128 | EWMAC_64_256 | SEASONALITY |
|---|---:|---:|---:|---:|---:|---:|
| **EWMAC_4_16** | 1.000 | 0.864 | 0.573 | 0.324 | 0.169 | 0.128 |
| **EWMAC_8_32** | 0.864 | 1.000 | 0.862 | 0.589 | 0.336 | 0.125 |
| **EWMAC_16_64** | 0.573 | 0.862 | 1.000 | 0.874 | 0.596 | 0.087 |
| **EWMAC_32_128** | 0.324 | 0.589 | 0.874 | 1.000 | 0.864 | 0.026 |
| **EWMAC_64_256** | 0.169 | 0.336 | 0.596 | 0.864 | 1.000 | -0.023 |
| **SEASONALITY** | 0.128 | 0.125 | 0.087 | 0.026 | -0.023 | 1.000 |

## Cost Filter

| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |
|------|-----------------|-------------|----------------------------------|
| EWMAC_4_16 | 24.3 | 0.0053 | Cocoa |
| EWMAC_8_32 | 13.0 | 0.0100 | Cocoa |
| EWMAC_16_64 | 9.9 | 0.0132 | — |
| EWMAC_32_128 | 8.3 | 0.0156 | — |
| EWMAC_64_256 | 7.7 | 0.0169 | — |
| SEASONALITY | 10.7 | 0.0122 | — |

## Forecast Weights Template

| Rule | Weight |
|------|--------|
| EWMAC_4_16 | 0.100000 |
| EWMAC_8_32 | 0.100000 |
| EWMAC_16_64 | 0.100000 |
| EWMAC_32_128 | 0.100000 |
| EWMAC_64_256 | 0.100000 |
| SEASONALITY | 0.500000 |
