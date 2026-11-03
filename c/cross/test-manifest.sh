#!/bin/sh
# Tests of c/cross/manifest.sh (the installers' tree manifests) on temporary trees.
# Usage: sh c/cross/test-manifest.sh   (prints "manifest: OK"; exit 1 on a failure)
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT
fail() { echo "manifest: FAIL: $1" >&2; exit 1; }
. "$here/manifest.sh" || fail "manifest.sh does not load"

# expect_fail CMD...: runs CMD, stdout and stderr into $tmp/out; must exit 1
expect_fail() { "$@" >"$tmp/out" 2>&1 && return 1; [ $? -eq 1 ]; }

t=$tmp/tree
mkdir -p "$t/dir"
echo alpha >"$t/a"
echo beta >"$t/dir/b c"
echo gamma >"$t/new
line"
ln -s "dir/b c" "$t/l"
pin=$(manifest_write test "$t" 0123abcd) || fail "manifest_write failed"
[ -f "$t/.svf-manifest" ] || fail "no manifest written"
[ "$(head -n 1 "$t/.svf-manifest")" = 0123abcd ] || fail "line 1 is not the archive sha"
[ "$pin" = "$(sha256sum <"$t/.svf-manifest" | cut -d' ' -f1)" ] || fail "printed pin is not the manifest's sha256"
grep -q '^link \./l -> dir/b\\ c$' "$t/.svf-manifest" || fail "symlink target not recorded escaped"
manifest_verify test "$t" "$pin" >/dev/null || fail "fresh manifest does not verify"
nlsha=$(cd "$t" && sha256sum "./new
line" | cut -c2-65)
grep -qxF "\\$nlsha  ./new\\nline" "$t/.svf-manifest" || fail "newline-named file is not one escaped line: $(grep -n 'new' "$t/.svf-manifest")"
echo GAMMA >"$t/new
line"
expect_fail manifest_verify test "$t" "$pin" || fail "changed newline-named file verified"
echo gamma >"$t/new
line"
manifest_verify test "$t" "$pin" >/dev/null || fail "restored newline-named file does not verify"
# a link whose name has a newline stays one line, its name escaped like its target
ln -s a "$t/lk
nm"
[ "$(manifest_list "$t" | grep -c '^link ')" -eq 2 ] || fail "newline-named link split over lines: $(manifest_list "$t" | grep -n link)"
manifest_list "$t" | grep -qxF "link \$'./lk\\nnm' -> a" || fail "link name not escaped: $(manifest_list "$t" | grep lk)"
rm "$t/lk
nm"

# a changed byte names the file
echo ALPHA >"$t/a"
expect_fail manifest_verify test "$t" "$pin" || fail "changed file verified"
grep -q './a' "$tmp/out" || fail "changed file not named: $(cat "$tmp/out")"
echo alpha >"$t/a"
manifest_verify test "$t" "$pin" >/dev/null || fail "restored file does not verify"

# the same change with the manifest regenerated: the old pin fails on the pin
echo ALPHA >"$t/a"
pin2=$(manifest_write test "$t" 0123abcd)
[ "$pin2" != "$pin" ] || fail "manifest unchanged by an edit"
manifest_verify test "$t" "$pin2" >/dev/null || fail "regenerated manifest does not verify against its own pin"
expect_fail manifest_verify test "$t" "$pin" || fail "old pin accepted"
grep -qi 'pin' "$tmp/out" || fail "pin failure not named: $(cat "$tmp/out")"

# an edited manifest (one character) fails on the pin, not on the tree
cp "$t/.svf-manifest" "$tmp/manifest.orig"
sed '1s/0/1/' "$tmp/manifest.orig" >"$t/.svf-manifest"
expect_fail manifest_verify test "$t" "$pin2" || fail "edited manifest accepted"
grep -qi 'pin' "$tmp/out" || fail "edited manifest not refused on the pin: $(cat "$tmp/out")"
cp "$tmp/manifest.orig" "$t/.svf-manifest"
manifest_verify test "$t" "$pin2" >/dev/null || fail "restored manifest does not verify"

# an added file, a removed file and a retargeted link are differences of the list
echo x >"$t/extra"
expect_fail manifest_verify test "$t" "$pin2" || fail "extra file verified"
grep -q './extra' "$tmp/out" || fail "extra file not named"
rm "$t/extra"
ln -sfn dir "$t/l"
expect_fail manifest_verify test "$t" "$pin2" || fail "retargeted link verified"
grep -q './l' "$tmp/out" || fail "retargeted link not named"
ln -sfn "dir/b c" "$t/l"

# absolute and escaping symlinks fail in manifest_list, and so in manifest_write
ln -s /etc/hostname "$t/bad"
expect_fail manifest_list "$t" || fail "absolute symlink listed"
rm "$t/bad"
ln -s ../x "$t/up"
expect_fail manifest_list "$t" || fail "escaping symlink listed"
rm "$t/up"
ln -s ../../x "$t/dir/up2"
expect_fail manifest_list "$t" || fail "deep escaping symlink listed"
rm "$t/dir/up2"
ln -s ../a "$t/dir/ok" # stays inside the tree
manifest_list "$t" >/dev/null || fail "inside-tree '..' link refused"
rm "$t/dir/ok"
ln -s ../x "$t/up"
before=$(sha256sum <"$t/.svf-manifest")
expect_fail manifest_write test "$t" 0123abcd || fail "manifest written over an escaping link"
[ "$before" = "$(sha256sum <"$t/.svf-manifest")" ] || fail "manifest changed by a failed write"
rm "$t/up"

# a removed file is a difference; a missing manifest is an error
cp "$t/a" "$tmp/a.keep"
rm "$t/a"
expect_fail manifest_verify test "$t" "$pin2" || fail "removed file verified"
grep -q './a' "$tmp/out" || fail "removed file not named: $(cat "$tmp/out")"
cp "$tmp/a.keep" "$t/a"
mv "$t/.svf-manifest" "$tmp/m.keep"
expect_fail manifest_verify test "$t" "$pin2" || fail "missing manifest verified"
grep -q 'manifest' "$tmp/out" || fail "missing manifest not named"
mv "$tmp/m.keep" "$t/.svf-manifest"
manifest_verify test "$t" "$pin2" >/dev/null || fail "restored tree does not verify"

# exec bits are part of the manifest: an accidental loss of +x fails verify
x=$tmp/xtree
mkdir "$x"
printf '#!/bin/sh\n' >"$x/run"
chmod 755 "$x/run"
px=$(manifest_write x "$x" ff)
manifest_verify x "$x" "$px" >/dev/null || fail "exec tree does not verify"
chmod 644 "$x/run"
expect_fail manifest_verify x "$x" "$px" || fail "lost +x verified"
grep -q './run' "$tmp/out" || fail "lost +x: file not named"

# a failure of find (unreadable directory) or of the link pass (a symlink loop) fails the list, never a short one
u=$tmp/unreadable
mkdir -p "$u/locked"
echo f >"$u/locked/f"
echo g >"$u/g"
chmod 000 "$u/locked"
expect_fail manifest_list "$u" || { chmod 755 "$u/locked"; fail "unreadable directory gave a list"; }
expect_fail manifest_write x "$u" ff || { chmod 755 "$u/locked"; fail "manifest written for an unreadable tree"; }
[ ! -e "$u/.svf-manifest" ] || { chmod 755 "$u/locked"; fail "manifest file left after a failed write"; }
chmod 755 "$u/locked"
l=$tmp/loop
mkdir "$l"
ln -s loop "$l/loop"
expect_fail manifest_list "$l" || fail "symlink loop listed"
grep -q 'symlink loop' "$tmp/out" || fail "symlink loop not named"
# ... in any locale: stat's message is read under LC_ALL=C
LANGUAGE=de LC_ALL=en_US.utf8 expect_fail manifest_list "$l" || fail "symlink loop listed (LANGUAGE=de)"
grep -q 'symlink loop' "$tmp/out" || fail "symlink loop not named (LANGUAGE=de)"
# a symlink named .svf-manifest is not part of the list either
sm=$tmp/smlink
mkdir "$sm"
echo q >"$sm/q"
ln -s q "$sm/.svf-manifest"
manifest_list "$sm" | grep -q 'svf-manifest' && fail ".svf-manifest symlink listed"

# a file or a symlink where the tree should be is an error, only an absent path is "not installed"
echo notadir >"$tmp/afile"
expect_fail manifest_verify f "$tmp/afile" "$pin2" || fail "a file at the destination verified"
ln -s "$t" "$tmp/alink"
expect_fail manifest_verify f "$tmp/alink" "$pin2" || fail "a symlink at the destination verified"
ln -s "$tmp/nowhere" "$tmp/dangling"
expect_fail manifest_verify f "$tmp/dangling" "$pin2" || fail "a dangling symlink at the destination counted as not installed"

# an empty tree and a tree of only symlinks (xargs -r: no stray hash of stdin)
e=$tmp/empty
mkdir "$e"
[ -z "$(manifest_list "$e")" ] || fail "empty tree lists something"
pe=$(manifest_write empty "$e" ff) || fail "empty tree write"
manifest_verify empty "$e" "$pe" >/dev/null || fail "empty tree does not verify"
[ "$(wc -l <"$e/.svf-manifest")" -eq 1 ] || fail "empty tree manifest has more than the archive line"
s=$tmp/links
mkdir "$s"
ln -s x "$s/one"
ln -s one "$s/two"
[ "$(manifest_list "$s")" = "link ./one -> x
link ./two -> one" ] || fail "link-only tree list: $(manifest_list "$s")"
ps=$(manifest_write links "$s" ff) || fail "link-only tree write"
manifest_verify links "$s" "$ps" >/dev/null || fail "link-only tree does not verify"

# only ./.svf-manifest is excluded: a nested one is listed and hashed
n=$tmp/nested
mkdir -p "$n/sub"
echo top >"$n/f"
echo one >"$n/sub/.svf-manifest"
manifest_list "$n" | grep -q '\./sub/\.svf-manifest' || fail "nested .svf-manifest excluded"
pn=$(manifest_write nested "$n" aa)
echo two >"$n/sub/.svf-manifest"
expect_fail manifest_verify nested "$n" "$pn" || fail "edited nested .svf-manifest verified"
grep -q 'sub/.svf-manifest' "$tmp/out" || fail "nested .svf-manifest not named"

# a missing directory is not installed (exit 0); an empty pin is unpinned (exit 1)
manifest_verify gone "$tmp/absent" "" >"$tmp/out" || fail "absent dir is an error"
grep -q 'not installed' "$tmp/out" || fail "absent dir: no 'not installed'"
# the message names where the pin comes from
expect_fail manifest_verify test "$t" "$pin" "the local pin /x/y" || fail "old pin accepted (named source)"
grep -q 'does not match the local pin /x/y' "$tmp/out" || fail "pin source not named"
expect_fail manifest_verify test "$t" "$pin" || fail "old pin accepted (default source)"
grep -q 'does not match the pin in the script' "$tmp/out" || fail "default pin source not named"
expect_fail manifest_verify test "$t" "" || fail "empty pin accepted"
grep -q 'unpinned' "$tmp/out" || fail "empty pin: no 'unpinned'"
echo "manifest: OK"
