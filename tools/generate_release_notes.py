"""Generate release notes from git tags and conventional commits."""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime


CONVENTIONAL_PATTERN = re.compile(
    r'^(?P<type>\w+)(?:\((?P<scope>[\w.-]+)\))?:\s*(?P<description>.+)$'
)

TYPE_LABELS = {
    'feat': 'features',
    'feature': 'features',
    'fix': 'bug_fixes',
    'bugfix': 'bug_fixes',
    'docs': 'documentation',
    'refactor': 'refactoring',
    'perf': 'performance',
    'test': 'tests',
    'build': 'build_ci',
    'ci': 'build_ci',
    'chore': 'chores',
    'style': 'style',
    'release': 'chores',
}

TYPE_TITLES = {
    'features': '新功能',
    'bug_fixes': 'Bug 修复',
    'documentation': '文档',
    'refactoring': '代码重构',
    'performance': '性能优化',
    'tests': '测试',
    'build_ci': '构建 / CI',
    'chores': '杂项',
    'style': '代码风格',
    'other': '其他变更',
}


def run_git(*args):
    result = subprocess.run(
        ['git', *args],
        capture_output=True,
        text=True,
        check=True,
        encoding='utf-8',
    )
    return result.stdout.strip()


def get_sorted_tags():
    tags = run_git('tag', '--sort=-creatordate').splitlines()
    semver_tags = [t for t in tags if re.match(r'^v?\d+\.\d+\.\d+$', t)]
    return semver_tags


def find_previous_tag(current_tag):
    tags = get_sorted_tags()
    try:
        idx = tags.index(current_tag)
        if idx + 1 < len(tags):
            return tags[idx + 1]
    except ValueError:
        pass
    return None


def get_commits_between(old_tag, new_tag):
    if old_tag:
        range_spec = f'{old_tag}..{new_tag}'
    else:
        range_spec = new_tag
    try:
        log = run_git('log', '--oneline', '--format=%H%n%an%n%ai%n%s%n---', range_spec)
    except subprocess.CalledProcessError:
        print(f"::warning::无法获取 {range_spec} 之间的提交记录", file=sys.stderr)
        return []

    commits = []
    for block in log.split('\n---\n'):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) < 4:
            continue
        commits.append({
            'hash': lines[0][:8],
            'author': lines[1],
            'date': lines[2][:10],
            'subject': lines[3],
        })
    return commits


def classify_commit(subject):
    m = CONVENTIONAL_PATTERN.match(subject)
    if m:
        commit_type = m.group('type').lower()
        scope = m.group('scope')
        desc = m.group('description')
        category = TYPE_LABELS.get(commit_type, 'other')
        return category, scope, desc
    return 'other', None, subject


def generate_notes(current_tag, previous_tag=None, repo_url=''):
    if previous_tag is None:
        previous_tag = find_previous_tag(current_tag)

    commits = get_commits_between(previous_tag, current_tag)

    grouped = defaultdict(list)
    for c in commits:
        category, scope, desc = classify_commit(c['subject'])
        # Deduplicate similar messages
        if not any(desc == item[0] for item in grouped[category]):
            grouped[category].append((desc, c['hash']))

    today = datetime.now().strftime('%Y-%m-%d')
    ver = current_tag.lstrip('v')

    lines = [f'## ParkMan v{ver} ({today})', '']

    if not commits:
        lines.append('无变更记录')
        lines.append('')
        return '\n'.join(lines)

    for category in ['features', 'bug_fixes', 'refactoring', 'performance',
                     'documentation', 'tests', 'build_ci', 'chores', 'style', 'other']:
        if category not in grouped:
            continue
        title = TYPE_TITLES.get(category, category)
        lines.append(f'### {title}')
        for desc, hash_ in grouped[category]:
            lines.append(f'- {desc} ({hash_})')
        lines.append('')

    if previous_tag and current_tag:
        if repo_url:
            compare_url = f'{repo_url}/compare/{previous_tag}...{current_tag}'
            lines.append(f'**完整变更**: [{previous_tag}...{current_tag}]({compare_url})')
        else:
            lines.append(f'**完整变更**: {previous_tag}...{current_tag}')
        lines.append('')

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Generate release notes from git tags')
    parser.add_argument('--current-tag', required=True, help='当前版本标签 (例如 v1.10.3)')
    parser.add_argument('--previous-tag', help='上一版本标签 (留空则自动查找)')
    parser.add_argument('--repo-url', default='', help='仓库 URL，用于生成比较链接')
    parser.add_argument('--output', '-o', help='输出文件路径 (默认输出到 stdout)')
    args = parser.parse_args()

    notes = generate_notes(args.current_tag, args.previous_tag, args.repo_url)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(notes)
        print(f'Release notes written to {args.output}')
    else:
        print(notes)


if __name__ == '__main__':
    main()
