import argparse
import json
import os
import sys
from pathlib import Path
import re


def scan_repo(repo_dir):
    p = Path(repo_dir)
    result = {
        "dockerfiles": [],
        "package_json_paths": [],
        "readme_paths": [],
        "react_ts_files_count": 0,
        "uses_pdfjs": False,
        "uses_react_dropzone": False,
        "uses_react_router": False,
        "uses_tailwind": False,
        "top_dependencies": []
    }

    try:
        for fp in p.rglob('*'):
            if fp.is_file():
                name = fp.name.lower()
                if name == 'dockerfile' or name.startswith('dockerfile.') or 'docker' in fp.parts:
                    if 'docker' in fp.parts or name.startswith('dockerfile'):
                        result['dockerfiles'].append(str(fp.relative_to(p)))
                if name.startswith('readme'):
                    result['readme_paths'].append(str(fp.relative_to(p)))
                if name == 'package.json':
                    result['package_json_paths'].append(str(fp.relative_to(p)))
                    try:
                        data = json.loads(fp.read_text(encoding='utf-8'))
                        deps = {}
                        for k in ('dependencies','devDependencies','peerDependencies'):
                            if k in data and isinstance(data[k], dict):
                                deps.update(data[k])
                        result['top_dependencies'] = list(deps.keys())[:50]
                        # feature flags from deps
                        all_deps = ' '.join(result['top_dependencies']).lower()
                        if 'pdfjs' in all_deps or 'pdfjs-dist' in all_deps:
                            result['uses_pdfjs'] = True
                        if 'react-dropzone' in all_deps:
                            result['uses_react_dropzone'] = True
                        if 'react-router' in all_deps or '@react-router' in all_deps:
                            result['uses_react_router'] = True
                        if 'tailwind' in all_deps:
                            result['uses_tailwind'] = True
                    except Exception:
                        pass
                if fp.suffix in ('.js','.jsx','.ts','.tsx'):
                    try:
                        txt = fp.read_text(encoding='utf-8')
                    except Exception:
                        txt = ''
                    if re.search(r"\bReact\b|from\s+['\"]react['\"]", txt) or re.search(r"\.tsx?\b", fp.name):
                        result['react_ts_files_count'] += 1
                    if 'pdfjs' in txt or 'pdfjs-dist' in txt:
                        result['uses_pdfjs'] = True
                    if 'react-dropzone' in txt:
                        result['uses_react_dropzone'] = True
                    if 'react-router' in txt or '@react-router' in txt:
                        result['uses_react_router'] = True
                    if 'tailwind' in txt or 'className' in txt and 'tw-' in txt:
                        result['uses_tailwind'] = True
        return result
    except Exception as e:
        raise


def write_output(out_path, data):
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Extractor for React Dockerized frontend library')
    parser.add_argument('repo_dir')
    parser.add_argument('output_file')
    subparsers = parser.add_subparsers(dest='subcommand')

    scan_p = subparsers.add_parser('scan')

    args = parser.parse_args()
    if not args.subcommand:
        print('No subcommand provided. Use "scan".', file=sys.stderr)
        sys.exit(1)

    repo_dir = args.repo_dir
    out_file = args.output_file

    try:
        res = scan_repo(repo_dir)
        # Basic confidence heuristics
        confidence = 0.0
        if res['dockerfiles']:
            confidence += 0.4
        if res['react_ts_files_count'] > 0:
            confidence += 0.4
        if res['top_dependencies']:
            confidence += 0.2
        res['confidence'] = min(1.0, confidence)
        write_output(out_file, res)
        print('scan: success')
        sys.exit(0)
    except Exception as e:
        print('scan: failure - ' + str(e), file=sys.stderr)
        try:
            # write minimal failure output
            write_output(out_file, {"error": str(e)})
        except Exception:
            pass
        sys.exit(1)


if __name__ == '__main__':
    main()
