import os
import shutil
import json
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any
from app.eca.language_loader import is_binary as _registry_is_binary, get_ignore_dirs

# NOTE: IGNORE_DIRS and BINARY_EXTS are now loaded from the language registry.
# Edit app/eca/config/language_registry.json to add new directories or binary types.

def is_binary(file_path: Path) -> bool:
    """Return True if the file should be skipped (binary extension or unreadable content)."""
    if _registry_is_binary(file_path.suffix.lower()):
        return True
    try:
        with open(file_path, 'tr') as check_file:
            check_file.read(1024)
            return False
    except UnicodeDecodeError:
        return True
    except Exception:
        return False

def clone_repository(repo_url: str, dest_dir: Path) -> bool:
    """Clones the repository and returns True if successful."""
    if dest_dir.exists():
        try:
            shutil.rmtree(dest_dir)
        except Exception as e:
            print(f"Error removing existing directory: {e}")
            return False
    
    try:
        # Use subprocess directly to avoid GitPython dependency for this isolated module
        subprocess.run(["git", "clone", repo_url, str(dest_dir)], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error cloning repository: {e.stderr.decode('utf-8', errors='ignore')}")
        return False
    except FileNotFoundError:
        print("Error: 'git' command not found. Please ensure Git is installed.")
        return False

def scan_repository(repo_url: str, dest_dir_str: str = "runtime/outputs/repo_scanner", skip_clone: bool = False) -> Dict[str, Any]:
    """Clones and scans a repository, returning metadata matching the output schema."""
    dest_dir = Path(dest_dir_str)
    
    # Extract repo name from URL
    repo_name = repo_url.rstrip('/').split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    if skip_clone and dest_dir.exists():
        print(f"Skipping clone, using existing directory {dest_dir}...")
    else:
        print(f"Cloning {repo_url}...")
        if not clone_repository(repo_url, dest_dir):
            if dest_dir.exists():
                print("Clone failed, but directory exists. Proceeding with existing files...")
            else:
                return {"error": "Failed to clone repository"}

    print("Scanning files...")
    file_metadata: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(dest_dir):
        # Load ignore set from registry on each walk step
        _ignore = get_ignore_dirs()
        dirs[:] = [d for d in dirs if d not in _ignore]
        
        for file in files:
            file_path = Path(root) / file
            
            # Skip symlinks
            if file_path.is_symlink():
                continue
                
            # Skip binaries based on extension and content check
            if is_binary(file_path):
                continue

            try:
                rel_path = file_path.relative_to(dest_dir)
                size = file_path.stat().st_size
                extension = file_path.suffix.lower() if file_path.suffix else ""
                
                file_metadata.append({
                    "path": str(rel_path),
                    "extension": extension,
                    "size": size
                })
            except Exception as e:
                print(f"Warning: Could not process file {file_path}: {e}")

    return {
        "repo_name": repo_name,
        "root_path": str(dest_dir.absolute()),
        "files": file_metadata
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RepoScanner: Clone and scan a GitHub repository.")
    parser.add_argument("repo_url", help="The URL of the GitHub repository")
    parser.add_argument("--out", default="runtime/outputs/repo_scan.json", help="Output JSON file path")
    args = parser.parse_args()

    result = scan_repository(args.repo_url)
    
    if "error" in result:
        print(f"Scan failed: {result['error']}")
        exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
        
    print(f"Scan complete. Found {len(result['files'])} valid files.")
    print(f"Output saved to {out_path}")
