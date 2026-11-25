# Genie QA: Study Insights space

Five questions asked of the **Study Insights** Genie space (`01f1e8f14e48158f971d172374654eba`) against the Gold tables after the RESP-303 onboarding run. Answers and SQL are recorded as Genie returned them on the live workspace (Genie Conversations API, run 2026-11-25). The Gold tables are synthetic demo data.

All five answers were checked by hand against the table exports in [`query_results/`](query_results/). The numbers match in every case.


## 1. How many studies are in the portfolio and what is the phase of each?

**Genie status:** COMPLETED

**Answer**

There are **3 studies** in the portfolio. The phases are:
- **CARD-202** — **Phase 3**
- **ONC-101** — **Phase 2**
- **RESP-303** — **Phase 2**

Across these 3 studies, **Phase 2** is the most common phase, appearing in **2 of 3** studies.

**SQL**

```sql
SELECT COUNT(*) OVER () AS `portfolio_study_count`, `study_id`, `phase`
FROM `<catalog>`.`study_onboarding`.`gold_study_overview`
WHERE `study_id` IS NOT NULL
  AND `phase` IS NOT NULL
ORDER BY `study_id`
```

**Result**

| portfolio_study_count | study_id | phase |
|---|---|---|
| 3 | CARD-202 | Phase 3 |
| 3 | ONC-101 | Phase 2 |
| 3 | RESP-303 | Phase 2 |


## 2. What is the enrollment percentage of each study against its planned enrollment?

**Genie status:** COMPLETED

**Answer**

Enrollment is at **78.7%** of plan for **CARD-202** (236 of 300), **82.7%** for **ONC-101** (124 of 150), and **73.3%** for **RESP-303** (88 of 120). Across the 3 studies shown, **ONC-101** is closest to plan and **RESP-303** is furthest behind.

**SQL**

```sql
SELECT `study_id`, `enrolled`, `planned_enrollment`, ROUND(try_divide(100.0 * `enrolled`,NULLIF(`planned_enrollment`, 0)), 1) AS `pct_enrollment_target` FROM `<catalog>`.`study_onboarding`.`gold_study_overview` WHERE `study_id` IS NOT NULL AND `enrolled` IS NOT NULL AND `planned_enrollment` IS NOT NULL ORDER BY `study_id`
```

**Result**

| study_id | enrolled | planned_enrollment | pct_enrollment_target |
|---|---|---|---|
| CARD-202 | 236 | 300 | 78.7 |
| ONC-101 | 124 | 150 | 82.7 |
| RESP-303 | 88 | 120 | 73.3 |


## 3. Which study has the highest serious adverse event rate per subject?

**Genie status:** COMPLETED

**Answer**

**RESP-303** has the highest serious adverse event rate per subject at **29.5%**. Based on the result shown, **RESP-303** is the top study on this measure.

**SQL**

```sql
WITH ranked_studies AS (
  SELECT
    `study_id`,
    `sae_subject_rate_pct`,
    RANK() OVER (ORDER BY `sae_subject_rate_pct` DESC, `study_id` ASC) AS `rnk`
  FROM `<catalog>`.`study_onboarding`.`gold_study_overview`
  WHERE `study_id` IS NOT NULL
    AND `sae_subject_rate_pct` IS NOT NULL
)
SELECT
  `study_id`,
  `sae_subject_rate_pct`
FROM ranked_studies
WHERE `rnk` = 1
ORDER BY `study_id`
```

**Result**

| study_id | sae_subject_rate_pct |
|---|---|
| RESP-303 | 29.5 |


## 4. How many high-severity data quality issues does each study have?

**Genie status:** COMPLETED

**Answer**

Each study’s **high-severity data quality issue** count is shown below, based on the available results.

- **CARD-202:** **46**
- **ONC-101:** **21**
- **RESP-303:** **13**

Across the 3 studies shown, **CARD-202** has the most high-severity issues and **RESP-303** has the fewest.

**SQL**

```sql
SELECT `study_id`, SUM(`issue_count`) AS `high_severity_issue_count`
FROM `<catalog>`.`study_onboarding`.`gold_dq_summary`
WHERE `severity` = 'High'
  AND `study_id` IS NOT NULL
GROUP BY `study_id`
ORDER BY `high_severity_issue_count` DESC, `study_id`
```

**Result**

| study_id | high_severity_issue_count |
|---|---|
| CARD-202 | 46 |
| ONC-101 | 21 |
| RESP-303 | 13 |


## 5. Which study sites have the lowest enrollment so far?

**Genie status:** COMPLETED

**Answer**

The lowest-enrolling sites so far are **CARD-202 site 102 (Brazil)** and **site 105 (Japan)** with **14** enrolled each, **ONC-101 site 103 (Spain)** with **11**, and **RESP-303 site 102 (France)** with **11**. Across the 4 returned rows, the lowest enrollment ranges from **11 to 14**, and **CARD-202** is the only study with a tie for the lowest-enrolling site.

**SQL**

```sql
WITH ranked_sites AS (
  SELECT
    `study_id`,
    `site_id`,
    `country`,
    `enrolled`,
    RANK() OVER (PARTITION BY `study_id` ORDER BY `enrolled` ASC) AS `enrollment_rank`
  FROM `<catalog>`.`study_onboarding`.`gold_site_performance`
  WHERE `enrolled` IS NOT NULL
    AND `site_id` IS NOT NULL
    AND `study_id` IS NOT NULL
)
SELECT
  `study_id`,
  `site_id`,
  `country`,
  `enrolled`
FROM ranked_sites
WHERE `enrollment_rank` = 1
ORDER BY `study_id`, `site_id`;
```

**Result**

| study_id | site_id | country | enrolled |
|---|---|---|---|
| CARD-202 | 102 | Brazil | 14 |
| CARD-202 | 105 | Japan | 14 |
| ONC-101 | 103 | Spain | 11 |
| RESP-303 | 102 | France | 11 |

