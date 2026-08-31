# Step 3 Rule Calibration Report

## Scalars

| Rule | Raw MAF | Scalar |
|------|---------|--------|
| EWMAC_4_16 | 1.002 | 9.98 |
| EWMAC_8_32 | 1.522 | 6.57 |
| EWMAC_16_64 | 2.337 | 4.28 |
| EWMAC_32_128 | 3.589 | 2.79 |
| EWMAC_64_256 | 5.187 | 1.93 |
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
| SEASONALITY_Sugar | 22.355 | 0.45 |
| SEASONALITY_Corn | 28.239 | 0.35 |
| SEASONALITY_Cotton | 27.923 | 0.36 |
| SEASONALITY_Soybeans | 17.916 | 0.56 |
| SEASONALITY_Wheat | 25.440 | 0.39 |

## Correlation Matrix

| | EWMAC_4_16 | EWMAC_8_32 | EWMAC_16_64 | EWMAC_32_128 | EWMAC_64_256 | SEASONALITY |
|---|---:|---:|---:|---:|---:|---:|
| **EWMAC_4_16** | 1.000 | 0.865 | 0.575 | 0.325 | 0.171 | 0.132 |
| **EWMAC_8_32** | 0.865 | 1.000 | 0.863 | 0.588 | 0.337 | 0.130 |
| **EWMAC_16_64** | 0.575 | 0.863 | 1.000 | 0.874 | 0.598 | 0.092 |
| **EWMAC_32_128** | 0.325 | 0.588 | 0.874 | 1.000 | 0.866 | 0.028 |
| **EWMAC_64_256** | 0.171 | 0.337 | 0.598 | 0.866 | 1.000 | -0.024 |
| **SEASONALITY** | 0.132 | 0.130 | 0.092 | 0.028 | -0.024 | 1.000 |

## Cost Filter

| Rule | Turnover (rt/yr) | Max Std Cost | Potentially Expensive Instruments |
|------|-----------------|-------------|----------------------------------|
| EWMAC_4_16 | 24.5 | 0.0053 | — |
| EWMAC_8_32 | 13.2 | 0.0099 | — |
| EWMAC_16_64 | 9.9 | 0.0132 | — |
| EWMAC_32_128 | 8.3 | 0.0157 | — |
| EWMAC_64_256 | 7.6 | 0.0170 | — |
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
