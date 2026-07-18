import os
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any

def determine_module_name(file_path_str: str) -> str:
    """
    Determines the module name deterministically based on folder structure.
    Files in the root directory are grouped under 'root'.
    Files in subdirectories are grouped by their top-level directory name.
    """
    path = Path(file_path_str)
    parts = path.parts
    
    if len(parts) > 1:
        # Use the top-level directory as the module name
        return parts[0]
    else:
        # File is in the root directory
        return "root"

def aggregate_context(chunks_data: Dict[str, Any]) -> Dict[str, Any]:
    modules_map: Dict[str, Dict[str, Any]] = {}
    
    for chunk in chunks_data.get("chunks", []):
        file_path = chunk.get("file_path", "")
        chunk_id = chunk.get("chunk_id", "")
        
        if not file_path or not chunk_id:
            continue
            
        module_name = determine_module_name(file_path)
        
        if module_name not in modules_map:
            modules_map[module_name] = {
                "module_name": module_name,
                "files": set(),
                "chunk_ids": []
            }
            
        modules_map[module_name]["files"].add(file_path)
        modules_map[module_name]["chunk_ids"].append(chunk_id)
        
    # Convert sets to lists for JSON serialization
    modules_list = []
    for mod_name, mod_data in modules_map.items():
        modules_list.append({
            "module_name": mod_name,
            "files": sorted(list(mod_data["files"])),
            "chunk_ids": mod_data["chunk_ids"]
        })
        
    # Sort modules alphabetically for deterministic output
    modules_list.sort(key=lambda x: x["module_name"])
        
    return {
        "modules": modules_list
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ContextAggregator: Group chunks into modules.")
    parser.add_argument("chunks_input", help="Path to the ContentProcessor JSON output")
    parser.add_argument("--out", default="runtime/outputs/aggregated_context.json", help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.chunks_input)
    
    if not input_path.exists():
        print(f"Error: Chunks input file {input_path} does not exist.")
        exit(1)
        
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            chunks_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {input_path}: {e}")
            exit(1)
            
    result = aggregate_context(chunks_data)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Aggregation complete. Found {len(result['modules'])} modules.")
    for mod in result['modules']:
        print(f"  - {mod['module_name']}: {len(mod['files'])} files, {len(mod['chunk_ids'])} chunks")
    print(f"Output saved to {out_path}")
