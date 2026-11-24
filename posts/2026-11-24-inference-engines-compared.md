# Strix Halo inference engines, measured on one box: Halogen, hipEngine, HRX vs llama.cpp Vulkan (plus Inkling 2 Mini and Gemma 4)

*24 November 2026. Also posted on the Framework Community forum, Framework Desktop category.*

I run a Framework Desktop (Ryzen AI Max+ 395, 128 GB) as a headless home inference server, and over the last month I benchmarked most of the "faster than llama.cpp" engines that came up on the Framework Community forum. Everything below was measured on the same machine, against the same llama.cpp baseline, with the same client. Short version: the only engine that beat a recent llama.cpp Vulkan build on my workloads was Halogen, and it beat it by a lot.

## Setup

- Framework Desktop, Ryzen AI Max+ 395, Radeon 8060S (gfx1151), 128 GB LPDDR5x
- Fedora 44, headless
- BIOS iGPU carve-out set to the minimum (512 MB), GPU memory through GTT with `ttm.pages_limit=26214400` (100 GiB)
- Baseline: official llama.cpp Vulkan release **b11344**, served through llama-swap
- Reference model: Ornith 1.5 35B-A3B (MoE, Q8_0 GGUF), my daily driver until last week

Two notes on the baseline, because they change every comparison. First, Vulkan b11344 is much faster at prompt processing than the builds from the summer: on Ornith Q8_0, pp512 went from 1,205 to 1,599 t/s and pp8192 from 1,207 to 1,513 t/s compared with b10488, with identical decode (55 t/s). Any "2x to 4x llama.cpp" claim measured against an older build or a ROCm build is not comparing against what you get today. Second, ROCm vs Vulkan depends on the build: an old llama.cpp ROCm build (b9965) collapsed at long prompts (pp8192 681 t/s vs 1,207 on Vulkan), while the ROCm build that ships with Lemonade (b10394 + TheRock 7.13) was 10 to 13% ahead of Vulkan on prefill and matched it on decode once MTP was on. If you compare backends, measure at pp8192 and with MTP, not just pp512.

## Halogen (Qwen3.8-Flash-Next): the clear winner

