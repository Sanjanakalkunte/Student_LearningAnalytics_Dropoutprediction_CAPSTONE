"""
OULAD Phase 2 - Full Data Generation Script
Generates all required CSVs and SHAP values for the dashboard
"""

import os
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text

print("="*65)
print("  OULAD PHASE-2 DATA GENERATION")
print("="*65)

DB_URL = 'postgresql://postgres:23210415@localhost:5432/oulad'
engine = create_engine(DB_URL)

os.makedirs('processed', exist_ok=True)

# ─── STEP 1: Load Core Tables ────────────────────────────────────────────────
print("\n[1/7] Loading core tables from PostgreSQL...")

with engine.connect() as conn:
    df_info = pd.read_sql('SELECT * FROM "studentInfo"', conn)
    df_reg  = pd.read_sql('SELECT * FROM "studentRegistration"', conn)
    df_courses = pd.read_sql('SELECT * FROM courses', conn)
    df_assess  = pd.read_sql('SELECT * FROM assessments', conn)
    df_sa      = pd.read_sql('SELECT * FROM "studentAssessment"', conn)

print(f"  studentInfo: {len(df_info):,} rows")
print(f"  studentRegistration: {len(df_reg):,} rows")
print(f"  studentAssessment: {len(df_sa):,} rows")

# ─── STEP 2: Clean & Build Master Dataset ────────────────────────────────────
print("\n[2/7] Cleaning data & building master dataset...")

df_info_c = df_info.copy()
df_info_c['imdBand'] = df_info_c['imdBand'].fillna('Unknown')

df_reg_c = df_reg.copy()
median_reg = df_reg_c['dateRegistration'].median()
df_reg_c['dateRegistration'] = df_reg_c['dateRegistration'].fillna(median_reg)

df_assess_c = df_assess.copy()
for mod in df_assess_c['codeModule'].unique():
    mask = (df_assess_c['codeModule'] == mod) & df_assess_c['date'].isna()
    med  = df_assess_c.loc[df_assess_c['codeModule']==mod, 'date'].median()
    df_assess_c.loc[mask, 'date'] = med

df_sa_c = df_sa.dropna(subset=['score']).copy()

df_master = df_info_c.merge(
    df_reg_c[['idStudent','codeModule','codePresentation','dateRegistration','dateUnregistration']],
    on=['idStudent','codeModule','codePresentation'], how='left'
).merge(
    df_courses[['codeModule','codePresentation','modulePresentationLength']],
    on=['codeModule','codePresentation'], how='left'
)

df_master['is_dropout'] = (df_master['finalResult'] == 'Withdrawn').astype(int)
df_master['is_success'] = (df_master['finalResult'].isin(['Pass','Distinction'])).astype(int)
df_master['outcome_binary'] = df_master['is_success']

timing_bins  = [-999, -100, -30, 0, 999]
timing_labels = ['Very Early (>100d)', '>30d Before', '0-30d Before', 'After Start']
df_master['reg_timing'] = pd.cut(df_master['dateRegistration'], bins=timing_bins, labels=timing_labels)

print(f"  Master dataset: {df_master.shape}")
print(f"  Dropout rate: {df_master['is_dropout'].mean()*100:.1f}%")

# ─── STEP 3: Assessment Features ─────────────────────────────────────────────
print("\n[3/7] Engineering assessment features...")

df_sa_merged = df_sa_c.merge(
    df_assess_c[['idAssessment','assessmentType','weight','date','codeModule','codePresentation']],
    on='idAssessment', how='left'
)
df_sa_merged['submission_delay'] = df_sa_merged['date'] - df_sa_merged['dateSubmitted']

assess_agg = df_sa_merged.groupby(['idStudent','codeModule','codePresentation']).agg(
    num_assessments   = ('idAssessment','count'),
    avg_score         = ('score','mean'),
    min_score         = ('score','min'),
    max_score         = ('score','max'),
    score_std         = ('score','std'),
    num_banked        = ('isBanked','sum'),
    avg_submission_delay = ('submission_delay','mean'),
    late_submissions  = ('submission_delay', lambda x: (x < 0).sum()),
).reset_index()
assess_agg['late_submission_rate'] = assess_agg['late_submissions'] / assess_agg['num_assessments'].clip(lower=1)
assess_agg['score_std'] = assess_agg['score_std'].fillna(0)

