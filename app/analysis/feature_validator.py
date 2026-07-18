"""
feature_validator.py — Layer 3 Tool
--------------------------------------
FeatureValidator

Input:
  List of ExtractedFeature dicts (output of FeatureExtractionAgent):
  [
    {
      "id": str,
      "name": str,
      "description": str,
      "source_modules": [str],
      "confidence": float
    }
  ]

Tasks (applied in order):
  1. DEDUPLICATION   — exact-name duplicates collapsed; description and confidence
                       taken from the highest-confidence entry.
  2. OVERLAP MERGING — semantically overlapping features are merged using a
                       hand-coded MERGE_GROUPS table. Only features whose
                       canonical_key appears in a merge group are candidates.
                       No new features are created; the group produces one output
                       entry whose description comes from the highest-confidence member.
  3. NAME NORMALISATION — output name is snake_case derived from the display name.
                          Display name is preserved as the description's first sentence
                          label; the normalized name is what populates the `name` field.

Output schema (strict):
  {
    "validated_features": [
      {
        "id": str,           # feat-NNN, re-indexed after all passes
        "name": str,         # snake_case
        "description": str,  # from highest-confidence source; NOT rewritten
        "confidence": float, # max-pooled; never inflated
        "merge_of": [str]    # original input ids collapsed into this entry
      }
    ]
  }

Invariants:
  - No feature is introduced that was absent from the input
  - confidence is only ever max-pooled (never averaged up or inflated)
  - description is copied verbatim from the best-confidence input member
  - merge_of records every original id consumed

Usage (CLI):
  python -m app.analysis.feature_validator \
    --features runtime/outputs/extracted_features.json \
    [--out     runtime/outputs/validated_features.json]
"""

from __future__ import annotations

import re
import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

from app.schemas.models import ValidatedFeature, FeatureValidationResult

# ---------------------------------------------------------------------------
# Merge groups
# Each entry maps a canonical group name (snake_case) → set of canonical_keys
# that should be collapsed into it.
# canonical_key = _to_snake(feature.name)
#
# Rules:
#   - Only features whose canonical_key is present in ANY group set are merged.
#   - Features not in any group pass through untouched.
#   - A feature can belong to at most one group (first match wins).
#   - The group name itself becomes the output snake_case name.
# ---------------------------------------------------------------------------

MERGE_GROUPS: Dict[str, Set[str]] = {
    # Infrastructure / deployment layer
    "container_and_cicd_config": {
        "container_orchestration_config",
        "ci_cd_pipeline_config",
    },
    # Auth + secrets share the same trust boundary
    "authentication_and_credential_management": {
        "token_based_authentication",
        "secret_credential_management",
    },
    # Domain model + service are tightly coupled DDD concepts
    "domain_model_and_service_layer": {
        "domain_entity_modelling",
        "domain_service_layer",
    },
}

