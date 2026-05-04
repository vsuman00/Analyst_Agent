import os
import json
import uuid
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any

# Common noise folders that usually don't represent business logic modules
NOISE_MODULES = {
    ".idea", ".vscode", ".git", ".gradle", ".github", ".husky",
    "node_modules", "build", "dist", "out", "target", "bin", "obj", 
    "vendor", "tmp", "temp", "logs", "coverage", "__pycache__"
}

def standardize_name(name: str) -> str:
    """
    Standardize a module name to snake_case format.
    """
    # Remove leading dots if any slipped through
    name = name.lstrip('.')
    # Convert to lowercase
    name = name.lower()
    # Replace non-alphanumeric chars (like spaces or dashes) with underscores
    name = re.sub(r'[^a-z0-9]+', '_', name)
    # Strip leading/trailing underscores
    name = name.strip('_')
    
    return name if name else "unnamed"

def normalize_context(aggregated_data: Dict[str, Any]) -> Dict[str, Any]:
    normalized_map = {}
    
    for module in aggregated_data.get("modules", []):
        raw_name = module.get("module_name", "")
        
        # 1. Remove noise
        if raw_name in NOISE_MODULES or raw_name.startswith('.'):
            continue
            
        # 2. Standardize name
        std_name = standardize_name(raw_name)
        
        # Initialize if not exists
        if std_name not in normalized_map:
            normalized_map[std_name] = {
                # Create a deterministic ID based on the namespace URL and module name
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, std_name)),
                "name": std_name,
                "files": set(),
                "confidence": 1.0 # High confidence as it's structurally deterministic
            }
            
        # 3. Merge duplicate files (if multiple raw modules mapped to the same std_name)
        for f in module.get("files", []):
            normalized_map[std_name]["files"].add(f)
            
    # Format output
    normalized_list = []
    for std_name, mod_data in normalized_map.items():
        normalized_list.append({
            "id": mod_data["id"],
            "name": std_name,
            "files": sorted(list(mod_data["files"])),
            "confidence": mod_data["confidence"]
        })
        
    # Sort for deterministic output
    normalized_list.sort(key=lambda x: x["name"])
    
    return {
        "normalized_modules": normalized_list
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ContextNormalizer: Standardize and clean up aggregated modules.")
    parser.add_argument("aggregated_input", help="Path to the ContextAggregator JSON output")
    parser.add_argument("--out", default="runtime/outputs/normalized_context.json", help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.aggregated_input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.")
        exit(1)
        
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            aggregated_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {input_path}: {e}")
            exit(1)
            
    result = normalize_context(aggregated_data)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Normalization complete. Retained {len(result['normalized_modules'])} core modules.")
    for mod in result['normalized_modules']:
        print(f"  - {mod['name']} (files: {len(mod['files'])})")
    print(f"Output saved to {out_path}")
