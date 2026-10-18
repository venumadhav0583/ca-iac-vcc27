#!/usr/bin/env bash
# Reproduce every result in the paper. Total wall time ~70 min on 2 vCPUs.
set -euo pipefail
cd "$(dirname "$0")"
# raw logs from the reported runs ship as one archive
[ -d results/raw ] || tar xzf results/raw_logs.tar.gz -C results
(cd cpr && go test ./... && go build -o cpr .)
cd testbed
# 1) training telemetry (seeds 101,102) -- never used for evaluation
if [ ! -f ../results/raw/telemetry_seed101.jsonl ]; then
  python3 run.py telemetry --seed 101 --duration 600 --port 21000 &
  python3 run.py telemetry --seed 102 --duration 600 --port 21100 &
  wait
fi
python3 train.py
# 2) evaluation seeds 1..6, two at a time
for pair in "1 2" "3 4" "5 6"; do
  set -- $pair
  python3 run.py eval --seed $1 --instants 30 --port 22000 --model ../results/model.pkl &
  python3 run.py eval --seed $2 --instants 30 --port 22100 --model ../results/model.pkl &
  wait
done
python3 analyze.py
python3 ablation.py
python3 staleness.py
python3 lifetime.py
python3 stats_audit.py
python3 lifetime_ci.py
# 3) sensitivity: 4x longer congestion/load episodes (reactive CPR only), seeds 11-14
mkdir -p ../results/raw_sens4
for pair in "11 12" "13 14"; do
  set -- $pair
  CAIAC_EPISODE_SCALE=4 CAIAC_RAW=../results/raw_sens4 python3 run.py eval --seed $1 --instants 30 --port 25000 &
  CAIAC_EPISODE_SCALE=4 CAIAC_RAW=../results/raw_sens4 python3 run.py eval --seed $2 --instants 30 --port 25100 &
  wait
done
python3 lifetime_ci.py ../results/raw_sens4 ../results/lifetime_ci_sens4.json
python3 fig_timeline.py 3
(cd ../paper && python3 make_numbers.py >/dev/null)
