import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from app.eca.language_loader import get_role, is_entry_point as _is_ep

# NOTE: All language-specific data (extensions, entry points) is loaded from
# app/eca/config/language_registry.json — no hardcoding here.

def classify_file(file_path_str: str, extension: str) -> tuple[str, float]:
    """Classify a file into a category using path heuristics + language registry."""
    path = Path(file_path_str)
    filename = path.name.lower()
    parts = [p.lower() for p in path.parts]
    ext = extension.lower()

    # 1. Entry Point — sourced from language registry
    if _is_ep(filename):
        return "entry_point", 1.0

    # 2. Config — universal config extensions from registry
    if get_role(ext) == "config":
        return "config", 0.9
    if "config" in filename or "settings" in filename or "setup" in filename:
        return "config", 0.8
    if any(part in {"config", "configs", "settings", ".idea", ".vscode"} for part in parts):
        return "config", 0.7

    # 3. Route
    if any(p in {"routes", "route", "controllers", "controller", "api", "routers"} for p in parts):
        return "route", 0.9
    if "route" in filename or "controller" in filename:
        return "route", 0.8

    # 4. Service
    if any(p in {"service", "services", "logic", "usecase", "usecases", "providers", "core"} for p in parts):
        return "service", 0.9
    if "service" in filename or "logic" in filename:
        return "service", 0.8

    # 5. Component — sourced from language registry (frontend role)
    if any(p in {"components", "component", "views", "view", "pages", "page", "ui", "templates", "layouts"} for p in parts):
        return "component", 0.9
    if get_role(ext) == "frontend":
        return "component", 0.8
    if "component" in filename:
        return "component", 0.8

    # 6. Unknown
    return "unknown", 0.0

def run_classifier(scan_output: Dict[str, Any]) -> Dict[str, Any]:
    classified_files = []
    
    for file_info in scan_output.get("files", []):
        path_str = file_info.get("path", "")
        ext = file_info.get("extension", "")
        
        category, confidence = classify_file(path_str, ext)
        
        classified_files.append({
            "path": path_str,
            "category": category,
            "confidence": confidence
        })
        
    return {
        "classified_files": classified_files
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FileClassifier: Classify files from RepoScanner output.")
    parser.add_argument("scan_input", help="Path to the RepoScanner JSON output")
    parser.add_argument("--out", default="runtime/outputs/classified_files.json", help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.scan_input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.")
        exit(1)
        
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            scan_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {input_path}: {e}")
            exit(1)
        
    result = run_classifier(scan_data)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Classification complete. Classified {len(result['classified_files'])} files.")
    
    # Optional: Print summary
    summary = {}
    for item in result['classified_files']:
        cat = item['category']
        summary[cat] = summary.get(cat, 0) + 1
    
    for cat, count in summary.items():
        print(f"  - {cat}: {count}")
        
    print(f"Output saved to {out_path}")
