# Student Learning Analytics & Dropout Prediction
### Open University Learning Analytics Dataset (OULAD)

> **Goal:** Understand, predict, and ultimately reduce student dropout in online higher education using the Open University Learning Analytics Dataset — covering 32,593 student enrollments, 8.4 million VLE interaction events, and 173,912 assessment submissions across 7 modules.

---

## Project Phases

| Phase | Status | Description |
|---|---|---|
| [Phase 0](#phase-0--data-infrastructure--schema-design) | ✅ Complete | Data infrastructure & PostgreSQL schema |
| [Phase 1](#phase-1--data-cleaning--exploratory-data-analysis) | ✅ Complete | Data cleaning & professional EDA |
| [Phase 2](#phase-2--feature-engineering--dropout-prediction) | 🔜 Upcoming | Feature engineering & predictive modelling |
| [Phase 3](#phase-3--time-series-forecasting-of-learning-behaviour) | 🔜 Upcoming | Time-series forecasting of learning behaviour |
| [Phase 4](#phase-4--interactive-dashboard) | 🔜 Upcoming | Interactive dashboard for educators |

---

## Dataset

**Source:** [Open University Learning Analytics Dataset (OULAD)](https://www.nature.com/articles/sdata2017171)

| Table | Rows | Description |
|---|---|---|
| `studentInfo` | 32,593 | Student demographics & final outcome |
| `studentRegistration` | 32,593 | Registration & unregistration dates |
| `assessments` | 206 | Assessment metadata (type, weight, due date) |
| `studentAssessment` | 173,912 | Student submission scores |
| `vle` | 6,364 | Virtual Learning Environment resource metadata |
| `studentVle` | 8,459,320 | Raw VLE click-event logs |
| `courses` | 22 | Module presentation details (7 modules) |

---

## Phase 0 — Data Infrastructure & Schema Design

**Scripts:** [`scripts/etl.js`](scripts/etl.js) · [`scripts/load_student_vle.js`](scripts/load_student_vle.js)  
**ORM:** Prisma (`prisma/schema.prisma`) with PostgreSQL adapter

### What We Did
- Designed a relational schema for all 7 OULAD tables preserving foreign key relationships
- Loaded all CSV files into a **PostgreSQL** database via a Node.js ETL pipeline (`scripts/etl.js`)
- Validated referential integrity across tables (student ↔ registration ↔ assessments ↔ VLE)
- Created an Entity Relationship Diagram (ERD) documenting all table relationships

### studentVle — Chunked Load with Date-Level Aggregation
The raw `studentVle.csv` (8.4M rows, 453 MB) required special handling:
- Streamed and processed in **chunks of 10,000–50,000 rows** to avoid memory overflow
- Within each chunk, rows were **aggregated by `codeModule × codePresentation × idStudent × idSite × date`** — summing `sumClick` for any duplicate entries sharing the same student–site–day key
- Upserted into PostgreSQL with `ON CONFLICT ... DO UPDATE SET sumClick = sumClick + EXCLUDED.sumClick` to correctly accumulate clicks across chunk boundaries
- A dedicated script (`scripts/load_student_vle.js`) was written using raw SQL for performance, bypassing the Prisma ORM overhead for this high-volume table

This means the `studentVle` table in PostgreSQL stores **one row per student × VLE resource × day**, with `sumClick` representing the total clicks for that student on that resource on that day.

### Schema Highlights
- Primary keys: `idStudent × codeModule × codePresentation` (composite) for student-level tables
- `assessments.idAssessment` → `studentAssessment.idAssessment`
- `vle.idSite` → `studentVle.idSite`
- `studentVle` composite key: `codeModule × codePresentation × idStudent × idSite × date`
- All date fields stored as integers relative to course start day (Day 0)

**ERD:** See [`ERD.png`](ERD.png)

---

## Phase 1 — Data Cleaning & Exploratory Data Analysis

**Notebook:** [`notebooks/oulad_phase1_eda.ipynb`](notebooks/oulad_phase1_eda.ipynb)  
**Report:** [`Docs/Phase1_DataCleaning_EDA_Report.md`](Docs/Phase1_DataCleaning_EDA_Report.md)

> Reads directly from CSV files — no database connection required.

### Data Cleaning Decisions

| Field | Issue | Action |
|---|---|---|
| `imdBand` | 3.4% missing | Filled with `'Unknown'` — admin gap, preserve rows |
| `dateRegistration` | 0.14% missing | Filled with median — trivially small gap |
| `dateUnregistration` | 69% null | **Kept as NaN** — null means still enrolled, not missing |
| `assessments.date` | 5.3% missing | Module-level median fill — used only for timing |
| `studentAssessment.score` | 0.1% missing | Rows dropped — score is dependent variable |

### studentVle — EDA-Level Aggregations

Since `studentVle` is a raw click-event log (one row per student × resource × day), two aggregations were computed in the notebook for analysis:

**1. Full-course engagement per student** (Section 9 — VLE Engagement Analysis)  
Grouped by `idStudent × codeModule × codePresentation`, computed:
- `total_clicks` — total VLE clicks across the entire course
- `active_days` — number of distinct days the student accessed the VLE
- `first_day` / `last_day` — earliest and latest interaction dates
- `activity_span` — `last_day − first_day` (days of sustained engagement)

Saved to: `notebooks/processed/student_vle_aggregated.csv`

**2. First-week engagement per student** (Section 9 — Early Warning Analysis)  
Filtered to **days 0–7** (first week of course), then grouped by `idStudent × codeModule × codePresentation`:
- `first_week_clicks` — total clicks in the first 7 days
- `first_week_days` — number of active days in the first week

This was used as an **early dropout warning signal** — ~55% of Withdrawn students had zero first-week VLE activity.  
Saved to: `notebooks/processed/student_vle_first_week.csv`

### Key Insights

#### Outcomes
- **31.2% of students withdraw** — the primary challenge for this project
- Only **47.2%** of enrollments result in Pass or Distinction
- Withdrawal rates vary significantly by module (range: ~20% to ~45%)

#### Demographics
- **Previous attempts** is the strongest demographic predictor — students with 2+ prior attempts have 55%+ dropout rates
- **IMD Band (deprivation):** Most-deprived students (0–10%) withdraw at 37% vs 24% for least-deprived — a 13-point socioeconomic gap
- **Education level:** Students with no formal qualifications withdraw at ~2× the rate of postgraduates
- **Registration timing:** Late registrants (after course start) show the highest dropout rates (~45%)

#### Assessment Behaviour
- Distinction students score a median of **91/100**; Withdrawn students median **70/100**
- **Late submission rate** for Withdrawn students is ~3× higher than Distinction students
- Bimodal score distribution for Withdrawn students — some scored well but still left

#### VLE Engagement
- **Distinction students generate 5× more clicks** than Withdrawn students
- **First-week VLE activity** is the strongest early warning signal:
  - ~55% of Withdrawn students had **zero VLE activity in Week 1**
  - vs only ~8% of Distinction students
- **Forum participation** (`forumng`) is disproportionately high among Distinction students
- Resources and subpages dominate overall click volume

#### Critical Dropout Windows
- **25% of withdrawals** happen before the course even starts (Day < 0)
- **50% of withdrawals** happen before **Day 27** (end of Week 4)
- **75% of withdrawals** happen before Day 109 (Week 16)
- → **Week 1–4 is the critical intervention window**

#### Statistical Validation
- All categorical predictors (gender, age, education, IMD, region, disability, previous attempts) are **statistically significant** vs outcome (chi-square, p < 0.001)
- All continuous predictors (VLE clicks, active days, assessment scores, first-week engagement, registration day) are **statistically significant** vs dropout (Mann-Whitney U, p < 0.001)

### Outputs
All saved to `notebooks/processed/`:
- `student_master_cleaned.csv` — main cleaned student dataset
- `student_vle_aggregated.csv` — per-student VLE totals
- `student_vle_first_week.csv` — first-week engagement metrics
- `assessment_scores_merged.csv` — scores merged with metadata
- 18 publication-quality figures (PNG)

---

## Phase 2 — Feature Engineering & Dropout Prediction

**Status:** 🔜 Upcoming  
**Planned notebook:** `notebooks/oulad_phase2_modelling.ipynb`

### Planned Approach
- Engineer engagement trajectory features (weekly click bins, running assessment averages, score trends)
- Build composite risk scores combining IMD band, previous attempts, and early engagement
- Train and evaluate multiple classifiers:
  - Logistic Regression (baseline)
  - Random Forest & Gradient Boosting (XGBoost, LightGBM)
  - Survival Analysis (Cox Proportional Hazards) for time-to-withdrawal
- Target variables: `is_dropout` (binary) and `finalResult` (4-class)
- Evaluation: ROC-AUC, F1, Precision-Recall, Brier Score (for calibration)
- Explainability: SHAP values for feature importance

---

## Phase 3 — Time-Series Forecasting of Learning Behaviour

**Status:** 🔜 Upcoming  
**Planned notebook:** `notebooks/oulad_phase3_timeseries.ipynb`

### Planned Approach
- Aggregate `studentVle` into weekly engagement sequences per student
- Model learning trajectories using:
  - LSTM / Temporal CNN for sequence-based dropout prediction
  - ARIMA / Prophet for cohort-level engagement forecasting
- Early-warning trigger design: flag at-risk students by Week 3–4 (before 50% of withdrawals occur)
- Investigate whether engagement trajectory shape (rising, declining, flat) predicts outcome independently of total volume

---

## Phase 4 — Interactive Dashboard

**Status:** 🔜 Upcoming

### Planned Features
- **At-risk student monitor** — ranked list updated weekly, exportable for advisor outreach
- **Module health overview** — dropout rates, engagement trends, assessment pass rates per module
- **Individual student timeline** — VLE activity, assessment submissions, and outcome prediction
- **Cohort comparison** — slice by IMD band, education level, module, or presentation period
- **Stack:** Streamlit (Python) or Power BI

---

## Repository Structure

```
├── data/                          # Raw OULAD CSV files (not tracked in git)
│   ├── studentInfo.csv
│   ├── studentRegistration.csv
│   ├── assessments.csv
│   ├── studentAssessment.csv
│   ├── vle.csv
│   ├── studentVle.csv             # 453 MB — 8.4M rows
│   └── courses.csv
│
├── notebooks/
│   ├── oulad_phase1_eda.ipynb     # ✅ Phase 1 — Cleaning & EDA (42 cells)
│   └── processed/                 # Cleaned CSVs & figures (auto-generated)
│
├── Docs/
│   └── Phase1_DataCleaning_EDA_Report.md
│
├── scripts/                       # Phase 0 — DB loading scripts
├── prisma/                        # Prisma ORM schema
├── ERD.png                        # Entity Relationship Diagram
└── README.md

---

## Contributers
**Aditya Kanbargi - MS Data Science, GWU — Data Science Capstone 2026**
**Sanjana Kadambe Muralidhar - MS Data Science, GWU — Data Science Capstone 2026**