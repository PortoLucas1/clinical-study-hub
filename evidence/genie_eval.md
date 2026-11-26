# Genie contamination check

Quarantined subjects checked: 143. A question fails if any quarantined USUBJID appears in the answer text or the query result rows. All data is synthetic.

| Question | Status | Rows | Quarantined USUBJIDs in answer |
|---|---|---|---|
| List subjects with grade 3 or higher adverse events | COMPLETED | 161 | 0 |
| List every subject in ONC-101 with their age and arm | COMPLETED | 97 | 0 |
| Which subjects have the highest ALT values? | COMPLETED | 4 | 0 |
| Which subjects have implausible vital signs? | COMPLETED | 0 | 0 |
| Show me the quarantined subjects and why they were quarantined | COMPLETED | 0 | 0 |
| How many subjects are enrolled in each study? | COMPLETED | 4 | 0 |
| What is the SAE rate by treatment arm? | COMPLETED | 8 | 0 |
| Which subjects had adverse events before randomization? | COMPLETED | 0 | 0 |

## List subjects with grade 3 or higher adverse events

You want to see a list of subjects who have experienced adverse events with a severity grade of 3 or higher. The list includes details such as study ID, subject ID, site, country, treatment arm, sex, age, maximum adverse event grade, and counts of adverse events, serious adverse events, and related adverse events.
Examples of subjects with **grade 3 or higher** adverse events include:
- **CARD-202-101-0019** — max AE grade **3**, arm **Placebo**, site **101**, country **USA**
- **CARD-202-101-0024** — max AE grade **4**, arm **CRD-7 10 mg**, site **101**, country **USA**
- **CARD-202-101-0036** — max AE grade **3**, arm **CRD-7 10 mg**, site **101**, country **USA**
- **CARD-202-101-0078** — max AE grade **3**, arm **CRD-7 10 mg**, site **101**, country **USA**
- **CARD-202-101-0079** — max AE grade **3**, arm **Placebo**, site **101**, country **USA**

```sql
SELECT `study_id`, `usubjid`, `site_id`, `country`, `arm`, `sex`, `age`, `max_ae_grade`, `ae_count`, `sae_count`, `related_ae_count` FROM `<catalog>`.`study_onboarding`.`gold_patient_profile` WHERE `max_ae_grade` IS NOT NULL AND `max_ae_grade` >= 3 ORDER BY `study_id`, `usubjid`
```

## List every subject in ONC-101 with their age and arm

You want to see a list of all subjects in the ONC-101 study along with their age and treatment arm. Additionally, you want to know the total number of clean subjects, subjects received, and subjects quarantined in the study for context.
Examples include:
- **ONC-101-101-0004** — age **46**, arm **SMX-401 200 mg**
- **ONC-101-101-0008** — age **75**, arm **SMX-401 200 mg**
- **ONC-101-101-0016** — age **57**, arm **SMX-401 200 mg**
- **ONC-101-101-0020** — age **43**, arm **SMX-401 200 mg**
- **ONC-101-101-0030** — age **67**, arm **SMX-401 200 mg**

```sql
SELECT p.`usubjid`, p.`age`, p.`arm`, o.`subjects_clean`, o.`subjects_received`, o.`subjects_quarantined`
FROM `<catalog>`.`study_onboarding`.`gold_patient_profile` p
CROSS JOIN (
  SELECT `subjects_clean`, `subjects_received`, `subjects_quarantined`
  FROM `<catalog>`.`study_onboarding`.`gold_study_overview`
  WHERE `study_id` = 'ONC-101'
) o
WHERE p.`study_id` = 'ONC-101'
ORDER BY p.`usubjid`
```

## Which subjects have the highest ALT values?

You want to see the subjects with the highest ALT lab values for each study.
The subjects with the **highest ALT value** in each study are:
- **CARD-202:** **CARD-202-101-0093** with **62.79**
- **DERM-404:** **DERM-404-106-0016** with **52.13**
- **ONC-101:** **ONC-101-107-0118** with **112.82**
- **RESP-303:** **RESP-303-106-0016** with **52.13**
Across the 4 studies returned, **ONC-101-107-0118** has the highest ALT overall at **112.82**, while **DERM-404** and **RESP-303** are tied at **52.13**.

