"""Hosted-model comparison through OpenRouter (ruling 2026-09-13). Generation tasks only, on the LOCKED TEST SPLITS, chat mode:
FLORES and IN22 both directions, IndicQA, GSM8K. Prompts and scoring are exactly eval/suite.py's: the suite's score_items() runs
unchanged with its generation functions routed to the API. Log-likelihood tasks (MILU, MMLU, bpc, probe) cannot be scored
through a hosted chat API and are not run.

Every request is pinned to the lab's own provider (no fallbacks), with providers that retain or train on prompts refused,
temperature 0, reasoning switched off where the model allows it. The provider that served each request, its token counts,
reasoning tokens and cost are stored next to the response. Rate limits and transient errors retry with exponential backoff.
A hard budget stops the run before any request that could take actual spend past the cap. Responses are cached per model, so an
interrupted run resumes without paying twice.

Key: OPENROUTER_API_KEY in the environment, else ~/.config/openrouter/key. The key is never written anywhere by this script.

  .venv/bin/python eval/hosted_compare.py --plan                      # no requests: request counts and cost estimate
  .venv/bin/python eval/hosted_compare.py --smoke --models M1,M2      # one request per model (a few cents at most)
  .venv/bin/python eval/hosted_compare.py --models M1,M2 --budget 5   # the full run
Writes eval/results/hosted_<name>_chat_test.json (suite-format rows) and eval/results/hosted_raw/<name>.jsonl (every response).
"""
import argparse, http.client, json, os, random, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import suite

API = "https://openrouter.ai/api/v1/chat/completions"
# Lab-owned provider per author: OpenRouter routing slug and the provider name its responses and endpoint list report.
# Google: Vertex, not AI Studio: only Vertex offers zero data retention for Gemini on OpenRouter (checked 2026-09-13).
OFFICIAL = {"google": ("google-vertex", "Google"), "openai": ("openai", "OpenAI"), "deepseek": ("deepseek", "DeepSeek"), "anthropic": ("anthropic", "Anthropic"), "x-ai": ("xai", "xAI")}
TASKS = {"flores_en_ta": "translation", "flores_ta_en": "translation", "in22gen_en_ta": "translation", "in22gen_ta_en": "translation",
         "indicqa_ta": "qa", "gsm8k_en": "gsm8k"}
RAW = os.path.join(HERE, "results", "hosted_raw")
# Any-provider models (ruling 2026-09-13: gpt-oss-20b and gpt-oss-120b "from any provider"): no pin; OpenRouter routes to the cheapest
# live endpoint first with fallbacks allowed, providers that collect prompt data refused (as for every hosted run: DeepSeek's own
# endpoint was excluded because it trains on prompts), and the provider that served each response is recorded. gpt-oss cannot switch
# reasoning off, so it runs at the lowest effort ("low"); reasoning tokens count against max_tokens, so these requests send the
# suite's answer cap plus REASONING_ALLOWANCE, and the cache key stays the suite's cap.
ANY_PROVIDER = {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
# v3 answer caps for hosted models (ruling 2026-09-14): the suite's per-tokenizer caps, computed with the closest public tokenizer
# (Gemini: the Gemma 3 tokenizer, which shares Gemini's vocabulary; OpenAI: o200k through the gpt-oss tokenizer). A response that
# completed under the old cap (finish_reason stop) is re-used as is; only responses stopped at the old cap are re-sent.
CAP_PROXY = {"google": "google/gemma-3-1b-it", "openai": "openai/gpt-oss-20b"}
class ProxyTok:
    def __init__(self, name):
        from transformers import AutoTokenizer
        self.t = AutoTokenizer.from_pretrained(name); self.name = name
    def __call__(self, text, add_special_tokens=False):
        return self.t(text, add_special_tokens=add_special_tokens)
REASONING_ALLOWANCE = 1024

def key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        p = os.path.expanduser("~/.config/openrouter/key")
        if os.path.exists(p): k = open(p).read().strip()
    if not k: raise SystemExit("no key: set OPENROUTER_API_KEY for this command or write ~/.config/openrouter/key (chmod 600)")
    return k

def slug(model): return model.replace("/", "_").replace(":", "_")

def account():
    """The key's usage as OpenRouter reports it (GET /api/v1/key: usage in USD, limit)."""
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key()}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode()).get("data", {})
    return {k: d.get(k) for k in ("label", "usage", "usage_daily", "usage_weekly", "usage_monthly", "limit", "limit_remaining")}

class Budget:
    def __init__(self, cap, spent):
        self.cap, self.spent, self.reserved, self.lock = cap, spent, 0.0, threading.Lock()
    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount > self.cap: return False
            self.reserved += amount; return True
    def settle(self, reserved, actual):
        with self.lock: self.reserved -= reserved; self.spent += actual

