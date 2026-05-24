# app/skills/ — Dynamic Skill Pack Engine
#
# Architecture (SKILL.md pattern — same as Codex / Claude Code / Antigravity):
#
#   packs/{skill_id}/
#   ├── SKILL.md          ← YAML frontmatter (detection signals) + Markdown (instructions)
#   ├── scripts/          ← Optional Python CLI tools (argparse, subcommands)
#   │   └── extractor.py  ← python scripts/extractor.py <repo_dir> <output.json> <subcommand>
#   └── references/       ← Optional deep docs loaded on-demand
#       └── patterns.md
#
# Key modules:
#   skill_loader.py   — Discovers SKILL.md files, parses YAML frontmatter
#   skill_matcher.py  — Scores loaded skills against repo evidence (no hardcoding)
#   skill_executor.py — Runs skill scripts against the cloned repo
#   skill_composer.py — Auto-generates new SKILL.md + scripts via LLM
