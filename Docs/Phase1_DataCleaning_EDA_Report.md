# OULAD Phase-1: Data Cleaning & Exploratory Data Analysis Report

**Project:** Student Learning Analytics & Dropout Prediction  
**Dataset:** Open University Learning Analytics Dataset (OULAD)  
**Phase:** 1 — Data Understanding, Cleaning & EDA  
**Notebook:** `notebooks/oulad_phase1_eda.ipynb`  
**Date:** February 2026  

---

## 1. Dataset Overview

| Table | Rows | Columns | Description |
|---|---|---|---|
| `studentInfo` | 32,593 | 12 | Core table — demographics + final outcome per enrollment |
| `studentRegistration` | 32,593 | 5 | Registration & unregistration dates per enrollment |
| `assessments` | 206 | 6 | Assessment metadata: type, weight, due date |
| `studentAssessment` | 173,912 | 5 | Student submission scores |
| `vle` | 6,364 | 6 | Virtual Learning Environment resource metadata |
| `studentVle` | 8,459,320 | 6 | Raw click-event logs (largest table — 453 MB) |
| `courses` | 22 | 3 | Module presentation lengths (7 modules, 22 offerings) |

**Total records:** ~8.7 million across all tables.

---

## 2. Strategic Data Cleaning Decisions

### 2.1 Missing Values

| Field | Table | Missing % | Decision | Rationale |
|---|---|---|---|---|
| `imdBand` | studentInfo | 3.41% | Fill → `'Unknown'` | Likely admin gap (not MCAR). Preserve rows; `Unknown` treated as a valid category in EDA. |
| `dateRegistration` | studentRegistration | 0.14% | Fill → median (−69 days) | Trivially small gap. Median is robust to the skewed registration distribution. |
| `dateUnregistration` | studentRegistration | 69% | Keep as `NaN` | **Null is meaningful** — it indicates the student did NOT unregister (still enrolled). Not a missing value problem. |
| `assessments.date` | assessments | 5.3% | Fill → module-level median | Date is only used to compute relative submission timing. Module-level imputation preserves temporal context. |
| `studentAssessment.score` | studentAssessment | 0.1% | Drop rows (173 rows) | Score is the dependent variable for assessment analysis. Imputation would introduce bias. |
| `vle.weekFrom / weekTo` | vle | 82% | Keep as-is | These columns are not used in Phase-1 EDA. |

### 2.2 Duplicates
- **No duplicate rows** found in any table.
- Key uniqueness constraints verified: `idStudent × codeModule × codePresentation` is unique in `studentInfo`.

### 2.3 Outliers
- `studentAssessment.score`: Scores range 0–100 by design. Values at 0 and 100 are legitimate (perfect fail / perfect score). **Retained.**
- `studiedCredits`: 655 is an extreme high value. Retained — some students genuinely register for many credits.
- `studentVle.sumClick`: Values up to 6,977 clicks in a single day are extreme but **retained**; they reflect genuine heavy usage sessions.
- `dateRegistration`: Values as low as −322 (10+ months early) are plausible for early-enrolled students. **Retained.**

### 2.4 Engineered Columns Added During Cleaning
| Column | Source | Description |
|---|---|---|
| `outcome_binary` | `finalResult` | `Success` (Pass/Distinction) vs `Failure` (Fail/Withdrawn) |
| `is_dropout` | `finalResult` | Binary: 1 = Withdrawn |
| `is_success` | `finalResult` | Binary: 1 = Pass or Distinction |
| `reg_timing` | `dateRegistration` | Binned: Very Early / >30d Before / 0-30d Before / After Start |

---

## 3. Key EDA Findings

### 3.1 Overall Outcome Distribution

| Outcome | Count | % |
|---|---|---|
| Pass | 12,361 | 37.9% |
| Withdrawn | 10,156 | 31.2% |
| Fail | 7,052 | 21.6% |
| Distinction | 3,024 | 9.3% |

- **31.2% dropout rate** is the central challenge for this project.
- Only **47.2% of enrollments result in Pass or Distinction** (success).

---

### 3.2 Demographics & Dropout Risk

#### Gender
- Male students: **33% dropout rate** vs Female: **29%**
- Chi-square test: **significant (p < 0.001)**

#### Age Band
- `0-35`: 30% dropout | `35-55`: 34% dropout | `55<=`: 28% dropout
- Older working-age students (35-55) are at **highest risk**

