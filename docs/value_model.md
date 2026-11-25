# Value model (estimates)

All figures are **estimates built from stated assumptions**, for a fictional customer (Helix Clinical Research).
They are not measurements. Replace each assumption with the customer's own numbers before using them in a business case.

## Assumptions

| Input | Value | Basis |
|---|---|---|
| Studies onboarded per year | 40 | Customer portfolio size (assumed) |
| Manual harmonization effort per study today | 60 hours | Mapping vendor columns, checking rules, writing the status summary (assumed) |
| Effort per study with the Study Hub | 6 hours | Review of AI-proposed findings plus approval (assumed) |
| Loaded cost per data-management hour | $95 | Assumed blended rate |
| Time from package receipt to first data review, today | about 3 weeks | Assumed |
| Time from package receipt to first data review, with the Study Hub | under 1 day | Approval plus the job run (target) |
| Value of one day earlier first data review | $4,000 per study | Earlier detection of issues and faster start of monitoring (assumed) |

## Outputs

| Outcome | Calculation | Estimate |
|---|---|---|
| Data-management hours saved per year | 40 studies x (60 - 6) h | 2,160 h |
| Labour cost avoided per year | 2,160 h x $95 | about $205k |
| Days earlier first data review per study | about 21 days minus 1 day | about 20 days |
| Value of earlier first review per year (upper bound) | 40 studies x 20 days x $4,000 per day | about $3.2M |

Note: the timing line is an upper bound that shows the scale of the benefit, not a forecast. A conservative case counts
only the labour saving and a small share of the timing value.

## KPIs to track in the pilot

- Hours from approval to published portfolio (target: under 2 hours of job time, and under 1 day end to end).
- Share of high-severity data quality issues caught before the first data review.
- Number of analyst questions answered by Genie without a ticket to the data team.
- Share of AI-generated findings the reviewer accepts without edits.
