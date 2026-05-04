import os
import json
import argparse
from typing import Dict, Any, List
from app.schemas.models import ECAOutput, ClassifiedFiles, FileChunk

FRONTEND_EXTS = {".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss", ".vue"}
BACKEND_EXTS = {".py", ".java", ".go", ".rb", ".php", ".cs", ".rs", ".cpp", ".c"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".xml", ".cfg"}
DOCS_EXTS = {".md", ".txt", ".rst"}

def is_text_file(filepath: str) -> bool:
    try:
        with open(filepath, 'tr') as check_file:
            check_file.read(1024)
            return True
    except UnicodeDecodeError:
        return False
    except Exception:
        return False

def build_file_tree(startpath: str) -> Dict[str, Any]:
    tree = {}
    for root, dirs, files in os.walk(startpath):
        if '.git' in dirs:
            dirs.remove('.git')
        
        rel_root = os.path.relpath(root, startpath)
        if rel_root == '.':
            current_level = tree
        else:
            parts = rel_root.split(os.sep)
            current_level = tree
            for part in parts:
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
        
        for f in files:
            current_level[f] = None
    return tree

def classify_file(filename: str, classified: ClassifiedFiles):
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    
    if ext in FRONTEND_EXTS:
        classified.frontend.append(filename)
    elif ext in BACKEND_EXTS:
        classified.backend.append(filename)
    elif ext in CONFIG_EXTS:
        classified.config.append(filename)
    elif ext in DOCS_EXTS:
        classified.docs.append(filename)
    else:
        classified.unknown.append(filename)

def extract_eca(repo_path: str) -> ECAOutput:
    readme_content = ""
    file_tree = build_file_tree(repo_path)
    classified = ClassifiedFiles()
    chunks: List[FileChunk] = []

    for root, dirs, files in os.walk(repo_path):
        if '.git' in dirs:
            dirs.remove('.git')
            
        for file in files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, repo_path)
            
            classify_file(rel_path, classified)
            
            if file.lower() == 'readme.md' and root == repo_path:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        readme_content = f.read()
                except Exception as e:
                    print(f"Error reading README: {e}")
                    
            if is_text_file(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        chunks.append(FileChunk(file=rel_path, content=content))
                except Exception:
                    pass
                    
    return ECAOutput(
        readme=readme_content,
        file_tree=file_tree,
        classified_files=classified,
        chunks=chunks
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract ECA from a repository.")
    parser.add_argument("--repo", default="runtime/outputs/repo", help="Path to the repository directory")
    parser.add_argument("--out", default="runtime/outputs/eca_output.json", help="Path to the output JSON file")
    args = parser.parse_args()
    
    if not os.path.exists(args.repo):
        print(f"Error: Repository path {args.repo} does not exist.")
        exit(1)
        
    eca_output = extract_eca(args.repo)
    
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(eca_output.model_dump_json(indent=2))
        
    print(f"ECA output successfully written to {args.out}")
