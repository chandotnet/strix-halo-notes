#!/usr/bin/env bash
# Runs llama-bench with two llama.cpp builds on the same GGUF, in both orders (A then B, then B then A).
#
# The first build to load a model reads it from disk, the next ones from a warm page cache: a single pass in one
# order can show a gain that is only the cache. Compare the two passes before believing a difference.
# GPU load and available memory are logged after each pass: discard a pass taken while something else computed.
#
# Usage:
#   A_DIR=/path/to/build-a B_DIR=/path/to/build-b ./ab-llama-bench.sh model.gguf results.md
#
# A_DIR and B_DIR are folders that contain `llama-bench` (directly or in bin/). Extra llama-bench options for each
# build go in A_ARGS / B_ARGS, for example B_ARGS="-dev HRX0" for a build that needs a device name.
# MIT licence, see bench/README.md.
set -u
M=${1:?usage: $0 model.gguf results.md}
OUT=${2:?usage: $0 model.gguf results.md}
: "${A_DIR:?set A_DIR to the first llama.cpp build}" "${B_DIR:?set B_DIR to the second llama.cpp build}"
A_NAME=${A_NAME:-$(basename "$A_DIR")}
B_NAME=${B_NAME:-$(basename "$B_DIR")}
BENCH_ARGS=${BENCH_ARGS:-"-ngl 99 -fa 1 -p 512,8192 -n 128 -r 3"}

bin() { if [ -x "$1/bin/llama-bench" ]; then echo "$1/bin/llama-bench"; else echo "$1/llama-bench"; fi; }
libs() { if [ -d "$1/lib" ]; then echo "$1/lib"; else echo "$1"; fi; }
# shellcheck disable=SC2086
run_a() { LD_LIBRARY_PATH="$(libs "$A_DIR")" "$(bin "$A_DIR")" -m "$M" $BENCH_ARGS ${A_ARGS:-} -o md; }
# shellcheck disable=SC2086
run_b() { LD_LIBRARY_PATH="$(libs "$B_DIR")" "$(bin "$B_DIR")" -m "$M" $BENCH_ARGS ${B_ARGS:-} -o md; }
state() {
  echo "gpu_busy=$(cat /sys/class/drm/card*/device/gpu_busy_percent 2>/dev/null | tr '\n' ' ')" \
       "mem_available=$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)GiB"
}

{ echo "## $(basename "$M") $(date +%F\ %T)"
  echo "### Pass 1: $A_NAME"; run_a; echo "### Pass 1: $B_NAME"; run_b; state
  echo "### Pass 2: $B_NAME"; run_b; echo "### Pass 2: $A_NAME"; run_a; state
} >> "$OUT" 2>&1
