---
name: cli-tool-analysis
version: "1.0"
description: >-
  Analysis pack for command-line tool repositories. Activate when CLI
  argument parsing libraries (argparse, click, typer, cobra, clap,
  commander) are detected, or main entry points with flag parsing patterns
  are found. This is an instruction-only pack — no scripts needed.
  DO NOT activate for: web APIs that happen to have CLI admin commands,
  full applications with incidental CLI utilities.

detection_signals:
  evidence_flags: []
  dependency_keywords: [click, typer, fire, argparse, docopt, cobra, clap, commander, yargs, clippy, thor, optparse]
  file_patterns: ["**/cli.py", "**/cli/**", "**/cmd/**", "**/commands/**", "**/main.go"]
  confidence_threshold: 0.6

nfr_emphasis: [command_response_time, error_messages_clarity, help_documentation, exit_codes]
memory_tags: [cli_tool, command_hierarchy, flags, subcommands]
brd_section_notes:
  section_5: "Focus on command hierarchy, subcommands, flags/options, and input/output formats"
  section_6: "Emphasise CLI response time, helpful error messages, and shell completion support"
  section_8: "Document distribution method (pip, brew, go install, cargo, npm) and OS compatibility"
---

# CLI Tool Analysis Skill Pack

## Overview

This is an **instruction-only** skill pack — it does not have extraction scripts.
Instead, it provides structured guidance to the pipeline's LLM-based feature
extraction about what to look for in CLI tool repositories.

CLI tools have fundamentally different feature profiles than web apps or mobile
apps. This pack reframes the analysis to focus on:
- Command hierarchy (top-level commands, subcommands)
- Flag/option definitions and their types
- Input/output format handling (JSON, YAML, table, plain text)
- Shell integration (completion scripts, piping, exit codes)
- Help text quality and documentation generation

## When This Skill Activates

- Dependencies include CLI framework libraries: click, typer, cobra, clap
- File tree contains `cli.py`, `cmd/`, `commands/` directories
- Main entry points import argument parsing libraries

## Extraction Guidance (No Scripts)

The standard feature extraction agent should look for these patterns:

### Command Structure
- Functions decorated with `@click.command`, `@app.command()`, `@cli.group()`
- Go functions registered as `cobra.Command`
- Rust functions annotated with `#[derive(Parser)]`

### Flag/Option Patterns
- `@click.option("--verbose")`, `parser.add_argument("--output")`
- Required vs optional flags, default values, type constraints

### Output Formats
- `--format json|yaml|table|csv` options
- Pretty-printing, colour output, progress bars

### Distribution
- `setup.py entry_points`, `pyproject.toml [project.scripts]`
- `go install`, `cargo install`, `npm link`

## How Results Are Used

- BRD Section 5 focuses on commands and their business purpose
- BRD Section 6 includes CLI-specific NFRs (response time, error clarity)
- BRD Section 8 documents distribution and installation methods

## Fallback Behavior

Since this pack has no scripts, there is nothing to fail. The guidance
is injected into the feature extraction context as additional signals.
