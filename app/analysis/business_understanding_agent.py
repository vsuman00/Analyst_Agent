"""
business_understanding_agent.py — Layer 3 Tool
-----------------------------------------------
BusinessUnderstandingAgent

Inputs:
  - features    : List of feature dictionaries
  - system_type : String representing the system architecture type

Output (strict JSON):
  {
    "business_context": {
      "product_type": str,
      "primary_users": [str],
      "core_value": str
    }
  }

Strict Rules:
  - Derive ONLY from features
  - No assumptions beyond technical scope
  - Keep concise
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any

from app.schemas.models import BusinessContext, BusinessUnderstandingResult

# ---------------------------------------------------------------------------
# Signal Registries
# ---------------------------------------------------------------------------

USER_SIGNALS = {
    "admin": "Administrators",
    "dashboard": "System Operators",
    "auth": "Authenticated Users",
    "customer": "Customers",
    "client": "Clients",
    "patient": "Patients",
    "vet": "Veterinarians",
    "student": "Students",
    "payment": "Subscribers",
    "developer": "Developers",
    "api": "API Consumers"
}

PRODUCT_TYPE_SIGNALS = {
    "dashboard": "Analytics Platform",
    "auth": "Identity Management System",
    "payment": "E-Commerce/Billing System",
    "tweet": "Social Platform",
    "post": "Content/Social Platform",
    "feed": "Content Distribution System",
    "api": "API Backend Service",
    "clinic": "Clinic Management System",
    "booking": "Booking/Reservation System",
    "data": "Data Management Platform",
    "search": "Search/Discovery Platform"
}

def understand_business(
    features: List[Dict[str, Any]],
    system_type: str
) -> BusinessUnderstandingResult:
    """
    Derive business context deterministically from features and system type.
    """
    product_type_votes = {}
    users_set = set()
    
    # 1. Analyze features for signals
    for feature in features:
        name_lower = feature.get("name", "").lower()
        desc_lower = feature.get("description", "").lower()
        combined_text = f"{name_lower} {desc_lower}"
        
        # Detect product types
        for kw, ptype in PRODUCT_TYPE_SIGNALS.items():
            if kw in combined_text:
                product_type_votes[ptype] = product_type_votes.get(ptype, 0) + 1
                
        # Detect primary users
        for kw, user_type in USER_SIGNALS.items():
            if kw in combined_text:
                users_set.add(user_type)

    # 2. Resolve Product Type
    if product_type_votes:
        product_type = max(product_type_votes.items(), key=lambda x: x[1])[0]
    else:
        # Fallback to pure technical description based on system type
        if system_type and system_type != "unknown":
            product_type = f"{system_type.capitalize()} Software System"
        else:
            product_type = "Technical Software System"
            
    # 3. Resolve Primary Users
    primary_users = sorted(list(users_set))
    if not primary_users:
        primary_users = ["General System Users"]
        
    # 4. Resolve Core Value (Strictly derived from top features)
    core_value_features = []
    # Sort by confidence
    sorted_features = sorted(features, key=lambda f: float(f.get("confidence", 0)), reverse=True)
    # Take top 3 for core value statement
    for feat in sorted_features[:3]:
        name = feat.get("name", "")
        if name:
            core_value_features.append(name.replace("_", " ").title())
            
    if core_value_features:
        if len(core_value_features) == 1:
            core_value = f"Delivers {core_value_features[0]} functionality."
        elif len(core_value_features) == 2:
            core_value = f"Delivers {core_value_features[0]} and {core_value_features[1]} functionality."
        else:
            core_value = f"Delivers {core_value_features[0]}, {core_value_features[1]}, and {core_value_features[2]} functionality."
    else:
        core_value = "Delivers basic functional capabilities."

    return BusinessUnderstandingResult(
        business_context=BusinessContext(
            product_type=product_type,
            primary_users=primary_users,
            core_value=core_value
        )
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BusinessUnderstandingAgent")
    parser.add_argument("--features", required=True, help="Path to features JSON")
    parser.add_argument("--system-type", default="unknown", help="System type descriptor")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()
    
    features_path = Path(args.features)
    if not features_path.exists():
        print(f"[ERROR] Features file not found: {features_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(features_path, "r", encoding="utf-8") as f:
        raw_features = json.load(f)
        
    # Extract feature list robustly
    feature_list = []
    if isinstance(raw_features, dict):
        if "features" in raw_features:
            feature_list = raw_features["features"]
        elif "validated_features" in raw_features:
            feature_list = raw_features["validated_features"]
        else:
            feature_list = []
    elif isinstance(raw_features, list):
        feature_list = raw_features
        
    result = understand_business(feature_list, args.system_type)
    
    output_json = result.model_dump_json(indent=2)
    
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[OK] Business context written to {out_path}", file=sys.stderr)
    else:
        print(output_json)
