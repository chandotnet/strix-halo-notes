# Strix Halo notes

Measurements and write-ups from a Framework Desktop (AMD Ryzen AI Max+ 395, "Strix Halo") used as a headless home inference server. Each post compares engines, builds or models on the same machine, with the same client, so the numbers can be compared with each other.

## Posts

| Date | Post | Topics |
|---|---|---|
| 2026-11-24 | [Local French text-to-speech: which models can read a number?](posts/2026-11-24-french-tts-numbers.md) | Phonon, ZONOS3-Mini, Qwen3-TTS, Fish S2 Pro, Piper, Pocket TTS, NeuTTS, MOSS-TTS, whisper as a referee |
| 2026-11-24 | [Strix Halo inference engines, measured on one box](posts/2026-11-24-inference-engines-compared.md) | Halogen, hipEngine, AMD HRX, llama.cpp Vulkan, Inkling 2 Mini, Gemma 4, benchmarking traps |

## The machine

- Framework Desktop, Ryzen AI Max+ 395, Radeon 8060S (gfx1151, RDNA 3.5, 40 CUs)
- 128 GB LPDDR5x unified memory
- BIOS iGPU carve-out at the minimum (512 MB); the GPU borrows up to 100 GiB of system memory through GTT, set with the kernel parameter `ttm.pages_limit=26214400`
- Fedora 44, headless
- llama.cpp Vulkan official releases as the baseline, served through llama-swap

## How the numbers are taken

- Speeds are in tokens per second (t/s). "Prefill" is prompt processing, "decode" is generation.
- Every A/B comparison is run in both orders, because the first model loaded reads from disk and the next ones from a warm page cache.
- GPU load (`gpu_busy_percent`) is checked before and after a run; a number taken while something else computes on the GPU is thrown away.
- When a table says "same client", the numbers come from one HTTP client (streaming, greedy decoding, a nonce in each prompt to defeat prompt caches), which is what an application sees, rather than from each engine's own benchmark tool.
- Quality checks use my own workloads (tool-calling agents, JSON extraction, French text). They are described but not published, because they replay private requests.

## Benchmark scripts

The speed scripts are in [bench/](bench/): one HTTP client for any OpenAI-compatible server, and a llama-bench wrapper that runs two builds in both orders. MIT licence.

## Issues welcome

If a number looks wrong, if you get different results on the same hardware, or if you would like a model or an engine measured, open an issue.

## License

Text and tables in the posts are under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/): reuse them freely, with a link back.
