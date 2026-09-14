"""Result-file guard (ruling 2026-09-11): a scorer never overwrites an existing result file silently. If the target exists
it is moved to <path>.bak.<UTC timestamp> first, so a re-score of one round can never erase another round's record.
"""
import json, os, shutil, time

def write_json(path, obj, **kw):
    if os.path.exists(path):
        bak = f"{path}.bak.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        shutil.move(path, bak)
        print(f"[result_guard] existing {os.path.basename(path)} kept as {os.path.basename(bak)}")
    kw.setdefault("ensure_ascii", False); kw.setdefault("indent", 1)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, **kw)
