"""
Unit tests for sim/src/stats.py.
Run with: pytest sim/tests/
"""

import pytest
from stats import (
    MLB_AVG,
    LeagueAverages,
    pa_probabilities,
    sb_attempt_rate,
    sb_success_rate,
    batter_pa_cap,
    pitcher_bf_cap,
    pitcher_pitch_cap,
    _log5,
    _blend,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sum_probs(d: dict) -> float:
    return sum(d.values())

OUTCOMES = ('bb', 'hbp', 'k', 'single', 'double', 'triple', 'hr', 'go', 'fo')

def _minimal_batter(pa: int = 100) -> dict:
    """A batter whose per-PA rates exactly match MLB_AVG."""
    return {
        'pa': pa,
        'vs_rhp_pa': pa,
        **{f'vs_rhp_{k}': round(MLB_AVG[k] * pa) for k in OUTCOMES if k != 'single'},
        'vs_rhp_singles': round(MLB_AVG['single'] * pa),
        'vs_rhp_bb': round(MLB_AVG['bb'] * pa),
        'vs_rhp_hbp': round(MLB_AVG['hbp'] * pa),
        'vs_rhp_k': round(MLB_AVG['k'] * pa),
        'vs_rhp_doubles': round(MLB_AVG['double'] * pa),
        'vs_rhp_triples': round(MLB_AVG['triple'] * pa),
        'vs_rhp_hr': round(MLB_AVG['hr'] * pa),
        'vs_rhp_go': round(MLB_AVG['go'] * pa),
        'vs_rhp_fo': round(MLB_AVG['fo'] * pa),
    }

def _minimal_pitcher(bf: int = 100) -> dict:
    """A pitcher whose per-BF rates exactly match MLB_AVG."""
    return {
        'bf': bf,
        'vs_rhb_bf': bf,
        'vs_rhb_bb': round(MLB_AVG['bb'] * bf),
        'vs_rhb_hbp': round(MLB_AVG['hbp'] * bf),
        'vs_rhb_k': round(MLB_AVG['k'] * bf),
        'vs_rhb_singles': round(MLB_AVG['single'] * bf),
        'vs_rhb_doubles': round(MLB_AVG['double'] * bf),
        'vs_rhb_triples': round(MLB_AVG['triple'] * bf),
        'vs_rhb_hr': round(MLB_AVG['hr'] * bf),
        'vs_rhb_go': round(MLB_AVG['go'] * bf),
        'vs_rhb_fo': round(MLB_AVG['fo'] * bf),
    }


# ── LeagueAverages ────────────────────────────────────────────────────────────

class TestLeagueAverages:
    def test_mlb_fallback_sums_to_one(self):
        lg = LeagueAverages.from_mlb_fallback()
        total = lg.bb + lg.hbp + lg.k + lg.single + lg.double + lg.triple + lg.hr + lg.go + lg.fo
        assert abs(total - 1.0) < 1e-9

    def test_mlb_fallback_matches_constants(self):
        lg = LeagueAverages.from_mlb_fallback()
        assert lg.bb == MLB_AVG['bb']
        assert lg.hr == MLB_AVG['hr']


# ── _log5 ─────────────────────────────────────────────────────────────────────

class TestLog5:
    def test_league_average_in_league_average_out(self):
        """log5(lg, lg, lg) == lg for any valid lg."""
        for lg in (0.1, 0.25, 0.5):
            assert abs(_log5(lg, lg, lg) - lg) < 1e-9

    def test_above_average_batter_and_pitcher_raises_rate(self):
        lg = 0.08
        assert _log5(0.12, 0.12, lg) > lg

    def test_below_average_batter_and_pitcher_lowers_rate(self):
        lg = 0.08
        assert _log5(0.04, 0.04, lg) < lg

    def test_degenerate_lg_zero_returns_batter_rate(self):
        assert _log5(0.1, 0.2, 0.0) == 0.1

    def test_degenerate_lg_one_returns_batter_rate(self):
        assert _log5(0.1, 0.2, 1.0) == 0.1


# ── _blend ────────────────────────────────────────────────────────────────────

class TestBlend:
    def test_result_sums_to_one(self):
        result = _blend(MLB_AVG.copy(), MLB_AVG.copy(), 50, 0.8)
        assert abs(_sum_probs(result) - 1.0) < 1e-9

    def test_large_sample_weight_dominates(self):
        """With sample=1000 the player rate dominates over league."""
        # Skew toward HR/K, away from GO/FO — a genuinely different profile
        player = MLB_AVG.copy()
        player['hr'] *= 3
        player['k']  *= 2
        player['go'] *= 0.4
        player['fo'] *= 0.4
        total = sum(player.values())
        player = {k: v / total for k, v in player.items()}
        result = _blend(player, MLB_AVG.copy(), 1000, 0.9)
        # Result should be closer to player than to league for the skewed outcomes
        for k in ('hr', 'k', 'go', 'fo'):
            diff_player = abs(result[k] - player[k])
            diff_league = abs(result[k] - MLB_AVG[k])
            assert diff_player < diff_league

    def test_zero_sample_clamps_to_league(self):
        player = {k: 0.0 for k in MLB_AVG}
        player['bb'] = 1.0
        result = _blend(player, MLB_AVG.copy(), 0, 0.8)
        # weight = min(0.8, 0/(0+50)) = 0 → pure league
        assert abs(result['bb'] - MLB_AVG['bb']) < 1e-9


# ── pa_probabilities ──────────────────────────────────────────────────────────

class TestPaProbabilities:
    def setup_method(self):
        self.lg = LeagueAverages.from_mlb_fallback()

    def test_probs_sum_to_one_with_real_stats(self):
        b = _minimal_batter(200)
        p = _minimal_pitcher(200)
        probs = pa_probabilities(b, p, 'R', 'R', self.lg)
        assert abs(_sum_probs(probs) - 1.0) < 1e-9

    def test_probs_sum_to_one_with_none_stats(self):
        probs = pa_probabilities(None, None, 'R', 'R', self.lg)
        assert abs(_sum_probs(probs) - 1.0) < 1e-9

    def test_all_outcomes_present(self):
        probs = pa_probabilities(None, None, 'R', 'R', self.lg)
        assert set(probs.keys()) == set(OUTCOMES)

    def test_all_probs_non_negative(self):
        b = _minimal_batter(200)
        p = _minimal_pitcher(200)
        probs = pa_probabilities(b, p, 'R', 'R', self.lg)
        assert all(v >= 0 for v in probs.values())

    def test_high_hr_batter_raises_hr_prob(self):
        """A batter who hits twice as many HRs vs RHP should raise the HR probability."""
        b = _minimal_batter(200)
        b['vs_rhp_hr'] = round(MLB_AVG['hr'] * 200 * 2)
        p = _minimal_pitcher(200)
        probs_avg = pa_probabilities(_minimal_batter(200), p, 'R', 'R', self.lg)
        probs_hr  = pa_probabilities(b, p, 'R', 'R', self.lg)
        assert probs_hr['hr'] > probs_avg['hr']

    def test_small_sample_batter_falls_back_toward_mlb(self):
        """Batter with <20 PA vs RHP but ≥20 season PA blends with season rates."""
        b = {
            'pa': 100,
            'vs_rhp_pa': 5,  # too small → blend
            'vs_rhp_bb': 1, 'vs_rhp_hbp': 0, 'vs_rhp_k': 1,
            'vs_rhp_singles': 1, 'vs_rhp_doubles': 0, 'vs_rhp_triples': 0,
            'vs_rhp_hr': 0, 'vs_rhp_go': 1, 'vs_rhp_fo': 1,
            # season totals (MLB-average rates)
            'bb': 8, 'hbp': 1, 'k': 22, 'singles': 15,
            'doubles': 4, 'triples': 0, 'hr': 3, 'go': 23, 'fo': 22,
        }
        probs = pa_probabilities(b, None, 'R', 'R', self.lg)
        assert abs(_sum_probs(probs) - 1.0) < 1e-9


# ── batter_pa_cap ─────────────────────────────────────────────────────────────

class TestBatterPaCap:
    def test_none_returns_unlimited(self):
        assert batter_pa_cap(None) == 999

    def test_zero_pa_benched(self):
        assert batter_pa_cap({'pa': 0}) == 0

    def test_boundary_1_to_3(self):
        for pa in (1, 2, 3):
            assert batter_pa_cap({'pa': pa}) == 1

    def test_boundary_4_to_6(self):
        for pa in (4, 5, 6):
            assert batter_pa_cap({'pa': pa}) == 2

    def test_boundary_7_to_9(self):
        for pa in (7, 8, 9):
            assert batter_pa_cap({'pa': pa}) == 3

    def test_10_plus_unlimited(self):
        for pa in (10, 50, 162):
            assert batter_pa_cap({'pa': pa}) == 999


# ── pitcher_bf_cap / pitcher_pitch_cap ────────────────────────────────────────

class TestPitcherCaps:
    def test_bf_cap_none_returns_zero(self):
        assert pitcher_bf_cap(None) == 0

    def test_bf_cap_110_percent(self):
        assert pitcher_bf_cap({'bf': 100}) == 110

    def test_bf_cap_truncates(self):
        assert pitcher_bf_cap({'bf': 7}) == int(7 * 1.1)  # 7

    def test_pitch_cap_none_returns_zero(self):
        assert pitcher_pitch_cap(None) == 0

    def test_pitch_cap_110_percent(self):
        assert pitcher_pitch_cap({'pitches_thrown': 200}) == 220


# ── sb_attempt_rate / sb_success_rate ─────────────────────────────────────────

class TestSbRates:
    def test_attempt_rate_none_returns_zero(self):
        assert sb_attempt_rate(None) == 0.0

    def test_attempt_rate_no_opportunities(self):
        assert sb_attempt_rate({'sb': 5, 'cs': 1, 'singles': 0, 'bb': 0, 'hbp': 0}) == 0.0

    def test_attempt_rate_capped_at_half(self):
        # 10 attempts on 10 opportunities would be 1.0, but capped at 0.5
        assert sb_attempt_rate({'sb': 8, 'cs': 2, 'singles': 10, 'bb': 0, 'hbp': 0}) == 0.5

    def test_attempt_rate_normal(self):
        rate = sb_attempt_rate({'sb': 3, 'cs': 1, 'singles': 20, 'bb': 10, 'hbp': 0})
        assert abs(rate - 4 / 30) < 1e-9

    def test_success_rate_none_returns_mlb_average(self):
        assert sb_success_rate(None) == 0.70

    def test_success_rate_no_attempts_returns_mlb_average(self):
        assert sb_success_rate({'sb': 0, 'cs': 0}) == 0.70

    def test_success_rate_computed(self):
        assert abs(sb_success_rate({'sb': 3, 'cs': 1}) - 0.75) < 1e-9
