#!/bin/sh
# guardrails-ai: delete ONE line from rail.xml and one live rule stops firing.
#
# needs: pip install guardrails-ai   (tested against 0.11.0)
# tip:   printf 'enable_metrics=false\nuse_remote_inferencing=false\n' > "$HOME/.guardrailsrc"
#        otherwise every run stalls ~10s on a telemetry export attempt.
#
# usage: sh run.sh
set -u
cd "$(dirname "$0")"

PY=${PY:-python}
T=./_tmp_run            # 注意：不要用 mktemp。MSYS 的 /tmp 是 C:\tmp，原生 python 看不到
rm -rf "$T"; mkdir -p "$T"
cp rail.xml validators.py output_valid.txt "$T/"

echo "[1] legal answer, all five rules loaded          (expect exit 0)"
$PY runner.py "$T"; echo "    -> exit $?"
echo

cp probes/competitor.txt "$T/output_valid.txt"
echo "[2] answer naming a competitor                   (expect non-zero)"
$PY runner.py "$T"; echo "    -> exit $?"
echo

grep -v '^ *no-competitor-mention;$' rail.xml > "$T/rail.xml"
echo "[3] the same answer, after deleting one line from rail.xml"
$PY runner.py "$T"; echo "    -> exit $?"
echo
echo "the other four rules still fire:"
for p in pii url profanity too_long; do
  cp "probes/$p.txt" "$T/output_valid.txt"
  $PY runner.py "$T" >/dev/null 2>&1; echo "    $p -> exit $?"
done

rm -rf "$T"
