"""
Plate-appearance outcome probabilities using the log5 method.

Outcomes (mutually exclusive, sum to 1.0):
  bb, hbp, k, single, double, triple, hr, go, fo

The log5 formula combines batter and pitcher rates against a league-average baseline:
  P(event) = (b * p / lg) / (b * p / lg + (1-b) * (1-p) / (1-lg))
where b = batter rate, p = pitcher rate, lg = league average rate.
"""

from dataclasses import dataclass

# MLB historical averages (per PA) — fallback when no in-season data exists
MLB_AVG = {
    'bb':     0.0847,
    'hbp':    0.0103,
    'k':      0.2228,
    'single': 0.1491,
    'double': 0.0443,
    'triple': 0.0047,
    'hr':     0.0340,
    'go':     0.2300,
    'fo':     0.2201,
}


@dataclass
class LeagueAverages:
    bb: float
    hbp: float
    k: float
    single: float
    double: float
    triple: float
    hr: float
    go: float
    fo: float

    @classmethod
    def from_mlb_fallback(cls) -> 'LeagueAverages':
        return cls(**MLB_AVG)

    @classmethod
    def from_db_rows(cls, batter_agg: dict, pitcher_agg: dict) -> 'LeagueAverages':
        """Build averages from aggregated DB stats.

        Uses batter aggregate for batter-side outcomes and pitcher aggregate for
        pitcher-side; then averages them as an approximation of the true league mean.
        """
        def _rates(row: dict, denom_key: str) -> dict:
            denom = row[denom_key]
            if denom == 0:
                return None
            return {
                'bb':     row['bb'] / denom,
                'hbp':    row['hbp'] / denom,
                'k':      row['k'] / denom,
                'single': row['singles'] / denom,
                'double': row['doubles'] / denom,
                'triple': row['triples'] / denom,
                'hr':     row['hr'] / denom,
                'go':     row['go'] / denom,
                'fo':     row['fo'] / denom,
            }

        br = _rates(batter_agg, 'pa')
        pr = _rates(pitcher_agg, 'bf')
        if br is None or pr is None:
            return cls.from_mlb_fallback()

        keys = ('bb', 'hbp', 'k', 'single', 'double', 'triple', 'hr', 'go', 'fo')
        avg = {k: (br[k] + pr[k]) / 2 for k in keys}
        total = sum(avg.values())
        if total == 0:
            return cls.from_mlb_fallback()
        # Renormalize
        avg = {k: v / total for k, v in avg.items()}
        return cls(**avg)


def _batter_rates(stats: dict | None, pitcher_throws: str) -> dict[str, float]:
    """Per-PA rates for a batter against a given pitcher handedness."""
    if stats is None:
        return MLB_AVG.copy()

    prefix = 'vs_lhp_' if pitcher_throws == 'L' else 'vs_rhp_'
    pa = stats.get(prefix + 'pa', 0)

    if pa < 20:
        # Too small: blend 80/20 toward MLB average
        season_pa = stats.get('pa', 0)
        season_rates = _rates_from_stats(stats, 'pa', '', season_pa)
        if season_pa >= 20:
            return _blend(season_rates, MLB_AVG, season_pa, weight=0.8)
        return MLB_AVG.copy()

    return _rates_from_stats(stats, prefix + 'pa', prefix, pa)


def _pitcher_rates(stats: dict | None, batter_bats: str) -> dict[str, float]:
    """Per-BF rates for a pitcher against a given batter handedness."""
    if stats is None:
        return MLB_AVG.copy()

    prefix = 'vs_lhb_' if batter_bats == 'L' else 'vs_rhb_'
    bf = stats.get(prefix + 'bf', 0)

    if bf < 20:
        season_bf = stats.get('bf', 0)
        season_rates = _rates_from_stats(stats, 'bf', '', season_bf)
        if season_bf >= 20:
            return _blend(season_rates, MLB_AVG, season_bf, weight=0.8)
        return MLB_AVG.copy()

    return _rates_from_stats(stats, prefix + 'bf', prefix, bf)


