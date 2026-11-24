# Local French text-to-speech on Strix Halo: which models can read a number?

*24 November 2026.*

Between August and November 2026 I tested eleven text-to-speech models for the voice of a French-speaking home assistant that runs on a Framework Desktop (Ryzen AI Max+ 395, 128 GB). The assistant mostly says short sentences full of numbers: temperatures, times, dates, percentages, amounts. That turned out to be the hard part. Most models sound good in a demo and still say "87" when asked to say "97".

Short version: Phonon 40M FR (CPU, 27 ms to first audio) and ZONOS3-Mini (Vulkan, Apache 2.0) are the best fit for a real-time assistant; Qwen3-TTS and Fish S2 Pro read numbers best but are slower; Piper is still a reliable fallback if you pick the right voice.

## How I judge a voice: whisper as the referee

A synthesized sentence can sound perfect and say something else. Your ear forgives, a transcription does not. So each candidate reads a fixed set of sentences, whisper.cpp (`large-v3-turbo`) transcribes the audio, and the script compares the numbers and the words with what was asked. Piper, which phonemizes text before synthesis, serves as the control: when whisper mishears Piper the same way, the error is whisper's, not the model's.

The sentence set grew over three months, so the denominators differ between rows. The core is seven sentences from the assistant's daily life ("Il fait 23 degrés dans le bureau", "mardi 1er septembre", "rendez-vous à 15 h 00", "la pile est à 97 %", "dans 10 jours", plus "Oui, j'écoute." and "Je regarde."), each drawn several times. Later benches added three hard ones: "41 093,38 $", "2026, -3,5 °C" and "1 500 kWh". "RTF" is the real-time factor: seconds of compute per second of audio, so lower is faster and anything above 1 cannot keep up with speech.

## Results

| Model | Runs on | RTF, idle box | Numbers read right | Licence | Verdict |
|---|---|---:|---|---|---|
| **Phonon 40M FR** (Gradium), q8 GGUF, `ptts` | CPU, 2 threads | **0.070** (27 ms to first audio) | **29/30** | CC BY-NC 4.0 | Best for a live assistant, if non-commercial is fine |
| **ZONOS3-Mini** (Zyphra), `zonos3.cpp` | Vulkan | **0.057** (23 ms) | 27/30 with the built-in voice, 19/20 with a clean cloned voice | Apache 2.0 | Best permissive option |
| **Qwen3-TTS 12Hz 1.7B** Q8, `llama-tts` | Vulkan | 0.33 | **133/133** draws | Apache 2.0 | Most accurate, but 0.70 RTF when the GPU is busy |
| **Fish S2 Pro** Q8, `audio.cpp` | Vulkan | 1.06 | **28/28** | Non-commercial | Accurate, too slow for conversation; fine for narration |
| **Piper**, voice `fr-siwis` | CPU | 0.14 | right (deterministic) | MIT engine, voice licences vary | Reliable fallback |
| Pocket TTS (Kyutai), int8 ONNX, 6 layers | CPU, 2 threads | 0.078 | 15/21 | CC BY 4.0 | Fast, cannot read numbers on its own |
| NeuTTS nano French (official) | Vulkan | 0.09 to 0.14 | 42/50 sentences right, "97" still fails | NeuTTS Open License 1.0 | Good with the official code only |
| ice-012-audio | PyTorch ROCm | 0.37 to 0.63 warm | "97" becomes "87", "1er" fails 3/3 | Apache 2.0 | Rejected |
| MOSS-TTS v1.5 8B, Q8 | Vulkan | 1.04 (2 s to first audio) | 17/20 | see model card | Too slow, runs away on short sentences |
| MOSS-TTS-Local v1.5, Q8 | Vulkan | 0.58 | 15/20, invents words | see model card | Rejected |
| Orpheus 3B French, Q8 | Vulkan | 1.6 to 2.1 | 3/3 | see model card | Too slow on this memory bandwidth |
| Chatterbox, French fine-tune (Thomcles, 1,400 h of Emilia) | PyTorch ROCm | 2.0 to 2.8 | same "97" problem | see model card | Rejected, diffusion decoder too heavy for this iGPU |

Notes on the table:

