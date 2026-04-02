"""
Dashboard data preparation — runs after generate_data.py completes
Compiles all CSVs into a single JSON payload for the HTML dashboard
"""
import json
import pandas as pd
import numpy as np

print("Preparing dashboard data...")

# Load all generated CSVs
df = pd.read_csv('processed/student_features_clustered.csv')
shap_imp = pd.read_csv('processed/shap_importance.csv')

print(f"Loaded {len(df):,} students")

# ── KPI Numbers ───────────────────────────────────────────────────────────────
total = len(df)
dropout_rate = round(df['is_dropout'].mean() * 100, 1)
high_risk = int((df['risk_score'] >= 3).sum())
high_risk_pct = round(high_risk / total * 100, 1)
zero_week = int(df['flag_zero_first_week'].sum())
zero_week_pct = round(zero_week / total * 100, 1)
avg_prob = round(df['dropout_probability'].mean() * 100, 1)
deprived_pct = round(df['flag_deprived_area'].mean() * 100, 1)

kpis = {
    'total_students': total,
    'dropout_rate': dropout_rate,
    'high_risk_count': high_risk,
    'high_risk_pct': high_risk_pct,
    'zero_week_count': zero_week,
    'zero_week_pct': zero_week_pct,
    'avg_dropout_prob': avg_prob,
    'deprived_pct': deprived_pct,
}

# ── Cluster Summary ───────────────────────────────────────────────────────────
cluster_summary = df.groupby('cluster_name').agg(
    count=('is_dropout','count'),
    dropout_rate=('is_dropout','mean'),
    avg_clicks=('total_clicks','mean'),
    avg_score=('avg_score','mean'),
    avg_active_days=('active_days','mean'),
    avg_risk=('dropout_probability','mean'),
).reset_index()
cluster_summary['dropout_pct'] = (cluster_summary['dropout_rate'] * 100).round(1)
cluster_summary['avg_risk_pct'] = (cluster_summary['avg_risk'] * 100).round(1)
cluster_data = cluster_summary.to_dict('records')

# ── Module Risk ───────────────────────────────────────────────────────────────
module_risk = df.groupby('codeModule').agg(
    count=('is_dropout','count'),
    dropout_rate=('is_dropout','mean'),
    avg_risk=('dropout_probability','mean'),
    high_risk=('risk_score', lambda x: (x >= 3).sum()),
).reset_index()
module_risk['dropout_pct'] = (module_risk['dropout_rate'] * 100).round(1)
module_risk['avg_risk_pct'] = (module_risk['avg_risk'] * 100).round(1)
module_data = module_risk.sort_values('dropout_pct', ascending=False).to_dict('records')

# ── Risk Distribution ─────────────────────────────────────────────────────────
risk_dist = df.groupby('risk_score')['is_dropout'].agg(['count','mean']).reset_index()
risk_dist.columns = ['score','count','dropout_rate']
risk_dist['dropout_pct'] = (risk_dist['dropout_rate'] * 100).round(1)
risk_dist_data = risk_dist.to_dict('records')

# ── SHAP Feature Importance ───────────────────────────────────────────────────
# Clean up feature names
def clean_name(name):
    name_map = {
        'activity_span': 'Activity Span',
        'engagement_ratio': 'Engagement Ratio',
        'module_dropout_rate': 'Module Dropout Rate',
        'num_assessments': 'Assessments Completed',
        'avg_score': 'Avg Assessment Score',
        'studiedCredits': 'Credits Studied',
        'active_days': 'Active Days',
        'codePresentation_enc': 'Presentation Period',
        'late_submission_rate': 'Late Submission Rate',
        'total_clicks': 'Total VLE Clicks',
        'first_week_clicks': 'First-Week Clicks',
        'first_week_days': 'First-Week Active Days',
        'zero_first_week': 'Zero First-Week Activity',
        'numOfPrevAttempts': 'Prior Attempts',
        'clicks_per_day': 'Clicks Per Day',
        'engagement_ratio': 'Engagement Ratio',
        'days_before_start': 'Days Before Start',
        'dateRegistration': 'Registration Timing',
        'imdBand_enc': 'Deprivation Band (IMD)',
        'highestEducation_enc': 'Education Level',
        'score_std': 'Score Variability',
        'min_score': 'Min Score',
        'max_score': 'Max Score',
        'avg_submission_delay': 'Avg Submission Delay',
        'codeModule_enc': 'Module',
        'ageBand_enc': 'Age Band',
        'gender_enc': 'Gender',
        'region_enc': 'Region',
        'first_week_pct': 'First-Week Click Share',
    }
    return name_map.get(name, name.replace('_', ' ').title())

