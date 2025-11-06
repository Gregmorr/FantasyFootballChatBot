import argparse, pandas as pd
from pathlib import Path

OFF_POS = {"QB","RB","WR","TE"}

def main():
    ap = argparse.ArgumentParser(description="Suggest next picks using VORP, tiers, and roster needs.")
    ap.add_argument("tiers_csv")
    ap.add_argument("--start_qb", type=int, default=1)
    ap.add_argument("--start_rb", type=int, default=2)
    ap.add_argument("--start_wr", type=int, default=2)
    ap.add_argument("--start_te", type=int, default=1)
    ap.add_argument("--have_qb", type=int, default=0)
    ap.add_argument("--have_rb", type=int, default=0)
    ap.add_argument("--have_wr", type=int, default=0)
    ap.add_argument("--have_te", type=int, default=0)
    ap.add_argument("--top_n", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    p = Path(args.tiers_csv)
    out_path = Path(args.out) if args.out else (p.parent / "suggestions.csv")

    df = pd.read_csv(p)
    need = {"player_name","team","pos","fantasy_points","VORP","Tier"}
    if not need.issubset(df.columns): raise ValueError(f"Missing columns: {sorted(need - set(df.columns))}")

    df["pos"] = df["pos"].astype(str).str.upper().str.strip()
    df = df[df["pos"].isin(OFF_POS)].copy()
    df["VORP"] = pd.to_numeric(df["VORP"], errors="coerce").fillna(0.0)
    df["Tier"] = pd.to_numeric(df["Tier"], errors="coerce").fillna(999).astype(int)

    def tier_bonus(t): return 15 if t==1 else 10 if t==2 else 6 if t==3 else 3 if t==4 else 0
    df["TierBonus"] = df["Tier"].map(tier_bonus)

    starters = {"QB":args.start_qb, "RB":args.start_rb, "WR":args.start_wr, "TE":args.start_te}
    have = {"QB":args.have_qb, "RB":args.have_rb, "WR":args.have_wr, "TE":args.have_te}
    def need_penalty(pos): return -8.0 if have.get(pos,0) >= starters.get(pos,0) else 0.0
    df["NeedPenalty"] = df["pos"].map(need_penalty)

    df["SuggestScore"] = (df["VORP"] + df["TierBonus"] + df["NeedPenalty"]).round(2)
    out = df.sort_values(["SuggestScore","VORP"], ascending=[False, False]).head(args.top_n)
    out.to_csv(out_path, index=False)
    print(f"Wrote suggestions to: {out_path}")
    print(out[["player_name","team","pos","Tier","VORP","SuggestScore"]].to_string(index=False))

if __name__ == "__main__":
    main()
