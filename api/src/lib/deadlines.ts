// Deadline offsets from sim_scheduled_at — see build-plan.md for the source of truth.
export interface Deadlines {
  road_sp: string;
  home_sp: string;
  batting_order: string;
}

export function computeDeadlines(simScheduledAt: Date): Deadlines {
  // NOTE: ET clock times are hardcoded as fixed UTC hours assuming EDT (UTC−4).
  // This is correct for the entire MLB season (regular season + playoffs fall within
  // US DST, mid-March to early November), so in-season deadlines always land in EDT.
  // A deadline computed for a sim near the DST boundary could be off by one hour in ET;
  // if support for out-of-DST dates is ever needed, convert via a real ET timezone.
  // Road SP: sim date − 8 days, 22:00 UTC (= 6 PM ET)
  const roadSp = new Date(simScheduledAt);
  roadSp.setUTCDate(roadSp.getUTCDate() - 8);
  roadSp.setUTCHours(22, 0, 0, 0);

  // Home SP: same calendar day in ET as road SP, 3 h later = next UTC day at 01:00
  const homeSp = new Date(roadSp);
  homeSp.setUTCDate(homeSp.getUTCDate() + 1);
  homeSp.setUTCHours(1, 0, 0, 0);

  // Batting order: sim date − 7 days, 16:00 UTC (= 12 PM ET)
  const battingOrder = new Date(simScheduledAt);
  battingOrder.setUTCDate(battingOrder.getUTCDate() - 7);
  battingOrder.setUTCHours(16, 0, 0, 0);

  return {
    road_sp: roadSp.toISOString(),
    home_sp: homeSp.toISOString(),
    batting_order: battingOrder.toISOString(),
  };
}