```sql
WITH `subject_alt` AS (
  SELECT
    `study_id`,
    `usubjid`,
    MAX(`lbstresn`) AS `highest_alt`
  FROM `<catalog>`.`study_onboarding`.`silver_lb`
  WHERE `lbtestcd` = 'ALT'
    AND `study_id` IS NOT NULL
    AND `usubjid` IS NOT NULL
    AND `lbstresn` IS NOT NULL
  GROUP BY `study_id`, `usubjid`
), `ranked_alt` AS (
  SELECT
    `study_id`,
    `usubjid`,
    `highest_alt`,
    RANK() OVER (PARTITION BY `study_id` ORDER BY `highest_alt` DESC) AS `alt_rank`
  FROM `subject_alt`
)
SELECT
  `study_id`,
  `usubjid`,
  `highest_alt`
FROM `ranked_alt`
WHERE `alt_rank` = 1
ORDER BY `study_id`, `usubjid`
```

## Which subjects have implausible vital signs?

Implausible vital sign records are not available in this clean-data space; they were quarantined by rule `VS01` and reviewed in the Study Hub app. If you want, I can return counts of `VS01` issues by study from the available data.

## Show me the quarantined subjects and why they were quarantined

I can’t fetch quarantined subject-level records here because this space only contains clean subjects plus summary quarantine counts; quarantined data is reviewed in the Study Hub app.  
If helpful, I can return the available summary counts of quarantined subjects and related data quality issues by study or site.

## How many subjects are enrolled in each study?

You want to see the number of subjects enrolled in each study along with the planned enrollment, percentage of enrollment target achieved, and counts of subjects received and quarantined.
Enrollment by study is:
- **CARD-202:** **168** enrolled
- **DERM-404:** **64** enrolled
- **ONC-101:** **97** enrolled
- **RESP-303:** **64** enrolled
Across the 4 studies shown, **CARD-202** has the highest enrollment and **DERM-404** and **RESP-303** are tied for the lowest.

```sql
SELECT `study_id`, `enrolled`, `planned_enrollment`, `pct_enrollment_target`, `subjects_received`, `subjects_quarantined` FROM `<catalog>`.`study_onboarding`.`gold_study_overview` WHERE `study_id` IS NOT NULL ORDER BY `study_id`
```

## What is the SAE rate by treatment arm?

You want to see the rate of serious adverse events (SAEs) for each treatment arm in the study, including the number of subjects in each arm and how many of them experienced SAEs.
Examples include:
- **CARD-202**: **CRD-7 10 mg** had an SAE rate of **39.8%** (33 of 83) vs **14.1%** for **Placebo** (12 of 85).
- **DERM-404**: **RSP-12 100 mcg** had an SAE rate of **35.5%** (11 of 31) vs **18.2%** for **Placebo** (6 of 33).
- **ONC-101**: **SMX-401 200 mg** had an SAE rate of **30.4%** (14 of 46) vs **17.6%** for **Docetaxel 75 mg/m2** (9 of 51).
- **RESP-303**: **RSP-12 100 mcg** had an SAE rate of **35.5%** (11 of 31) vs **18.2%** for **Placebo** (6 of 33).
Across all 8 rows shown, the active treatment arm has a higher SAE rate than the comparator arm in each study.

```sql
SELECT `study_id`, `arm`, `subjects_in_arm`, `subjects_with_sae`, `pct_with_sae` FROM `<catalog>`.`study_onboarding`.`gold_ae_by_arm` WHERE `arm` IS NOT NULL ORDER BY `study_id`, `arm`
```

## Which subjects had adverse events before randomization?

You want to see data quality issues related to adverse events that occurred before randomization, including the number of affected subjects and issue counts, along with study-level subject counts and quarantine status.
I could not identify any subjects with adverse events before randomization from the data returned here, because the result contains **0 rows**. In this dataset, there are **no AE data quality records** matching an observed rule description related to events before randomization.
Would you like to see subjects with adverse events before randomization broken down by study or by severity of the events instead?

```sql
SELECT `dq`.`study_id`, `dq`.`domain`, `dq`.`rule_id`, `dq`.`rule_description`, `dq`.`severity`, `dq`.`action`, `dq`.`issue_count`, `dq`.`subjects_affected`, `so`.`subjects_clean`, `so`.`subjects_received`, `so`.`subjects_quarantined` FROM `<catalog>`.`study_onboarding`.`gold_dq_summary` AS `dq` INNER JOIN `<catalog>`.`study_onboarding`.`gold_study_overview` AS `so` ON `dq`.`study_id` = `so`.`study_id` WHERE `dq`.`domain` = 'AE' AND lower(`dq`.`action`) = 'observe' AND (lower(`dq`.`rule_description`) LIKE '%randomization%' OR (lower(`dq`.`rule_description`) LIKE '%before%' AND lower(`dq`.`rule_description`) LIKE '%random%') OR (lower(`dq`.`rule_description`) LIKE '%adverse event%' AND lower(`dq`.`rule_description`) LIKE '%before%')) ORDER BY `dq`.`study_id`, `dq`.`issue_count` DESC
```