[Halogen](https://github.com/peonist-ai/halogen-flash-server) is a closed-source container with kernels written for gfx1151 and for one model family only, using its own `.hgn` weight format. I ran version 0.20.7 with the `ht43` checkpoint and a 131,072-token KV pool. Same HTTP client for all three columns (streaming, greedy, thinking off, a nonce in each prompt to defeat prompt caches), medians of 3 runs, in t/s:

| | Halogen 0.20.7 (ht43) | Same model, llama.cpp b11344 (Q2_0) | Ornith 1.5 35B Q8_0, llama.cpp b11344 |
|---|---:|---:|---:|
| Prefill, ~500 tokens | 1,099 | 403 | ~1,190 |
| Prefill, ~7,200 tokens | **2,001** | 460 | ~1,390 |
| Prefill, ~28,800 tokens | **2,005** | 409 | ~1,130 |
| Decode, prose | **65.8** | 31.4 | 52.7 |
| Decode, writing code | **100.6** | 31.8 | 54.4 |
| Decode, editing a file (copy-heavy) | **145.8** | 31.7 | 52.5 |
| Decode, tool call that copies a file | **142.9** | 31.7 | 53.6 |
| Decode, prose after ~28,800 tokens | **61.6** | 28.9 | 45.4 |

The decode speed comes from speculative decoding (an MTP head plus lookup in the prompt), which is why copy-heavy tasks go so fast. The vendor states that output at temperature 0 is byte-identical to plain serial greedy decoding; I checked that on my own prompts and it passed on every case. Prefill does not drop with context length, which is where llama.cpp loses ground.

Quality on my own tests (24 closed questions, and a replay of 81 captured requests from my real workloads: a home-automation voice agent with tools, a coding agent, JSON extraction, summarisation) was the same as Ornith, with zero truncated or failed requests. On the 20-request voice-agent replay, median time per request went from 13.0 s with Ornith to 2.4 s with Halogen.

Costs to know about: it is closed source; the default checkpoint plus its paged n-gram table is large (the `ht43` setup takes about 70 GiB, against 82 GiB for the earlier `v2`); and it serves one model family. It is now my default model.

## hipEngine 0.8.3: slower than llama.cpp everywhere

Tested on Ornith 1.5 35B-A3B GGUFs. hipEngine refuses the Q8_0 (no certified kernel for Q8_0 MoE experts), so the fair comparison is the Q4_K_M, same file in both engines:

| Engine, file | pp ~600 | pp ~5,000 | pp ~19,700 | Decode | 4 concurrent, total |
|---|---:|---:|---:|---:|---:|
| llama.cpp b11344, Ornith Q4_K_M | 1,181 | 1,264 | 1,112 | 74.4 | 142.0 |
| llama.cpp b11344, Ornith Q8_0 | 1,190 | 1,364 | 1,184 | 54.7 | 111.1 |
| hipEngine, Ornith Q6_K | 223 to 310 | 265 to 274 | 269 | 40.8 | 61.7 |
| hipEngine, Ornith Q4_K_M | 501 | 475 | not measured | not measured | not measured |
| hipEngine, Qwen3.6 UD-Q4_K_M (Unsloth) | 799 | 767 | 681 | 46.6 | 84.6 |

hipEngine's own `bench sweep` gets closer on some shapes (1,194 t/s at 4K on the Unsloth file), but through HTTP, which is what a client sees, it lost on prefill, decode and concurrency. MTP was not possible either: hipEngine requires the MTP head in Q8_0 and the published Ornith GGUFs ship it in Q6_K or Q4_K. I also saw some French text degrade (invented words).

## AMD HRX (hrx-b148): faster prefill, slower decode, not ready

HRX is AMD's experimental ggml backend (a llama.cpp branch, daily tarballs with the ROCm runtime included, so nothing to install on the host). `llama-bench -ngl 99 -fa 1 -p 512,8192 -n 128 -r 3`, run in both orders (HRX then Vulkan, Vulkan then HRX). Halogen was loaded but idle during the test, so only models that fit in the remaining 25 GiB were tested.

| Model | Engine | pp512 | pp8192 | tg128 |
|---|---|---:|---:|---:|
| Qwen3-Coder-30B-A3B Q4_K_XL (qwen3moe) | Vulkan b11344 | 1,447 to 1,464 | 952 to 961 | 93.3 to 94.3 |
| | HRX b148 | **2,049** (+40%) | **1,280** (+34%) | 75.5 (**−20%**) |
| Gemma 4 12B Q4_0 (dense) | Vulkan b11344 | 1,121 to 1,124 | 968 to 970 | 27.4 to 27.5 |
| | HRX b148 | 235 to 314 | 286 to 295 | 26.1 to 26.8 |
| GLM-4.7-Flash REAP 23B-A3B Q4_K_XL (deepseek2) | Vulkan b11344 | 1,467 to 1,482 | 731 to 736 | 65.7 to 67.8 |
| | HRX b148 | crash | | |

- deepseek2 crashes with `unsupported HRX node ... MUL_MAT ... q8_0`: MLA attention is not covered yet.
- The first HRX run of Qwen3-Coder crashed (`materialize host weight value ... failed`) while the file was not yet in the page cache; the second run worked. HRX can refuse a model cold that it reads fine warm.
- For interactive and agent use, a 20% decode loss cancels much of the prefill gain. Worth watching, not worth switching to yet.

## Two models that look good on paper

**Inkling 2 Mini** (26B total, 3.4B active MoE, vision and tools, layers 6 to 17 run three times with shared weights). llama.cpp b12606, bartowski Q8_0, compared with Ornith 1.5 35B Q8_0 on the same build:

| | Inkling 2 Mini | Ornith 1.5 35B | Ratio |
|---|---:|---:|---:|
| pp512 | 474 / 487 | 1,618 / 1,635 | 0.29 |
| pp8192 | 358 / 366 | 1,811 / 1,823 | 0.20 |
| pp16384 | 332 / 325 | 1,690 / 1,702 | 0.19 |
| tg128 | 21.0 / 21.2 | 55.0 / 55.6 | 0.38 |

The decode is slow by design: the loop reads the experts three times per token and this machine is memory-bandwidth bound. Early quality checks were good (French, images, tools). **Warning:** avoid the NVFP4 GGUFs until llama.cpp PR [#32704](https://github.com/ggml-org/llama.cpp/pull/32704) is merged. It reports that llama.cpp loses the NVFP4 expert scales on the 2nd and 3rd loop passes (perplexity 130 instead of 7.65). Standard ggml quants such as Q8_0 are not affected (I measured 3.02 perplexity on Q8_0).

**Gemma 4 26B-A4B** (Unsloth UD-Q4_K_M, llama.cpp b11344 with its MTP head: `-md mtp-gemma-4-26B-A4B-it.gguf --spec-type draft-mtp -ngld 99`). Fast: 67.7 t/s on prose, 96.2 on code, prefill 1,240 / 1,610 / 1,220 t/s at ~500 / ~7,200 / ~28,800 tokens. On the 12B, MTP took code writing from 27 to 72.5 t/s with 73% of drafted tokens accepted. But as an agent it is weak on my workloads: on the 20 voice-agent requests it called tools in 4 cases where Halogen called them in 15, and in a coding agent it gave advice instead of running `bash`. It is a good chat model and a poor default for tool use. The 31B dense ran at 17 t/s decode and 130 t/s prefill at 32K, too slow for interactive use here.

## Benchmarking traps on this machine

These cost me wrong numbers at least once each:

1. **Run every A/B comparison in both orders.** The first model loaded reads from disk, later ones from a warm page cache. AMD recommends `--no-mmap` on Ryzen AI Max+; my first pass showed +3.8% prefill for it, and the reversed pass showed nothing (1,221 vs 1,217 t/s, 53.2 vs 53.0 decode). It was the run order.
2. **Per-process GPU memory is split across two counters.** With a 512 MB carve-out, everything physically lives in system RAM, but llama.cpp Vulkan reports its memory as `drm-total-vram` in `/proc/<pid>/fdinfo` and PyTorch ROCm reports it as `drm-total-gtt`. Add both. `mem_info_vram_used` alone shows 0.5 GB.
3. **MIOpen searches kernels for every new input shape** and caches the result in `~/.config/miopen/`. A convolutional TTS model gave RTF 2.43 on its first run of a sentence and 0.37 on the second run of the same sentence. Measure the second run.
4. **Check `gpu_busy_percent` before and after a run.** The same TTS model gave RTF 0.33 on an idle GPU and 0.70 while another job was computing. A large model that is resident but idle costs nothing; one that is computing halves your numbers.
5. **llama.cpp releases are flagged as prerelease**, so `releases/latest` on the GitHub API does not return the newest build. List `releases?per_page=8` instead.

Questions, corrections or a model you would like measured: open an issue on this repository.
