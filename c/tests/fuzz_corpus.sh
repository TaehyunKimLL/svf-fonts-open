#!/bin/sh
# fuzz_corpus.sh DIR - the seed corpora of the fuzz targets (make -C c fuzz-corpus), from the repository's svf/ faces.
#   DIR/corpus         every face in the default, dos, full, simd16, mcu-strict and wasm profiles (JSET version 1, as
#                      svf/ has it) + the JSET version 2 copies (svf2to3 --jset-version 2) of jamo-extra/NSQRB16.SVF
#                      (aliases) and dos/NEODG16G.SVF (6x2x1, width 0) in the default and mcu-strict profiles + every
#                      svf_synth --layout-bad kind, --jset-bad kind of both JSET versions and --jset-variant face
#                      (fuzz-open)
#   DIR/corpus-strict  the mcu-strict faces, the mcu-strict v2 copies, and the same synthetic faces (fuzz-open-strict)
#   JMAP seeds (JSET version 3, from NEODG16G, default and mcu-strict profiles): every svf_synth --jmap-variant face and
#   --jmap-bad kind, as jmap-<profile>-variant-V.svf / jmap-<profile>-bad-K.svf, in both corpora (the strict corpus
#   gets them too: mapped, one layout, no streaming)
#   LIST seeds (the same faces and profiles): every svf_synth.LIST_VARIANTS face and LIST_BAD_KINDS kind
#   (via --jmap-variant / --jmap-bad), as jlist-<profile>-variant-V.svf / jlist-<profile>-bad-K.svf, in both corpora
# Prints the seed counts. Scratch conversions go under DIR/tmp (removed). Run from c/.
set -e
D=${1:?usage: fuzz_corpus.sh DIR}
T=$(cd "$(dirname "$0")/../../tools" && pwd)
R=$(cd "$T/.." && pwd)
mkdir -p "$D"; D=$(cd "$D" && pwd)
mkdir -p "$D/corpus" "$D/corpus-strict" "$D/tmp"
for p in default dos full simd16 mcu-strict wasm; do
	rm -rf "$D/tmp/$p"
	python3 -I "$T/svf2to3.py" --tree "$R/svf" "$D/tmp/$p" --profile $p >/dev/null
	(cd "$D/tmp/$p" && find . -name '*.SVF' | while read -r f; do
		n=$p-$(echo "${f#./}" | tr / _)
		cp "$f" "$D/corpus/$n"
		if [ $p = mcu-strict ]; then cp "$f" "$D/corpus-strict/$n"; fi
	done)
done
base="$D/tmp/default/dos/NEODG16.SVF"
for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.LAYOUT_BAD))"); do
	python3 -I "$T/svf_synth.py" --layout-bad "$k" --from "$base" "$D/corpus/bad-$k.svf"
	cp "$D/corpus/bad-$k.svf" "$D/corpus-strict/"
done
# JSET version 2 copies of two real faces: the alias path (NSQRB16) and the width-0 path (NEODG16G, 6x2x1)
for p in default mcu-strict; do
	for f in jamo-extra/NSQRB16.SVF dos/NEODG16G.SVF; do
		n=v2-$p-$(basename "$f")
		python3 -I "$T/svf2to3.py" "$R/svf/$f" "$D/tmp/$n" --profile $p --jset-version 2 >/dev/null
		cp "$D/tmp/$n" "$D/corpus/$n"
		if [ $p = mcu-strict ]; then cp "$D/tmp/$n" "$D/corpus-strict/$n"; fi
	done
done
# every bad JSET block of both versions and every valid version 2 variant, made from NEODG16G
jb="$R/svf/dos/NEODG16G.SVF"
for v in 1 2; do
	for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.BAD_KINDS_V1 + svf_synth.BAD_KINDS_BIG if $v == 1 else svf_synth.BAD_KINDS_STD + svf_synth.BAD_KINDS))"); do
		python3 -I "$T/svf_synth.py" --jset-bad "$k" --jset-version $v --from "$jb" "$D/corpus/jset$v-bad-$k.svf"
		cp "$D/corpus/jset$v-bad-$k.svf" "$D/corpus-strict/"
	done
