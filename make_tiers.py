import argparse, pandas as pd
from pathlib import Path

OFF_POS = {"QB","RB","WR","TE"}

def make_pos_tiers(df_pos: pd.DataFrame, gap: float) -> pd.DataFrame:
    tiers, tier, prev = [], 1, None
    for _, row in df_pos.iterrows():
        v = float(row["VORP"])
        if prev is not None and (prev - v) > gap:
            tier += 1
        tiers.append(tier); prev = v
    out = df_pos.copy(); out["Tier"] = tiers
    return out

def main():
    ap = argparse.ArgumentParser(description="Create tiers from VORP using a gap rule per position.")
    ap.add_argument("vorp_csv")
    ap.add_argument("--gap", type=float, default=10.0, help="New tier when VORP drop > gap (default 10)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    p = Path(args.vorp_csv)
    out_path = Path(args.out) if args.out else (p.parent / "tiers_output.csv")

    df = pd.read_csv(p)
    need = {"player_name","team","pos","fantasy_points","VORP"}
    if not need.issubset(df.columns): raise ValueError(f"Missing columns: {sorted(need - set(df.columns))}")

    df["pos"] = df["pos"].astype(str).str.upper().str.strip()
    df["VORP"] = pd.to_numeric(df["VORP"], errors="coerce").fillna(0.0)
    df = df[df["pos"].isin(OFF_POS)].copy()

    result = []
    for pos in sorted(OFF_POS):
        sub = df[df["pos"] == pos].sort_values("VORP", ascending=False)
        if not sub.empty: result.append(make_pos_tiers(sub, args.gap))
    tiers = pd.concat(result, ignore_index=True) if result else df.copy()
    tiers = tiers.sort_values(["pos","Tier","VORP"], ascending=[True, True, False]).reset_index(drop=True)
    tiers.to_csv(out_path, index=False)
    print(f"Wrote tiers to: {out_path}")
    for pos in ["QB","RB","WR","TE"]:
        k = tiers[tiers["pos"]==pos]
        if not k.empty:
            print(f"\n{pos} tiers preview:")
            print(k[["player_name","Tier","VORP"]].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
