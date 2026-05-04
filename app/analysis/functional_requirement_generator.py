"""
functional_requirement_generator.py — Layer 3 Tool
-----------------------------------------------------
FunctionalRequirementGenerator

Input:
  List of features (dict):
  [
    {
      "id": str,
      "name": str,          # snake_case
      "description": str,
      "confidence": float
    }
  ]

Output (strict JSON):
  {
    "functional_requirements": [
      {
        "id": "FR-N",
        "description": str,
        "linked_feature": str,
        "acceptance_criteria": [str]
      }
    ]
  }

Rules:
- Each feature -> 1-3 requirements
- Must be testable
- No vague wording
- No "should be fast" type statements
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any

from app.schemas.models import FunctionalRequirement, FunctionalRequirementsResult

# ---------------------------------------------------------------------------
# Strict Testable Templates
# ---------------------------------------------------------------------------

# Banned vague words: "efficient", "fast", "user-friendly", "scalable", "robust"

FR_TEMPLATES = {
    "database_access_layer": [
        {
            "description": "The system SHALL execute CRUD operations against the primary datastore.",
            "acceptance_criteria": [
                "Verify that create, read, update, and delete operations succeed against the test database.",
                "Verify that operations on non-existent records return an explicit Not Found error (e.g., HTTP 404)."
            ]
        },
        {
            "description": "The system SHALL enforce database connection pooling to handle concurrent requests.",
            "acceptance_criteria": [
                "Verify that maximum active connections do not exceed the configured limit during load testing."
            ]
        }
    ],
    "authentication_credential_management": [
        {
            "description": "The system SHALL validate user credentials and issue a signed authentication token upon success.",
            "acceptance_criteria": [
                "Verify that valid credentials return HTTP 200 with a valid token payload.",
                "Verify that invalid credentials return HTTP 401 Unauthorized."
            ]
        },
        {
            "description": "The system SHALL reject requests to protected endpoints if the authentication token is missing or expired.",
            "acceptance_criteria": [
                "Verify that a request without an Authorization header returns HTTP 401.",
                "Verify that a request with an expired token returns HTTP 401."
            ]
        }
    ],
    "rest_api_routing": [
        {
            "description": "The system SHALL route incoming HTTP requests to their corresponding endpoint handlers.",
            "acceptance_criteria": [
                "Verify that registered endpoints return the expected HTTP status code for valid requests.",
                "Verify that requests to unregistered paths return HTTP 404 Not Found."
            ]
        }
    ],
    "user_management": [
        {
            "description": "The system SHALL allow creation of new user records with unique identifiers.",
            "acceptance_criteria": [
                "Verify that a new user record is successfully persisted when valid data is provided.",
                "Verify that creating a user with an already existing identifier (e.g., email) returns an HTTP 409 Conflict."
            ]
        }
    ]
}

def generate_generic_requirements(feature_name: str, description: str) -> List[Dict[str, Any]]:
    """
    Generate generic, testable functional requirements for unknown features.
    """
    display_name = feature_name.replace("_", " ").title()
    
    return [
        {
            "description": f"The system SHALL expose an interface or endpoint to execute the {display_name} capability.",
            "acceptance_criteria": [
                f"Verify that the {display_name} interface accepts correctly formatted input without error.",
                f"Verify that malformed input is rejected with a structured error response."
            ]
        },
        {
            "description": f"The system SHALL record an audit or standard log entry upon execution of the {display_name} capability.",
            "acceptance_criteria": [
                "Verify that a log entry containing the operation name and outcome is generated upon execution."
            ]
        }
    ]

def generate_requirements(features: List[Dict]) -> FunctionalRequirementsResult:
    """
    Generate 1-3 testable functional requirements per feature.
    """
    all_frs: List[FunctionalRequirement] = []
    fr_counter = 0

    for feat in features:
        feat_name: str = feat.get("name", "")
        if not feat_name:
            continue
            
        confidence: float = float(feat.get("confidence", 0.5))
        
        # Determine number of requirements to extract (1 to 3 based on confidence)
        if confidence >= 0.8:
            max_frs = 3
        elif confidence >= 0.5:
            max_frs = 2
        else:
            max_frs = 1

        # Look up feature templates or use generic fallback
        templates = FR_TEMPLATES.get(feat_name.lower())
        if not templates:
            templates = generate_generic_requirements(feat_name, feat.get("description", ""))

        selected = templates[:max_frs]

        for tmpl in selected:
            fr_counter += 1
            all_frs.append(FunctionalRequirement(
                id=f"FR-{fr_counter}",
                description=tmpl["description"],
                linked_feature=feat_name,
                acceptance_criteria=tmpl["acceptance_criteria"],
            ))

    return FunctionalRequirementsResult(functional_requirements=all_frs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FunctionalRequirementGenerator: Generates FRs from features."
    )
    parser.add_argument("--features", required=True, help="Path to features JSON")
    parser.add_argument("--out", default=None, help="Output path")
    args = parser.parse_args()

    feat_path = Path(args.features)
    if not feat_path.exists():
        print(f"[ERROR] File not found: {feat_path}", file=sys.stderr)
        raise SystemExit(1)

    with open(feat_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    # Robust extraction
    feat_list: List[Dict] = []
    if isinstance(raw, dict):
        if "features" in raw:
            feat_list = raw["features"]
        elif "validated_features" in raw:
            feat_list = raw["validated_features"]
        else:
            feat_list = []
    elif isinstance(raw, list):
        feat_list = raw

    result = generate_requirements(feat_list)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
        print(f"[OK] Requirements written to {out_path}", file=sys.stderr)
    else:
        print(output_json)
