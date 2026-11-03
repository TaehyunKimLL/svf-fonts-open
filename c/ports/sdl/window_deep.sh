# window_deep.sh - sourced by check.sh: is the window of an `svfsdl:` line at least 24 bits deep?
#   window_of LINE        the SDL_PIXELFORMAT_ name after " window " in LINE
#   window_deep NAME      exit 0 for a 24 or 32 bit (or deeper) packed colour format, 1 for anything else (a 16 bit or
#                         8 bit window quantises a palette, so the shot palette comparison must not run on it)
# An explicit list of names: a suffix test would take RGB332 (8 bits) for a 32 bit format.
window_of() { w=${1#* window }; echo "${w%% *}"; }
window_deep() {
	case $1 in
	SDL_PIXELFORMAT_*8888 | SDL_PIXELFORMAT_RGB888 | SDL_PIXELFORMAT_BGR888 | SDL_PIXELFORMAT_RGB24 | SDL_PIXELFORMAT_BGR24 | \
		SDL_PIXELFORMAT_*[AX]32 | SDL_PIXELFORMAT_*2101010) return 0 ;;
	*) return 1 ;;
	esac
}
