#!/bin/bash
# run-verify.sh SQUASHFS_ROOT REGENERATED_THIRD_PARTY CHECKOUT [REPORT_SCRIPT]: release-check's verification step. Runs
# verify-report.sh and prints its CHECK lines; exits 1 when it fails. When the report script is missing or dies without
# printing a CHECK FAIL line (argument check, bash error), a "CHECK verify-extraction FAIL ..." line is printed anyway.
HERE=$(cd "$(dirname "$0")" && pwd)
REPORT=${4:-$HERE/verify-report.sh}
OUT=$(bash "$REPORT" "$1" "$2" "$3" 2>&1)
RC=$?
[ -n "$OUT" ] && printf '%s\n' "$OUT"
if [ "$RC" -ne 0 ]; then
    case $'\n'"$OUT" in
        *$'\n'"CHECK "*" FAIL "*) ;;
        *) echo "CHECK verify-extraction FAIL verify-report.sh exited $RC" ;;
    esac
    exit 1
fi
exit 0
