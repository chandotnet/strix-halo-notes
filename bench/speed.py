#!/usr/bin/env python3
"""Client-side speed benchmark for any OpenAI-compatible server (llama.cpp, llama-swap, Halogen, vLLM, ...).

llama-bench and engine-specific sweep tools do not compare across engines: one runs without a server, another
uses its own chat template. This script measures what an application sees instead: everything goes through
/v1/chat/completions, streaming, greedy decoding, with a random nonce at the start of every prompt so that no
prompt cache can help.

- Prefill: a filler text of about 512, 8,192 and 32,768 tokens, and a single output token.
  Speed = prompt tokens (from `usage`) / time to the first streamed byte.
- Decode: four kinds of output (prose, writing code, editing a file and returning it whole, copying a file
  into a tool call), then prose after about 32,768 tokens of context.
  Speed = (output tokens - 1) / (last token time - first token time).

The edit and tool-call cases use this very file as the document to edit or copy, so anyone can reproduce them.

Usage:

    python3 speed.py --url http://127.0.0.1:8080/v1/chat/completions --model my-model --label vulkan --out results.jsonl

Each request is written as one JSON line in --out (appended), and summarised on stdout. Read the real prompt
size from `prompt_tokens` in the output: the filler sizes are approximate and depend on the tokenizer.

Requires Python 3.9+ and nothing else (standard library only). MIT licence, see bench/README.md.
"""
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request

# Filler sentences with random numbers, so every prompt is different and nothing can be cached.
FILLER = {
    "en": [
        "Sensor {n} in the basement read {t} degrees at {h} o'clock, and humidity stayed under {u} percent.",
        "Invoice number {n}, dated March {j}, totals {t} dollars before taxes.",
        "At kilometre {n} of the highway the road was icy and visibility dropped to {u} metres.",
        "Lot {n} of the land registry measures {t} square metres according to the survey certificate.",
        "In the kitchen, lamp {n} draws {t} watts and stays on {h} hours a day on average.",
        "Meeting {n} lasted {h} hours; it covered a budget of {t} dollars and {u} pending requests.",
    ],
    # The French filler is the one used for the numbers published in this repository.
    "fr": [
        "Le capteur {n} du sous-sol a relevé {t} degrés à {h} h, et l'humidité est restée sous {u} %.",
        "La facture numéro {n} de la ville de Québec, datée du {j} mars, totalise {t} $ avant les taxes.",
        "Au kilomètre {n} de la route 175, la chaussée était glacée et la visibilité tombait à {u} mètres.",
        "Le lot {n} du cadastre du Québec mesure {t} mètres carrés selon le certificat de localisation.",
        "Dans la cuisine, la lampe {n} consomme {t} watts et reste allumée {h} heures par jour en moyenne.",
        "La réunion {n} a duré {h} heures ; on y a parlé du budget de {t} $ et de {u} demandes en attente.",
    ],
}
# Approximate tokens per word of filler (the random numbers cost many tokens). Depends on the tokenizer.
TOKENS_PER_WORD = {"en": 2.1, "fr": 2.27}
# Exact word counts of the published French runs, so that --lang fr regenerates the same filler.
FR_WORDS = {512: 225, 8192: 3600, 32768: 14400}

PROMPTS = {
    "en": {
        "prose": "Write a text of about 400 words on the history of the city of Quebec, from Champlain to today.",
        "code": "Write a complete Python LRUCache class (get, put, capacity, docstrings), then its unittest tests. Code only.",
        "edit": "Here is the file `speed.py` from our project:\n\n```python\n{code}\n```\n\nRename the function `stream` to "
                "`stream_request` everywhere in this file, then give back the COMPLETE modified file, without comments.",
        "tool": "Here is a Python file:\n\n```python\n{code}\n```\n\nSave it as is to `/tmp/speed_copy.py` with the write_file tool.",
        "deep": "\n\nNow write a text of about 400 words on the history of the city of Quebec.",
        "ok": "\n\nAnswer only: OK.",
    },
    "fr": {
        "prose": "Écris un texte d'environ 400 mots sur l'histoire de la ville de Québec, de Champlain à aujourd'hui.",
        "code": "Écris en Python une classe LRUCache complète (get, put, capacité, docstrings), puis ses tests unittest. Seulement le code.",
        "edit": "Voici le fichier `speed.py` de notre projet :\n\n```python\n{code}\n```\n\nRenomme la fonction `stream` en "
                "`stream_request` partout dans ce fichier, puis redonne le fichier COMPLET modifié, sans commentaire.",
        "tool": "Voici un fichier Python :\n\n```python\n{code}\n```\n\nEnregistre-le tel quel dans `/tmp/speed_copy.py` avec l'outil write_file.",
        "deep": "\n\nÉcris maintenant un texte d'environ 400 mots sur l'histoire de la ville de Québec.",
        "ok": "\n\nRéponds seulement : OK.",
    },
}

with open(__file__, encoding="utf-8") as _f:
    CODE = _f.read()