print(f"  Assessment features: {assess_agg.shape}")

# ─── STEP 4: VLE Engagement Features ─────────────────────────────────────────
print("\n[4/7] Loading VLE data in chunks (8.4M rows)...")

CHUNK = 500_000
OFFSET = 0
agg_chunks = []

with engine.connect() as conn:
    total_rows = conn.execute(text('SELECT COUNT(*) FROM "studentVle"')).scalar()

print(f"  Total VLE rows: {total_rows:,}")

while OFFSET < total_rows:
    q = text(f'''SELECT "idStudent","codeModule","codePresentation","date","sumClick"
               FROM "studentVle" LIMIT {CHUNK} OFFSET {OFFSET}''')
    with engine.connect() as conn:
        chunk = pd.read_sql(q, conn)
    
    chunk_agg = chunk.groupby(['idStudent','codeModule','codePresentation']).agg(
        total_clicks  = ('sumClick','sum'),
        active_days   = ('date','nunique'),
        first_day     = ('date','min'),
        last_day      = ('date','max'),
    ).reset_index()
    agg_chunks.append(chunk_agg)
    OFFSET += CHUNK
    if OFFSET % 2_000_000 == 0 or OFFSET >= total_rows:
        print(f"  Processed {min(OFFSET, total_rows):,} / {total_rows:,} rows...")

df_svle_agg = pd.concat(agg_chunks).groupby(['idStudent','codeModule','codePresentation']).agg(
    total_clicks = ('total_clicks','sum'),
    active_days  = ('active_days','sum'),
    first_day    = ('first_day','min'),
    last_day     = ('last_day','max'),
).reset_index()
df_svle_agg['activity_span'] = df_svle_agg['last_day'] - df_svle_agg['first_day']
print(f"  VLE aggregated: {df_svle_agg.shape}")

# First-week engagement
print("\n  Loading first-week VLE data...")
with engine.connect() as conn:
    df_early = pd.read_sql(text('''
        SELECT "idStudent","codeModule","codePresentation",
               SUM("sumClick") as first_week_clicks,
               COUNT(DISTINCT date) as first_week_days
        FROM "studentVle"
        WHERE date BETWEEN 0 AND 7
        GROUP BY "idStudent","codeModule","codePresentation"
    '''), conn)
print(f"  First-week data: {df_early.shape}")

# ─── STEP 5: Build Feature Matrix ────────────────────────────────────────────
print("\n[5/7] Building complete feature matrix...")

df_feat = df_master[[
    'idStudent','codeModule','codePresentation',
    'gender','region','highestEducation','imdBand','ageBand',
    'numOfPrevAttempts','studiedCredits','dateRegistration',
    'modulePresentationLength','finalResult','is_dropout','is_success'
]].copy()

# Merge VLE
df_feat = df_feat.merge(df_svle_agg[['idStudent','codeModule','codePresentation',
    'total_clicks','active_days','first_day','last_day','activity_span']],
    on=['idStudent','codeModule','codePresentation'], how='left')

# Merge first-week
df_feat = df_feat.merge(df_early, on=['idStudent','codeModule','codePresentation'], how='left')

# Merge assessments
df_feat = df_feat.merge(assess_agg[['idStudent','codeModule','codePresentation',
    'num_assessments','avg_score','min_score','max_score','score_std',
    'num_banked','avg_submission_delay','late_submission_rate']],
    on=['idStudent','codeModule','codePresentation'], how='left')

# Fill NaN with 0 for engagement/assessment
fill_zero_cols = ['total_clicks','active_days','activity_span','first_week_clicks',
                  'first_week_days','num_assessments','avg_score','min_score','max_score',
                  'score_std','num_banked','avg_submission_delay','late_submission_rate',
                  'first_day','last_day']