class Client:
    """One model. Cache: every response keyed by a hash of (prompt, max_tokens)."""
    def __init__(self, model, budget, max_price, smoke=False, zdr=True, allow_collection=False, route=None):
        self.model, self.budget, self.max_price, self.smoke = model, budget, max_price, smoke
        self.policy = {"data_collection": "allow" if allow_collection else "deny", **({"zdr": True} if zdr else {})}
        self.any = model in ANY_PROVIDER
        self.slug, self.provider = ("any", "any provider") if self.any else (route or OFFICIAL[model.split("/")[0]])
        os.makedirs(RAW, exist_ok=True)
        self.path = os.path.join(RAW, slug(model) + ".jsonl"); self.cache = {}; self.lock = threading.Lock()
        if os.path.exists(self.path):
            for l in open(self.path, encoding="utf-8"):
                if l.strip():
                    r = json.loads(l); self.cache[r["key"]] = r
        self.reasoning = {"effort": "low"} if self.any else {"enabled": False}
        self.k = key()
        self.recap = False; self.old_caps = (160, 48, 256)

    def _post(self, body):
        req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {self.k}", "Content-Type": "application/json",
                                     "HTTP-Referer": "https://timegravity.ai", "X-Title": "tamil-lm evaluation"})
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode())

    def complete(self, prompt, max_new):
        import hashlib
        ck = hashlib.sha1(f"{max_new}\x00{prompt}".encode()).hexdigest()
        if ck in self.cache: return self.cache[ck]["text"]
        if self.recap:   # v3 caps: re-use a response that completed under a smaller earlier cap
            for old in self.old_caps:
                if old >= max_new: continue
                ok_ = hashlib.sha1(f"{old}\x00{prompt}".encode()).hexdigest()
                r0 = self.cache.get(ok_)
                if r0 and r0.get("finish_reason") == "stop":
                    rec = dict(r0, key=ck, max_tokens=max_new, reused_from_cap=old, cost_usd=0.0, ts=time.strftime("%FT%TZ", time.gmtime()))
                    with self.lock:
                        self.cache[ck] = rec
                        with open(self.path, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    return rec["text"]
        # worst-case cost of this request: prompt at about one token per 1.5 characters, the full output cap plus a reasoning allowance
        sent = max_new + REASONING_ALLOWANCE if self.any else max_new
        est = (len(prompt) / 1.5) * self.max_price[0] / 1e6 + (sent + 400) * self.max_price[1] / 1e6
        if not self.budget.reserve(est):
            raise BudgetStop(f"budget: spent {self.budget.spent:.4f} USD of {self.budget.cap}; the next request could exceed it")
        prov = {"sort": "price", "allow_fallbacks": True, "data_collection": "deny"} if self.any else {"order": [self.slug], "only": [self.slug], "allow_fallbacks": False, **self.policy}
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "max_tokens": sent, "temperature": 0,
                "provider": prov,
                "reasoning": self.reasoning, "usage": {"include": True}}
        delay = 2.0; last = None
        for attempt in range(8):
            try:
                d = self._post(body)
                if not d.get("choices") or not d.get("provider"):   # a 200 with no answer or no provider (one Gemini response, 2026-09-13): retried, never cached
                    last = f"empty 200 response: {json.dumps(d)[:160]}"; time.sleep(delay + random.random()); delay = min(delay * 2, 120); continue
                break
            except urllib.error.HTTPError as e:
                msg = e.read().decode(errors="replace")[:400]; last = f"HTTP {e.code}: {msg}"
                if e.code == 400 and "reason" in msg.lower() and body["reasoning"] == {"enabled": False}:
                    body["reasoning"] = self.reasoning = {"effort": "minimal"}; continue   # the model cannot switch reasoning off
                if e.code in (408, 429, 500, 502, 503, 504, 529):
                    time.sleep(delay + random.random()); delay = min(delay * 2, 120); continue
                self.budget.settle(est, 0.0); raise RuntimeError(f"{self.model}: {last}")
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, json.JSONDecodeError, OSError) as e:
                # a dropped connection or a truncated body (IncompleteRead, 2026-09-13): retried; if the provider had already billed the
                # lost response, that charge is not in the local total, so the summary reads the account's own usage at the end
                last = f"{type(e).__name__}: {str(e)[:120]}"; time.sleep(delay + random.random()); delay = min(delay * 2, 120)
        else:
            self.budget.settle(est, 0.0); raise RuntimeError(f"{self.model}: gave up after retries: {last}")
        ch = (d.get("choices") or [{}])[0]; msg = ch.get("message") or {}
        u = d.get("usage") or {}; cost = float(u.get("cost") or 0.0)
        self.budget.settle(est, cost)
        rec = {"key": ck, "model": self.model, "requested_provider": self.provider, "served_by": d.get("provider"), "text": msg.get("content") or "",
               "finish_reason": ch.get("finish_reason"), "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
               "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"), "cost_usd": cost,
               "reasoning_setting": body["reasoning"], "provider_constraints": prov, "max_tokens": max_new, "max_tokens_sent": sent, "ts": time.strftime("%FT%TZ", time.gmtime())}
        if rec["served_by"] and rec["served_by"] != self.provider and not self.any:
            raise RuntimeError(f"{self.model}: served by {rec['served_by']}, not the pinned {self.provider}; stopped")
        with self.lock:
            self.cache[ck] = rec
            with open(self.path, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec["text"]

class BudgetStop(RuntimeError): pass

def prices(model, prov=None):
    """Price per million tokens (in, out) of the pinned provider (the lab's own unless overridden), read live from OpenRouter."""
    with urllib.request.urlopen(f"https://openrouter.ai/api/v1/models/{model}/endpoints", timeout=60) as r:
        eps = json.loads(r.read().decode())["data"]["endpoints"]
    if model in ANY_PROVIDER:   # any provider: budget reservations use the dearest live endpoint, so the cap holds whichever one serves
        mine = [e for e in eps if e.get("status", 0) == 0]
        return max(float(e["pricing"]["prompt"]) for e in mine) * 1e6, max(float(e["pricing"]["completion"]) for e in mine) * 1e6
    prov = prov or OFFICIAL[model.split("/")[0]][1]
    mine = [e for e in eps if e.get("provider_name") == prov and e.get("status", 0) == 0]
    if not mine: raise SystemExit(f"{model}: no live endpoint from {prov}")
    return max((float(e["pricing"]["prompt"]) * 1e6, float(e["pricing"]["completion"]) * 1e6) for e in mine)   # the dearest official tier, to be safe

def selected(task):
    items = {it["id"]: it for it in suite.load_items(task)}
    return [items[i] for i in json.load(open(os.path.join(suite.SPLITS, f"{task}.json")))["test"] if i in items]

def run_model(model, budget, workers, smoke, zdr=True, allow_collection=False, route=None, recap=False):
    pin, pout = prices(model, route[1] if route else None); cl = Client(model, budget, (pin, pout), smoke, zdr, allow_collection, route)
    cl.recap = recap
    tok = ProxyTok(CAP_PROXY[model.split("/")[0]]) if recap else None
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=workers)
    suite.greedy_batch = lambda m, tok, prompts, max_new, **kw: list(pool.map(lambda p: cl.complete(p, max_new), prompts))
    suite.greedy = lambda m, tok, prompt, max_new, **kw: cl.complete(prompt, max_new)
    rows = []; commit = suite.git_commit()
    for task, kind in TASKS.items():
        sel = selected(task)[:1] if smoke else selected(task)
        t0 = time.time()
        if kind == "gsm8k":   # the suite decodes GSM8K item by item; parallelise the API calls here, then score through the suite
            list(pool.map(lambda it: cl.complete(suite.prompt_template("gsm8k").format(question=it["question"]), 512 if recap else 256), sel))
        suite.GEN_CAPS.pop(task, None)
        metrics, recs = suite.score_items(kind, sel, None, tok, task=task)
        for metric, score in metrics.items():
            rows.append({"benchmark": task, "split": "test", "n": len(sel), "metric": metric, "score": round(score, 4), "script": "eval/hosted_compare.py",
                         "commit": commit, "harness": "hosted-openrouter-v1", "gen_mode": "api", "stage": f"hosted_{slug(model)}", "model": model,
                         "provider_pinned": cl.provider, "timestamp": time.strftime("%FT%T"), **({"gen_cap": suite.GEN_CAPS[task], "cap_rule": f"v3 per-tokenizer caps, proxy tokenizer {tok.name}"} if recap and task in suite.GEN_CAPS else {})})
        print(f"[hosted] {model} {task} n={len(sel)} {metrics} ({time.time()-t0:.0f}s) spent so far {budget.spent:.4f} USD", flush=True)
    served = {}; rtok = 0; cost = 0.0
    for r in cl.cache.values():
        served[r["served_by"]] = served.get(r["served_by"], 0) + 1; rtok += r.get("reasoning_tokens") or 0; cost += r.get("cost_usd") or 0
    summary = {"model": model, "provider_pinned": cl.provider, "served_by_counts": served, "reasoning_tokens_total": rtok, "cost_usd_total": round(cost, 4),
               "price_per_million": {"in": pin, "out": pout}, "reasoning_setting": cl.reasoning, "data_policy": cl.policy, "lab_owned_provider": route is None}
    if not smoke:
        json.dump(rows, open(os.path.join(HERE, "results", f"hosted_{slug(model)}_chat_test.json"), "w"), indent=1)
    print("[hosted] summary", json.dumps(summary), flush=True)
    return summary

