#!/bin/bash
# verify-report.sh SQUASHFS_ROOT REGENERATED_THIRD_PARTY CHECKOUT [VERIFIER]: runs verify-extraction.sh (or VERIFIER, for tests)
# and turns its lines into "CHECK <name> ok|FAIL <why>" lines. Fails closed: exit 1 when the verifier exits non-zero or
# cannot run, or when the "notices" or "repo-sources" line is missing from its output (a verifier that dies early must not pass).
HERE=$(cd "$(dirname "$0")" && pwd)
VERIFIER=${4:-$HERE/verify-extraction.sh}
FAILED=0
OUTPUT=$(bash "$VERIFIER" "${1:?extraction root}" "${2:?regenerated THIRD-PARTY.txt}" "${3:?checkout}" 2>&1)
STATUS=$?
if [ "$STATUS" -ne 0 ]; then
    echo "CHECK verify-extraction FAIL the verifier exited $STATUS"
    FAILED=1
fi
# Only "notices" and "repo-sources" lines are accepted, each exactly once; any other line (a duplicate, another name, garbage) is a FAIL
# that names the line. The verifier's stderr is merged into OUTPUT on purpose (2>&1): a stray warning therefore fails the check
# (fail closed) and is printed in the FAIL message.
SEEN=" "
while IFS= read -r line; do
    [ -n "$line" ] || continue
    name=${line%% *}
    case "$name" in
        notices|repo-sources)
            case "$SEEN" in *" $name "*) echo "CHECK verify-extraction FAIL unexpected output: $line (duplicate $name)"; FAILED=1; continue ;; esac
            SEEN="$SEEN$name " ;;
        *) echo "CHECK verify-extraction FAIL unexpected output: $line"; FAILED=1; continue ;;
    esac
    case "$line" in
        *" ok") echo "CHECK $name ok" ;;
        *" FAIL "*) echo "CHECK $name FAIL ${line#* FAIL }"; FAILED=1 ;;
        *) echo "CHECK verify-extraction FAIL unexpected output: $line"; FAILED=1 ;;
    esac
done <<< "$OUTPUT"
for name in notices repo-sources; do
    case "$SEEN" in *" $name "*) ;; *) echo "CHECK $name FAIL the verifier printed no result for it"; FAILED=1 ;; esac
done
exit $FAILED
