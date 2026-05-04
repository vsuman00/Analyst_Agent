"""
non_functional_requirement_generator.py — Layer 3 Tool
-------------------------------------------------------
NonFunctionalRequirementGenerator

Input:
  - system_type : String
  - tech_stack  : List of strings

Output (strict JSON):
  {
    "non_functional_requirements": [
      {
        "id": "NFR-1",
        "category": "performance|security|scalability|availability",
        "description": str
      }
    ]
  }

Rules:
- Max 6-8 NFRs
- Only obvious system-level needs
- No generic fluff
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any

from app.schemas.models import NonFunctionalRequirement, NonFunctionalRequirementsResult

# ---------------------------------------------------------------------------
# Strict Deterministic NFR Templates
# ---------------------------------------------------------------------------

BASE_NFRS = [
    {
        "category": "performance",
        "description": "The system SHALL respond to 95% of synchronous API requests within 500 milliseconds under normal load."
    },
    {
        "category": "security",
        "description": "The system SHALL encrypt all data in transit using TLS 1.2 or higher."
    },
    {
        "category": "availability",
        "description": "The system SHALL support graceful degradation, returning static or cached responses if downstream dependencies fail."
    }
]

TECH_SPECIFIC_NFRS = {
    "database": [
        {
            "category": "performance",
            "description": "The system SHALL execute primary key database queries in under 50 milliseconds at the 99th percentile."
        },
        {
            "category": "availability",
            "description": "The system SHALL persist automated database backups at least daily, retained for 30 days."
        }
    ],
    "microservices": [
        {
            "category": "scalability",
            "description": "The system SHALL support horizontal scaling, allowing independent stateless instances to be added dynamically."
        },
        {
            "category": "availability",
            "description": "The system SHALL implement automated health checks and restart failed instances within 60 seconds."
        }
    ],
    "frontend": [
        {
            "category": "performance",
            "description": "The frontend application SHALL achieve a Time to Interactive (TTI) of under 3 seconds on standard broadband connections."
        }
    ],
    "cache": [
        {
            "category": "performance",
            "description": "The system SHALL maintain a cache hit ratio of at least 80% for frequently accessed, read-heavy data endpoints."
        }
    ]
}

def generate_nfrs(system_type: str, tech_stack: List[str]) -> NonFunctionalRequirementsResult:
    """
    Generate 6-8 obvious, system-level NFRs deterministically from tech stack.
    """
    selected_nfrs = list(BASE_NFRS)
    
    combined_tech = set(tech_stack)
    if system_type and system_type != "unknown":
        combined_tech.add(system_type.lower())
        
    combined_tech_str = " ".join(combined_tech).lower()
    
    # Simple keyword-based triggers
    if "db" in combined_tech_str or "sql" in combined_tech_str or "mongo" in combined_tech_str or "database" in combined_tech_str:
        selected_nfrs.extend(TECH_SPECIFIC_NFRS["database"])
        
    if "microservice" in combined_tech_str or "kubernetes" in combined_tech_str or "docker" in combined_tech_str:
        selected_nfrs.extend(TECH_SPECIFIC_NFRS["microservices"])
        
    if "react" in combined_tech_str or "vue" in combined_tech_str or "ui" in combined_tech_str or "frontend" in combined_tech_str:
        selected_nfrs.extend(TECH_SPECIFIC_NFRS["frontend"])
        
    if "redis" in combined_tech_str or "memcached" in combined_tech_str or "cache" in combined_tech_str:
        selected_nfrs.extend(TECH_SPECIFIC_NFRS["cache"])

    # If we still need more to hit our quota (but we cap at 8)
    if len(selected_nfrs) < 6:
        selected_nfrs.append({
            "category": "security",
            "description": "The system SHALL log all authentication failures and administrative actions to a centralized, append-only audit trail."
        })
        selected_nfrs.append({
            "category": "scalability",
            "description": "The system SHALL decouple asynchronous background tasks from the main request thread using a message queue or task worker."
        })

    # Limit to max 8 NFRs
    selected_nfrs = selected_nfrs[:8]
    
    final_nfrs = []
    for i, nfr_data in enumerate(selected_nfrs):
        final_nfrs.append(NonFunctionalRequirement(
            id=f"NFR-{i+1}",
            category=nfr_data["category"],
            description=nfr_data["description"]
        ))

    return NonFunctionalRequirementsResult(non_functional_requirements=final_nfrs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NonFunctionalRequirementGenerator")
    parser.add_argument("--system-type", default="unknown", help="System type descriptor")
    parser.add_argument("--tech-stack", default=None, help="Path to tech_stack JSON")
    parser.add_argument("--out", default=None, help="Output JSON path")
    args = parser.parse_args()
    
    tech_stack_list = []
    if args.tech_stack:
        ts_path = Path(args.tech_stack)
        if ts_path.exists():
            with open(ts_path, "r", encoding="utf-8") as f:
                raw_ts = json.load(f)
            if isinstance(raw_ts, dict):
                tech_stack_list = raw_ts.get("tech_stack", [])
            elif isinstance(raw_ts, list):
                tech_stack_list = raw_ts

    result = generate_nfrs(args.system_type, tech_stack_list)
    output_json = result.model_dump_json(indent=2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(output_json)
        print(f"[OK] NFRs written to {out_path}", file=sys.stderr)
    else:
        print(output_json)