def plan(models):
    n = {t: len(selected(t)) for t in TASKS}
    print("requests per model:", n, "total", sum(n.values()))
    chars_in = sum(len(suite.prompt_template(k if k != "qa" else "qa").format(**({"context": it["context"][:3000], "question": it["question"]} if k == "qa" else {"question": it["question"]} if k == "gsm8k" else {"src_lang": "English", "tgt_lang": "Tamil", "src": it["src"]}))) for t, k in TASKS.items() for it in selected(t))
    for m in models:
        pin, pout = prices(m); label = "dearest live endpoint" if m in ANY_PROVIDER else f"official {OFFICIAL[m.split('/')[0]][1]}"
        out_tok = sum(n.values()) * (300 if m in ANY_PROVIDER else 120)   # answer plus low-effort reasoning, per request
        print(f"  {m}: {label} in {pin:.3f} out {pout:.3f} USD per million; about {chars_in/1.5/1e6:.2f}M input and {out_tok/1e6:.2f}M output tokens -> worst case {chars_in/1.5*pin/1e12 + out_tok*pout/1e6:.2f} USD")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--models", default="google/gemini-3.5-flash-lite,openai/gpt-5.4-nano,deepseek/deepseek-v4.1-flash")
    ap.add_argument("--budget", type=float, default=4.5); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--plan", action="store_true"); ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--no-zdr", action="store_true", help="do not require zero data retention (ruling 2026-09-13: not required)")
    ap.add_argument("--allow-data-collection", default="", help="comma list of models whose lab-owned provider needs data collection allowed")
    ap.add_argument("--recap", action="store_true", help="v3 answer caps (ruling 2026-09-14): re-use completed responses, re-send the ones stopped at the old cap")
    ap.add_argument("--account", action="store_true", help="print the key's own usage figure from OpenRouter at the start and end")
    ap.add_argument("--route", action="append", default=[], help="MODEL=slug:Served Name, a third-party provider for a model whose lab endpoint is unusable (ruling 2026-09-13: DeepSeek via another provider)")
    a = ap.parse_args(); models = [m.strip() for m in a.models.split(",") if m.strip()]
    if a.plan: return plan(models)
    spent = 0.0
    for m in models:   # money already spent on earlier runs counts against the cap
        p = os.path.join(RAW, slug(m) + ".jsonl")
        if os.path.exists(p): spent += sum(json.loads(l).get("cost_usd") or 0 for l in open(p) if l.strip())
    budget = Budget(a.budget, spent); print(f"[hosted] budget {a.budget} USD, already spent {spent:.4f}", flush=True)
    if a.account: print("[hosted] account at start:", account(), flush=True)
    out = []
    for m in models:
        try:
            routes = {x.split("=", 1)[0]: tuple(x.split("=", 1)[1].split(":", 1)) for x in a.route}
            out.append(run_model(m, budget, a.workers, a.smoke, zdr=not a.no_zdr, allow_collection=m in a.allow_data_collection.split(","), route=routes.get(m), recap=a.recap))
        except BudgetStop as e:
            print(f"[hosted] STOP {m}: {e}", flush=True); break
        except RuntimeError as e:   # a provider constraint cannot be met (not the official provider, no ZDR endpoint): report and go on
            print(f"[hosted] FAILED {m}: {e}", flush=True); out.append({"model": m, "error": str(e)[:300]})
    json.dump({"models": out, "spent_usd": round(budget.spent, 4), "budget_usd": a.budget, "smoke": a.smoke},
              open(os.path.join(HERE, "results", "hosted_summary_" + "_".join(slug(m).split("_")[0] for m in models) + ("_smoke" if a.smoke else "") + ".json"), "w"), indent=1)
    print(f"[hosted] done; spent {budget.spent:.4f} USD", flush=True)
    if a.account:
        acc = account(); print("[hosted] account at end:", acc, flush=True)
        json.dump({"ts": time.strftime("%FT%TZ", time.gmtime()), "account": acc}, open(os.path.join(HERE, "results", "hosted_account_" + time.strftime("%Y%m%dT%H%M") + ".json"), "w"), indent=1)

if __name__ == "__main__":
    main()
