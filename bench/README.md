# Benchmark scripts

The speed scripts behind the numbers in [posts/](../posts/). Quality checks are not here: they replay private requests.

## speed.py: what an application sees

One HTTP client for every engine, so the numbers compare across llama.cpp, Halogen, vLLM or anything that serves `/v1/chat/completions` with streaming. Standard library only.

```bash
python3 speed.py --url http://127.0.0.1:8080/v1/chat/completions --model my-model --label vulkan --out results.jsonl
```

- **Prefill:** filler text of about 512, 8,192 and 32,768 tokens, one output token. Speed = prompt tokens / time to first byte.
- **Decode:** prose, writing code, editing a file and returning it whole, copying a file into a tool call, then prose after about 32k tokens of context. Speed = (output tokens − 1) / (last token − first token).
- **No cache help:** each prompt starts with a random nonce, and `cache_prompt` is off.
- **Greedy:** `temperature: 0`, and thinking off by default (`--extra '{"reasoning_effort": "none"}'`). Change `--extra` for a server that wants another switch, for example `--extra '{"chat_template_kwargs": {"enable_thinking": false}}'`.
- **Options:** `--runs` (default 2), `--skip-32k`, `--timeout`, `--lang`.

Results go to a JSONL file, one line per request, with `prompt_tokens`, `completion_tokens`, `pp_tps`, `tg_tps`, the first 300 characters of the output and llama.cpp's own `timings` when the server sends them. Read the real prompt size from `prompt_tokens`: the filler sizes depend on the tokenizer. Some servers (Ollama, for one) send a tool call in a single chunk instead of streaming it: the tool case then has no decode speed.

**Differences with the published runs.** The posts used French prompts (`--lang fr` gives the same ones) and, for the edit and tool-copy cases, a different file of about 1,500 tokens that stays private. This version edits and copies `speed.py` itself, so those two rows will not reproduce exactly. Prefill, prose, code and deep decode do.

## ab-llama-bench.sh: two builds, both orders

`llama-bench` with two llama.cpp builds on the same GGUF, in both orders: A then B, then B then A. The first build to load a model reads it from disk and the next one from a warm page cache, so a single pass can show a gain that is only the cache. GPU load and available memory are logged after each pass.

```bash
A_DIR=~/llama-b11344 B_DIR=~/llama-hrx-b148 B_ARGS="-dev HRX0" ./ab-llama-bench.sh model.gguf results.md
```

`BENCH_ARGS` replaces the default `-ngl 99 -fa 1 -p 512,8192 -n 128 -r 3`.

## Before you trust a number

- Check that nothing else computes on the GPU (`cat /sys/class/drm/card*/device/gpu_busy_percent`) before and after a run.
- On a 512 MB carve-out, add `drm-total-vram` and `drm-total-gtt` from `/proc/<pid>/fdinfo/*` to get a process's GPU memory.
- Compare against a recent llama.cpp Vulkan build, not only against ROCm or an old build.

## Licence

The scripts in this folder are under the MIT licence ([LICENSE](LICENSE)). The posts stay under CC BY 4.0.
