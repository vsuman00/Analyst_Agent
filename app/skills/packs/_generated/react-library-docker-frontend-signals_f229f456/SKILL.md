---
name: react-library-docker-frontend-signals
version: "1.0"
description: >-
  Analyzes React/TypeScript frontend libraries packaged with Docker (no server APIs). Activates when repo is a JS/TS React component/app library that includes Docker artifacts.

detection_signals:
  evidence_flags: ["has_docker"]
  dependency_keywords: ["react","react-dom","typescript","vite","tailwindcss","pdfjs-dist","react-dropzone","@react-router/node","@react-router/serve"]
  file_patterns: ["**/Dockerfile","**/docker/**","**/package.json","**/README*","**/src/**/*.{js,jsx,ts,tsx}"]
  confidence_threshold: 0.5

nfr_emphasis: ["containerization","build_reproducibility","bundle_size","client_performance"]
memory_tags: ["frontend_library","react","docker_ready","ui_components","pdf_handling"]
brd_section_notes:
  section_5: "List UI features (PDF resume parsing, dropzone uploads, routing) and component contracts (props/events)."
  section_8: "Document tech stack: React + TypeScript, Vite build, Tailwind, Docker setup, and any native browser APIs or third-party libs (pdfjs-dist)."
---

# Extraction guidance

This skill pack extracts repository signals relevant to a Dockerized React/TypeScript frontend library. It looks for Dockerfile(s), package.json, README mentions, and source files to infer features: PDF handling, file-drop components, client routing, and bundler/tooling. Use the provided CLI extractor to enumerate these artifacts and produce a small JSON summary for the BRD pipeline.