for col in fill_zero_cols:
    if col in df_feat.columns:
        df_feat[col] = df_feat[col].fillna(0)

# Engineered features
df_feat['engagement_ratio']  = df_feat['activity_span'] / df_feat['modulePresentationLength'].clip(lower=1)
df_feat['clicks_per_day']    = df_feat['total_clicks'] / df_feat['active_days'].clip(lower=1)
df_feat['first_week_pct']    = df_feat['first_week_clicks'] / df_feat['total_clicks'].clip(lower=1)
df_feat['zero_first_week']   = (df_feat['first_week_clicks'] == 0).astype(int)
df_feat['days_before_start'] = (-df_feat['dateRegistration']).clip(lower=0)

# Module dropout rate
module_dropout = df_feat.groupby(['codeModule','codePresentation'])['is_dropout'].mean().reset_index()
module_dropout.columns = ['codeModule','codePresentation','module_dropout_rate']
df_feat = df_feat.merge(module_dropout, on=['codeModule','codePresentation'], how='left')

print(f"  Feature matrix: {df_feat.shape}")

# ─── STEP 6: Train Models & SHAP ─────────────────────────────────────────────
print("\n[6/7] Training models and computing SHAP values...")

from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (roc_auc_score, f1_score, precision_score,
                              recall_score, accuracy_score, confusion_matrix)
import xgboost as xgb
import lightgbm as lgb
import shap

cat_cols = ['gender','region','highestEducation','imdBand','ageBand','codeModule','codePresentation']
le = LabelEncoder()
df_model = df_feat.copy()
for col in cat_cols:
    if col in df_model.columns:
        df_model[col + '_enc'] = le.fit_transform(df_model[col].astype(str))

numeric_features = [
    'numOfPrevAttempts','studiedCredits','dateRegistration',
    'first_week_clicks','first_week_days','total_clicks',
    'active_days','activity_span','avg_score','num_assessments',
    'late_submission_rate','score_std','avg_submission_delay',
    'engagement_ratio','clicks_per_day','zero_first_week',
    'days_before_start','module_dropout_rate','first_week_pct',
    'min_score','max_score',
]
enc_features = [c + '_enc' for c in cat_cols]
feature_cols = [f for f in numeric_features + enc_features if f in df_model.columns]

X = df_model[feature_cols].fillna(0).values
y = df_model['is_dropout'].values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s  = scaler.transform(X_test)

models = {
    'Logistic Regression': LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42),
    'Random Forest':       RandomForestClassifier(n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1),
    'XGBoost':             xgb.XGBClassifier(n_estimators=300, scale_pos_weight=(y==0).sum()/(y==1).sum(), random_state=42, n_jobs=-1, eval_metric='logloss', verbosity=0),
    'LightGBM':            lgb.LGBMClassifier(n_estimators=300, class_weight='balanced', random_state=42, n_jobs=-1, verbose=-1),
}

results = {}
trained_models = {}
print("\n  Model Results:")
print(f"  {'Model':<25} {'AUC-ROC':>8} {'Recall':>8} {'Precision':>10} {'F1':>8}")
print("  " + "-"*65)

for name, model in models.items():
    Xtr = X_train_s if name == 'Logistic Regression' else X_train
    Xte = X_test_s  if name == 'Logistic Regression' else X_test
    model.fit(Xtr, y_train)
    y_prob = model.predict_proba(Xte)[:,1]
    y_pred = model.predict(Xte)
    
    auc  = roc_auc_score(y_test, y_prob)
    rec  = recall_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    f1   = f1_score(y_test, y_pred)
    
    results[name] = {'auc': auc, 'recall': rec, 'precision': prec, 'f1': f1, 'y_prob': y_prob}
    trained_models[name] = model
    print(f"  {name:<25} {auc:>8.4f} {rec:>8.4f} {prec:>10.4f} {f1:>8.4f}")

best_model_name = max(results, key=lambda k: results[k]['auc'])
best_model = trained_models[best_model_name]
print(f"\n  Best model: {best_model_name}")

