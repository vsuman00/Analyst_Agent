import argparse
import json
import os
import sys
from pathlib import Path
import re

DESCRIPTION = "Extract PowerBuilder UI signals: Ribbon XML, files referencing RibbonBar/Clicked, README mentions"

def scan_repo(repo_dir):
    repo = Path(repo_dir)
    if not repo.exists():
        raise FileNotFoundError(f"repo_dir not found: {repo_dir}")

    results = {
        "powerbuilder_mentions": False,
        "ribbon_xml_files": [],
        "ui_source_files": [],
        "clicked_references": [],
        "readme_matches": []
    }

    # Patterns
    rb_xml_pattern = re.compile(r"ribbon", re.IGNORECASE)
    pb_keywords = re.compile(r"powerbuilder|appeon|pbl|pbd|srp|sr*", re.IGNORECASE)
    clicked_pattern = re.compile(r"Clicked", re.IGNORECASE)

    for path in repo.rglob("*"):
        if path.is_file():
            name = path.name
            try:
                text = path.read_text(errors="ignore")
            except Exception:
                text = ""

            # README check
            if name.lower().startswith("readme") or name.lower().endswith(".md"):
                if re.search(r"powerbuilder|appeon", text, re.IGNORECASE):
                    results["powerbuilder_mentions"] = True
                    results["readme_matches"].append(str(path.relative_to(repo)))

            # Ribbon XML detection by filename or content
            if name.lower().endswith(".xml") and rb_xml_pattern.search(name):
                results["ribbon_xml_files"].append(str(path.relative_to(repo)))
            else:
                # content-based xml ribbon detection
                if name.lower().endswith(".xml") and rb_xml_pattern.search(text):
                    results["ribbon_xml_files"].append(str(path.relative_to(repo)))

            # PowerBuilder source/object heuristics by extension or content
            if name.lower().endswith(('.srp', '.sru', '.sr*', '.pbl', '.pbd', '.pbr', '.pb', '.w')) or re.search(r"\bPowerBuilder\b|appeon", text, re.IGNORECASE):
                results["ui_source_files"].append(str(path.relative_to(repo)))

            # Clicked event references
            if clicked_pattern.search(text):
                # record line snippets where Clicked appears
                snippets = []
                for i, line in enumerate(text.splitlines(), 1):
                    if clicked_pattern.search(line):
                        snippets.append({"file": str(path.relative_to(repo)), "line": i, "text": line.strip()})
                results["clicked_references"].extend(snippets)

    # Deduplicate lists
    results["ribbon_xml_files"] = sorted(set(results["ribbon_xml_files"]))
    results["ui_source_files"] = sorted(set(results["ui_source_files"]))
    results["readme_matches"] = sorted(set(results["readme_matches"]))

    return results


def main():
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("repo_dir")
    parser.add_argument("output_file")
    subparsers = parser.add_subparsers(dest="subcommand")

    subparsers.add_parser("extract", help="Run extraction")

    args = parser.parse_args()
    if args.subcommand != "extract":
        print("Expected subcommand: extract", file=sys.stderr)
        sys.exit(1)

    try:
        results = scan_repo(args.repo_dir)
        out_path = Path(args.output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, indent=2))
        print("ok")
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
