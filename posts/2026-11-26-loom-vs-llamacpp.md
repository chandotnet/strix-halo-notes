# AMD Loom vs llama.cpp Vulkan on Strix Halo: twice the prefill, no faster decode

*26 November 2026. Written after a question on the Framework Community forum, under the [inference engines post](2026-11-24-inference-engines-compared.md).*

[Loom](https://loom-fun.dev/) is AMD's new serving stack (tech preview): a kernel language and compiler, the `hrx-system` runtime, and `loom-serve`, an OpenAI-compatible server. Each model ships as a package of hand-written (or agent-written) Loom programs plus the original GGUF weights. Their site shows large gains over llama.cpp on Strix Halo, so I measured one model on my Framework Desktop against the llama.cpp Vulkan build I use every day.

Short version: Loom reads a prompt about twice as fast as llama.cpp b11344. It does not write faster: without speculative decoding the two are even, and with the same DFlash draft model, llama.cpp is well ahead on code and tool calls.

## Setup

- Framework Desktop, Ryzen AI Max+ 395, Radeon 8060S (gfx1151), 128 GB, Fedora 44, 512 MB carve-out and 100 GiB GTT
- Model: Ornith-1.5-35B-A3B `Q4_K_M` (bartowski), the exact file that `loom-fetch` downloads for the Loom package, so both engines read the same weights
- **Loom 0.2.0** (the version their published numbers use), package `loom-fun/bartowski-Ornith-1.5-35B-A3B-loom` revision `a04f7adb`, preset `chat`. "No draft" is a copy of the package with `draft_depth: 0`.
- **llama.cpp Vulkan b11344** (official release): `-ngl 99 -c 131072 -np 1 -fa auto -ub 1024 -b 2048 --jinja`. DFlash with `--spec-type draft-dflash -md <the DFlash GGUF from the Loom package> -ngld 99` at the default draft depth; MTP with `--spec-type draft-mtp`.
- Client: [`bench/speed.py`](../bench/), streaming, greedy, thinking off, a nonce in every prompt, best of 2 runs. One engine loaded at a time, nothing else on the GPU.
- Order: Loom, llama.cpp, llama.cpp, Loom, then the other variants. The two orders agreed within 1 to 2%.

## Results

Tokens per second as the client sees them, best of two runs.

| Workload | Loom, DFlash (as shipped) | Loom, no draft | b11344, no draft | b11344, MTP | b11344, DFlash |
|---|---:|---:|---:|---:|---:|
| Prefill, ~500 tokens | 1,970 | 1,982 | 1,214 | 1,064 | 1,034 |
| Prefill, ~7,200 tokens | 2,854 | **2,920** | 1,269 | 1,212 | 1,177 |
| Prefill, ~28,800 tokens | 2,418 | **2,464** | 1,059 | 999 | 992 |
| Decode, prose | 66.4 | 69.2 | **70.5** | 42.7 | 64.1 |
| Decode, writing code | 79.3 | 69.1 | 70.2 | 56.5 | **102.3** |
| Decode, editing a file | 72.4 | 66.6 | 68.8 | 61.3 | **120.5** |
| Decode, copying a file into a tool call | ~74.8 ¹ | ~67.7 ¹ | 69.1 | 63.9 | **127.5** |
| Decode, prose after ~28,800 tokens | 53.9 | 55.0 | **58.4** | 35.3 | 49.4 |

¹ Loom does not stream tool-call arguments: they arrive in one block at the end, so the client cannot time the decode. Estimated from the total time minus the prefill time.

DFlash acceptance in llama.cpp (from the server's `timings`): 27% on prose, 67% on code, 94% on file editing, 99% on the tool-call copy. That explains the spread: the draft pays when the output is predictable and costs a little when it is not.

## What I take from it

1. **Prefill: Loom wins clearly**, 1.6x at 500 tokens and 2.2 to 2.3x from a few thousand tokens on. That matches their own page, and even beats it at 8k. The draft model costs Loom almost nothing on prefill, while it costs llama.cpp 6 to 15%.
2. **Decode: no gain.** Without a draft on either side it is a tie (69.2 vs 70.5 on prose), and Loom is 6% behind after 28k tokens of context. Its DFlash draft at depth 1 adds 15% on code but loses 4% on prose.
3. **The fastest decoder here is llama.cpp b11344 with the same DFlash draft**: 102 t/s writing code, 120 editing, 127 copying into a tool call, 1.3 to 1.7x Loom with its draft.
4. **Why their page shows +88% on decode:** their llama.cpp baselines run DFlash with `--spec-draft-n-max 8`, which gives 25 t/s on Vulkan b12211 for this model. llama.cpp without a draft, or with the default draft depth, is about three times faster than that.
5. **MTP on this model is a loss everywhere** on llama.cpp (−40% on prose), as I had already seen on the Q8_0.

## Correctness

Same output from both engines. With greedy decoding, the tool-call copy (1,608 tokens) is byte-identical across all five configurations. It differs from the source file by the same 4 characters everywhere: the model itself "translates" `in` and `or` into French inside French-named code, which is a model quirk, not an engine bug. Five quick checks (a capital, 17 × 23, a short explanation, a translation, a weather tool call with the right arguments) passed on every engine.

## Costs I noticed with Loom 0.2.0

- **The GPU stays at 100% busy while idle.** Model loaded, no request: `gpu_busy_percent` 100, 2.9 GHz, about 40 W. llama.cpp with the model loaded sits at 2%, about 800 MHz and 16 W. Same with `--wait_mode=blocking`, so it is not the spin-wait.
- **Memory:** the `chat` preset reserves a fixed pool of about 45 GiB (4 rows of 262,144 positions), against about 23 GiB of GTT for llama.cpp at 131,072 context. A smaller preset would reserve less.
- **`completion_spin_ns=4294967295`**, from their recommended command, keeps a CPU core spinning during requests and brought nothing measurable: `--wait_mode=blocking` gave the same numbers.
- **"ready" before it is ready:** the server reports ready in 3 s while weights keep loading in the background; the first request is slow, the second is normal.
- No MTP support for this model, and the draft depth is fixed by the preset.

## Verdict

For prompt-heavy work (long documents, summaries, OCR output, a short answer after a big context), Loom is worth a look: twice the prefill is a real gain. For agents and chat, where generation weighs as much as reading, llama.cpp b11344 matches it without a draft and beats it clearly with DFlash on code and tool calls, while leaving the GPU idle between requests. For this model on this box I'm staying with llama.cpp, and llama.cpp + DFlash looks like the better bet for a coding setup.

Loom moves fast (0.3.0 came out on 21 November), so these numbers describe 0.2.0 only.

*Note: French is my first language. This post was written in English with the help of an LLM, from my own benchmark notes. All measurements are mine, and I reviewed the text before posting.*

Questions, corrections or a model you would like measured: open an issue on this repository.