TOOL = [{"type": "function", "function": {
    "name": "write_file", "description": "Writes a complete file to disk.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                   "required": ["path", "content"]}}}]


def words_for(lang: str, tokens: int) -> int:
    return FR_WORDS[tokens] if lang == "fr" else int(tokens / TOKENS_PER_WORD[lang])


def filler(lang: str, n_words: int, seed: int) -> str:
    r = random.Random(seed)
    lines, words = [], 0
    while words < n_words:
        s = r.choice(FILLER[lang]).format(n=r.randint(1, 99999), t=round(r.uniform(1, 9999), 1), h=r.randint(1, 23),
                                          u=r.randint(1, 99), j=r.randint(1, 28))
        lines.append(s)
        words += len(s.split())
    return "\n".join(lines)


def nonce() -> str:
    return f"[{random.getrandbits(64):016x}] "


def stream(url: str, body: dict, timeout: int) -> dict:
    """Sends one streaming request and times the first and last streamed tokens."""
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.monotonic()
    first = last = None
    chunks = 0
    usage = timings = finish = None
    text = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                line = line.decode("utf-8", "ignore").strip()
                if not line.startswith("data:") or line == "data: [DONE]":
                    continue
                d = json.loads(line[5:])
                usage = d.get("usage") or usage
                timings = d.get("timings") or timings  # llama.cpp only, kept for comparison
                for c in d.get("choices") or []:
                    delta = c.get("delta") or {}
                    piece = (delta.get("content") or "") + (delta.get("reasoning_content") or "")
                    for call in delta.get("tool_calls") or []:
                        piece += (call.get("function") or {}).get("arguments") or ""
                    if piece:
                        t = time.monotonic()
                        first = first or t
                        last = t
                        chunks += 1
                        text.append(piece)
                    finish = c.get("finish_reason") or finish
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}", "duration_s": round(time.monotonic() - t0, 2)}
    pt = (usage or {}).get("prompt_tokens")
    ct = (usage or {}).get("completion_tokens") or chunks  # falls back to chunk count if the server sends no usage
    res = {"duration_s": round(time.monotonic() - t0, 2), "first_s": first and round(first - t0, 3),
           "prompt_tokens": pt, "completion_tokens": ct, "chunks": chunks, "finish": finish, "timings": timings,
           "text_start": "".join(text)[:300]}
    if first and pt:
        res["pp_tps"] = round(pt / (first - t0), 1)
    if first and last and last > first and ct and ct > 1:
        res["tg_tps"] = round((ct - 1) / (last - first), 1)
    return res


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--url", required=True, help="full URL of /v1/chat/completions")
    p.add_argument("--model", required=True, help="model name sent in the request")
    p.add_argument("--label", required=True, help="free label written in each result line")
    p.add_argument("--out", required=True, help="JSONL file, appended")
    p.add_argument("--lang", choices=["en", "fr"], default="en", help="prompt language (fr = the published runs)")
    p.add_argument("--extra", type=json.loads, default={"reasoning_effort": "none"},
                   help='JSON merged into every request, default {"reasoning_effort": "none"}')
    p.add_argument("--runs", type=int, default=2, help="runs per case")
    p.add_argument("--timeout", type=int, default=900, help="seconds per request")
    p.add_argument("--skip-32k", action="store_true", help="skip the 32k prefill and the deep decode case")
    a = p.parse_args()

    P = PROMPTS[a.lang]
    base = {"model": a.model, "temperature": 0, "cache_prompt": False, **a.extra}
    decode = [
        ("prose", P["prose"], {}),
        ("code", P["code"], {}),
        ("edit", P["edit"].format(code=CODE), {"max_tokens": 4096}),
        ("tool", P["tool"].format(code=CODE), {"tools": TOOL, "max_tokens": 4096}),
    ]
    sizes = (512, 8192) if a.skip_32k else (512, 8192, 32768)

    with open(a.out, "a", encoding="utf-8") as f:
        def record(case: str, i: int, res: dict) -> None:
            res.update({"label": a.label, "case": case, "run": i})
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{a.label:14} {case:10} #{i} prompt={res.get('prompt_tokens')} out={res.get('completion_tokens')} "
                  f"first={res.get('first_s')}s pp={res.get('pp_tps')} tg={res.get('tg_tps')} finish={res.get('finish')} "
                  f"{res.get('error') or ''}", flush=True)

        for target in sizes:
            for i in range(a.runs):
                msg = nonce() + filler(a.lang, words_for(a.lang, target), target * 10 + i) + P["ok"]
                record(f"pp{target}", i, stream(a.url, {**base, "max_tokens": 1,
                                                        "messages": [{"role": "user", "content": msg}]}, a.timeout))
        for case, prompt, extra in decode:
            for i in range(a.runs):
                body = {**base, "max_tokens": 1024, **extra,
                        "messages": [{"role": "user", "content": nonce() + prompt}]}
                record(case, i, stream(a.url, body, a.timeout))
        if not a.skip_32k:
            for i in range(a.runs):
                msg = nonce() + filler(a.lang, words_for(a.lang, 32768), 999 + i) + P["deep"]
                record("prose@32k", i, stream(a.url, {**base, "max_tokens": 1024,
                                                      "messages": [{"role": "user", "content": msg}]}, a.timeout))


if __name__ == "__main__":
    main()