# Human-readable display names for merged groups (used in description prefix)
MERGE_GROUP_DISPLAY: Dict[str, str] = {
    "container_and_cicd_config":                   "Container Orchestration & CI/CD Config",
    "authentication_and_credential_management":    "Authentication & Credential Management",
    "domain_model_and_service_layer":              "Domain Model & Service Layer",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_snake(name: str) -> str:
    """
    Convert any feature display name to a stable snake_case key.

    Steps:
      1. Lower-case the entire string
      2. Replace runs of non-alphanumeric characters with a single underscore
      3. Strip leading/trailing underscores
    """
    lowered = name.lower()
    snaked = re.sub(r"[^a-z0-9]+", "_", lowered)
    return snaked.strip("_")


def _best(features: List[Dict]) -> Dict:
    """Return the dict with the highest confidence (tiebreak: first seen)."""
    return max(features, key=lambda f: f["confidence"])


# ---------------------------------------------------------------------------
# Pass 1 — Exact-name deduplication
# ---------------------------------------------------------------------------

def _deduplicate(features: List[Dict]) -> List[Dict]:
    """
    Collapse entries with identical names (case-insensitive).

    Strategy:
      - Group by lower(name).
      - Keep description + confidence from the highest-confidence entry.
      - Merge merge_of lists (start with id if merge_of is absent).
    """
    groups: Dict[str, List[Dict]] = {}
    for feat in features:
        key = feat["name"].lower()
        groups.setdefault(key, []).append(feat)

    result: List[Dict] = []
    for key, group in groups.items():
        best = _best(group)
        all_ids = _all_ids(group)
        result.append({
            "name":        best["name"],
            "description": best["description"],
            "confidence":  best["confidence"],
            "merge_of":    all_ids,
        })
    return result


def _all_ids(group: List[Dict]) -> List[str]:
    """Collect all original input ids from a group, expanding merge_of if present."""
    ids: List[str] = []
    for feat in group:
        if feat.get("merge_of"):
            ids.extend(feat["merge_of"])
        elif feat.get("id"):
            ids.append(feat["id"])
    return sorted(set(ids))


# ---------------------------------------------------------------------------
# Pass 2 — Overlap merging via MERGE_GROUPS
# ---------------------------------------------------------------------------

def _merge_overlapping(features: List[Dict]) -> List[Dict]:
    """
    Apply MERGE_GROUPS: collapse semantically overlapping features into one entry.

    A feature is matched to a group if its canonical snake_case name is in the
    group's key set.  Features with no group membership are passed through
    unchanged.

    The merged entry's description comes from the highest-confidence member.
    Confidence is max-pooled.
    merge_of collects all original ids from all members.
    """
    # Build reverse index: canonical_key → group_name
    key_to_group: Dict[str, str] = {}
    for group_name, members in MERGE_GROUPS.items():
        for member_key in members:
            key_to_group[member_key] = group_name

    # Bucket features
    group_buckets: Dict[str, List[Dict]] = {g: [] for g in MERGE_GROUPS}
    ungrouped: List[Dict] = []

    for feat in features:
        ck = _to_snake(feat["name"])
        group = key_to_group.get(ck)
        if group:
            group_buckets[group].append(feat)
        else:
            ungrouped.append(feat)

    merged: List[Dict] = []

    for group_name, members in group_buckets.items():
        if not members:
            continue  # no members from input — skip group entirely

        if len(members) == 1:
            # Only one member matched — pass through with the group name applied
            feat = members[0]
            merged.append({
                "name":        MERGE_GROUP_DISPLAY.get(group_name, group_name),
                "description": feat["description"],
                "confidence":  feat["confidence"],
                "merge_of":    _all_ids(members),
            })
        else:
            best = _best(members)
            max_conf = max(f["confidence"] for f in members)
            merged.append({
                "name":        MERGE_GROUP_DISPLAY.get(group_name, group_name),
                "description": best["description"],
                "confidence":  round(max_conf, 2),
                "merge_of":    _all_ids(members),
            })

    return ungrouped + merged


# ---------------------------------------------------------------------------
# Pass 3 — Name normalisation
# ---------------------------------------------------------------------------

def _normalise_names(features: List[Dict]) -> List[Dict]:
    """
    Convert the display name to snake_case for the `name` field.
    description is left untouched.
    """
    out = []
    for feat in features:
        out.append({
            **feat,
            "name": _to_snake(feat["name"]),
        })
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_features(features: List[Dict]) -> FeatureValidationResult:
    """
    Run all three validation passes and return a FeatureValidationResult.

    Parameters
    ----------
    features : list of dicts matching ExtractedFeature schema
        [{ "id": str, "name": str, "description": str,
           "source_modules": [str], "confidence": float }]

    Returns
    -------
    FeatureValidationResult
        { "validated_features": [ ValidatedFeature, ... ] }

    Invariants enforced:
      - No feature in output was absent from input
      - confidence values are never inflated beyond max of inputs
      - description is copied verbatim from best-confidence source
    """
    if not features:
        return FeatureValidationResult(validated_features=[])

    # --- Pass 1: exact deduplication ---
    after_dedup = _deduplicate(features)

    # --- Pass 2: overlap merging ---
    after_merge = _merge_overlapping(after_dedup)

    # --- Pass 3: name normalisation ---
    after_norm = _normalise_names(after_merge)

    # --- Sort: confidence desc, name asc ---
    after_norm.sort(key=lambda f: (-f["confidence"], f["name"]))

    # --- Re-index IDs ---
    validated: List[ValidatedFeature] = []
    for i, feat in enumerate(after_norm, start=1):
        validated.append(
            ValidatedFeature(
                id=f"feat-{i:03d}",
                name=feat["name"],
                description=feat["description"],
                confidence=feat["confidence"],
                merge_of=sorted(feat.get("merge_of", [])),
            )
        )

    return FeatureValidationResult(validated_features=validated)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "FeatureValidator: Deduplicate, merge overlapping, and normalise "
            "features from FeatureExtractionAgent output. Returns JSON only."
        )
    )
    parser.add_argument(
        "--features",
        default="runtime/outputs/extracted_features.json",
        help="Path to extracted_features.json (default: runtime/outputs/extracted_features.json)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write output JSON (prints to stdout if omitted)",
    )
    args = parser.parse_args()

    features_path = Path(args.features)
    if not features_path.exists():
        print(f"[ERROR] File not found: {features_path}", file=sys.stderr)
        raise SystemExit(1)

    with open(features_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    # Accept { "features": [...] } or bare list
    features_list: List[Dict] = (
        raw.get("features", raw) if isinstance(raw, dict) else raw
    )

    result = validate_features(features_list)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
        print(f"[OK] Validated features written to {out_path}", file=sys.stderr)
    else:
        print(output_json)

    before = len(features_list)
    after  = len(result.validated_features)
    merged_count = sum(1 for f in result.validated_features if len(f.merge_of) > 1)
    print(
        f"\n[SUMMARY] input={before} → output={after} "
        f"(deduplicated/merged {before - after}, merged_groups={merged_count})",
        file=sys.stderr,
    )
