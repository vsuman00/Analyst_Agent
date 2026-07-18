"""
feature_interpretation_agent.py — Layer 3 Tool
-----------------------------------------------
FeatureInterpretationAgent

Input:
  - feature_signals : List of detected feature signals
  - modules         : List of detected modules
  - system_type     : String representing the system architecture type

Output (strict JSON):
  {
    "features": [
      {
        "id": str,
        "name": str,
        "description": str,
        "evidence": [str],
        "confidence": float
      }
    ]
  }

Strict Rules:
  - Every feature MUST map to evidence
  - No feature without supporting files/modules
  - Do NOT invent missing functionality
  - If unclear → reduce confidence
  - No business assumptions yet.
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Set

from app.schemas.models import InterpretedFeature, FeatureInterpretationResult

def interpret_features(
    feature_signals: List[Dict[str, Any]],
    modules: List[Dict[str, Any]],
    system_type: str,
    entry_points: List[str] = None,
    tech_stack: List[str] = None
) -> FeatureInterpretationResult:
    """
    Convert feature signals into refined features.
    Ensures all reasoning is grounded in modules, feature_signals, entry_points, and tech_stack.
    """
    interpreted_features: List[InterpretedFeature] = []
    
    entry_points = entry_points or []
    tech_stack = tech_stack or []
    
    # Ground tech stack and system type into evidence implicitly
    base_evidence_pool = set(entry_points + tech_stack)
    if system_type and system_type != "unknown":
        base_evidence_pool.add(system_type)
    
    for i, signal in enumerate(feature_signals):
        # Extract base properties from signal
        raw_name = signal.get("name") or signal.get("signal") or f"unnamed_signal_{i}"
        description = signal.get("description") or f"Interpreted capability: {raw_name}."
        base_confidence = float(signal.get("confidence", 0.5))
        
        # Gather initial evidence from the signal itself (sources/files)
        evidence_set: Set[str] = set()
        for key in ["evidence", "sources", "files"]:
            if key in signal and isinstance(signal[key], list):
                evidence_set.update(signal[key])
                
        # Ground reasoning in modules and entry_points
        # Cross-reference signal evidence with module contents to validate functionality
        matched_modules = []
        for mod in modules:
            mod_name = mod.get("name", "unknown_module")
            mod_files = mod.get("files", [])
            mod_sources = mod.get("sources", [])
            
            # If the signal's evidence overlaps with the module's files/sources
            overlap = any(ev in mod_files or ev in mod_sources for ev in evidence_set)
            
            # Or if the module name itself suggests it provides this feature
            name_match = raw_name.lower().replace("_", " ") in mod_name.lower().replace("_", " ")
            
            if overlap or name_match:
                evidence_set.add(mod_name)
                matched_modules.append(mod_name)
                
        # Also map to entry_points and tech_stack if mentioned
        for ev_pool_item in base_evidence_pool:
            if ev_pool_item.lower() in raw_name.lower() or ev_pool_item.lower() in description.lower():
                evidence_set.add(ev_pool_item)
        
        # Strict Rule: No feature without supporting files/modules
        if not evidence_set:
            continue
            
        # Strict Rule: If unclear -> reduce confidence
        # A feature is "unclear" if it only maps to a single vague evidence point
        # or doesn't map to any clear architectural modules.
        if not matched_modules:
            base_confidence *= 0.7  # Reduce confidence significantly if no module anchors it
        elif len(evidence_set) == 1:
            base_confidence *= 0.9  # Reduce slightly if evidence is very thin
            
        # Cap confidence
        final_confidence = round(min(1.0, max(0.1, base_confidence)), 2)
        
        feature = InterpretedFeature(
            id=f"feat-int-{i+1:03d}",
            name=raw_name,
            description=description,
            evidence=sorted(list(evidence_set)),
            confidence=final_confidence
        )
        interpreted_features.append(feature)
        
    return FeatureInterpretationResult(features=interpreted_features)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FeatureInterpretationAgent")
    parser.add_argument("--signals", required=True, help="Path to feature_signals JSON")
    parser.add_argument("--modules", required=True, help="Path to modules JSON")
    parser.add_argument("--system-type", default="unknown", help="System type descriptor")
    parser.add_argument("--entry-points", default=None, help="Path to entry_points JSON")
    parser.add_argument("--tech-stack", default=None, help="Path to tech_stack JSON")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()
    
    # Load feature signals
    signals_path = Path(args.signals)
    if not signals_path.exists():
        print(f"[ERROR] Signals file not found: {signals_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(signals_path, "r", encoding="utf-8") as f:
        raw_signals = json.load(f)
    feature_signals = raw_signals.get("feature_signals", raw_signals.get("features", raw_signals)) if isinstance(raw_signals, dict) else raw_signals
    
    # Load modules
    modules_path = Path(args.modules)
    if not modules_path.exists():
        print(f"[ERROR] Modules file not found: {modules_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(modules_path, "r", encoding="utf-8") as f:
        raw_modules = json.load(f)
    modules_list = raw_modules.get("modules", raw_modules) if isinstance(raw_modules, dict) else raw_modules
    
    # Load entry_points
    entry_points_list = []
    if args.entry_points and Path(args.entry_points).exists():
        with open(args.entry_points, "r", encoding="utf-8") as f:
            raw_eps = json.load(f)
        entry_points_list = raw_eps.get("entry_points", raw_eps) if isinstance(raw_eps, dict) else raw_eps

    # Load tech_stack
    tech_stack_list = []
    if args.tech_stack and Path(args.tech_stack).exists():
        with open(args.tech_stack, "r", encoding="utf-8") as f:
            raw_ts = json.load(f)
        tech_stack_list = raw_ts.get("tech_stack", raw_ts) if isinstance(raw_ts, dict) else raw_ts

    # Execute agent logic
    result = interpret_features(
        feature_signals=feature_signals if isinstance(feature_signals, list) else [],
        modules=modules_list if isinstance(modules_list, list) else [],
        system_type=args.system_type,
        entry_points=entry_points_list if isinstance(entry_points_list, list) else [],
        tech_stack=tech_stack_list if isinstance(tech_stack_list, list) else []
    )
    
    output_json = result.model_dump_json(indent=2)
    
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[OK] Interpreted features written to {out_path}", file=sys.stderr)
    else:
        print(output_json)
