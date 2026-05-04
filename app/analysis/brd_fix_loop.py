"""
brd_fix_loop.py — Layer 3 Tool
--------------------------------
BRDFixLoop

Input:
  - Initial BRD (Markdown string)
  
Output:
  - Fixed BRD (Markdown string)
  - Final validation result
  - Iterations used (0, 1, or 2)

Logic:
  - Validates the BRD using BRDValidator.
  - If score < 0.85, applies deterministic string patches based on the 
    issues reported (formatting, removing vague words, stripping filler text).
  - Does NOT alter core JSON structured data.
  - Max 2 iterations.
"""

import re
import argparse
import sys
from pathlib import Path
from typing import Dict, Any

from app.analysis.brd_validator import validate_brd
from app.schemas.models import BRDValidationResult

def _apply_fixes(markdown: str, issues: list[str]) -> str:
    """
    Apply deterministic fixes based on validation issues.
    """
    fixed = markdown

    # 1. Fix storytelling intro
    if any("storytelling detected" in issue for issue in issues):
        # Find the real start
        match = re.search(r'(#\s+Business Requirement Document.*)', fixed, flags=re.DOTALL)
        if match:
            fixed = match.group(1)
        else:
            # Force it at the top
            fixed = "# Business Requirement Document\n\n" + fixed

    # 2. Fix vague language
    vague_issue = next((issue for issue in issues if "Vague language detected" in issue), None)
    if vague_issue:
        # Extract the list of words from the issue string: "Vague language detected in document: ['user-friendly']"
        # We'll just strip the known banned words out deterministically.
        banned = ['user-friendly', 'efficient', 'seamless', 'robust']
        for word in banned:
            # We use a case-insensitive replacement to just remove the word and its adjacent space if any
            # A simple replace works, but let's be careful about leaving double spaces.
            pattern = re.compile(r'\b' + re.escape(word) + r'\b[\s\-]*', re.IGNORECASE)
            fixed = pattern.sub('', fixed)
            
    # 3. Fix missing sections — aligned to new 16-section structure
    new_sections = [
        "## 2. Business Context", "## 3. Current State Analysis",
        "## 4. Stakeholders", "## 5. Functional Requirements",
        "## 6. Non-Functional Requirements", "## 7. Data Requirements",
        "## 11. Risk Register", "## 13. Acceptance Criteria",
    ]
    for heading in new_sections:
        label = heading.replace("## ", "")
        if heading not in fixed:
            fixed += f"\n{heading}\n*{label} — content pending.*\n"

    # Clean up double empty lines caused by replacements
    fixed = re.sub(r'\n{3,}', '\n\n', fixed)
    
    return fixed.strip()

def run_fix_loop(
    initial_markdown: str,
    max_iterations: int = 2,
    features: list = None,
    functional_requirements: list = None,
) -> Dict[str, Any]:
    """
    Run the validation/fix loop.
    Returns:
      {
        "final_markdown": str,
        "final_validation": BRDValidationResult,
        "iterations": int
      }
    """
    features = features or []
    functional_requirements = functional_requirements or []
    current_markdown = initial_markdown
    iteration = 0

    while iteration < max_iterations:
        val_result = validate_brd(current_markdown, features, functional_requirements)

        if not val_result.needs_revision:
            # Score >= 0.85, we are good
            return {
                "final_markdown": current_markdown,
                "final_validation": val_result.model_dump(),
                "iterations": iteration
            }

        # Needs revision -> apply deterministic fixes
        current_markdown = _apply_fixes(current_markdown, val_result.issues)
        iteration += 1

    # Max iterations reached, return current state
    final_val = validate_brd(current_markdown, features, functional_requirements)
    return {
        "final_markdown": current_markdown,
        "final_validation": final_val.model_dump(),
        "iterations": iteration
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BRDFixLoop: Automatically repair a generated BRD based on validation feedback.")
    parser.add_argument("--brd", required=True, help="Path to initial BRD Markdown file.")
    parser.add_argument("--out-md", default=None, help="Optional path to write the fixed Markdown.")
    parser.add_argument("--out-json", default=None, help="Optional path to write the loop result JSON.")
    args = parser.parse_args()

    brd_path = Path(args.brd)
    if not brd_path.exists():
        print(f"[ERROR] BRD file not found: {brd_path}", file=sys.stderr)
        sys.exit(1)

    with open(brd_path, "r", encoding="utf-8") as f:
        markdown_str = f.read()

    loop_result = run_fix_loop(markdown_str)

    if args.out_md:
        out_md_path = Path(args.out_md)
        out_md_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_md_path, "w", encoding="utf-8") as fh:
            fh.write(loop_result["final_markdown"])
        print(f"[OK] Fixed BRD written to {out_md_path}", file=sys.stderr)

    if args.out_json:
        import json
        out_json_path = Path(args.out_json)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json_path, "w", encoding="utf-8") as fh:
            json.dump(loop_result, fh, indent=2)
        print(f"[OK] Fix loop result written to {out_json_path}", file=sys.stderr)
    else:
        # If neither output is explicitly defined, just print summary to stdout
        if not args.out_md:
            print(f"Iterations: {loop_result['iterations']}")
            print(f"Final Score: {loop_result['final_validation']['score']}")
            if loop_result['final_validation']['issues']:
                print(f"Remaining Issues: {loop_result['final_validation']['issues']}")
