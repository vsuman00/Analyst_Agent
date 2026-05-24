"""
screen_extractor.py — Mobile App Skill Pack Extraction Script
---------------------------------------------------------------
Extracts screen/activity definitions, permissions, and platform metadata
from mobile app repositories (Android, iOS, Flutter, React Native).

Usage:
    python scripts/screen_extractor.py <repo_dir> <output_file> <subcommand>

Subcommands:
    screens     — Detect Activities, ViewControllers, Flutter pages, RN screens
    permissions — Extract declared permissions from manifests
    platform    — Identify target platforms, SDK versions, build config
    extract     — Run all subcommands and merge

Uses ONLY stdlib — no pip installs required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Screen Detection Patterns
# ---------------------------------------------------------------------------

# Android: Activity, Fragment classes
_ANDROID_ACTIVITY_RE = re.compile(
    r"class\s+(\w+)\s*(?:\(|:)\s*\w*(?:AppCompat)?(?:Activity|Fragment|ComponentActivity)",
    re.IGNORECASE,
)

# iOS: UIViewController, SwiftUI View
_IOS_VC_RE = re.compile(
    r"class\s+(\w+)\s*:\s*(?:UI)?(?:ViewController|TableViewController|CollectionViewController|NavigationController)",
    re.IGNORECASE,
)
_SWIFTUI_VIEW_RE = re.compile(
    r"struct\s+(\w+)\s*:\s*View\b",
    re.IGNORECASE,
)

# Flutter: StatelessWidget / StatefulWidget with Page/Screen in name
_FLUTTER_SCREEN_RE = re.compile(
    r"class\s+(\w*(?:Page|Screen|View)\w*)\s+extends\s+(?:Stateless|Stateful)Widget",
    re.IGNORECASE,
)

# React Native: export default function/class XxxScreen
_RN_SCREEN_RE = re.compile(
    r"(?:export\s+default\s+)?(?:function|class|const)\s+(\w*(?:Screen|Page|View)\w*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Permission Patterns
# ---------------------------------------------------------------------------

# Android: <uses-permission android:name="android.permission.CAMERA"/>
_ANDROID_PERM_RE = re.compile(
    r'<uses-permission\s+android:name="([^"]+)"',
    re.IGNORECASE,
)

# iOS: Privacy keys in Info.plist
_IOS_PERM_RE = re.compile(
    r"<key>(NS\w+UsageDescription)</key>",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# File Walker
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv", "vendor",
    "build", "dist", ".gradle", ".idea", "Pods", ".dart_tool",
}

_MOBILE_EXTS = {
    ".java", ".kt", ".swift", ".m", ".dart",
    ".js", ".jsx", ".ts", ".tsx",
    ".xml", ".plist", ".yaml", ".yml",
}


def _walk_mobile_files(repo_dir: str) -> List[tuple[str, str]]:
    """Walk repo and yield (relative_path, content) for mobile-relevant files."""
    results = []
    root = Path(repo_dir)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in _MOBILE_EXTS:
                continue
            fpath = Path(dirpath) / fname
            if fpath.stat().st_size > 500_000:
                continue
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                results.append((str(rel_dir / fname), content))
            except (OSError, UnicodeDecodeError):
                continue
    return results


# ---------------------------------------------------------------------------
# Subcommand: screens
# ---------------------------------------------------------------------------

def cmd_screens(repo_dir: str) -> Dict[str, Any]:
    """Detect screen/activity/page definitions."""
    screens: List[Dict[str, Any]] = []
    seen = set()

    patterns = [
        ("android_activity", _ANDROID_ACTIVITY_RE),
        ("ios_viewcontroller", _IOS_VC_RE),
        ("swiftui_view", _SWIFTUI_VIEW_RE),
        ("flutter_screen", _FLUTTER_SCREEN_RE),
        ("react_native_screen", _RN_SCREEN_RE),
    ]

    for rel_path, content in _walk_mobile_files(repo_dir):
        for screen_type, pattern in patterns:
            for match in pattern.finditer(content):
                name = match.group(1)
                key = (name, screen_type)
                if key not in seen:
                    seen.add(key)
                    screens.append({
                        "name": name,
                        "type": screen_type,
                        "source_file": rel_path,
                    })

    # Generate features
    features = []
    if screens:
        # Group by type
        by_type: Dict[str, int] = {}
        for s in screens:
            by_type[s["type"]] = by_type.get(s["type"], 0) + 1

        for stype, count in by_type.items():
            platform = stype.split("_")[0].title()
            features.append({
                "name": f"{platform.lower()}_screen_navigation",
                "description": f"{platform} app with {count} screen(s)/page(s): {', '.join(s['name'] for s in screens if s['type'] == stype)[:200]}",
                "confidence": min(0.9, 0.7 + 0.05 * count),
                "source_modules": list(set(s["source_file"] for s in screens if s["type"] == stype))[:5],
            })

    return {
        "screens": screens,
        "total_screens": len(screens),
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: permissions
# ---------------------------------------------------------------------------

def cmd_permissions(repo_dir: str) -> Dict[str, Any]:
    """Extract declared permissions from manifest/plist files."""
    android_perms = set()
    ios_perms = set()

    for rel_path, content in _walk_mobile_files(repo_dir):
        for m in _ANDROID_PERM_RE.finditer(content):
            android_perms.add(m.group(1))
        for m in _IOS_PERM_RE.finditer(content):
            ios_perms.add(m.group(1))

    features = []
    all_perms = list(android_perms) + list(ios_perms)
    if all_perms:
        features.append({
            "name": "device_permission_management",
            "description": f"App requests {len(all_perms)} device permission(s): {', '.join(all_perms[:10])}",
            "confidence": 0.9,
            "source_modules": [],
        })

    return {
        "android_permissions": sorted(android_perms),
        "ios_permissions": sorted(ios_perms),
        "total_permissions": len(all_perms),
        "features": features,
    }


# ---------------------------------------------------------------------------
# Subcommand: platform
# ---------------------------------------------------------------------------

def cmd_platform(repo_dir: str) -> Dict[str, Any]:
    """Identify target platforms and build configuration."""
    platforms = set()
    root = Path(repo_dir)

    # Android markers
    if list(root.rglob("AndroidManifest.xml")):
        platforms.add("android")
    if list(root.rglob("build.gradle*")):
        platforms.add("android")

    # iOS markers
    if list(root.rglob("*.xcodeproj")) or list(root.rglob("*.xcworkspace")):
        platforms.add("ios")
    if list(root.rglob("Podfile")):
        platforms.add("ios")

    # Flutter
    if (root / "pubspec.yaml").exists():
        platforms.add("flutter")

    # React Native
    if (root / "app.json").exists() or (root / "metro.config.js").exists():
        platforms.add("react_native")

    features = []
    if platforms:
        features.append({
            "name": "cross_platform_mobile_support",
            "description": f"App targets {len(platforms)} platform(s): {', '.join(sorted(platforms))}",
            "confidence": 0.95,
            "source_modules": [],
        })

    return {
        "platforms": sorted(platforms),
        "features": features,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Mobile App Skill Pack — Extract screens, permissions, and platform info"
    )
    parser.add_argument("repo_dir", help="Path to cloned repository root")
    parser.add_argument("output_file", help="Path to write JSON output")
    parser.add_argument(
        "subcommand",
        choices=["screens", "permissions", "platform", "extract"],
        help="Extraction subcommand",
    )
    args = parser.parse_args()

    if not Path(args.repo_dir).is_dir():
        print(f"Error: {args.repo_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    handlers = {
        "screens": cmd_screens,
        "permissions": cmd_permissions,
        "platform": cmd_platform,
        "extract": lambda d: {
            **cmd_screens(d),
            "permissions": cmd_permissions(d),
            "platform": cmd_platform(d),
        },
    }

    result = handlers[args.subcommand](args.repo_dir)
    out = Path(args.output_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Success! {args.subcommand} → {out} ({len(result.get('features', []))} features)")


if __name__ == "__main__":
    main()
