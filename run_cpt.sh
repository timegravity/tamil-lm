#!/usr/bin/env bash
# Supervisor for the long CPT run. Survives terminal closure and reboots
# (systemd user service tamil-trainer.service runs this).
# Loops "python train_long.py --resume" until DONE-CPT sentinel exists.
# Honors PAUSE (sleep+poll), PAUSE-SCHEDULE (from schedule.yaml), STOP (exit).
set -u
cd "$(dirname "$0")"
PY=.venv/bin/python
RUN_NAME="${CPT_RUN_NAME:-cpt}"

check_schedule() {
    # creates/removes PAUSE-SCHEDULE according to schedule.yaml
    $PY - <<'EOF'
import yaml, datetime, os, sys
cfg = {}
if os.path.exists("schedule.yaml"):
    cfg = yaml.safe_load(open("schedule.yaml")) or {}
windows = cfg.get("windows") or []
if not windows:
    ok = True                     # empty list: always allowed
else:
    now = datetime.datetime.now()
    days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today = days[now.weekday()]
    def day_in(spec):
        spec = spec.lower()
        if "-" in spec:
            a, b = spec.split("-")
            ia, ib = days.index(a), days.index(b)
            rng = days[ia:ib+1] if ia <= ib else days[ia:] + days[:ib+1]
            return today in rng
        return today in [s.strip() for s in spec.split(",")]
    def in_window(w):
        if not day_in(str(w.get("days", "mon-sun"))):
            return False
        t = now.strftime("%H:%M")
        s, e = w.get("start", "00:00"), w.get("end", "23:59")
        if s <= e:
            return s <= t <= e
        return t >= s or t <= e      # crosses midnight
    ok = any(in_window(w) for w in windows)
if ok:
    if os.path.exists("PAUSE-SCHEDULE"):
        os.remove("PAUSE-SCHEDULE")
else:
    open("PAUSE-SCHEDULE", "w").close()
sys.exit(0)
EOF
}

gpu_busy() {
    # returns 0 (busy) if other processes use > 8GB
    # WSL2: per-process usage is [N/A]; use total memory in use (ours is not running yet)
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -dc '0-9')
    [ "${used:-0}" -gt 8192 ]
}

echo "[supervisor] start $(date)"
while true; do
    [ -f DONE-CPT ] && { echo "[supervisor] DONE-CPT sentinel; exiting"; exit 0; }
    if [ -f STOP ]; then
        echo "[supervisor] STOP file; exiting"
        ./notify.sh "tamil-lm: supervisor stopped by STOP file"
        exit 0
    fi
    check_schedule
    if [ -f PAUSE ] || [ -f PAUSE-SCHEDULE ]; then
        sleep 30
        continue
    fi
    if gpu_busy; then
        echo "[supervisor] GPU busy (>8GB other processes); rechecking in 120s. Reason logged to STATUS.md"
        grep -q "GPU busy, launch deferred" STATUS.md 2>/dev/null || \
            printf '\n- %s: GPU busy, launch deferred by supervisor (other process > 8GB)\n' "$(date '+%F %T')" >> STATUS.md
        sleep 120
        continue
    fi
    ./notify.sh "tamil-lm: launching train_long.py --resume (run $RUN_NAME)"
    $PY train_long.py --run "$RUN_NAME" --resume
    code=$?
    if [ $code -eq 0 ]; then
        # clean exit: either finished (writes DONE-CPT itself) or paused
        continue
    fi
    echo "[supervisor] train_long.py exited $code; restarting in 30s"
    ./notify.sh "tamil-lm: train crashed with exit $code, restarting in 30s"
    sleep 30
done