shap_top10 = shap_imp.head(10).copy()
shap_top10['display_name'] = shap_top10['feature'].apply(clean_name)
shap_top10['mean_shap_pct'] = (shap_top10['mean_shap'] / shap_top10['mean_shap'].sum() * 100).round(1)
shap_data = shap_top10[['display_name','mean_shap','mean_shap_pct']].to_dict('records')

# ── Outcome Distribution ──────────────────────────────────────────────────────
outcome_dist = df['finalResult'].value_counts().to_dict()

# ── Flag Breakdown ────────────────────────────────────────────────────────────
flags = {
    'Zero First-Week Activity': {
        'count': int(df['flag_zero_first_week'].sum()),
        'dropout_rate': round(df.loc[df['flag_zero_first_week']==1,'is_dropout'].mean()*100, 1),
        'desc': 'No VLE activity in Week 1 — strongest early signal (+25pp above baseline)'
    },
    'High Prior Attempts': {
        'count': int(df['flag_high_attempts'].sum()),
        'dropout_rate': round(df.loc[df['flag_high_attempts']==1,'is_dropout'].mean()*100, 1),
        'desc': '3+ previous course attempts — structural engagement barrier'
    },
    'Low Engagement': {
        'count': int((df['engagement_ratio'] < 0.1).sum()),
        'dropout_rate': round(df.loc[df['engagement_ratio'] < 0.1,'is_dropout'].mean()*100, 1),
        'desc': 'Active <10% of module duration — disengaged across the semester (+17pp above baseline)'
    },
    'Zero Assessments': {
        'count': int(df['flag_low_assessment'].sum()),
        'dropout_rate': round(df.loc[df['flag_low_assessment']==1,'is_dropout'].mean()*100, 1),
        'desc': 'No assessment submissions — near-certain withdrawal (+50pp above baseline)'
    },
    'Deprived Area': {
        'count': int(df['flag_deprived_area'].sum()),
        'dropout_rate': round(df.loc[df['flag_deprived_area']==1,'is_dropout'].mean()*100, 1),
        'desc': 'IMD Band 0-20% (most deprived) — socioeconomic risk factor'
    },
}

# ── Student Search Data (top 5000 by risk for fast load) ─────────────────────
student_cols = [
    'idStudent','codeModule','codePresentation','finalResult',
    'risk_score','dropout_probability','cluster_name',
    'flag_zero_first_week','flag_high_attempts','flag_late_registration',
    'flag_low_assessment','flag_deprived_area',
    'first_week_clicks','total_clicks','active_days',
    'avg_score','num_assessments','numOfPrevAttempts',
    'imdBand','highestEducation','dateRegistration','engagement_ratio','activity_span'
]
avail_cols = [c for c in student_cols if c in df.columns]
df_students = df[avail_cols].sort_values('dropout_probability', ascending=False)
# Round floats
for col in ['dropout_probability','engagement_ratio','activity_span','avg_score']:
    if col in df_students.columns:
        df_students[col] = df_students[col].round(4)
students_data = df_students.head(5000).to_dict('records')  # top 5k highest risk

# ── Engagement By Outcome (for line chart) ────────────────────────────────────
# Bins for dropout probability distribution
prob_hist = {}
for outcome in ['Withdrawn','Pass','Distinction','Fail']:
    sub = df[df['finalResult'] == outcome]['dropout_probability'].dropna()
    counts, edges = np.histogram(sub, bins=20, range=(0,1))
    prob_hist[outcome] = {'counts': counts.tolist(), 'edges': [round(e,2) for e in edges.tolist()]}

# ── Compile All Data ──────────────────────────────────────────────────────────
dashboard_data = {
    'kpis': kpis,
    'cluster_data': cluster_data,
    'module_data': module_data,
    'risk_dist': risk_dist_data,
    'shap_importance': shap_data,
    'outcome_dist': outcome_dist,
    'flags': flags,
    'students': students_data,
    'prob_hist': prob_hist,
}

with open('processed/dashboard_data.json', 'w') as f:
    json.dump(dashboard_data, f)

print(f"\nDashboard data compiled:")
print(f"  KPIs: dropout={kpis['dropout_rate']}%, high_risk={kpis['high_risk_count']:,}")
print(f"  Clusters: {len(cluster_data)}")
print(f"  Modules: {len(module_data)}")
print(f"  SHAP features: {len(shap_data)}")
print(f"  Students (top 5k): {len(students_data)}")
print(f"\n  Saved: processed/dashboard_data.json")
print("DONE!")
