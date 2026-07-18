import os
import shutil
import json
import subprocess

def setup_dummy_repo(repo_path: str):
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)
    os.makedirs(repo_path)
    
    with open(os.path.join(repo_path, "README.md"), "w") as f:
        f.write("# Dummy Repo\nThis is a dummy repo for testing API and database integration.")
        
    os.makedirs(os.path.join(repo_path, "src"))
    with open(os.path.join(repo_path, "src", "auth.py"), "w") as f:
        f.write("def login():\n    pass\n\ndef signup():\n    pass")
        
    with open(os.path.join(repo_path, "src", "db.py"), "w") as f:
        f.write("import sqlite3\ndef connect():\n    pass")
        
    with open(os.path.join(repo_path, "package.json"), "w") as f:
        f.write('{"name": "dummy"}')

def run_pipeline():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = os.path.join(base_dir, "..", "runtime/outputs")
    repo_dir = os.path.join(tmp_dir, "dummy_repo")
    eca_out = os.path.join(tmp_dir, "eca_output.json")
    ctx_out = os.path.join(tmp_dir, "context_output.json")
    
    print("1. Setting up dummy repo...")
    setup_dummy_repo(repo_dir)
    
    print("2. Running ECA Extractor...")
    subprocess.run(["python", os.path.join(base_dir, "eca_extractor.py"), "--repo", repo_dir, "--out", eca_out], check=True)
    
    print("3. Running Context Builder...")
    subprocess.run(["python", os.path.join(base_dir, "context_builder.py"), "--eca_in", eca_out, "--out", ctx_out], check=True)
    
    print("4. Validating outputs...")
    with open(eca_out, "r") as f:
        eca = json.load(f)
        assert eca["readme"].startswith("# Dummy Repo")
        backend_files = eca["classified_files"]["backend"]
        assert any("auth.py" in f for f in backend_files)
        print("ECA Validation Passed!")
        
    with open(ctx_out, "r") as f:
        ctx = json.load(f)
        feature_names = [f["name"] for f in ctx["features"]]
        assert "Authentication" in feature_names
        assert "Database" in feature_names
        assert "Backend Services" in ctx["modules"]
        print("Context Validation Passed!")
        
    print("Pipeline run completed successfully!")

if __name__ == "__main__":
    run_pipeline()
