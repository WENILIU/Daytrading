# -*- coding: utf-8 -*-
"""One command for the 08:55 pre-open chain.

The schedule carried this chain as a ten-step prompt. Describing it was not enough: on
2026-10-29 and 2026-10-30 the schedule fired on time and nothing on disk moved - no
refresh, no preflight, no launch, no paper report. So the chain is code now, and the
schedule only runs this file and reports what it printed.

    python morning_chain.py                  full chain, starts paper when it may
    python morning_chain.py --no-launch      every step except starting paper
    python morning_chain.py --force          ignore the already-done guard
    python morning_chain.py --session-check  print session state as JSON and exit

The verdict is one of SKIP / BLOCKED / READY / LAUNCHED and is printed first, so the
report cannot invent a judgement this script did not make. The same verdict is written
to trading_logs/morning_chain_YYYYMMDD.json for the 13:32 job and for later review.
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

# not resolve(): this directory is reached through a junction, and resolving it
# prints a D:\ path for files the user knows under C:\. Same folder, wrong name.
HERE = Path(__file__).parent.absolute()
LOGS = HERE / "trading_logs"
PY = sys.executable
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
MARK_PAPER = "LIVE FEASIBILITY REPORT"
MARK_RISK1 = "RISK1 exchange opening-print time"
PAPER_FIRST, PAPER_LAST = "08:55", "13:25"


def sh(args, timeout):
    """Run one step as a child process. The children print Chinese, so force UTF-8 on
    both sides - the default cp950 console turns their details into unreadable bytes."""
    t0 = time.time()
    try:
        r = subprocess.run([PY] + args, cwd=str(HERE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=ENV)
        return r.returncode, (r.stdout or "") + "\n" + (r.stderr or ""), time.time() - t0
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT after %ds" % timeout, time.time() - t0


def session_check():
    """--session-check. Its own process: a finlab outage must not take the chain down,
    and must not be read as 'not a trading day' either."""
    sys.path.insert(0, str(HERE))
    out = {"today": date.today().isoformat(), "session": None, "prev_session": None}
    try:
        from finlab import data as fdata
        import pandas as pd
        from gap_fade_auto import _ensure_finlab_login
        if not _ensure_finlab_login():
            out["error"] = "finlab login failed"
        else:
            cal = fdata.get_calendar()
            out["session"] = bool(cal.is_session(date.today()))
            try:
                out["prev_session"] = str(pd.Timestamp(
                    cal.previous_session(date.today() - timedelta(days=1))).date())
            except Exception as exc:
                out["error"] = "previous_session %s: %s" % (type(exc).__name__, exc)
    except Exception as exc:
        out["error"] = "%s: %s" % (type(exc).__name__, exc)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["session"] is not None else 1


def today_log():
    p = LOGS / ("trading_%s.log" % date.today().isoformat())
    return p if p.exists() else None


def ran_today(marker):
    p = today_log()
    return bool(p) and marker in p.read_text(encoding="utf-8", errors="replace")


def find(text, needle):
    hits = [l.strip() for l in text.splitlines() if needle in l]
    return hits[-1] if hits else ""


def score(text):
    """The n/n from the summary line only. A bare regex over the whole output picks
    up ratios printed inside individual check details (seen: a suite reporting 40/40
    while a detail line said 0/3), which is the opposite of a verdict."""
    for l in reversed(text.splitlines()):
        if "passed" in l or "checks" in l and "->" in l:
            m = re.search(r"\d+/\d+", l)
            if m:
                return m.group(0)
    return "no summary line"


def launch_paper():
    """Start paper detached, the way the 2026-10-28 13:57 test proved works."""
    flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    fo = open(HERE / "paper_console.txt", "w", encoding="utf-8")
    fe = open(HERE / "paper_err.txt", "w", encoding="utf-8")
    p = subprocess.Popen([PY, "gap_fade_auto.py", "paper"], cwd=str(HERE),
                         stdout=fo, stderr=fe, creationflags=flags, env=ENV)
    for _ in range(20):
        time.sleep(1)
        if p.poll() is not None:
            # the reason is usually on stdout, not stderr: the window guard prints
            # there (measured 2026-10-30 14:55, rc=0 with the reason in stdout only).
            txt = ""
            for name in ("paper_console.txt", "paper_err.txt"):
                try:
                    txt += (HERE / name).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass
            return None, "process exited rc=%s: %s" % (p.returncode, txt.strip()[-300:])
        if today_log() is not None:
            return p, "pid %d, log %s started" % (p.pid, today_log().name)
    if p.poll() is None:
        return p, "pid %d alive but no log file yet - check paper_err.txt" % p.pid
    return None, "process died"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--session-check", action="store_true")
    a = ap.parse_args()
    if a.session_check:
        return session_check()

    now = datetime.now()
    steps = []

    def note(name, ok, detail):
        steps.append({"step": name, "ok": bool(ok), "detail": str(detail)})
        print("  %s %s: %s" % ("OK  " if ok else "FAIL", name, detail))

    print("GAP FADE v13 MORNING CHAIN  %s" % now.strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 78)
    verdict = why = None
    s = {"today": now.date().isoformat(), "session": None, "prev_session": None}

    code, out, _ = sh(["morning_chain.py", "--session-check"], 120)
    try:
        s = json.loads([l for l in out.splitlines() if l.startswith("{")][-1])
    except Exception:
        s["error"] = out.strip()[-200:]

    if s.get("session") is None:
        note("trading calendar", False, s.get("error", "unreadable"))
        verdict, why = "BLOCKED", ("the session calendar did not answer. Being quiet here "
                                   "would cost a whole trading day, so it is a block.")
    elif not s["session"]:
        note("trading calendar", True, "%s is not a session" % s["today"])
        verdict, why = "SKIP", "not a trading day"
    elif ran_today(MARK_PAPER) and not a.force:
        note("trading calendar", True, "%s is a session" % s["today"])
        note("already done", True, "today's log already carries " + MARK_PAPER)
        verdict, why = "SKIP", "paper already ran today; the 13:32 job reports it"
    else:
        note("trading calendar", True, "%s is a session, previous session %s"
             % (s["today"], s.get("prev_session")))
        t1 = s.get("prev_session")

        code, out, secs = sh(["v13_factors.py", "--refresh"], 300)
        ends = find(out, "panel ends")
        fresh = bool(t1) and t1 in ends
        note("factor panel", code == 0 and fresh,
             "%s (%.0fs)" % (ends or out.strip()[-200:], secs))
        if not fresh:
            verdict, why = "BLOCKED", (
                "the factor panel is behind %s. finlab publishes daily bars some time after "
                "the close, so this is a real block and not a bug: the model may not score "
                "on a panel that is missing the previous session." % t1)
        else:
            code2, out2, secs = sh(["refresh_executability_panels.py"], 240)
            got = " | ".join(l.strip() for l in out2.splitlines() if l.startswith("OK"))
            note("day-trade executability panels", code2 == 0,
                 "%s (%.0fs)" % (got or out2.strip()[-200:], secs))
            if code2 != 0:
                print("        the chain continues: live will use the previous panels and "
                      "must be labelled STALE, not 'nothing is blocked'")

            code3, out3, secs = sh(["preflight.py"], 240)
            note("preflight", code3 == 0,
                 "%s (%.0fs)" % (find(out3, "checks |") or out3.strip()[-200:], secs))
            for l in out3.splitlines():
                if l.strip().startswith(("[FAIL]", "[WARN]")):
                    print("        %s" % l.strip())

            code4, out4, _ = sh(["test_paper_path.py"], 300)
            note("paper-path suites", code4 == 0, score(out4))
            code5, out5, _ = sh(["_test_daytrade.py"], 180)
            note("day-trade filter suite", code5 == 0, score(out5))

            bad = [n["step"] for n in steps
                   if not n["ok"] and n["step"] != "day-trade executability panels"]
            if bad:
                verdict, why = "BLOCKED", "a gate failed: " + ", ".join(bad)

    if verdict is None:
        late = now.strftime("%H:%M") > "09:00"
        window = PAPER_FIRST <= now.strftime("%H:%M") <= PAPER_LAST
        if a.no_launch:
            verdict, why = "READY", "every gate passed; launch skipped by --no-launch"
        elif not window:
            verdict, why = "BLOCKED", ("every gate passed but the paper window is %s-%s and "
                                       "it is now %s" % (PAPER_FIRST, PAPER_LAST,
                                                         now.strftime("%H:%M")))
        else:
            p, detail = launch_paper()
            note("launch paper", p is not None, detail + (
                " | LATE START: opening slippage will be measured as a late start, not as "
                "the real value" if late else ""))
            if p is not None:
                verdict, why = "LAUNCHED", "paper is running; the 13:32 job reads the report"
            else:
                verdict, why = "BLOCKED", "paper would not start: " + detail

    print("-" * 78)
    print("VERDICT: %s - %s" % (verdict, why))
    print("  RISK1 measured today: %s" % ("yes" if ran_today(MARK_RISK1) else "no"))
    LOGS.mkdir(exist_ok=True)
    rp = LOGS / ("morning_chain_%s.json" % date.today().strftime("%Y%m%d"))
    rp.write_text(json.dumps({"at": now.isoformat(timespec="seconds"), "verdict": verdict,
                              "why": why, "session": s, "steps": steps},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    print("  written %s" % rp)
    return 0 if verdict in ("SKIP", "LAUNCHED", "READY") else 1


if __name__ == "__main__":
    sys.exit(main())
