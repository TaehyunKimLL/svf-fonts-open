#!/bin/bash
# verify-extraction.sh SQUASHFS_ROOT REGENERATED_THIRD_PARTY CHECKOUT: what the AppImage ships against what it must ship.
#   notices: resources/THIRD-PARTY.txt is byte-equal to the file the generator writes over the extraction;
#   sources: resources/repo/{maker,tools}/*.py are exactly the checkout's non-test *.py files, equal by sha256.
# Prints one "<name> ok" or "<name> FAIL <why>" line per check and exits 1 on any FAIL (used by release-check.sh).
SQ=${1:?extraction root}; REGEN=${2:?regenerated THIRD-PARTY.txt}; CO=${3:?checkout}
FAILED=0
if cmp -s "$SQ/resources/THIRD-PARTY.txt" "$REGEN"; then echo "notices ok"; else echo "notices FAIL bundled THIRD-PARTY.txt differs from the regenerated one"; FAILED=1; fi
BAD=""
for d in maker tools; do
    exp=$(cd "$CO/$d" && ls *.py 2>/dev/null | grep -v '^test_' | sort)
    got=$(cd "$SQ/resources/repo/$d" 2>/dev/null && ls *.py 2>/dev/null | sort)
    [ "$exp" = "$got" ] || BAD="$BAD $d(file set differs)"
    for f in $got; do
        a=$(sha256sum "$SQ/resources/repo/$d/$f" | cut -d' ' -f1)
        b=$(sha256sum "$CO/$d/$f" 2>/dev/null | cut -d' ' -f1)
        [ "$a" = "$b" ] || BAD="$BAD repo/$d/$f"
    done
done
if [ -z "$BAD" ]; then echo "repo-sources ok"; else echo "repo-sources FAIL$BAD"; FAILED=1; fi
exit $FAILED
