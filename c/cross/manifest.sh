# manifest.sh - tree manifests of the installers (sourced by c/cross/install-toolchains.sh and c/bench/install-emulators.sh).
#
# Threat model: accidental drift or corruption of a host-local tree (a stray edit, a truncated copy, a half-run upgrade),
# not an adversary. The manifest pin is held in the repository script, so a manifest edited together with its tree is
# caught; someone who can edit both the script and the tree is out of scope.
#
# manifest_list DIR            prints "<sha256>  ./path" for every regular file of DIR (find -print0, sort -z, then
#                              xargs -0 -r sha256sum, so any file name is safe), then "exec <octal> <path>" for every
#                              file with an exec bit (mode & 0111, so a lost +x is a difference; umask does not matter),
#                              then "link <path> -> <target>" for every symlink, path and target both printf %q. Only
#                              ./.svf-manifest (DIR's own) is excluded from either pass. Exit 1 when a find or realpath
#                              fails (unreadable directory), on a symlink loop, or when a target is absolute or leaves DIR.
# manifest_write NAME DIR ARCHIVE_SHA   writes DIR/.svf-manifest (line 1 ARCHIVE_SHA; for ch583 the pinned commit, as
#                              install-toolchains.sh passes it, then manifest_list) and prints its
#                              sha256 (the pin for the script). Nothing is written when manifest_list fails.
# manifest_verify NAME DIR PIN "NAME: not installed" (exit 0) if DIR is absent; exit 1 "unpinned" if PIN is empty; exit 1 if
#                              sha256(DIR/.svf-manifest) != PIN; exit 1 naming the first differing path if the tree no
#                              longer matches the manifest.
# The functions need bash (printf %q) for the symlink part only; it runs as `bash -c`, so a /bin/sh script may source this.

manifest_list() {
	(
		cd "$1" || exit 1
		root=$(pwd -P)
		w=$(mktemp -d) || exit 1
		trap 'rm -rf "$w"' EXIT
		# every stage writes a file and its status is checked: a failed find (an unreadable directory) must not
		# leave a shorter list behind a pipeline's last status
		find . -type f ! -path ./.svf-manifest -print0 >"$w/f" || exit 1
		LC_ALL=C sort -z <"$w/f" >"$w/fs" || exit 1
		xargs -0 -r sha256sum <"$w/fs" || exit 1
		find . -type f ! -path ./.svf-manifest -printf '%p\t%m\0' >"$w/m" || exit 1
		LC_ALL=C sort -z <"$w/m" >"$w/ms" || exit 1
		find . -type l ! -path ./.svf-manifest -print0 >"$w/l" || exit 1
		LC_ALL=C sort -z <"$w/l" >"$w/ls" || exit 1
		bash -c '
			root=$1 w=$2
			while IFS= read -r -d "" rec; do
				p=${rec%$'"'"'\t'"'"'*} m=${rec##*$'"'"'\t'"'"'}
				x=$(( 8#$m & 8#111 ))
				[ "$x" -eq 0 ] || printf "exec %03o %q\n" "$x" "$p"
			done <"$w/ms" || exit 1
			while IFS= read -r -d "" l; do
				t=$(readlink -- "$l") || exit 1
				case $t in
				/*) echo "manifest: absolute symlink target: $l -> $t" >&2; exit 1 ;;
				esac
				# LC_ALL=C: the loop test reads the message of stat, which a translated locale would change
				if e=$(LC_ALL=C stat -L -c %F -- "$l" 2>&1 >/dev/null); then :; else
					case $e in *"Too many levels"*) echo "manifest: symlink loop: $l" >&2; exit 1 ;; esac
				fi
				r=$(realpath -m --relative-base="$root" -- "$(dirname -- "$l")/$t") || { echo "manifest: realpath failed: $l" >&2; exit 1; }
				case $r in
				/*) echo "manifest: symlink leaves the tree: $l -> $t" >&2; exit 1 ;;
				esac
				printf "link %q -> %q\n" "$l" "$t"
			done <"$w/ls"' _ "$root" "$w" || exit 1
	)
}

manifest_write() {
	_mw_name=$1 _mw_dir=$2 _mw_sha=$3
	_mw_tmp=$(mktemp) || return 1
	{ echo "$_mw_sha"; manifest_list "$_mw_dir"; } >"$_mw_tmp" || { rm -f "$_mw_tmp"; return 1; }
	chmod 644 "$_mw_tmp" && cp "$_mw_tmp" "$_mw_dir/.svf-manifest" || { rm -f "$_mw_tmp"; return 1; }
	rm -f "$_mw_tmp"
	sha256sum <"$_mw_dir/.svf-manifest" | cut -d' ' -f1
}

# manifest_verify NAME DIR PIN [WHAT]: WHAT names where PIN comes from in messages (default "the pin in the script")
manifest_verify() {
	_mv_name=$1 _mv_dir=$2 _mv_pin=$3 _mv_what=${4:-the pin in the script}
	# only an absent path is "not installed": a file, a symlink (even a dangling one) or any non-directory is an error
	if [ -L "$_mv_dir" ] || { [ -e "$_mv_dir" ] && [ ! -d "$_mv_dir" ]; }; then
		echo "$_mv_name: $_mv_dir is a symlink or not a directory" >&2
		return 1
	fi
	[ -d "$_mv_dir" ] || { echo "$_mv_name: not installed ($_mv_dir)"; return 0; }
	[ -n "$_mv_pin" ] || { echo "$_mv_name: unpinned (no MANIFEST_PIN in the script; run --adopt $_mv_name)" >&2; return 1; }
	[ -f "$_mv_dir/.svf-manifest" ] || { echo "$_mv_name: $_mv_dir/.svf-manifest is missing" >&2; return 1; }
	_mv_got=$(sha256sum <"$_mv_dir/.svf-manifest" | cut -d' ' -f1)
	[ "$_mv_got" = "$_mv_pin" ] || {
		echo "$_mv_name: $_mv_dir/.svf-manifest does not match $_mv_what (pin $_mv_pin, manifest $_mv_got)" >&2
		return 1
	}
	_mv_tmp=$(mktemp -d) || return 1
	if ! manifest_list "$_mv_dir" >"$_mv_tmp/now" 2>"$_mv_tmp/err"; then
		cat "$_mv_tmp/err" >&2
		rm -rf "$_mv_tmp"
		return 1
	fi
	tail -n +2 "$_mv_dir/.svf-manifest" >"$_mv_tmp/was"
	if ! cmp -s "$_mv_tmp/was" "$_mv_tmp/now"; then
		_mv_d=$(diff "$_mv_tmp/was" "$_mv_tmp/now" | grep '^[<>]' | head -n 1)
		echo "$_mv_name: $_mv_dir differs from its manifest, first difference: $_mv_d" >&2
		rm -rf "$_mv_tmp"
		return 1
	fi
	rm -rf "$_mv_tmp"
	echo "$_mv_name: OK ($_mv_dir)"
}
