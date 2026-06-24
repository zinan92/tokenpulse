"""Daily local card snapshots.

Renders both public share-card formats from one data snapshot and stores them
under `.card-out/daily-snapshots/YYYY-MM-DD/`. The launch agent runs this at
12:00 Beijing time; the script itself is also safe to run manually.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import badges
import card

ROOT = Path(__file__).resolve().parent
OUT_ROOT = ROOT / ".card-out" / "daily-snapshots"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
SNAPSHOT_TIME = "12:00"


def _beijing_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(BEIJING_TZ)
    if now.tzinfo is None:
        return now.replace(tzinfo=BEIJING_TZ)
    return now.astimezone(BEIJING_TZ)


def snapshot_cards(out_root: str | Path = OUT_ROOT, now: datetime | None = None,
                   force: bool = False) -> dict:
    """Render monthly + single-day-record cards into the daily snapshot folder."""
    bj_now = _beijing_now(now)
    day = bj_now.strftime("%Y-%m-%d")
    stamp = f"{day}-1200"
    out_dir = Path(out_root).expanduser() / day
    monthly_path = out_dir / f"tokenpulse-card-{stamp}.png"
    record_path = out_dir / f"tokenpulse-record-card-{stamp}.png"
    manifest_path = out_dir / "manifest.json"

    if not force and monthly_path.exists() and record_path.exists() and manifest_path.exists():
        return {
            "ok": True,
            "skipped": True,
            "reason": "already exists",
            "date": day,
            "timezone": "Asia/Shanghai",
            "scheduled_time": SNAPSHOT_TIME,
            "cards": {"monthly": str(monthly_path), "record": str(record_path)},
            "manifest": str(manifest_path),
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    data = badges.card_data(now=bj_now)
    cards: dict[str, str] = {}
    errors: list[str] = []

    try:
        cards["monthly"] = card.render(data, out_path=str(monthly_path), date_str=day)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"monthly card: {exc}")
    try:
        cards["record"] = card.render_record(data, out_path=str(record_path), date_str=day)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"record card: {exc}")

    manifest = {
        "ok": not errors,
        "skipped": False,
        "generated_at_beijing": bj_now.isoformat(),
        "date": day,
        "timezone": "Asia/Shanghai",
        "scheduled_time": SNAPSHOT_TIME,
        "cards": cards,
        "record_day": data.get("record_day"),
        "monthly_tokens": data.get("monthly_tokens"),
        "tier": data.get("tier"),
        "errors": errors,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**manifest, "manifest": str(manifest_path)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render daily TokenPulse card snapshots.")
    ap.add_argument("--out-dir", default=str(OUT_ROOT), help="snapshot output root")
    ap.add_argument("--force", action="store_true", help="overwrite today's snapshot")
    ap.add_argument("--json", action="store_true", help="print machine-readable result")
    args = ap.parse_args(argv)

    result = snapshot_cards(args.out_dir, force=args.force)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = "skipped" if result.get("skipped") else ("wrote" if result.get("ok") else "wrote with errors")
        print(f"[snapshot] {status} {result['date']} ({result['timezone']} {result['scheduled_time']})")
        for kind, path in result.get("cards", {}).items():
            print(f"[snapshot] {kind}: {path}")
        if result.get("manifest"):
            print(f"[snapshot] manifest: {result['manifest']}")
        for err in result.get("errors", []):
            print(f"[snapshot] error: {err}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
