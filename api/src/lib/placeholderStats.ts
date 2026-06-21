// Hardcoded placeholder stats applied uniformly to every player in lineup responses
// until Phase 6 wires up real pre-lock stats queries.

export const PLACEHOLDER_BATTER_STATS = {
  vs_lhp: {
    pa: 150, singles: 28, doubles: 9, triples: 1,
    hr: 6, bb: 16, hbp: 2, k: 35, go: 38, fo: 29,
  },
  vs_rhp: {
    pa: 300, singles: 57, doubles: 19, triples: 2,
    hr: 12, bb: 32, hbp: 3, k: 70, go: 77, fo: 59,
  },
};

// Derived from bf=650, singles=110, doubles=28, triples=3, hr=22, bb=65, hbp=8
// OBP allowed = (singles+doubles+triples+hr+bb+hbp) / bf = 236/650 ≈ 0.363
// SLG allowed = (singles + 2d + 3t + 4hr) / (bf−bb−hbp) = 263/577 ≈ 0.456
export const PLACEHOLDER_PITCHER_STATS = {
  obp_allowed: 0.363,
  slg_allowed: 0.456,
};
