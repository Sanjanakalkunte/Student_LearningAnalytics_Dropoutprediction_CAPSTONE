"""
Generate ML model comparison results and cluster scatter data
for the dashboard Model Results tab and Clusters scatterplot.
"""
import json, warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (roc_auc_score, f1_score, precision_score,
                              recall_score, accuracy_score, confusion_matrix, roc_curve)
from sklearn.decomposition import PCA
import xgboost as xgb
import lightgbm as lgb

print("=" * 65)
print("  GENERATING MODEL RESULTS & CLUSTER SCATTER DATA")
print("=" * 65)

# ── Load data ─────────────────────────────────────────────────────────────────
df = pd.read_csv('processed/student_features_clustered.csv')
with open('processed/feature_cols.json', 'r') as f:
    feature_cols_raw = json.load(f)

print(f"\nLoaded {len(df):,} students, {len(feature_cols_raw)} features in feature_cols.json")

# ── Encode categoricals (same as generate_data.py) ────────────────────────────
cat_cols = ['gender','region','highestEducation','imdBand','ageBand','codeModule','codePresentation']
le = LabelEncoder()
df_model = df.copy()
for col in cat_cols:
    if col in df_model.columns:
        df_model[col + '_enc'] = le.fit_transform(df_model[col].astype(str))

# Recreate derived features that may be missing from CSV
if 'first_week_pct' not in df_model.columns and 'first_week_clicks' in df_model.columns:
    df_model['first_week_pct'] = df_model['first_week_clicks'] / df_model['total_clicks'].clip(lower=1)
if 'score_std' not in df_model.columns and 'avg_score' in df_model.columns:
    df_model['score_std'] = 0.0
if 'min_score' not in df_model.columns:
    df_model['min_score'] = df_model.get('avg_score', pd.Series(0, index=df_model.index))
if 'max_score' not in df_model.columns:
    df_model['max_score'] = df_model.get('avg_score', pd.Series(0, index=df_model.index))
if 'avg_submission_delay' not in df_model.columns:
    df_model['avg_submission_delay'] = 0.0

# Filter to available columns only
feature_cols = [c for c in feature_cols_raw if c in df_model.columns]
missing = [c for c in feature_cols_raw if c not in df_model.columns]
if missing:
    print(f"  WARNING: {len(missing)} features missing, skipped: {missing}")
print(f"  Using {len(feature_cols)} features")

X = df_model[feature_cols].fillna(0).values
y = df_model['is_dropout'].values

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

print(f"Train: {len(X_train):,}  Test: {len(X_test):,}")

# ── Train all 4 models ───────────────────────────────────────────────────────
models = {
    'Logistic Regression': LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42),
    'Random Forest':       RandomForestClassifier(n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1),
    'XGBoost':             xgb.XGBClassifier(n_estimators=300, scale_pos_weight=(y==0).sum()/(y==1).sum(), random_state=42, n_jobs=-1, eval_metric='logloss', verbosity=0),
    'LightGBM':            lgb.LGBMClassifier(n_estimators=300, class_weight='balanced', random_state=42, n_jobs=-1, verbose=-1),
}

results = []
roc_curves = {}
conf_matrices = {}

print("\n  Training models...\n")
print(f"  {'Model':<25} {'AUC-ROC':>8} {'Accuracy':>10} {'Precision':>10} {'Recall':>8} {'F1':>8}")
print("  " + "-" * 75)

for name, model in models.items():
    Xtr = X_train_s if name == 'Logistic Regression' else X_train
    Xte = X_test_s if name == 'Logistic Regression' else X_test
    model.fit(Xtr, y_train)
    y_prob = model.predict_proba(Xte)[:, 1]
    y_pred = model.predict(Xte)

    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    results.append({
        'model': name,
        'auc_roc': round(auc, 4),
        'accuracy': round(acc, 4),
        'precision': round(prec, 4),
        'recall': round(rec, 4),
        'f1_score': round(f1, 4),
    })

    # ROC curve data (sampled to ~100 points)
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    indices = np.linspace(0, len(fpr) - 1, min(100, len(fpr)), dtype=int)
    roc_curves[name] = {
        'fpr': [round(float(fpr[i]), 4) for i in indices],
        'tpr': [round(float(tpr[i]), 4) for i in indices],
    }

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    conf_matrices[name] = {
        'tn': int(cm[0, 0]), 'fp': int(cm[0, 1]),
        'fn': int(cm[1, 0]), 'tp': int(cm[1, 1]),
    }

    print(f"  {name:<25} {auc:>8.4f} {acc:>10.4f} {prec:>10.4f} {rec:>8.4f} {f1:>8.4f}")

# Find best model
best = max(results, key=lambda x: x['auc_roc'])
print(f"\n  Best model: {best['model']} (AUC-ROC: {best['auc_roc']})")

# ── Feature importance from LightGBM ─────────────────────────────────────────
lgbm = models['LightGBM']
feat_imp = pd.DataFrame({
    'feature': feature_cols,
    'importance': lgbm.feature_importances_
}).sort_values('importance', ascending=False)

# ── Cluster scatter data (PCA 2D) ────────────────────────────────────────────
print("\n  Generating cluster scatter data (PCA)...")
cluster_features = [
    'total_clicks', 'active_days', 'activity_span', 'avg_score',
    'num_assessments', 'late_submission_rate', 'first_week_clicks',
    'first_week_days', 'engagement_ratio', 'clicks_per_day',
]
avail_feats = [f for f in cluster_features if f in df.columns]
X_clust = df[avail_feats].fillna(0).values

clust_scaler = StandardScaler()
X_clust_scaled = clust_scaler.fit_transform(X_clust)

pca = PCA(n_components=2, random_state=42)
X_pca = pca.fit_transform(X_clust_scaled)

explained = pca.explained_variance_ratio_
print(f"  PCA explained variance: {explained[0]:.1%} + {explained[1]:.1%} = {sum(explained):.1%}")

# Sample ~2000 points for the scatter (stratified by cluster)
np.random.seed(42)
sample_size = min(2000, len(df))
sample_idx = []
for cname in df['cluster_name'].unique():
    mask = df['cluster_name'] == cname
    cluster_indices = np.where(mask)[0]
    n_sample = max(100, int(sample_size * mask.sum() / len(df)))
    chosen = np.random.choice(cluster_indices, min(n_sample, len(cluster_indices)), replace=False)
    sample_idx.extend(chosen)

scatter_data = []
for i in sample_idx:
    scatter_data.append({
        'x': round(float(X_pca[i, 0]), 3),
        'y': round(float(X_pca[i, 1]), 3),
        'cluster': df.iloc[i]['cluster_name'],
        'dropout': int(df.iloc[i]['is_dropout']),
    })

print(f"  Scatter points: {len(scatter_data)}")

# ── Save everything ──────────────────────────────────────────────────────────
model_data = {
    'model_results': results,
    'roc_curves': roc_curves,
    'confusion_matrices': conf_matrices,
    'best_model': best['model'],
    'test_size': int(len(X_test)),
    'train_size': int(len(X_train)),
    'n_features': len(feature_cols),
    'cluster_scatter': scatter_data,
    'pca_explained': [round(float(e), 4) for e in explained],
}

with open('processed/model_results.json', 'w') as f:
    json.dump(model_data, f)

print(f"\n  Saved: processed/model_results.json")
print("  DONE!")
