"""Baseline storage rule (ruling 2026-09-10): one baseline on disk at a time. Download, evaluate, write the results
JSON, then delete the weights from the Hugging Face cache before the next download. Check free space before each
download and stop with a report when less than MIN_FREE_GB is free. Nothing here touches our own checkpoints or the
non-baseline models the serving stack uses (bge-m3, BioCLIP, the guard).
"""
import os, shutil, time

HUB = os.path.expanduser("~/.cache/huggingface/hub")
MIN_FREE_GB = 80
KEEP = {"BAAI/bge-m3", "imageomics/bioclip", "imageomics/bioclip-2", "Qwen/Qwen3.5-2B-Base", "Qwen/Qwen3Guard-Gen-0.6B"}   # never purged here

def free_gb(path="/home/user"):
    return round(shutil.disk_usage(path).free / 1e9, 1)

def cache_dir(model_id):
    return os.path.join(HUB, "models--" + model_id.replace("/", "--"))

def fetch(model_id, log=print):
    """Download one baseline after the free-space check. Raises RuntimeError when space is short (the caller records it)."""
    if os.path.isdir(model_id):   # a local path (ours): nothing to download
        return model_id
    f = free_gb()
    if f < MIN_FREE_GB:
        raise RuntimeError(f"free space {f} GB is below the {MIN_FREE_GB} GB floor; stopped before downloading {model_id}")
    from huggingface_hub import snapshot_download, HfApi
    t0 = time.time()
    files = HfApi().list_repo_files(model_id)
    weights = ["*.safetensors"] if any(f.endswith(".safetensors") for f in files) else ["*.bin"]   # older repos ship pytorch_model.bin only
    p = snapshot_download(model_id, allow_patterns=["*.json", "*.model", "*.txt", "*.py", "*.jinja", "*.tiktoken"] + weights,
                          ignore_patterns=["*.gguf", "*consolidated*", "*.pth"])
    log(f"[storage] downloaded {model_id} in {time.time() - t0:.0f}s; free {free_gb()} GB")
    return p

def purge(model_id, log=print):
    """Delete a baseline's weights from the cache (never ours, never the KEEP set)."""
    if os.path.isdir(model_id) or model_id in KEEP:
        return False
    d = cache_dir(model_id)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        log(f"[storage] purged {model_id}; free {free_gb()} GB")
        return True
    return False

def purge_all_baselines(ids, log=print):
    for m in ids:
        purge(m, log)