# SHAP Analysis
print("\n  Computing SHAP values (TreeExplainer on LightGBM)...")
lgbm_model = trained_models['LightGBM']
explainer = shap.TreeExplainer(lgbm_model)
# Compute on test set (6519 samples)
shap_values = explainer.shap_values(X_test)
# For binary, shap_values may be list [class0, class1]
if isinstance(shap_values, list):
    shap_vals_dropout = shap_values[1]
else:
    shap_vals_dropout = shap_values

print(f"  SHAP values computed: {shap_vals_dropout.shape}")

# Global feature importance via SHAP
mean_shap = np.abs(shap_vals_dropout).mean(axis=0)
shap_importance = pd.DataFrame({
    'feature': feature_cols,
    'mean_shap': mean_shap
}).sort_values('mean_shap', ascending=False).reset_index(drop=True)

print("\n  Top 10 SHAP Feature Importances:")
for _, row in shap_importance.head(10).iterrows():
    print(f"    {row['feature']:<30} {row['mean_shap']:.4f}")

# Save SHAP values for dashboard
shap_df = pd.DataFrame(shap_vals_dropout, columns=feature_cols)
shap_df.to_csv('processed/shap_values_test.csv', index=False)
shap_importance.to_csv('processed/shap_importance.csv', index=False)
print("  SHAP values saved.")

# Save scaler + feature list
import joblib
joblib.dump(lgbm_model, 'processed/lightgbm_model.pkl')
joblib.dump(scaler, 'processed/scaler.pkl')
with open('processed/feature_cols.json', 'w') as f:
    json.dump(feature_cols, f)
print("  Model and scaler saved.")

# ─── STEP 7: Risk Flags, Clusters, Save All CSVs ────────────────────────────
print("\n[7/7] Computing risk flags & clustering...")

from sklearn.cluster import KMeans

cluster_features = [
    'total_clicks','active_days','activity_span','avg_score',
    'num_assessments','late_submission_rate','first_week_clicks',
    'first_week_days','engagement_ratio','clicks_per_day',
    'zero_first_week','days_before_start','numOfPrevAttempts','score_std'
]
clust_df = df_feat[cluster_features].fillna(0).copy()
clust_scaler = StandardScaler()
X_clust = clust_scaler.fit_transform(clust_df)

kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
df_feat['cluster'] = kmeans.fit_predict(X_clust)

# Label clusters by dropout rate (ascending = less dangerous → more dangerous)
cluster_dropout = df_feat.groupby('cluster')['is_dropout'].mean().sort_values()
cluster_map = {}
labels = ['Power Users', 'Steady Completers', 'Struggling Engagers', 'Non-Starters']
for rank, (clust_id, _) in enumerate(cluster_dropout.items()):
    cluster_map[clust_id] = rank
df_feat['cluster_label'] = df_feat['cluster'].map(cluster_map)
df_feat['cluster_name']  = df_feat['cluster_label'].map({i: l for i, l in enumerate(labels)})

print("  Cluster profiles:")
for name in labels:
    sub = df_feat[df_feat['cluster_name'] == name]
    print(f"    {name:<25} n={len(sub):>6,} | dropout={sub['is_dropout'].mean()*100:.1f}%")

# Risk Flags
df_feat['flag_zero_first_week']    = (df_feat['first_week_clicks'] == 0).astype(int)
df_feat['flag_high_attempts']      = (df_feat['numOfPrevAttempts'] >= 3).astype(int)
df_feat['flag_late_registration']  = (df_feat['dateRegistration'] > 0).astype(int)
df_feat['flag_low_assessment']     = (df_feat['num_assessments'] == 0).astype(int)
df_feat['flag_deprived_area']      = df_feat['imdBand'].isin(['0-10%','10-20%']).astype(int)
df_feat['risk_score'] = (
    df_feat['flag_zero_first_week'] +
    df_feat['flag_high_attempts'] +
    df_feat['flag_late_registration'] +
    df_feat['flag_low_assessment'] +
    df_feat['flag_deprived_area']
)
df_feat['risk_level'] = pd.cut(df_feat['risk_score'], bins=[-1,0,2,5],
                                labels=['Low','Moderate','High'])

