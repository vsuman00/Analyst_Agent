import os
import json
import uuid
import argparse
from pathlib import Path
from typing import List, Dict, Any

# ~800 tokens is roughly 3200 characters (assuming ~4 chars per token).
CHUNK_SIZE_CHARS = 3200

def process_file(file_path: Path, rel_path_str: str, category: str) -> List[Dict[str, str]]:
    chunks = []
    
    if not file_path.exists() or not file_path.is_file():
        return chunks
        
    try:
        # Check if file is readable as text
        with open(file_path, 'r', encoding='utf-8') as f:
            current_chunk = ""
            chunk_index = 0
            
            # Read line by line to handle large files safely
            for line in f:
                current_chunk += line
                if len(current_chunk) >= CHUNK_SIZE_CHARS:
                    chunks.append({
                        "chunk_id": f"{rel_path_str}_{chunk_index}_{uuid.uuid4().hex[:8]}",
                        "file_path": rel_path_str,
                        "category": category,
                        "content": current_chunk
                    })
                    current_chunk = ""
                    chunk_index += 1
            
            # Add remaining chunk if it's not empty
            if current_chunk:
                chunks.append({
                    "chunk_id": f"{rel_path_str}_{chunk_index}_{uuid.uuid4().hex[:8]}",
                    "file_path": rel_path_str,
                    "category": category,
                    "content": current_chunk
                })
                
    except UnicodeDecodeError:
        # Skip binary/unreadable files quietly
        pass
    except Exception as e:
        print(f"Warning: Could not process {file_path}: {e}")
        
    return chunks

def run_content_processor(classified_data: Dict[str, Any], repo_dir: Path) -> Dict[str, Any]:
    all_chunks = []
    
    for item in classified_data.get("classified_files", []):
        path_str = item.get("path", "")
        category = item.get("category", "unknown")
        
        if not path_str:
            continue
            
        full_path = repo_dir / path_str
        file_chunks = process_file(full_path, path_str, category)
        all_chunks.extend(file_chunks)
        
    return {
        "chunks": all_chunks
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ContentProcessor: Split classified files into chunks.")
    parser.add_argument("classified_input", help="Path to the FileClassifier JSON output")
    parser.add_argument("repo_dir", help="Path to the repository root directory")
    parser.add_argument("--out", default="runtime/outputs/chunks_output.json", help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.classified_input)
    repo_path = Path(args.repo_dir)
    
    if not input_path.exists():
        print(f"Error: Classified input file {input_path} does not exist.")
        exit(1)
        
    if not repo_path.exists() or not repo_path.is_dir():
        print(f"Error: Repository directory {repo_path} does not exist or is not a directory.")
        exit(1)
        
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            classified_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON from {input_path}: {e}")
            exit(1)
            
    result = run_content_processor(classified_data, repo_path)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Content processing complete. Generated {len(result['chunks'])} chunks.")
    print(f"Output saved to {out_path}")
