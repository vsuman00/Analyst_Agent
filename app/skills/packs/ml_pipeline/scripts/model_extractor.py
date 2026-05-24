"""
model_extractor.py — ML Pipeline Skill Pack Extraction Script
---------------------------------------------------------------
Extracts ML pipeline stages, model architectures, and evaluation metrics
from machine learning repositories.

Usage:
    python scripts/model_extractor.py <repo_dir> <output_file> <subcommand>

Subcommands:
    stages  — Detect ML pipeline stages (data, preprocess, train, eval, serve)
    models  — Detect model architectures and frameworks
    metrics — Detect evaluation metrics used in the codebase
    extract — Run all subcommands and merge results

Uses ONLY stdlib — no pip installs required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# ML Stage Detection Patterns
# ---------------------------------------------------------------------------

_ML_STAGES = {
    "data_loading": {
        "patterns": [
            re.compile(r"pd\.read_csv|pd\.read_parquet|pd\.read_json|load_dataset|DataLoader|read_csv", re.IGNORECASE),
            re.compile(r"tf\.data\.Dataset|from_csv|from_parquet|ImageFolder", re.IGNORECASE),
        ],
        "description": "Data ingestion and loading from files, databases, or APIs",
    },
    "data_preprocessing": {
        "patterns": [
            re.compile(r"StandardScaler|MinMaxScaler|LabelEncoder|OneHotEncoder|fit_transform", re.IGNORECASE),
            re.compile(r"train_test_split|cross_val_score|StratifiedKFold|KFold", re.IGNORECASE),
            re.compile(r"fillna|dropna|normalize|tokenize|Tokenizer", re.IGNORECASE),
        ],
        "description": "Data cleaning, normalization, encoding, and train/test splitting",
    },
    "feature_engineering": {
        "patterns": [
            re.compile(r"PolynomialFeatures|SelectKBest|PCA|TruncatedSVD|feature_importance", re.IGNORECASE),
            re.compile(r"get_dummies|create_features|FeatureUnion|ColumnTransformer", re.IGNORECASE),
        ],
        "description": "Feature creation, selection, and dimensionality reduction",
    },
    "model_definition": {
        "patterns": [
            re.compile(r"class\s+\w+\(nn\.Module\)|class\s+\w+\(tf\.keras\.Model\)", re.IGNORECASE),
            re.compile(r"Sequential\(\)|compile\(|Model\(inputs=|nn\.Linear|nn\.Conv2d", re.IGNORECASE),
            re.compile(r"RandomForest|GradientBoosting|XGBClassifier|LGBMClassifier|LogisticRegression", re.IGNORECASE),
        ],
        "description": "Model architecture definition and configuration",
    },
    "model_training": {
        "patterns": [
            re.compile(r"model\.fit|model\.train|trainer\.train|\.backward\(\)|optimizer\.step", re.IGNORECASE),
            re.compile(r"for\s+epoch|num_epochs|training_loop|loss\.backward", re.IGNORECASE),
        ],
        "description": "Model training loop, optimization, and convergence monitoring",
    },
    "model_evaluation": {
        "patterns": [
            re.compile(r"model\.eval|model\.evaluate|accuracy_score|f1_score|classification_report", re.IGNORECASE),
            re.compile(r"confusion_matrix|roc_auc_score|mean_squared_error|r2_score", re.IGNORECASE),
        ],
        "description": "Model performance evaluation and metric computation",
    },
    "model_serving": {
        "patterns": [
            re.compile(r"torch\.save|model\.save|joblib\.dump|pickle\.dump|onnx\.export", re.IGNORECASE),
            re.compile(r"mlflow\.log_model|bentoml|TFServing|triton|torchserve", re.IGNORECASE),
            re.compile(r"predict_endpoint|inference|@app\.\w+.*predict", re.IGNORECASE),
        ],
        "description": "Model serialization, export, and serving infrastructure",
    },
    "experiment_tracking": {
        "patterns": [
            re.compile(r"mlflow\.log|wandb\.log|wandb\.init|neptune\.log|tensorboard", re.IGNORECASE),
            re.compile(r"optuna\.create_study|hyperopt|ray\.tune", re.IGNORECASE),
        ],
        "description": "Experiment logging, hyperparameter tracking, and reproducibility",
    },
}


# ---------------------------------------------------------------------------
# Model Architecture Patterns
# ---------------------------------------------------------------------------

_MODEL_TYPES = {
    "neural_network_cnn": re.compile(r"Conv2d|Conv1d|MaxPool|AveragePool|ResNet|VGG|InceptionV3", re.IGNORECASE),
    "neural_network_rnn": re.compile(r"LSTM|GRU|RNN\(|Bidirectional|seq2seq", re.IGNORECASE),
    "transformer": re.compile(r"Transformer|MultiHeadAttention|BertModel|GPT|attention_mask", re.IGNORECASE),
    "tree_ensemble": re.compile(r"RandomForest|GradientBoosting|XGB|LGBM|CatBoost|DecisionTree", re.IGNORECASE),
    "linear_model": re.compile(r"LogisticRegression|LinearRegression|Lasso|Ridge|ElasticNet|SGDClassifier", re.IGNORECASE),
    "clustering": re.compile(r"KMeans|DBSCAN|AgglomerativeClustering|GaussianMixture", re.IGNORECASE),
    "generative": re.compile(r"GAN|VAE|Diffusion|UNet|Generator|Discriminator", re.IGNORECASE),
}

_FRAMEWORK_PATTERNS = {
    "pytorch": re.compile(r"import torch|from torch|nn\.Module", re.IGNORECASE),
    "tensorflow": re.compile(r"import tensorflow|from tensorflow|tf\.keras", re.IGNORECASE),
    "scikit_learn": re.compile(r"from sklearn|import sklearn", re.IGNORECASE),
    "huggingface": re.compile(r"from transformers|AutoModel|AutoTokenizer|pipeline\(", re.IGNORECASE),
    "xgboost": re.compile(r"import xgboost|xgb\.XGB", re.IGNORECASE),
    "lightgbm": re.compile(r"import lightgbm|lgb\.LGB", re.IGNORECASE),
    "jax": re.compile(r"import jax|from jax|from flax", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# Metric Patterns
# ---------------------------------------------------------------------------

_METRIC_PATTERNS = {
    "accuracy": re.compile(r"accuracy_score|accuracy|\.acc\b", re.IGNORECASE),
    "f1_score": re.compile(r"f1_score|f1-score|f1\b", re.IGNORECASE),
    "precision": re.compile(r"precision_score|precision\b", re.IGNORECASE),
    "recall": re.compile(r"recall_score|recall\b", re.IGNORECASE),
    "auc_roc": re.compile(r"roc_auc|auc\b|roc_curve", re.IGNORECASE),
    "mse": re.compile(r"mean_squared_error|mse\b", re.IGNORECASE),
    "rmse": re.compile(r"rmse\b|root_mean_squared", re.IGNORECASE),
    "mae": re.compile(r"mean_absolute_error|mae\b", re.IGNORECASE),
    "r2": re.compile(r"r2_score|r_squared|R²", re.IGNORECASE),
    "loss": re.compile(r"CrossEntropyLoss|BCELoss|MSELoss|loss\.item\(\)", re.IGNORECASE),
    "bleu": re.compile(r"bleu_score|BLEU\b|corpus_bleu", re.IGNORECASE),
    "perplexity": re.compile(r"perplexity|ppl\b", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# File Walker
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "vendor",
    "dist", "build", ".next", "target", ".gradle",
}

_ML_EXTS = {".py", ".ipynb", ".r", ".R", ".jl"}


def _walk_ml_files(repo_dir: str) -> List[tuple[str, str]]:
    """Walk repo and yield (relative_path, content) for ML-relevant files."""
    results = []
    root = Path(repo_dir)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in _ML_EXTS:
                continue
            fpath = Path(dirpath) / fname
            if fpath.stat().st_size > 1_000_000:  # skip >1MB
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                # For notebooks, extract source cells
                if ext == ".ipynb":
                    try:
                        nb = json.loads(content)
                        cells = nb.get("cells", [])
                        content = "\n".join(
                            "\n".join(c.get("source", []))
                            for c in cells
                            if c.get("cell_type") == "code"
                        )
                    except json.JSONDecodeError:
                        continue
                results.append((str(rel_dir / fname), content))
            except (OSError, UnicodeDecodeError):
                continue
    return results


# ---------------------------------------------------------------------------
# Subcommand: stages
# ---------------------------------------------------------------------------

def cmd_stages(repo_dir: str) -> Dict[str, Any]:
    """Detect ML pipeline stages present in the codebase."""
    stage_evidence: Dict[str, List[str]] = {}

    for rel_path, content in _walk_ml_files(repo_dir):
        for stage_name, stage_info in _ML_STAGES.items():
            for pattern in stage_info["patterns"]:
                if pattern.search(content):
                    stage_evidence.setdefault(stage_name, []).append(rel_path)
                    break  # one match per stage per file is enough

    features = []
    for stage_name, files in stage_evidence.items():
        desc = _ML_STAGES[stage_name]["description"]
        features.append({
            "name": stage_name,
            "description": f"{desc}. Found in {len(files)} file(s): {', '.join(files[:3])}",
            "confidence": min(0.9, 0.6 + 0.1 * len(files)),
            "source_modules": files[:5],
        })

    return {
        "stages_detected": list(stage_evidence.keys()),
        "stage_file_count": {k: len(v) for k, v in stage_evidence.items()},
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: models
# ---------------------------------------------------------------------------

def cmd_models(repo_dir: str) -> Dict[str, Any]:
    """Detect model architectures and ML frameworks."""
    model_types: Dict[str, List[str]] = {}
    frameworks: Dict[str, List[str]] = {}

    for rel_path, content in _walk_ml_files(repo_dir):
        for mtype, pattern in _MODEL_TYPES.items():
            if pattern.search(content):
                model_types.setdefault(mtype, []).append(rel_path)

        for fw, pattern in _FRAMEWORK_PATTERNS.items():
            if pattern.search(content):
                frameworks.setdefault(fw, []).append(rel_path)

    features = []
    for mtype, files in model_types.items():
        features.append({
            "name": f"{mtype}_model",
            "description": f"{mtype.replace('_', ' ').title()} model architecture detected in {len(files)} file(s)",
            "confidence": min(0.9, 0.7 + 0.05 * len(files)),
            "source_modules": files[:3],
        })

    return {
        "model_types": list(model_types.keys()),
        "frameworks": list(frameworks.keys()),
        "framework_files": {k: len(v) for k, v in frameworks.items()},
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: metrics
# ---------------------------------------------------------------------------

def cmd_metrics(repo_dir: str) -> Dict[str, Any]:
    """Detect evaluation metrics used in the codebase."""
    metrics_found: Dict[str, List[str]] = {}

    for rel_path, content in _walk_ml_files(repo_dir):
        for metric_name, pattern in _METRIC_PATTERNS.items():
            if pattern.search(content):
                metrics_found.setdefault(metric_name, []).append(rel_path)

    return {
        "metrics_detected": list(metrics_found.keys()),
        "metric_files": {k: v[:3] for k, v in metrics_found.items()},
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ML Pipeline Skill Pack — Extract ML stages, models, and metrics"
    )
    parser.add_argument("repo_dir", help="Path to cloned repository root")
    parser.add_argument("output_file", help="Path to write JSON output")
    parser.add_argument(
        "subcommand",
        choices=["stages", "models", "metrics", "extract"],
        help="Extraction subcommand",
    )
    args = parser.parse_args()

    if not Path(args.repo_dir).is_dir():
        print(f"Error: {args.repo_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    handlers = {
        "stages": cmd_stages,
        "models": cmd_models,
        "metrics": cmd_metrics,
        "extract": lambda d: {
            **cmd_stages(d),
            "models": cmd_models(d),
            "metrics": cmd_metrics(d),
        },
    }

    result = handlers[args.subcommand](args.repo_dir)

    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Success! {args.subcommand} → {out} ({len(result.get('features', []))} features)")


if __name__ == "__main__":
    main()