#### Education Level
- Students with **No Formal Qualifications** have ~42% dropout rate
- **Post Graduate** students have ~20% dropout rate
- Strong monotonic trend: lower education → higher dropout

#### IMD Band (Socioeconomic Deprivation Index)
- **Most deprived (0-10%)**: ~37% dropout, ~40% success rate
- **Least deprived (90-100%)**: ~24% dropout, ~55% success rate
- IMD Band is one of the **strongest demographic predictors** of outcome
- All chi-square tests: **p < 0.001**

#### Disability
- Students with disability: **32% dropout** vs without: **31%**
- Marginally significant — disability alone is a weak predictor

#### Previous Attempts
- First-time students: **29% dropout**
- 1 prior attempt: **41% dropout**
- 2+ prior attempts: **55%+ dropout**
- **Previous attempts is the strongest single demographic predictor of dropout**

#### Studied Credits
- Students with higher credit loads trend toward more withdrawals
- Median credits: Distinction (60) < Pass (60) < Fail (120) < Withdrawn (120)

---

### 3.3 Course & Module Analysis

- **7 modules** (AAA–GGG) across **22 presentation offerings**
- Module-level dropout rates vary significantly (range: ~20% to ~45%)
- Some modules show consistently high failure rates across all presentations → suggest **inherent difficulty or poor support structures**
- Module × Presentation heatmap reveals specific high-risk cohorts

---

### 3.4 Registration & Withdrawal Timing

#### Registration
- **72% of students register more than 30 days before course start** (median: −69 days)
- Late registrants (after day 0): **highest dropout rate (~45%)**
- Very early registrants (>100 days early): **lowest dropout rate (~26%)**
- **Finding: Registration timing is a proxy for motivation and preparedness**

#### Withdrawal Timing
- **25% of withdrawals happen before day −2** (before course even starts)
- **50% of withdrawals happen by day 27** (end of Week 4)
- **75% of withdrawals happen by day 109** (Week 16)
- Critical risk windows:
  - **Pre-course** (day < 0): Administrative withdrawals
  - **Weeks 1–4** (day 0–30): Early disengagement
  - **Weeks 5–13** (day 30–90): Assessment-triggered dropout

---

### 3.5 Assessment Performance

| Outcome | Mean Score | Median | Std Dev |
|---|---|---|---|
| Distinction | 88.7 | 91.0 | 11.4 |
| Pass | 76.8 | 79.0 | 16.5 |
| Fail | 64.7 | 66.0 | 21.4 |
| Withdrawn | 66.1 | 70.0 | 23.2 |

- **Score KDE** shows clearly separated distributions: Distinction peaks at ~90, Withdrawn has a bimodal distribution (some never-submitted + some decent scores who still withdrew)
- **Assessment types**: TMA (Tutor Marked Assignments) most common; Exams carry highest weight
- **Submission timing**: Distinction students submit **earliest** (most negative delay); Withdrawn students submit latest
- **Late submission rate**: Withdrawn students have ~3× higher late submission rate than Distinction students

---

### 3.6 VLE Engagement

| Outcome | Mean Total Clicks | Mean Active Days |
|---|---|---|
| Distinction | ~3,500 | ~85 |
| Pass | ~1,800 | ~65 |
| Fail | ~900 | ~38 |
| Withdrawn | ~700 | ~28 |

- **Distinction students click 5× more than Withdrawn students**
- **Most-used activity types**: Resources (content files), Subpages, OUcontent, URLs
- **Forum participation** (`forumng`) is disproportionately high for Distinction students → collaborative engagement predicts success
- **Engagement timeline**: All outcome groups peak around Weeks 4–8; Withdrawn students show a sharp cliff at their withdrawal point

#### Early Engagement (First Week) — Critical Predictor
- Students with **zero first-week VLE activity**:
  - Withdrawn: ~55% had zero first-week clicks
  - Fail: ~40%
  - Pass: ~18%
  - Distinction: ~8%
- **First-week engagement is the single strongest early warning signal for dropout**

---

### 3.7 Correlation Analysis (Spearman ρ vs is_dropout)

| Feature | ρ with Dropout | Direction |
|---|---|---|
| total_clicks | −0.38 | More clicks → less dropout |
| active_days | −0.35 | More active days → less dropout |
| first_week_clicks | −0.32 | More early engagement → less dropout |
| avg_score | −0.41 | Higher scores → less dropout |
| activity_span | −0.34 | Longer engagement → less dropout |
| numOfPrevAttempts | +0.18 | More attempts → more dropout |
| studiedCredits | +0.12 | Higher load → more dropout |
| dateRegistration | +0.15 | Later registration → more dropout |

