import argparse
import pandas as pd
from pathlib import Path

OFF_POS = {"QB","RB","WR","TE"}

def normalize_pos(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.upper()

def get_replacement_points(df_pos: pd.DataFrame, index_1_based: int) -> float:
    """Return the fantasy_points at the given 1-based index for a position."""
    if df_pos.empty:
        return 0.0
    idx0 = max(0, min(len(df_pos) - 1, index_1_based - 1))
    return float(df_pos.iloc[idx0]["fantasy_points"])

def main():
    ap = argparse.ArgumentParser(description="Compute VORP with flexible league/lineup settings.")
    ap.add_argument("fp_csv", help="Path to fp_output.csv (must have fantasy_points)")
    # League size & starters
    ap.add_argument("--teams", type=int, default=12, help="Number of teams (default 12)")
    ap.add_argument("--start_qb", type=float, default=1, help="QB starters per team (default 1)")
    ap.add_argument("--start_rb", type=float, default=2, help="RB starters per team (default 2)")
    ap.add_argument("--start_wr", type=float, default=2, help="WR starters per team (default 2)")
    ap.add_argument("--start_te", type=float, default=1, help="TE starters per team (default 1)")
    # Optional direct replacement overrides (1-based ranks)
    ap.add_argument("--qb_rep", type=int, default=None, help="Override QB replacement rank (e.g., 12)")
    ap.add_argument("--rb_rep", type=int, default=None, help="Override RB replacement rank (e.g., 24)")
    ap.add_argument("--wr_rep", type=int, default=None, help="Override WR replacement rank (e.g., 24)")
    ap.add_argument("--te_rep", type=int, default=None, help="Override TE replacement rank (e.g., 12)")
    ap.add_argument("--out", default=None, help="Output CSV (default vorp_output.csv next to input)")
    args = ap.parse_args()

    fp_path = Path(args.fp_csv)
    out_path = Path(args.out) if args.out else (fp_path.parent / "vorp_output.csv")

    df = pd.read_csv(fp_path)
    needed = {"player_name","team","pos","fantasy_points"}
    miss = needed - set(df.columns)
    if miss:
        raise ValueError(f"Missing columns in {fp_path.name}: {sorted(miss)}")

    # Clean & sort
    df["fantasy_points"] = pd.to_numeric(df["fantasy_points"], errors="coerce").fillna(0.0)
    df["pos"] = normalize_pos(df["pos"])
    df = df[df["pos"].isin(OFF_POS)].copy()
    df = df.sort_values(["pos","fantasy_points"], ascending=[True, False])

    # Compute default replacement indices from league settings
    default_rep = {
        "QB": int(round(args.teams * args.start_qb)),
        "RB": int(round(args.teams * args.start_rb)),
        "WR": int(round(args.teams * args.start_wr)),
        "TE": int(round(args.teams * args.start_te)),
    }
    # Apply overrides if provided
    rep_index = {
        "QB": args.qb_rep if args.qb_rep is not None else default_rep["QB"],
        "RB": args.rb_rep if args.rb_rep is not None else default_rep["RB"],
        "WR": args.wr_rep if args.wr_rep is not None else default_rep["WR"],
        "TE": args.te_rep if args.te_rep is not None else default_rep["TE"],
    }

    # Compute replacement FP per position
    replacement_points = {}
    for p in ["QB","RB","WR","TE"]:
        sub = df[df["pos"] == p]
        replacement_points[p] = get_replacement_points(sub, rep_index[p])

    # VORP = player FP - replacement FP for that position
    df["replacement_fp"] = df["pos"].map(replacement_points)
    df["VORP"] = (df["fantasy_points"] - df["replacement_fp"]).round(2)

    out = df.sort_values(["VORP","fantasy_points"], ascending=[False, False]).reset_index(drop=True)
    out.to_csv(out_path, index=False)

    print(f"Wrote VORP rankings to: {out_path}")
    print("Replacement baselines used:", replacement_points, "(indices:", rep_index, ")")
    print(out[["player_name","team","pos","fantasy_points","VORP"]].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
