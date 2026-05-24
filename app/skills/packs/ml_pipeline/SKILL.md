---
name: ml-pipeline-analysis
version: "1.0"
description: >-
  Analysis pack for machine learning and data science repositories.
  Activate when Jupyter notebooks (.ipynb), ML framework dependencies
  (sklearn, torch, tensorflow, keras, xgboost), or model training
  patterns are detected.
  DO NOT activate for: web APIs without ML, mobile apps, CLI tools.

detection_signals:
  evidence_flags: []
  dependency_keywords: [scikit-learn, sklearn, torch, pytorch, tensorflow, keras, xgboost, lightgbm, transformers, huggingface, datasets, mlflow, wandb, optuna, catboost, jax, flax]
  file_patterns: ["**/*.ipynb", "**/models/**", "**/training/**", "**/notebooks/**", "**/experiments/**", "**/model_*", "**/train_*"]
  confidence_threshold: 0.5

nfr_emphasis: [model_latency, inference_throughput, model_accuracy, training_reproducibility, data_privacy]
memory_tags: [ml_pipeline, model_training, data_processing, feature_engineering]
brd_section_notes:
  section_5: "Focus on ML pipeline stages: data ingestion, feature engineering, training, evaluation, serving"
  section_6: "Include model accuracy targets, inference latency SLAs, retraining frequency"
  section_7: "Emphasise training data requirements, data quality standards, and data versioning"
  section_8: "Document ML infrastructure: GPU requirements, model registry, experiment tracking"
---

# ML Pipeline Analysis Skill Pack

## Overview

This skill pack extracts machine learning pipeline stages, model architectures,
evaluation metrics, and data processing patterns from ML/data science repositories.

## When This Skill Activates

- Dependencies include ML frameworks: sklearn, PyTorch, TensorFlow, HuggingFace
- File tree contains `.ipynb` notebooks, `models/`, `training/` directories
- Python files import ML libraries or define model classes

## Extraction Scripts

### Script 1: ML Pipeline Stages

```bash
python scripts/model_extractor.py <repo_dir> <output.json> stages
```

Extracts the ML pipeline stages: data loading, preprocessing, feature engineering,
model definition, training loop, evaluation, and serving/export.

### Script 2: Model Architecture Detection

```bash
python scripts/model_extractor.py <repo_dir> <output.json> models
```

Detects model types (classification, regression, NLP, CV, etc.) and frameworks used.

### Script 3: Evaluation Metrics

```bash
python scripts/model_extractor.py <repo_dir> <output.json> metrics
```

Extracts evaluation metrics (accuracy, F1, AUC, RMSE, etc.) used in the codebase.

## How Results Are Used

- `stages` → generates features for each pipeline stage
- `models` → informs product understanding (ML product archetype)
- `metrics` → enriches NFR generation with measurable targets

## Common Mistakes

- Do NOT count utility/helper functions as pipeline stages
- Do NOT assume production deployment exists just because training code exists
- Jupyter notebooks may be exploratory — weigh them at lower confidence

## Fallback Behavior

If scripts fail, pipeline continues with standard feature extraction.
ML repositories still produce valid BRDs without this skill.
