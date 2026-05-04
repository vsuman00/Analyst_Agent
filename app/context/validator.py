import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

CORE_STRUCTURE_KEYWORDS = {"src", "app", "lib", "main", "backend", "frontend", "source", "core"}

def validate_context(normalized_data: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[str] = []
    score = 1.0
    
    modules = normalized_data.get("normalized_modules", [])
    
    if not modules:
        issues.append("No modules found in the context.")
        return {
            "score": 0.0,
            "issues": issues,
            "valid": False
        }
        
    has_core_structure = False
    
    for module in modules:
        name = module.get("name", "unnamed")
        files = module.get("files", [])
        confidence = float(module.get("confidence", 1.0))
        
        # Check for empty modules
        if not files:
            issues.append(f"Empty module: {name}")
            score -= 0.1
            
        # Check for low confidence modules
        if confidence < 0.5:
            issues.append(f"Low confidence ({confidence}) for module: {name}")
            score -= 0.1
            
        # Check for core structural patterns
        if any(keyword in name for keyword in CORE_STRUCTURE_KEYWORDS):
            has_core_structure = True
            
    if not has_core_structure:
        issues.append("Missing core application structure (e.g., no module named src, app, lib, backend, or frontend).")
        score -= 0.3
        
    # Cap score at 0.0 to prevent negatives
    score = max(0.0, round(score, 2))
    
    # Validation criteria: a healthy score and the presence of core structural folders
    is_valid = score >= 0.7 and has_core_structure
    
    return {
        "score": score,
        "issues": issues,
        "valid": is_valid
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ContextValidator: Validate normalized context.")
    parser.add_argument("normalized_input", help="Path to the ContextNormalizer JSON output")
    parser.add_argument("--out", default="runtime/outputs/validation_result.json", help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.normalized_input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.")
        exit(1)
        
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            normalized_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {input_path}: {e}")
            exit(1)
            
    result = validate_context(normalized_data)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Validation complete.")
    print(f"Valid: {result['valid']}, Score: {result['score']}")
    if result['issues']:
        print("Issues found:")
        for issue in result['issues']:
            print(f"  - {issue}")
            
    print(f"Output saved to {out_path}")
