---
name: mobile-app-analysis
version: "1.0"
description: >-
  Analysis pack for mobile application repositories (Android, iOS, Flutter,
  React Native, Kotlin Multiplatform). Activate when has_android or has_ios
  evidence flags are true, or mobile framework dependencies are detected.
  DO NOT activate for: backend-only APIs, desktop apps, web-only SPAs.

detection_signals:
  evidence_flags: [has_android, has_ios]
  dependency_keywords: [react-native, flutter, expo, ionic, capacitor, swiftui, uikit, jetpack, compose, kotlin-multiplatform, xamarin, maui]
  file_patterns: ["**/AndroidManifest.xml", "**/*.xcodeproj", "**/Podfile", "**/pubspec.yaml", "**/app.json", "**/Info.plist"]
  confidence_threshold: 0.5

nfr_emphasis: [app_startup_time, battery_usage, offline_capability, crash_rate, app_size]
memory_tags: [mobile_app, android, ios, flutter, react_native, navigation, permissions]
brd_section_notes:
  section_5: "Focus on screen flows, user journeys, permissions, and platform-specific features"
  section_6: "Include app startup time targets, crash-free rate, battery impact SLAs"
  section_8: "Document mobile frameworks, state management, and CI/CD for app stores"
  section_12: "Include App Store/Play Store compliance, data privacy (GDPR/CCPA), and permissions justification"
---

# Mobile App Analysis Skill Pack

## Overview

This skill pack extracts mobile app screens, navigation flows, permission
requirements, and platform-specific patterns from Android, iOS, Flutter,
and React Native repositories.

## When This Skill Activates

- `evidence.has_android == True` or `evidence.has_ios == True`
- Dependencies include mobile frameworks (React Native, Flutter, etc.)
- File tree contains `AndroidManifest.xml`, `.xcodeproj`, `pubspec.yaml`

## Extraction Scripts

### Script 1: Screen Flow Extraction

```bash
python scripts/screen_extractor.py <repo_dir> <output.json> screens
```

Detects Activities, Fragments, ViewControllers, Flutter Widgets, and RN screens.

### Script 2: Permission Detection

```bash
python scripts/screen_extractor.py <repo_dir> <output.json> permissions
```

Extracts declared permissions from manifests and Info.plist files.

### Script 3: Platform Detection

```bash
python scripts/screen_extractor.py <repo_dir> <output.json> platform
```

Identifies target platform(s), min SDK versions, and build configuration.

## Common Mistakes

- Do NOT count test Activities/ViewControllers as user-facing screens
- Do NOT assume App Store deployment exists without build config evidence
- Flutter widgets named `*Page` or `*Screen` are likely screens; others are components
