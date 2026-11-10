#!/usr/bin/env python3
"""文档健康检查，与 verify.sh 并列（见 AGENTS.md「收工前必须」）。

四项硬检查 + 一项提示：
1. 本地 Markdown 链接可解析（行内代码路径与外部 file:// / http(s) 跳过，归档目录不参与）
2. 五个状态/规范文件存在且已被 git 跟踪（第 3 讲：agent 看不到的东西等于不存在）
3. 仓库根目录不允许同一份文档多版本并存（v1/v2 并存 = 两条矛盾的需求基线）
4. PROGRESS.md / FEATURES.md 不得落后于代码提交（第 5 讲：状态必须跟着工作走）；
   工作区里正在修改的文档不算落后，否则"修落后"这一条永远无法被自己验证
5. 提示：各文档声明的「依据 v2.x」与现行需求基线版本的漂移
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILES = [
    "AGENTS.md",
    "PROGRESS.md",
    "FEATURES.md",
    "GIT_COMMIT_CONVENTION.md",
    "STARTUP_READINESS.md",
]
CODE_PATHS = ["backend/app", "frontend/src"]
SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "__pycache__", ".pytest_cache", "docs/archive"}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
VERSIONED_RE = re.compile(r"^(?P<base>.+_)v\d+\.md$")
BASIS_RE = re.compile(r"开发指导文档_v2\.md[（(]\s*(v\d+\.\d+)")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def markdown_docs() -> list[Path]:
    found: list[Path] = []
    for path in sorted(ROOT.rglob("*.md")):
        relative = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in relative.split("/")[:-1]):
            continue
        found.append(path)
    return found


def tracked() -> set[str]:
    return set(git("ls-files").splitlines())


def last_commit(paths: list[str]) -> int | None:
    out = git("log", "-1", "--format=%ct", "--", *paths)
    return int(out) if out.isdigit() else None


def check_links(docs: list[Path], problems: list[str]) -> None:
    """只校验 Markdown 链接：`[文字](目标)` 是在断言目标存在。

    行内代码 `foo.md` 不算断言——它既可能是待创建的产物（FEATURES 任务里的
    `docs/验收报告.md`），也可能是被讨论的文件名，按存在性检查必然误报。
    """
    for doc in docs:
        for lineno, line in enumerate(
            doc.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for target in sorted(m.group(1).strip() for m in LINK_RE.finditer(line)):
                if target.startswith(("#", "http://", "https://", "mailto:")) or "://" in target:
                    continue
                cleaned = target.split("#", 1)[0].split(" ", 1)[0]
                if not cleaned:
                    continue
                if (doc.parent / cleaned).exists() or (ROOT / cleaned).exists():
                    continue
                problems.append(
                    f"{doc.relative_to(ROOT)}:{lineno}: 链接指向不存在的文件 {cleaned}"
                )


def check_state_tracked(tracked_files: set[str], problems: list[str]) -> None:
    for name in STATE_FILES:
        path = ROOT / name
        if not path.exists():
            problems.append(f"{name}: 状态/规范文件不存在")
        elif name not in tracked_files:
            problems.append(f"{name}: 存在于工作区但未被 git 跟踪（新会话从 git 里读不到它）")


def check_root_versions(problems: list[str]) -> None:
    families: dict[str, list[str]] = {}
    for path in sorted(ROOT.glob("*.md")):
        match = VERSIONED_RE.match(path.name)
        if match:
            families.setdefault(match.group("base"), []).append(path.name)
    for names in families.values():
        if len(names) > 1:
            problems.append(
                f"根目录同一文档存在 {len(names)} 个版本 {names}；旧版请移入 docs/archive/"
            )


def check_state_freshness(tracked_files: set[str], problems: list[str]) -> None:
    code_ts = last_commit(CODE_PATHS)
    if code_ts is None:
        return
    dirty: set[str] = set()
    for line in git("status", "--porcelain").splitlines():
        for raw in line[3:].split(" -> "):
            dirty.add(Path(raw.strip().strip('"')).name)
    for name in ("PROGRESS.md", "FEATURES.md"):
        if name not in tracked_files:
            continue  # 已由 check_state_tracked 报告
        if name in dirty:
            # 文档正在本次改动里更新（pre-commit 早于 commit 生效），无法要求它
            # 已经包含本次提交的时间戳；本次提交完成后此项自然转为通过。
            continue
        doc_ts = last_commit([name])
        if doc_ts is not None and code_ts > doc_ts:
            problems.append(
                f"{name}: 代码在它之后还有提交，进度文档已落后（每个 Task 提交都要同步更新）"
            )


def report_basis_drift(docs: list[Path]) -> list[str]:
    versions: dict[str, str] = {}
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        for match in BASIS_RE.finditer(text):
            versions.setdefault(str(doc.relative_to(ROOT)), match.group(1))
    if not versions:
        return []
    current = max(versions.values(), key=lambda v: tuple(int(p) for p in v[1:].split(".")))
    return [
        f"{name} 声明依据 {version}，现行基线 {current}（该文档尚未跟着复核）"
        for name, version in sorted(versions.items())
        if version != current
    ]


def main() -> int:
    try:
        git("rev-parse", "--git-dir")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("SKIP   非 git 仓库，文档检查跳过", file=sys.stderr)
        return 0

    docs = markdown_docs()
    tracked_files = tracked()
    problems: list[str] = []

    check_links(docs, problems)
    check_state_tracked(tracked_files, problems)
    check_root_versions(problems)
    check_state_freshness(tracked_files, problems)

    print(f"DOCS     扫描 {len(docs)} 份 Markdown，检查链接/入库/多版本/新鲜度")
    for note in report_basis_drift(docs):
        print(f"NOTE     {note}")
    if problems:
        for problem in problems:
            print(f"ERROR  {problem}", file=sys.stderr)
        print(
            "FIX    链接改指向真实文件；缺失的状态文件 git add；旧版本文档移入 docs/archive/；"
            "更新 PROGRESS.md / FEATURES.md 后重新提交",
            file=sys.stderr,
        )
        return 1
    print("DOCS OK  链接全部可解析，状态文件已入库，无多版本并存，进度文档未落后于代码")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
