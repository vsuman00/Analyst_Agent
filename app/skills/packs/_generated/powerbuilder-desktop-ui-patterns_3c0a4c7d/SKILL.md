---
name: powerbuilder-desktop-ui-patterns
version: "1.0"
description: >-
  Analyzes PowerBuilder desktop applications to detect UI modernization patterns (RibbonBar, MDI usage) and extract UI resource files and event wiring. Activate on repos containing PowerBuilder artifacts or README mentions. Max 300 chars.

detection_signals:
  evidence_flags: ["has_desktop"]
  dependency_keywords: ["appeon", "powerbuilder", "pb", "ribbonbar"]
  file_patterns: ["**/*.sr*", "**/*.pbl", "**/*.sru", "**/*.xml", "**/*Ribbon*.xml", "**/README*", "**/*.pbr"]
  confidence_threshold: 0.5

nfr_emphasis: ["usability", "desktop_ui", "accessibility"]
memory_tags: ["powerbuilder", "ribbonbar", "mdi", "desktop_ui", "appeon"]
brd_section_notes:
  section_5: "List functional requirements around RibbonBar loading, dynamic menu creation, and Clicked event handlers for child controls."
  section_8: "Specify tech stack: PowerBuilder (Appeon), target Windows desktop runtime, UI resource files (Ribbon XML) and any build artifacts (.pbl/.sr*)"
---

Skill: PowerBuilder Desktop UI Patterns

This skill helps extract UI-related signals from PowerBuilder desktop repositories—especially RibbonBar and MDI usage, Ribbon XML resources, and code locations wiring Clicked events—so BRD can capture functional requirements for UI modernization.

Instructions for use:
- The extractor scans for PowerBuilder source/object files (.sr*, .pbl), XML Ribbon files (names containing "Ribbon"), and README mentions of PowerBuilder/Appeon.
- It extracts listed UI resource file paths, example snippets of Ribbon XML, and files referencing RibbonBar or Clicked handlers.
- Use extracted outputs to populate BRD sections on UI behavior, integration points, and technical constraints.