def _rates_from_stats(stats: dict, denom_key: str, prefix: str, denom: int) -> dict[str, float]:
    if denom == 0:
        return MLB_AVG.copy()
    raw = {
        'bb':     stats.get(prefix + 'bb', 0) / denom,
        'hbp':    stats.get(prefix + 'hbp', 0) / denom,
        'k':      stats.get(prefix + 'k', 0) / denom,
        'single': stats.get(prefix + 'singles', 0) / denom,
        'double': stats.get(prefix + 'doubles', 0) / denom,
        'triple': stats.get(prefix + 'triples', 0) / denom,
        'hr':     stats.get(prefix + 'hr', 0) / denom,
        'go':     stats.get(prefix + 'go', 0) / denom,
        'fo':     stats.get(prefix + 'fo', 0) / denom,
    }
    total = sum(raw.values())
    if total == 0:
        return MLB_AVG.copy()
    return {k: v / total for k, v in raw.items()}


def _blend(player: dict[str, float], league: dict[str, float], sample: int, weight: float) -> dict[str, float]:
    """Blend player rates toward league average based on sample size."""
    w = min(weight, sample / (sample + 50))
    result = {k: w * player[k] + (1 - w) * league[k] for k in player}
    total = sum(result.values())
    return {k: v / total for k, v in result.items()} if total > 0 else league.copy()


def _log5(b: float, p: float, lg: float) -> float:
    """log5 combination of batter rate b, pitcher rate p, league average lg."""
    if lg <= 0 or lg >= 1:
        return b
    num = b * p / lg
    denom = num + (1 - b) * (1 - p) / (1 - lg)
    return num / denom if denom > 0 else lg


def pa_probabilities(
    batter_stats: dict | None,
    pitcher_stats: dict | None,
    batter_bats: str,
    pitcher_throws: str,
    league: LeagueAverages,
) -> dict[str, float]:
    """Return a normalized dict of PA outcome probabilities."""
    br = _batter_rates(batter_stats, pitcher_throws)
    pr = _pitcher_rates(pitcher_stats, batter_bats)
    lg = {
        'bb':     league.bb,
        'hbp':    league.hbp,
        'k':      league.k,
        'single': league.single,
        'double': league.double,
        'triple': league.triple,
        'hr':     league.hr,
        'go':     league.go,
        'fo':     league.fo,
    }

    combined = {outcome: _log5(br[outcome], pr[outcome], lg[outcome]) for outcome in lg}
    total = sum(combined.values())
    if total <= 0:
        return MLB_AVG.copy()
    return {k: v / total for k, v in combined.items()}


def sb_attempt_rate(batter_stats: dict | None) -> float:
    """Estimated probability that a batter attempts a steal when on 1st or 2nd."""
    if batter_stats is None:
        return 0.0
    sb = batter_stats.get('sb', 0)
    cs = batter_stats.get('cs', 0)
    opps = (
        batter_stats.get('singles', 0)
        + batter_stats.get('bb', 0)
        + batter_stats.get('hbp', 0)
    )
    if opps == 0:
        return 0.0
    attempts = sb + cs
    # Raw attempt rate per opportunity, capped at 0.5 to avoid absurd values
    return min(attempts / opps, 0.5)


def sb_success_rate(batter_stats: dict | None) -> float:
    """Historical steal success rate for the batter."""
    if batter_stats is None:
        return 0.70  # MLB average
    sb = batter_stats.get('sb', 0)
    cs = batter_stats.get('cs', 0)
    total = sb + cs
    if total == 0:
        return 0.70
    return sb / total


def batter_pa_cap(batter_stats: dict | None) -> int:
    """Maximum PA allowed based on pre-lock season PA count. 0 = benched."""
    if batter_stats is None:
        return 999  # no stats record = early season / not yet ingested → unlimited
    pa = batter_stats.get('pa', 0)
    if pa == 0:
        return 0
    if pa <= 3:
        return 1
    if pa <= 6:
        return 2
    if pa <= 9:
        return 3
    return 999  # unlimited


def pitcher_bf_cap(pitcher_stats: dict | None) -> int:
    """110% of pre-lock BF as hard cap."""
    if pitcher_stats is None:
        return 0
    return int(pitcher_stats.get('bf', 0) * 1.1)


def pitcher_pitch_cap(pitcher_stats: dict | None) -> int:
    """110% of pre-lock pitches_thrown as hard cap."""
    if pitcher_stats is None:
        return 0
    return int(pitcher_stats.get('pitches_thrown', 0) * 1.1)
