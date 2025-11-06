import argparse, pandas as pd
from pathlib import Path
from datetime import datetime

def normalize_names(s):
    return s.astype(str).str.strip().str.lower()

def main():
    ap = argparse.ArgumentParser(description="Remove drafted players from your board (case-insensitive).")
    ap.add_argument("board_csv", help="Current board CSV (start with tiers_output.csv or draft_board.csv)")
    ap.add_argument("--names", help='Comma-separated player names to remove, e.g. "Josh Allen,Jalen Hurts"', default="")
    ap.add_argument("--file", help="Text file with one player name per line (optional)", default=None)
    ap.add_argument("--out", help="Output board CSV (default overwrites draft_board.csv or creates it)", default=None)
    ap.add_argument("--log", help="Picks log CSV (default picks_log.csv)", default="picks_log.csv")
    args = ap.parse_args()

    board_path = Path(args.board_csv)
    if not board_path.exists():
        raise FileNotFoundError(f"{board_path} not found")

    df = pd.read_csv(board_path)

    # Collect names to remove
    to_remove = []
    if args.names:
        to_remove += [n.strip() for n in args.names.split(",") if n.strip()]
    if args.file:
        with open(args.file, "r") as f:
            to_remove += [line.strip() for line in f if line.strip()]
    if not to_remove:
        print("No names provided; nothing to remove.")
        return

    # Normalize
    df["_norm_name"] = normalize_names(df["player_name"])
    norm_remove = [n.lower().strip() for n in to_remove]

    # Split found / not found
    found_mask = df["_norm_name"].isin(norm_remove)
    removed = df[found_mask].copy()
    remaining = df[~found_mask].drop(columns=["_norm_name"])

    # Report
    missing = [n for n in norm_remove if n not in set(df["_norm_name"])]
    if not removed.empty:
        print("Removed:")
        print(removed[["player_name","team","pos","Tier","VORP"]].to_string(index=False))
    if missing:
        print("\nNot found (check spelling/csv):", ", ".join(missing))

    # Decide output board name
    if args.out:
        out_path = Path(args.out)
    else:
        # Use/overwrite a rolling board named draft_board.csv next to the input
        out_path = board_path.parent / "draft_board.csv"

    remaining.to_csv(out_path, index=False)
    print(f"\nWrote updated board to: {out_path}")

    # Append to picks log
    if not removed.empty:
        log_path = Path(args.log)
        removed = removed.drop(columns=[c for c in removed.columns if c.startswith("_")])
        removed["removed_at"] = datetime.now().isoformat(timespec="seconds")
        if log_path.exists():
            prev = pd.read_csv(log_path)
            pd.concat([prev, removed], ignore_index=True).to_csv(log_path, index=False)
        else:
            removed.to_csv(log_path, index=False)
        print(f"Appended {len(removed)} pick(s) to log: {log_path}")

if __name__ == "__main__":
    main()
