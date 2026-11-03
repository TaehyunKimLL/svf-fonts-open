# guard.sh - sourced by run-pico.sh and run-esp32.sh (needs HERE, LIMIT, OPT): run_guarded OUT ERR CMD... runs an emulator
# under guard.py (time limit LIMIT seconds, output caps, killed with the script) and returns its exit status; guard_why,
# verify_ok and note_unpinned (below) are the runners' shared helpers. SIGTERM, SIGINT
# and SIGHUP to the script kill the emulator (guard.py kills its process group) and end the script with 143, so no
# qemu or node outlives it.
GUARD_PID=
guard_on_signal() {
	[ -z "$GUARD_PID" ] || kill -TERM "$GUARD_PID" 2>/dev/null
	wait
	exit 143
}
trap guard_on_signal TERM INT HUP
run_guarded() {
	_gout=$1
	_gerr=$2
	shift 2
	python3 -I "$HERE/guard.py" "$LIMIT" "$_gout" "$_gerr" -- "$@" &
	GUARD_PID=$!
	wait "$GUARD_PID"
	_grc=$?
	GUARD_PID=
	return $_grc
}

# guard_why STATUS: what an exit status of run_guarded means (the text a runner prints with it)
guard_why() {
	case $1 in
	124) echo "no end within ${LIMIT}s (guard time limit)" ;;
	125) echo "output over the guard's cap" ;;
	127) echo "the emulator could not be run (missing?)" ;;
	143) echo "killed by a signal" ;;
	1) echo "the benchmark ended with a non-zero exit code or a failure" ;;
	*) echo "exit status $1" ;;
	esac
}

# verify_ok TAG SCRIPT NAME...: `SCRIPT --verify NAME...` must succeed and print "NAME: OK" for each name. --verify exits
# 0 for a tree that is absent ("not installed"), so the output is checked as well: a missing install ends the run (exit 1,
# the message prefixed "TAG: ").
verify_ok() {
	_tag=$1
	_script=$2
	shift 2
	_msg=$(OPT=$OPT sh "$_script" --verify "$@" 2>&1) ||
		{ echo "$_tag: install verification failed ($(basename "$_script") --verify $*): $_msg"; exit 1; }
	for _n in "$@"; do
		case $(printf '%s\n' "$_msg" | grep "^$_n: ") in
		"$_n: OK"*) ;;
		*) echo "$_tag: $_n is not installed or not verified ($(basename "$_script") --verify $_n): $_msg"; exit 1 ;;
		esac
	done
}

# note_unpinned TAG VAR DEFAULT: an override of a tool the installers pin is run as given but not verified, and the rows
# still name the pinned version: say so ("TAG: note: unpinned VAR=value", as run-screens.sh does)
note_unpinned() {
	eval "_v=\$$2"
	[ "$_v" = "$3" ] || echo "$1: note: unpinned $2=$_v"
}
