# GOA evaluation (live)

20 frozen briefs (`eval/briefs.json`, sha256 `c974ef17d239e209`), rules evaluated as of 2026-10-18.

**Live run:** every brief text was parsed by Gemma-4-31B-IT on AMD Token Factory (20 live calls, 0 from cache).

| Measure | GOA | Keyword search |
| --- | --- | --- |
| Valid composition rate (every part filled, every rule passes, within budget) | 55% | 30% |
| Grounding (first item shown per part exists and passes stock, size and delivery) | 100% | 82% |
| Parts filled with a verified item | 83% | 93% |
| Briefs that reach a sendable enquiry | 80% | 35% |
| Median steps to a sendable enquiry | 3 | 8 |
| Unmet parts captured as demand | 12 | 0 |

## How steps are counted

- GOA: describe (1), enter sizes if the text does not state them (1), send (1).
- Keyword search: one search per part, one step per product opened to check size, stock and delivery, one message per merchant.

## Per brief

| Brief | Market, scope | GOA | Baseline | GOA gaps |
| --- | --- | --- | --- | --- |
| b01 | ZA, local | 3/3 parts, within, 3 steps | 3/3 parts, near, 7 steps | - |
| b02 | ZA, local | 3/3 parts, within, 3 steps | 3/3 parts, within, 8 steps | - |
| b03 | ZA, global | 3/3 parts, within, 3 steps | 3/3 parts, over, not sendable | - |
| b04 | ZA, local | 4/4 parts, within, 3 steps | 3/4 parts, over, not sendable | - |
| b05 | ZA, region | 4/4 parts, within, 3 steps | 4/4 parts, within, 11 steps | - |
| b06 | ZA, global | 2/3 parts, within, 2 steps | 2/3 parts, over, not sendable | garment: out_of_stock_in_size |
| b07 | NG, local | 1/3 parts, within, 3 steps | 3/3 parts, within, 8 steps | garment: out_of_stock_in_size; shoes: no_match |
| b08 | NG, region | 3/3 parts, within, 3 steps | 3/3 parts, over, not sendable | - |
| b09 | NG, global | 3/4 parts, within, 3 steps | 4/4 parts, over, not sendable | outer_layer: no_match |
| b10 | US, local | 3/4 parts, within, 3 steps | 4/4 parts, over, not sendable | garment: out_of_stock_in_size |
| b11 | US, global | 4/4 parts, within, 3 steps | 4/4 parts, over, not sendable | - |
| b12 | US, global | 0/3 parts, within, not sendable | 0/3 parts, within, not sendable | garment: too_slow; shoes: too_slow; accessory: too_slow |
| b13 | GB, local | 3/4 parts, over, not sendable | 4/4 parts, over, not sendable | accessory: no_match |
| b14 | GB, region | 4/5 parts, over, not sendable | 5/5 parts, over, not sendable | accessory: no_match |
| b15 | GB, global | 4/4 parts, within, 3 steps | 4/4 parts, within, 11 steps | - |
| b16 | EU, local | 3/3 parts, over, not sendable | 3/3 parts, over, not sendable | - |
| b17 | EU, global | 4/4 parts, within, 3 steps | 4/4 parts, over, not sendable | - |
| b18 | CN, local | 2/4 parts, within, 3 steps | 4/4 parts, over, not sendable | garment: out_of_stock_in_size; accessory: no_match |
| b19 | CN, region | 3/3 parts, within, 3 steps | 3/3 parts, within, 7 steps | - |
| b20 | CN, global | 4/4 parts, within, 3 steps | 4/4 parts, within, 11 steps | - |

## Gaps captured

out_of_stock_in_size: 4, no_match: 5, too_slow: 3

Manual check: open `eval/blind/` for the fit rating sheet (systems hidden, order shuffled).

No revenue, conversion or retention claims: those need real users.
