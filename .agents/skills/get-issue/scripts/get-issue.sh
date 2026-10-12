#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/../../../lib/github-issues.sh"
[[ $# == 3 ]] || { github_error 'usage: get-issue.sh <owner> <repo> <issue-number>'; exit 2; }
github_issue_input "$1" "$2" "$3"
github_connect
github_read_issue "$1" "$2" "$3"
