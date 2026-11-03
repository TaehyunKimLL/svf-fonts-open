# install-lib.sh - helpers shared by c/cross/install-toolchains.sh and c/bench/install-emulators.sh (sourced, after
# manifest.sh; the caller sets PREFIX, DL and, for pin NAME, the variables MANIFEST_PIN_<name>).
#
# Everything the scripts create while installing or adopting (downloads' unpack areas, builds, clones, comparison trees)
# lives under PREFIX/.svf-work, which is removed when the script exits, whatever the exit path (trap).

WORK=$PREFIX/.svf-work

# work_ensure: PREFIX/.svf-work, empty (a leftover of a killed run is removed), removed again at exit.
work_ensure() {
	[ -z "${WORK_READY:-}" ] || return 0
	rm -rf "$WORK"
	mkdir -p "$WORK"
	trap 'rm -rf "$WORK"' EXIT
	WORK_READY=1
}

# pin NAME: prints MANIFEST_PIN_<name> (the name's '-' as '_'), empty if unset
pin() { eval "echo \"\${MANIFEST_PIN_$(echo "$1" | tr - _):-}\""; }

# bad NAME FILE: deletes FILE and stops.
bad() {
	rm -f "$2"
	echo "$1: hash mismatch for $2 (deleted)" >&2
	exit 1
}

# fetch_url NAME URL: downloads URL into DL/NAME/ (kept for a rerun); sets FETCHED to the file. The caller checks it.
fetch_url() {
	mkdir -p "$DL/$1"
	FETCHED=$DL/$1/$(basename "$2")
	if [ ! -f "$FETCHED" ]; then
		curl -fsSL --proto '=https' --proto-redir '=https' --retry 3 -o "$FETCHED.part" "$2" # HTTPS only, redirects too
		mv "$FETCHED.part" "$FETCHED"
	fi
}

# fetch_sha NAME URL SHA256 [LOCAL]: a LOCAL copy already on the host is used when its sha256 matches; otherwise URL is
# fetched (fetch_url) and checked; a file that fails the check is deleted and the script stops (exit 1). Sets FETCHED.
fetch_sha() {
	if [ -n "${4:-}" ] && [ -f "$4" ] && echo "$3  $4" | sha256sum -c - >/dev/null 2>&1; then
		FETCHED=$4
		return 0
	fi
	fetch_url "$1" "$2"
	echo "$3  $FETCHED" | sha256sum -c - >/dev/null || bad "$1" "$FETCHED"
}

# unpack NAME FILE DEST [flat]: unpacks FILE (verified) into a fresh directory and moves its single top directory to DEST
# (whose parent is created). With a fourth argument `flat` the tarball has no top directory (its bin/, lib/ ... are at
# its root): the fresh unpack directory itself is moved to DEST and the "one top directory" check is skipped. DEST must
# not exist: mv would move the directory inside it.
unpack() {
	[ ! -e "$3" ] && [ ! -L "$3" ] || { echo "$1: $3 exists" >&2; exit 1; }
	work_ensure
	tmp=$WORK/unpack-$1
	rm -rf "$tmp"
	mkdir -p "$tmp" "$(dirname "$3")"
	case $2 in
	*.zst) tar -I 'zstd -d --long=31' -xf "$2" -C "$tmp" ;; # LLVM: a 1 GiB window
	*) tar -xf "$2" -C "$tmp" ;;
	esac
	if [ "${4:-}" = flat ]; then
		mv "$tmp" "$3"
		return 0
	fi
	set -- "$1" "$3" "$tmp"/*
	[ $# -eq 3 ] && [ -d "$3" ] || { echo "$1: expected one top directory in the tarball" >&2; exit 1; }
	mv "$3" "$2"
}

# written NAME DIR ARCHIVE_SHA: the manifest of a fresh install: written, its pin printed when the script has none, else
# checked against it (exit 1 on a difference). The caller (SELF, the script) is named in the paste hint.
written() {
	got=$(manifest_write "$1" "$2" "$3") || exit 1
	if [ -z "$(pin "$1")" ]; then
		echo "$1: installed; manifest pin: MANIFEST_PIN_$(echo "$1" | tr - _)=$got (paste into $0)"
	elif [ "$got" != "$(pin "$1")" ]; then
		echo "$1: the fresh install's manifest ($got) is not the pin ($(pin "$1"))" >&2
		exit 1
	fi
}

# present NAME DIR: for a tree in place: verify it against its pin, or report it as not adopted when it has none yet.
present() {
	if [ -n "$(pin "$1")" ]; then
		manifest_verify "$1" "$2" "$(pin "$1")" || exit 1
	else
		echo "$1: present, not adopted (sh $0 --adopt $1)"
	fi
}

# adopt_compare NAME FRESH INSTALLED MODE: lists both trees (manifest_list) and compares them. MODE exact: any difference
# is refused (return 1, first difference named). MODE paths: the same path set, link targets and exec bits are required
# (file hashes with the sha256 stripped), content may differ: returns 2 for that case (the caller adopts as it is and
# says so). Returns 0 for identical trees.
adopt_compare() {
	work_ensure
	manifest_list "$2" >"$WORK/fresh" || return 1
	manifest_list "$3" >"$WORK/installed" || return 1
	cmp -s "$WORK/fresh" "$WORK/installed" && return 0
	if [ "$4" = paths ]; then
		sed -E 's/^\\?[0-9a-f]{64}  //' "$WORK/fresh" >"$WORK/fresh.p"
		sed -E 's/^\\?[0-9a-f]{64}  //' "$WORK/installed" >"$WORK/installed.p"
		if cmp -s "$WORK/fresh.p" "$WORK/installed.p"; then
			echo "$1: a fresh build has the same paths but different content in $(diff "$WORK/fresh" "$WORK/installed" | grep -c '^<') entries (first: $(diff "$WORK/fresh" "$WORK/installed" | grep '^[<>]' | head -n 2 | tr '\n' ' '))" >&2
			return 2
		fi
		echo "$1: $3 has a different set of paths (or links, exec bits) than a fresh build, first difference: $(diff "$WORK/fresh.p" "$WORK/installed.p" | grep '^[<>]' | head -n 1)" >&2
		return 1
	fi
	echo "$1: $3 differs from the verified download, first difference: $(diff "$WORK/fresh" "$WORK/installed" | grep '^[<>]' | head -n 1)" >&2
	return 1
}

# git_clean DIR NAME COMMIT: 0 if DIR is a real directory (not a symlink), its HEAD is COMMIT and `git status --porcelain`
# prints nothing (status runs with --no-optional-locks, so --verify writes nothing into the clone, not even the index) (tracked files and untracked, non-ignored files only: ignored files and .git are not covered).
git_clean() {
	if [ -L "$1" ] || [ ! -d "$1" ]; then
		echo "$2: $1 is a symlink or not a directory" >&2
		return 1
	fi
	head=$(git -C "$1" rev-parse HEAD) || return 1
	[ "$head" = "$3" ] || { echo "$2: $1 is at $head, not $3" >&2; return 1; }
	dirty=$(git --no-optional-locks -C "$1" status --porcelain) || return 1
	[ -z "$dirty" ] || { echo "$2: $1 has local changes:" >&2; echo "$dirty" | head -n 5 >&2; return 1; }
}

# absent DIR: 0 only if nothing is at DIR (a dangling symlink counts as something)
absent() { [ ! -e "$1" ] && [ ! -L "$1" ]; }