- Phonon reads "97 %", "1er", "15 h 00" and "10 jours" right on its own, which Pocket (its ancestor) cannot do: Pocket said "Anna Pompré" for "97 %". Its one weak spot is money: "41 093,38 $" comes out as "41 093 dollars et 38 cents", which a listener understands but whisper hears as 3,800. Under load (the LLM decoding on the GPU at 98%), Phonon only goes from 0.070 to 0.097 RTF because it never touches the GPU.
- ZONOS3 on Vulkan slows down 3.5 times while the LLM runs (0.057 to 0.200 RTF), because they share the GPU. Still far below real time. Its CPU build gives 0.145 idle and 0.21 under load.
- Qwen3-TTS was the first model to never miss a number. `llama-tts` reloads the model on every call (1.36 s, not counted in the RTF), so it wants a resident server for live use.
- The ratings for Fish S2 Pro and Qwen3-TTS come from the same seven-sentence bench. S2 Pro also handled "Home Assistant" correctly once given a fixed voice.

## What I learned, in order of cost

1. **Most autoregressive TTS models cannot read French numbers.** Four candidates in a row turned "97" into "87" and "1er septembre" into "8 septembre", in a described voice as well as a cloned one. A wrong date three draws out of three is a reading problem, not sampling noise, and no retry will fix it. Test numbers first, before you listen to anything else.
2. **Do not rewrite a TTS model's inference chain.** I lost an evening "measuring" defects in NeuTTS that came from my own prompt code (a different phonemizer, then a duplicated BOS token). With the official code, the same weights read 3 sentences out of 3, numbers included, at RTF 0.09. Quick check that would have saved the evening: generate without any reference voice. If the model still garbles the sentence, the problem is not your reference.
3. **Measure the second run.** ice-012-audio first measured at RTF 2.43, which would have rejected it. 86% of the time was in its convolutional codec, and MIOpen on gfx1151 searches kernels again for every new input shape. Warm, the same sentence ran at 0.37. Chatterbox, on the other hand, stays slow warm: its diffusion decoder genuinely computes. Same bad number, opposite causes.
4. **A busy GPU doubles the RTF.** Qwen3-TTS: 0.33 on an idle GPU, 0.70 while the LLM was generating, 0.34 again two minutes later. A resident but idle model costs nothing; a computing one does. An assistant speaks right after the LLM answers, so measure under load, not only idle. This is the main argument for a CPU model such as Phonon.
5. **A cloned voice copies everything in the clip.** Background hiss becomes a permanent breath, a leading silence becomes a pause before every sentence. With ZONOS3, a clip recorded on a kitchen microphone turned one sentence in ten into noise in reference mode, while the same clip as a speaker embedding scored 19/20. Clean clips made with a voice-design model worked in both modes.
6. **Piper voices trained on audiobooks fail on short sentences.** The MLS-based French Piper voices produce gibberish under about ten words ("Mais on dit, on se passe par." for a three-word sentence) because audiobooks contain no short utterances. Always include a three-word sentence in a TTS bench. Among Piper voices, `fr-tjiho2` (44.1 kHz) was the only one to pass every sentence; `fr-tjiho3`, its supposed successor, did worse.
7. **Memory bandwidth limits token-based TTS on this machine.** Orpheus needs 93 backbone tokens per second of audio and the box delivers about 57 t/s on its 3.3 GB of Q8 weights: it can never keep up. Models working at 12.5 frames per second (Qwen3-TTS, Pocket, Phonon) have a 7 times lighter load.

## Two whisper tricks, since it is the referee

- **whisper hallucinates on silence and on low input levels.** Two seconds of digital silence reliably produce "Sous-titrage Société Radio-Canada" (a subtitle credit from its French training data). A low input level (−35 dBFS peaks) produced invented sentences too. Put a voice activity detector in front of whisper, and set the microphone gain for the highest peak that does not clip.
- **The `prompt` parameter fixes proper nouns for free.** A one-sentence prompt quoting a name made whisper transcribe it right, where it wrote "T-shirt" without one. Cost: 0.315 s instead of 0.302 s. But on clips under 3 seconds a prompt can hurt, and a prompt written as a sentence ("Transcription en français…") gets copied into the output.

Questions, corrections or a model you would like measured: open an issue on this repository.
