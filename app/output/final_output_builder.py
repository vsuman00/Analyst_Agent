import os
import json
import argparse
from pathlib import Path
from typing import Dict, Any

def build_final_output(repo_scan: Dict, classified: Dict, chunks: Dict, modules: Dict, validation: Dict) -> Dict[str, Any]:
    """Combines all partial outputs into the final deterministic schema."""
    
    repo_name = repo_scan.get("repo_name", "unknown")
    
    # Unify files: Merge repo_scan files (size/extension) with classified files (category/confidence)
    files_map = {}
    for f in repo_scan.get("files", []):
        path = f.get("path")
        if path:
            files_map[path] = {
                "path": path,
                "extension": f.get("extension", ""),
                "size": f.get("size", 0),
                "category": "unknown",
                "confidence": 0.0
            }
            
    for f in classified.get("classified_files", []):
        path = f.get("path")
        if path and path in files_map:
            files_map[path]["category"] = f.get("category", "unknown")
            files_map[path]["confidence"] = f.get("confidence", 0.0)
            
    files_list = list(files_map.values())
    files_list.sort(key=lambda x: x["path"])
    
    # Strip unnecessary top-level keys and structure cleanly
    return {
        "repo_name": repo_name,
        "files": files_list,
        "modules": modules.get("normalized_modules", []),
        "chunks": chunks.get("chunks", []),
        "validation": {
            "score": validation.get("score", 0.0),
            "issues": validation.get("issues", []),
            "valid": validation.get("valid", False)
        }
    }

def load_json(path_str: str) -> Dict[str, Any]:
    path = Path(path_str)
    if not path.exists():
        print(f"Error: Required input file {path} does not exist.")
        exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {path}: {e}")
            exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinalOutputBuilder: Combine all pipeline outputs into one JSON payload.")
    parser.add_argument("--scan", default="runtime/outputs/repo_scan.json", help="Path to repo_scan.json")
    parser.add_argument("--classified", default="runtime/outputs/classified_files.json", help="Path to classified_files.json")
    parser.add_argument("--chunks", default="runtime/outputs/chunks_output.json", help="Path to chunks_output.json")
    parser.add_argument("--modules", default="runtime/outputs/normalized_context.json", help="Path to normalized_context.json")
    parser.add_argument("--validation", default="runtime/outputs/validation_result.json", help="Path to validation_result.json")
    parser.add_argument("--out", default="runtime/outputs/final_payload.json", help="Output JSON file path")
    args = parser.parse_args()

    repo_scan_data = load_json(args.scan)
    classified_data = load_json(args.classified)
    chunks_data = load_json(args.chunks)
    modules_data = load_json(args.modules)
    validation_data = load_json(args.validation)
    
    result = build_final_output(
        repo_scan_data,
        classified_data,
        chunks_data,
        modules_data,
        validation_data
    )
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print("Final output successfully built.")
    print(f"Validation Valid? {result['validation']['valid']} (Score: {result['validation']['score']})")
    print(f"Compiled {len(result['files'])} files, {len(result['modules'])} modules, and {len(result['chunks'])} chunks.")
    print(f"Output saved to {out_path}")
