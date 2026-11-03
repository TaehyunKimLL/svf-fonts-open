# report.awk - turns the output of a bench run (c/bench/bench.c through pico-run.mjs, avr-run or printf) into Markdown
# table rows, one a case:
#   | BUILD | case | iterations | cycles/iteration | µs/iteration | budget µs | result | checksum |
# Variables (-v):
#   build    the row's first column (platform, compiler, flags)
#   mhz      the emulated clock in MHz when the run reports cycles (µs = cycles / mhz); unset when it reports µs
#   budgets  "case:µs ..." the budget of each case that has one ("-" in the table for the others)
#   sums     "case:checksum ..." the expected pixel checksum of each case (tools/svfline.py / jamoset.py values)
#   exact    1: the cases run must be exactly those named in `sums`, each once (a missing, extra or repeated case fails)
#   need_insns  1: every case line must carry numeric insns= > 0 and per_iter_insns= > 0 (pico-run.mjs's instruction count)
# Exit status: 0 all cases ran with the expected checksums and within budget; 2 a budget missed; 1 the run failed (no
# "end=0", a checksum differs or is unknown, no case). Other lines (a profile, emulator messages) are ignored: the run
# script keeps the raw output.
function kv(s, m,   n, i, a, p) {
	n = split(s, a, " ")
	for (i = 1; i <= n; ++i) {
		split(a[i], p, ":")
		m[p[1]] = p[2]
	}
}
function field(name,   i, p) {
	for (i = 1; i <= NF; ++i)
		if (index($i, name "=") == 1)
			return substr($i, length(name) + 2)
	return ""
}
BEGIN { kv(budgets, budget); kv(sums, want); status = 0; cases = 0; ended = 0 }
/^case=/ {
	name = field("case")
	iters = field("iters")
	if (mhz != "") {
		cyc = field("per_iter_cycles")
		tot = field("cycles")
		# a cycle-reporting run: positive numbers, and per_iter_cycles the total over the iterations (printed with
		# one decimal, truncated or rounded: within 0.1)
		if (iters !~ /^[0-9]+$/ || tot !~ /^[0-9]+$/ || cyc !~ /^[0-9]+(\.[0-9]+)?$/ || iters + 0 <= 0 || tot + 0 <= 0 ||
		    cyc + 0 <= 0 || (tot / iters - cyc) > 0.1 || (cyc - tot / iters) > 0.1) {
			print "report: " name ": iters / cycles / per_iter_cycles missing, not positive or inconsistent" >"/dev/stderr"
			bad = 1
		}
		us = cyc / mhz
		cyc = sprintf("%.0f", cyc)
	} else {
		cyc = "-"
		us = field("per_iter_us") + 0
	}
	sum = field("sum")
	ok = (name in want) && want[name] == sum
	if (mhz != "" && bad) {
		ok = 0
		bad = 0
	}
	if (exact == 1 && (!(name in want) || (name in seen)))
		ok = 0
	seen[name] = 1
	if (need_insns == 1) {
		ins = field("insns")
		pins = field("per_iter_insns")
		if (ins !~ /^[0-9]+$/ || ins + 0 <= 0 || pins !~ /^[0-9]+(\.[0-9]+)?$/ || pins + 0 <= 0) {
			ok = 0
			print "report: " name ": insns / per_iter_insns missing or not positive" >"/dev/stderr"
		}
	}
	if (!ok)
		status = 1
	res = "-"
	if (name in budget) {
		res = us <= budget[name] + 0 ? "met" : "**missed**"
		if (us > budget[name] + 0 && status == 0)
			status = 2
	}
	printf "| %s | %s | %s | %s | %.2f | %s | %s | %s |\n", build, name, iters, cyc, us,
		(name in budget) ? budget[name] : "-", res, ok ? sum " ok" : sum " **expected " want[name] "**"
	++cases
	next
}
/^end=/ { ended = field("end") == "0" }
END {
	if (exact == 1)
		for (name in want)
			if (!(name in seen)) {
				print "report: case " name " missing from the run" >"/dev/stderr"
				status = 1
			}
	if (!ended || !cases)
		status = 1
	exit status
}