done
for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.VARIANTS))"); do
	python3 -I "$T/svf_synth.py" --jset-variant "$k" --from "$jb" "$D/corpus/jset2-variant-$k.svf"
	cp "$D/corpus/jset2-variant-$k.svf" "$D/corpus-strict/"
done
# the BIG limit face (19 x 28 classes, 128/128/64 sets) in JSET version 1 too (the loop above made their version 2 forms)
for k in limits_big; do # limits_big_alias is version 2 only (version 1 has no aliases)
	python3 -I "$T/svf_synth.py" --jset-variant "$k" --jset-version 1 --from "$jb" "$D/corpus/jset1-variant-$k.svf"
	cp "$D/corpus/jset1-variant-$k.svf" "$D/corpus-strict/"
done
# every JMAP variant and bad kind, made from NEODG16G in the default and the mcu-strict profile (svf2to3 first: the
# synthetic faces keep the profile's header)
for p in default mcu-strict; do
	python3 -I "$T/svf2to3.py" "$jb" "$D/tmp/jb-$p.svf" --profile $p >/dev/null
	for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.JMAP_VARIANTS))"); do
		python3 -I "$T/svf_synth.py" --jmap-variant "$k" --from "$D/tmp/jb-$p.svf" "$D/corpus/jmap-$p-variant-$k.svf"
		cp "$D/corpus/jmap-$p-variant-$k.svf" "$D/corpus-strict/"
	done
	for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.JMAP_BAD_KINDS))"); do
		python3 -I "$T/svf_synth.py" --jmap-bad "$k" --from "$D/tmp/jb-$p.svf" "$D/corpus/jmap-$p-bad-$k.svf"
		cp "$D/corpus/jmap-$p-bad-$k.svf" "$D/corpus-strict/"
	done
	for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.LIST_VARIANTS))"); do
		python3 -I "$T/svf_synth.py" --jmap-variant "$k" --from "$D/tmp/jb-$p.svf" "$D/corpus/jlist-$p-variant-$k.svf"
		cp "$D/corpus/jlist-$p-variant-$k.svf" "$D/corpus-strict/"
	done
	for k in $(python3 -I -c "import sys;sys.path.insert(0,'$T');import svf_synth;print(' '.join(svf_synth.LIST_BAD_KINDS))"); do
		python3 -I "$T/svf_synth.py" --jmap-bad "$k" --from "$D/tmp/jb-$p.svf" "$D/corpus/jlist-$p-bad-$k.svf"
		cp "$D/corpus/jlist-$p-bad-$k.svf" "$D/corpus-strict/"
	done
done
rm -rf "$D/tmp"
echo "corpus: $(ls "$D/corpus" | wc -l) files, corpus-strict: $(ls "$D/corpus-strict" | wc -l) files" \
	"($(ls "$D/corpus" | grep -c '^v2-') JSET v2 face seeds: $(ls "$D/corpus" | grep '^v2-' | paste -sd ' ' -); $(ls "$D/corpus" | grep -c '^jset[12]-bad-') bad-JSET kinds," \
	"$(ls "$D/corpus" | grep -c '^jset2-variant-') v2 variants, $(ls "$D/corpus" | grep -c '^jset1-variant-') BIG v1 variants," \
	"$(ls "$D/corpus" | grep -c '^jmap-.*-variant-') JMAP variant seeds," \
	"$(ls "$D/corpus" | grep -c '^jmap-.*-bad-') JMAP bad seeds," \
	"$(ls "$D/corpus" | grep -c '^jlist-.*-variant-') LIST variant seeds," \
	"$(ls "$D/corpus" | grep -c '^jlist-.*-bad-') LIST bad seeds)"
