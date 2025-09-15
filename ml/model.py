# model.py

import os
import joblib
import pandas as pd
from typing import Any, List, Optional, Dict
from sqlalchemy.orm import Session
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from app import database

MODELS_DIR = "ml/saved_models/"
FEATURES: Optional[List[str]] = None

AVAILABLE_MODELS = {
    "IsolationForest": IsolationForest(n_estimators=100, contamination="auto", random_state=42),
    "LogisticRegression": LogisticRegression(solver='liblinear', random_state=42),
    "DecisionTree": DecisionTreeClassifier(max_depth=5, random_state=42),
    "RandomForest": RandomForestClassifier(n_estimators=50, max_depth=10, random_state=42)
}

_models: Dict[str, Any] = {}

def train_model_from_df(df: pd.DataFrame, model_name: str) -> None:
    global _models, FEATURES
    if model_name not in AVAILABLE_MODELS:
        raise ValueError(f"Model '{model_name}' not available.")
    numeric_df = df.select_dtypes(include=["number"])
    if numeric_df.empty:
        raise ValueError("No numeric columns available.")
    if FEATURES is None:
        FEATURES = numeric_df.columns.tolist()
    numeric_df = numeric_df.reindex(columns=FEATURES, fill_value=0)
    clf = AVAILABLE_MODELS[model_name]

    if model_name == "IsolationForest":
        clf.fit(numeric_df)
    else:
        if 'is_fraud' not in df.columns:
            raise ValueError(f"Supervised model '{model_name}' requires 'is_fraud'.")
        target = df['is_fraud'].astype(int)
        features_to_train = [f for f in FEATURES if f != 'is_fraud']
        clf.fit(numeric_df[features_to_train], target)

    _models[model_name] = clf
    os.makedirs(MODELS_DIR, exist_ok=True)
    joblib.dump((clf, FEATURES), os.path.join(MODELS_DIR, f"{model_name}.pkl"))
    print(f"✅ Trained {model_name} on {len(df)} rows.")

def train_model(db: Session, model_name: str) -> None:
    df = pd.read_sql(db.query(database.Transaction).statement, db.bind)
    if df.empty:
        raise ValueError("No data in DB to train.")
    if model_name != "IsolationForest":
        labeled_df = df[df['is_fraud'] != -1]
        if len(labeled_df) < 10:
            raise ValueError(f"Need >=10 labeled rows. Run IsolationForest first.")
        df_train = labeled_df
    else:
        df_train = df
    df_train = df_train.drop(columns=['id','card_number_encrypted','explanation','timestamp'], errors='ignore')
    train_model_from_df(df_train, model_name)

def load_models() -> None:
    global _models, FEATURES
    os.makedirs(MODELS_DIR, exist_ok=True)
    for name in AVAILABLE_MODELS:
        path = os.path.join(MODELS_DIR, f"{name}.pkl")
        if os.path.exists(path):
            try:
                model, feats = joblib.load(path)
                _models[name] = model
                FEATURES = FEATURES or feats
                print(f"✅ Loaded {name} from {path}")
            except Exception as e:
                print(f"⚠️ Could not load {name}: {e}")

def predict(df: pd.DataFrame, model_name: str) -> pd.Series:
    if model_name not in _models or FEATURES is None:
        raise Exception(f"Model '{model_name}' not loaded.")
    model = _models[model_name]
    numeric_df = df.select_dtypes(include=["number"]).reindex(columns=FEATURES, fill_value=0.0)
    if model_name != "IsolationForest":
        features = [f for f in FEATURES if f != 'is_fraud']
        numeric_df = numeric_df[features]
    return pd.Series(model.predict(numeric_df), index=df.index)
