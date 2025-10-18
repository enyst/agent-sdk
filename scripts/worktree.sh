#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: $(basename "$0") <command> [options]

Commands:
  list                         Show all worktrees managed by this repository
  path <branch>                Print the filesystem path for a worktree branch
  create <branch> [start]      Create a new worktree in ${WORKTREES_DIR:-.worktrees}/<branch>
  remove <branch>              Remove the worktree for <branch>
  prune                        Run 'git worktree prune'
  open <branch>                Open the worktree in VS Code (requires 'code' on PATH)

Environment variables:
  WORKTREES_DIR  Override worktree base directory (default: <repo>/.worktrees)
  DEFAULT_BASE   Default branch/commit used when creating a new branch (default: origin/main)
EOF
}

err() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

require_branch_name() {
  if [[ -z "${1:-}" ]]; then
    err "missing branch name"
  fi
}

resolve_repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || err "not inside a git repository"
}

worktree_path_for_branch() {
  local branch=$1
  printf '%s/%s' "$WORKTREES_DIR" "$branch"
}

branch_exists() {
  git rev-parse --verify --quiet "refs/heads/$1" >/dev/null
}

branch_checked_out_elsewhere() {
  local branch=$1
  git worktree list --porcelain | awk -v b="refs/heads/$branch" '
    $1 == "branch" && $2 == b { found = 1 }
    END { exit found ? 0 : 1 }
  '
}

create_worktree() {
  local branch=$1
  local start_ref=${2:-$DEFAULT_BASE}
  local path
  path=$(worktree_path_for_branch "$branch")

  if [[ -d "$path" ]]; then
    err "target path $path already exists"
  fi

  if branch_checked_out_elsewhere "$branch"; then
    err "branch $branch is already checked out in another worktree"
  fi

  mkdir -p "$WORKTREES_DIR"

  if branch_exists "$branch"; then
    git worktree add "$path" "$branch"
  else
    git worktree add -b "$branch" "$path" "$start_ref"
  fi
}

remove_worktree() {
  local branch=$1
  local path
  path=$(worktree_path_for_branch "$branch")

  if [[ ! -d "$path" ]]; then
    err "no worktree directory found for branch $branch at $path"
  fi

  git worktree remove "$path"
}

open_in_vscode() {
  local branch=$1
  local path
  path=$(worktree_path_for_branch "$branch")

  if [[ ! -d "$path" ]]; then
    err "no worktree directory found for branch $branch at $path"
  fi

  if ! command -v code >/dev/null 2>&1; then
    err "'code' executable not found on PATH"
  fi

  code "$path"
}

list_worktrees() {
  git worktree list
}

main() {
  local repo_root
  repo_root=$(resolve_repo_root)
  cd "$repo_root"

  WORKTREES_DIR=${WORKTREES_DIR:-"$repo_root/.worktrees"}
  DEFAULT_BASE=${DEFAULT_BASE:-origin/main}

  local command=${1:-}

  case "$command" in
    list)
      shift
      list_worktrees "$@"
      ;;
    path)
      shift
      require_branch_name "${1:-}"
      worktree_path_for_branch "$1"
      ;;
    create)
      shift
      require_branch_name "${1:-}"
      create_worktree "$1" "${2:-}"
      ;;
    remove)
      shift
      require_branch_name "${1:-}"
      remove_worktree "$1"
      ;;
    prune)
      shift
      git worktree prune "$@"
      ;;
    open)
      shift
      require_branch_name "${1:-}"
      open_in_vscode "$1"
      ;;
    -h|--help|help|"")
      usage
      ;;
    *)
      err "unknown command: $command"
      ;;
  esac
}

main "$@"
