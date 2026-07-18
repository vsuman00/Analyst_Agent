import os
import json
import argparse
from typing import Dict, Any, List
from app.schemas.models import ECAOutput, NormalizedContext, Feature

FEATURE_KEYWORDS = {
    "Authentication": ["auth", "login", "signup", "jwt", "session", "passport"],
    "Database": ["db", "database", "sql", "mongo", "postgres", "redis", "models", "schema"],
    "API": ["api", "routes", "controllers", "endpoints", "graphql", "rest"],
    "Payment": ["payment", "stripe", "billing", "checkout", "cart"],
    "Search": ["search", "elastic", "query", "filter"],
    "User Management": ["user", "profile", "account", "settings", "role"]
}

def analyze_context(eca: ECAOutput) -> NormalizedContext:
    features_dict: Dict[str, Feature] = {}
    modules_set = set()
    gaps = []
    
    # 1. Feature Extraction from chunks (filenames and content snippets)
    for chunk in eca.chunks:
        filename_lower = chunk.file.lower()
        content_lower = chunk.content.lower()
        
        for feature_name, keywords in FEATURE_KEYWORDS.items():
            for kw in keywords:
                if kw in filename_lower or kw in content_lower:
                    if feature_name not in features_dict:
                        features_dict[feature_name] = Feature(name=feature_name, confidence=0.0, sources=[])
                    
                    if chunk.file not in features_dict[feature_name].sources:
                        features_dict[feature_name].sources.append(chunk.file)
                        features_dict[feature_name].confidence = min(1.0, round(features_dict[feature_name].confidence + 0.2, 2))

    # 2. Module Detection
    if eca.classified_files.frontend:
        modules_set.add("Frontend UI")
    if eca.classified_files.backend:
        modules_set.add("Backend Services")
    if eca.classified_files.config:
        modules_set.add("Configuration Management")
    if eca.classified_files.docs:
        modules_set.add("Documentation")

    # 3. Gap Analysis
    if not eca.readme:
        gaps.append("Missing or empty README.md")
    
    if not eca.classified_files.docs and eca.readme:
        gaps.append("Minimal documentation (only README found)")
        
    if not any("test" in f.lower() for files in [eca.classified_files.frontend, eca.classified_files.backend] for f in files):
        gaps.append("No obvious test files found")

    return NormalizedContext(
        features=list(features_dict.values()),
        modules=list(modules_set),
        gaps=gaps
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Context from ECA output.")
    parser.add_argument("--eca_in", default="runtime/outputs/eca_output.json", help="Path to ECA input JSON")
    parser.add_argument("--out", default="runtime/outputs/context_output.json", help="Path to Context output JSON")
    args = parser.parse_args()
    
    if not os.path.exists(args.eca_in):
        print(f"Error: ECA input file {args.eca_in} does not exist.")
        exit(1)
        
    with open(args.eca_in, 'r', encoding='utf-8') as f:
        eca_data = json.load(f)
        
    eca_output = ECAOutput(**eca_data)
    context_output = analyze_context(eca_output)
    
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(context_output.model_dump_json(indent=2))
        
    print(f"Context output successfully written to {args.out}")