# Validate risk flags
print("\n  Early Warning Flag Validation:")
for threshold in [1, 2, 3]:
    flagged = df_feat['risk_score'] >= threshold
    prec = df_feat.loc[flagged, 'is_dropout'].mean()
    rec  = df_feat.loc[flagged, 'is_dropout'].sum() / df_feat['is_dropout'].sum()
    print(f"    Risk score >= {threshold}: flagged={flagged.sum():,} | precision={prec:.3f} | recall={rec:.3f}")

# Add LightGBM probability scores to ALL students
print("\n  Scoring all 32,593 students with LightGBM...")
X_all = df_model[feature_cols].fillna(0).values
lgbm_probs = lgbm_model.predict_proba(X_all)[:,1]
df_feat['dropout_probability'] = lgbm_probs

# Save all CSVs
print("\n  Saving output CSVs...")
save_cols = ['idStudent','codeModule','codePresentation','finalResult',
             'is_dropout','is_success',
             'gender','region','highestEducation','imdBand','ageBand',
             'numOfPrevAttempts','studiedCredits','dateRegistration',
             'total_clicks','active_days','activity_span',
             'first_week_clicks','first_week_days',
             'avg_score','num_assessments','late_submission_rate',
             'engagement_ratio','clicks_per_day','zero_first_week',
             'days_before_start','module_dropout_rate',
             'cluster','cluster_name',
             'flag_zero_first_week','flag_high_attempts','flag_late_registration',
             'flag_low_assessment','flag_deprived_area','risk_score','risk_level',
             'dropout_probability']

df_save = df_feat[[c for c in save_cols if c in df_feat.columns]]
df_save.to_csv('processed/student_features_clustered.csv', index=False)
print(f"  student_features_clustered.csv saved: {df_save.shape}")

# Master cleaned
df_master_save = df_master.drop(columns=['imd_order','edu_order','age_order'], errors='ignore')
df_master_save.to_csv('processed/student_master_cleaned.csv', index=False)
print(f"  student_master_cleaned.csv saved: {df_master_save.shape}")

# Risk flags only
risk_cols = ['idStudent','codeModule','codePresentation',
             'flag_zero_first_week','flag_high_attempts','flag_late_registration',
             'flag_low_assessment','flag_deprived_area','risk_score','risk_level',
             'dropout_probability','cluster_name','is_dropout']
df_risk = df_feat[[c for c in risk_cols if c in df_feat.columns]]
df_risk.to_csv('processed/risk_flags.csv', index=False)
print(f"  risk_flags.csv saved: {df_risk.shape}")

# First-week VLE for dashboard
df_early_save = df_feat[['idStudent','codeModule','codePresentation',
                          'first_week_clicks','first_week_days','zero_first_week','is_dropout']]
df_early_save.to_csv('processed/student_vle_first_week.csv', index=False)
print(f"  student_vle_first_week.csv saved: {df_early_save.shape}")

# ─── FINAL SUMMARY ────────────────────────────────────────────────────────────
print("\n" + "="*65)
print("  GENERATION COMPLETE")
print("="*65)
print(f"\n  Students processed: {len(df_feat):,}")
print(f"  Dropout rate: {df_feat['is_dropout'].mean()*100:.1f}%")
print(f"  High-risk students (score >= 3): {(df_feat['risk_score'] >= 3).sum():,}")
print(f"  Zero first-week activity: {df_feat['flag_zero_first_week'].sum():,} ({df_feat['flag_zero_first_week'].mean()*100:.1f}%)")
print(f"\n  Files saved to: processed/")
print("  - student_features_clustered.csv")
print("  - student_master_cleaned.csv")  
print("  - risk_flags.csv")
print("  - student_vle_first_week.csv")
print("  - shap_values_test.csv")
print("  - shap_importance.csv")
print("  - lightgbm_model.pkl")
print("  - scaler.pkl")
print("  - feature_cols.json")
print("\n  Ready for dashboard generation!")