---

### 3.8 Statistical Validation

All categorical predictors are **statistically significant** (chi-square, p < 0.001):
- gender, ageBand, highestEducation, imdBand, region, disability, numOfPrevAttempts

All continuous predictors are **statistically significant** (Mann-Whitney U, p < 0.001):
- total_clicks, active_days, first_week_clicks, avg_score, activity_span, dateRegistration

---

## 4. Figures Produced (saved to `notebooks/processed/`)

| File | Section | Description |
|---|---|---|
| `fig_missing_values.png` | Section 2 | Missing % bar charts across all tables |
| `fig_demographics_overview.png` | Section 4 | 6-panel demographic distribution |
| `fig_outcome_by_demographics.png` | Section 4 | Normalised stacked bars by all demographics |
| `fig_imd_analysis.png` | Section 4 | IMD band dropout/success rates + composition |
| `fig_region_analysis.png` | Section 4 | Regional enrollment + diverging outcome chart |
| `fig_attempts_credits_disability.png` | Section 4 | Violin + line charts for key numeric demographics |
| `fig_module_analysis.png` | Section 5 | Module enrollment, dropout rates, outcome heatmap |
| `fig_outcome_deepdive.png` | Section 6 | Donut, presentation-level bars, module×presentation heatmap |
| `fig_registration_analysis.png` | Section 7 | Registration timing histograms and outcome rates |
| `fig_withdrawal_analysis.png` | Section 7 | Withdrawal timing distribution and risk windows |
| `fig_score_distributions.png` | Section 8 | KDE, boxplot, mean±SD by outcome |
| `fig_assessment_timing.png` | Section 8 | Violin by type, submission delay, late rate |
| `fig_vle_activity.png` | Section 9 | Activity type click totals and share |
| `fig_engagement_by_outcome.png` | Section 9 | Boxplots (log scale) for clicks/days/span |
| `fig_engagement_timeline.png` | Section 9 | Daily click timeline by outcome group |
| `fig_early_engagement.png` | Section 9 | First-week KDE, boxplot, non-starter rates |
| `fig_correlation_heatmap.png` | Section 10 | Spearman correlation matrix |
| `fig_imd_education_heatmap.png` | Section 10 | IMD × Education dropout/success/count heatmaps |

---

## 5. Cleaned Data Outputs (saved to `notebooks/processed/`)

| File | Description |
|---|---|
| `student_master_cleaned.csv` | Main cleaned student table with all demographic + registration + outcome fields |
| `studentAssessment_cleaned.csv` | Assessment submissions (score NAs dropped) |
| `assessments_cleaned.csv` | Assessment metadata (date NAs filled) |
| `student_vle_aggregated.csv` | Per-student VLE totals (total_clicks, active_days, first/last day) |
| `student_vle_first_week.csv` | Per-student first-week VLE engagement (days 0–7) |
| `assessment_scores_merged.csv` | Assessment scores merged with outcome and assessment metadata |

---

## 6. Future Phases

### Phase 2 — Feature Engineering & Dropout Prediction
**Inputs:** Cleaned datasets from Phase-1  
**Key features to engineer:**
- Engagement trajectory features (weekly click bins)
- Assessment cumulative performance (running average, trend)
- Risk score composites (IMD + prev_attempts + early_engagement)
- Time-to-event features for survival modelling

**Models to evaluate:** Logistic Regression, Random Forest, XGBoost, LightGBM, Survival Analysis (Cox PH)  
**Target:** Binary dropout prediction (`is_dropout`) + multi-class (`finalResult`)

---

### Phase 3 — Time-Series Forecasting of Learning Behaviour
**Goal:** Predict week-by-week engagement trajectory and flag students at risk before critical dropout windows  
**Approach:**
- Weekly VLE click aggregations as time-series per student
- LSTM / Temporal CNN for sequence modelling
- Early-warning trigger at Week 3–4 (before 50% of withdrawals occur)
- Potential: predict withdrawal date (survival regression)

---

### Phase 4 — Interactive Dashboard
**Goal:** Operational dashboard for module coordinators and student advisors  
**Recommended stack:** Streamlit (Python) or Power BI  
**Key views:**
- At-risk student list (updated weekly)
- Module-level dropout heat map
- Individual student engagement timeline
- Cohort comparison by IMD / education / module
