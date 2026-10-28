# -*- coding: utf-8 -*-
"""Re-classify the 2026-10-28 evidence with the corrected report. No market, no
orders: it replays the stored exec_stats through the new _paper_report so the
two-axis verdict can be compared against what the old code printed."""
import json, sys, logging, tempfile, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
import gap_fade_auto as G

old = json.loads(Path("trading_logs/paper_report_20261028.json").read_text(encoding="utf-8"))

t = G.GapFadePaperTrader.__new__(G.GapFadePaperTrader)
t.config = G.Config()
t.config.log_dir = tempfile.mkdtemp()
lg = logging.getLogger("reclass")
lg.handlers = [logging.StreamHandler(sys.stdout)]
lg.setLevel(logging.INFO)
t.log = lg
t.closed_trades = old["trades"]
t._smart_reports = []
t.exec_stats = {"orders": old["orders"], "entry_slippage": old["entry_slippage"]}
t._paper_report()

new = json.loads((Path(t.config.log_dir) / sorted(Path(t.config.log_dir).glob("paper_report_*.json"))[0].name).read_text(encoding="utf-8"))
print()
print("OLD checks :", json.dumps(old["checks"], ensure_ascii=False))
print("NEW checks :", json.dumps(new["checks"], ensure_ascii=False))
print("NEW axis   :", new["blocking_axis"])
print("NEW account:", json.dumps(new["blockers_account"], ensure_ascii=False))
print("NEW tech   :", json.dumps(new["blockers_technical"], ensure_ascii=False))
print("NEW unmeas :", json.dumps(new["unmeasurable_via_account"], ensure_ascii=False))
