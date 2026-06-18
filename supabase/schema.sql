-- ============================================================
-- Fantasy Baseball Sim — Database Schema
-- Run this in the Supabase SQL Editor (Database → SQL Editor).
-- ============================================================


-- ============================================================
-- Enums
-- ============================================================

CREATE TYPE field_position AS ENUM ('C', '1B', '2B', 'SS', '3B', 'LF', 'CF', 'RF', 'DH', 'P', 'PH');
CREATE TYPE sim_status     AS ENUM ('scheduled', 'sim_pending', 'sim_complete', 'sim_error');
CREATE TYPE half_inning    AS ENUM ('top', 'bottom');
CREATE TYPE sim_event_type AS ENUM ('plate_appearance', 'pitching_change', 'substitution', 'stolen_base', 'caught_stealing', 'pickoff', 'error');
CREATE TYPE putout_type    AS ENUM ('force', 'tag', 'caught_off_base');


-- ============================================================
-- 1. Users, Leagues, and Teams
-- ============================================================

CREATE TABLE profiles (
  id           UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username     TEXT        NOT NULL UNIQUE,
  display_name TEXT        NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE leagues (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT        NOT NULL,
  commissioner_id UUID        NOT NULL REFERENCES profiles(id),
  season_year     INTEGER     NOT NULL,
  roster_size     INTEGER     NOT NULL DEFAULT 22,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE teams (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id  UUID        NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  manager_id UUID        NOT NULL REFERENCES profiles(id),
  name       TEXT        NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (league_id, manager_id)
);


-- ============================================================
-- 2. Players and Rosters
-- ============================================================

CREATE TABLE players (
  mlb_id     INTEGER     PRIMARY KEY,
  full_name  TEXT        NOT NULL,
  last_name  TEXT        NOT NULL,
  throws     CHAR(1)     NOT NULL CHECK (throws IN ('L', 'R')),
  bats       CHAR(1)     NOT NULL CHECK (bats IN ('L', 'R', 'S')),
  mlb_team   TEXT        NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE player_positions (
  player_id INTEGER        NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
  position  field_position NOT NULL,
  source    TEXT           NOT NULL CHECK (source IN ('api', 'derived')),
  PRIMARY KEY (player_id, position)
);

CREATE TABLE roster_players (
  team_id   UUID    NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  player_id INTEGER NOT NULL REFERENCES players(mlb_id),
  league_id UUID    NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  PRIMARY KEY (team_id, player_id),
  UNIQUE (league_id, player_id)
);


-- ============================================================
-- 3. Matchups and Lineups
-- ============================================================

CREATE TABLE matchups (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  league_id        UUID        NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
  week_number      INTEGER     NOT NULL,
  home_team_id     UUID        NOT NULL REFERENCES teams(id),
  road_team_id     UUID        NOT NULL REFERENCES teams(id),
  sim_scheduled_at TIMESTAMPTZ NOT NULL,
  sim_status       sim_status  NOT NULL DEFAULT 'scheduled'
);

CREATE TABLE lineups (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  matchup_id   UUID        NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
  team_id      UUID        NOT NULL REFERENCES teams(id),
  sp_player_id INTEGER     REFERENCES players(mlb_id),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (matchup_id, team_id)
);

CREATE TABLE lineup_batting_order (
  lineup_id        UUID           NOT NULL REFERENCES lineups(id) ON DELETE CASCADE,
  batting_position INTEGER        NOT NULL CHECK (batting_position BETWEEN 1 AND 9),
  player_id        INTEGER        NOT NULL REFERENCES players(mlb_id),
  field_position   field_position NOT NULL CHECK (field_position <> 'PH'),
  PRIMARY KEY (lineup_id, batting_position),
  UNIQUE (lineup_id, player_id),
  UNIQUE (lineup_id, field_position)
);


-- ============================================================
-- 4. Player Stats
-- ============================================================

CREATE TABLE batter_pre_lock_stats (
  player_id      INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
  sim_date       DATE    NOT NULL,
  -- Season totals (stored for convenience where we could derive them from the platoon splits)
  pa             INTEGER NOT NULL DEFAULT 0,
  singles        INTEGER NOT NULL DEFAULT 0,
  doubles        INTEGER NOT NULL DEFAULT 0,
  triples        INTEGER NOT NULL DEFAULT 0,
  hr             INTEGER NOT NULL DEFAULT 0,
  bb             INTEGER NOT NULL DEFAULT 0,
  hbp            INTEGER NOT NULL DEFAULT 0,
  k              INTEGER NOT NULL DEFAULT 0,
  go             INTEGER NOT NULL DEFAULT 0,
  fo             INTEGER NOT NULL DEFAULT 0,
  sb             INTEGER NOT NULL DEFAULT 0,
  cs             INTEGER NOT NULL DEFAULT 0,
  -- Platoon splits vs LHP (sb/cs excluded — sample too small to split)
  vs_lhp_pa      INTEGER NOT NULL DEFAULT 0,
  vs_lhp_singles INTEGER NOT NULL DEFAULT 0,
  vs_lhp_doubles INTEGER NOT NULL DEFAULT 0,
  vs_lhp_triples INTEGER NOT NULL DEFAULT 0,
  vs_lhp_hr      INTEGER NOT NULL DEFAULT 0,
  vs_lhp_bb      INTEGER NOT NULL DEFAULT 0,
  vs_lhp_hbp     INTEGER NOT NULL DEFAULT 0,
  vs_lhp_k       INTEGER NOT NULL DEFAULT 0,
  vs_lhp_go      INTEGER NOT NULL DEFAULT 0,
  vs_lhp_fo      INTEGER NOT NULL DEFAULT 0,
  -- Platoon splits vs RHP
  vs_rhp_pa      INTEGER NOT NULL DEFAULT 0,
  vs_rhp_singles INTEGER NOT NULL DEFAULT 0,
  vs_rhp_doubles INTEGER NOT NULL DEFAULT 0,
  vs_rhp_triples INTEGER NOT NULL DEFAULT 0,
  vs_rhp_hr      INTEGER NOT NULL DEFAULT 0,
  vs_rhp_bb      INTEGER NOT NULL DEFAULT 0,
  vs_rhp_hbp     INTEGER NOT NULL DEFAULT 0,
  vs_rhp_k       INTEGER NOT NULL DEFAULT 0,
  vs_rhp_go      INTEGER NOT NULL DEFAULT 0,
  vs_rhp_fo      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, sim_date)
);

CREATE TABLE batter_post_lock_stats (
  player_id INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
  sim_date  DATE    NOT NULL,
  pa        INTEGER NOT NULL DEFAULT 0,
  singles   INTEGER NOT NULL DEFAULT 0,
  doubles   INTEGER NOT NULL DEFAULT 0,
  triples   INTEGER NOT NULL DEFAULT 0,
  hr        INTEGER NOT NULL DEFAULT 0,
  bb        INTEGER NOT NULL DEFAULT 0,
  hbp       INTEGER NOT NULL DEFAULT 0,
  k         INTEGER NOT NULL DEFAULT 0,
  go        INTEGER NOT NULL DEFAULT 0,
  fo        INTEGER NOT NULL DEFAULT 0,
  sb        INTEGER NOT NULL DEFAULT 0,
  cs        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, sim_date)
);

CREATE TABLE pitcher_pre_lock_stats (
  player_id             INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
  sim_date              DATE    NOT NULL,
  -- Season totals (stored for convenience where we could derive them from the platoon splits)
  bf                    INTEGER NOT NULL DEFAULT 0,
  pitches_thrown        INTEGER NOT NULL DEFAULT 0,
  singles               INTEGER NOT NULL DEFAULT 0,
  doubles               INTEGER NOT NULL DEFAULT 0,
  triples               INTEGER NOT NULL DEFAULT 0,
  hr                    INTEGER NOT NULL DEFAULT 0,
  bb                    INTEGER NOT NULL DEFAULT 0,
  hbp                   INTEGER NOT NULL DEFAULT 0,
  k                     INTEGER NOT NULL DEFAULT 0,
  go                    INTEGER NOT NULL DEFAULT 0,
  fo                    INTEGER NOT NULL DEFAULT 0,
  po                    INTEGER NOT NULL DEFAULT 0,
  -- Platoon splits vs LHB (pitches_thrown and po excluded)
  vs_lhb_bf             INTEGER NOT NULL DEFAULT 0,
  vs_lhb_singles        INTEGER NOT NULL DEFAULT 0,
  vs_lhb_doubles        INTEGER NOT NULL DEFAULT 0,
  vs_lhb_triples        INTEGER NOT NULL DEFAULT 0,
  vs_lhb_hr             INTEGER NOT NULL DEFAULT 0,
  vs_lhb_bb             INTEGER NOT NULL DEFAULT 0,
  vs_lhb_hbp            INTEGER NOT NULL DEFAULT 0,
  vs_lhb_k              INTEGER NOT NULL DEFAULT 0,
  vs_lhb_go             INTEGER NOT NULL DEFAULT 0,
  vs_lhb_fo             INTEGER NOT NULL DEFAULT 0,
  -- Platoon splits vs RHB
  vs_rhb_bf             INTEGER NOT NULL DEFAULT 0,
  vs_rhb_singles        INTEGER NOT NULL DEFAULT 0,
  vs_rhb_doubles        INTEGER NOT NULL DEFAULT 0,
  vs_rhb_triples        INTEGER NOT NULL DEFAULT 0,
  vs_rhb_hr             INTEGER NOT NULL DEFAULT 0,
  vs_rhb_bb             INTEGER NOT NULL DEFAULT 0,
  vs_rhb_hbp            INTEGER NOT NULL DEFAULT 0,
  vs_rhb_k              INTEGER NOT NULL DEFAULT 0,
  vs_rhb_go             INTEGER NOT NULL DEFAULT 0,
  vs_rhb_fo             INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, sim_date)
);

CREATE TABLE pitcher_post_lock_stats (
  player_id      INTEGER NOT NULL REFERENCES players(mlb_id) ON DELETE CASCADE,
  sim_date       DATE    NOT NULL,
  bf             INTEGER NOT NULL DEFAULT 0,
  pitches_thrown INTEGER NOT NULL DEFAULT 0,
  singles        INTEGER NOT NULL DEFAULT 0,
  doubles        INTEGER NOT NULL DEFAULT 0,
  triples        INTEGER NOT NULL DEFAULT 0,
  hr             INTEGER NOT NULL DEFAULT 0,
  bb             INTEGER NOT NULL DEFAULT 0,
  hbp            INTEGER NOT NULL DEFAULT 0,
  k              INTEGER NOT NULL DEFAULT 0,
  go             INTEGER NOT NULL DEFAULT 0,
  fo             INTEGER NOT NULL DEFAULT 0,
  po             INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, sim_date)
);


-- ============================================================
-- 5. Sim Results
-- ============================================================

CREATE TABLE sim_events (
  id                UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
  matchup_id        UUID           NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
  inning            INTEGER        NOT NULL,
  half              half_inning    NOT NULL,
  sequence_number   INTEGER        NOT NULL,
  event_type        sim_event_type NOT NULL,
  pitcher_player_id INTEGER        REFERENCES players(mlb_id),
  description       TEXT,
  runs_scored       INTEGER        NOT NULL DEFAULT 0,
  outs_before_play  INTEGER        NOT NULL CHECK (outs_before_play IN (0, 1, 2))
);

CREATE TABLE sim_event_runner_outcomes (
  sim_event_id      UUID        NOT NULL REFERENCES sim_events(id) ON DELETE CASCADE,
  base_before       INTEGER     NOT NULL CHECK (base_before IN (0, 1, 2, 3)),
  player_id         INTEGER     NOT NULL REFERENCES players(mlb_id),
  intermediate_base INTEGER     CHECK (intermediate_base IN (1, 2, 3)),
  final_base        INTEGER     CHECK (final_base IN (1, 2, 3, 4)),
  putout_at_base    INTEGER     CHECK (putout_at_base IN (1, 2, 3, 4)),
  putout_type       putout_type,
  PRIMARY KEY (sim_event_id, base_before),
  UNIQUE (sim_event_id, player_id)
);

CREATE TABLE sim_batter_stats (
  matchup_id             UUID    NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
  team_id                UUID    NOT NULL REFERENCES teams(id),
  player_id              INTEGER NOT NULL REFERENCES players(mlb_id),
  batting_order_position INTEGER NOT NULL CHECK (batting_order_position BETWEEN 1 AND 9),
  sequence_within_spot   INTEGER NOT NULL,
  ab                     INTEGER NOT NULL DEFAULT 0,
  r                      INTEGER NOT NULL DEFAULT 0,
  h                      INTEGER NOT NULL DEFAULT 0,
  doubles                INTEGER NOT NULL DEFAULT 0,
  triples                INTEGER NOT NULL DEFAULT 0,
  hr                     INTEGER NOT NULL DEFAULT 0,
  rbi                    INTEGER NOT NULL DEFAULT 0,
  bb                     INTEGER NOT NULL DEFAULT 0,
  k                      INTEGER NOT NULL DEFAULT 0,
  sb                     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (matchup_id, player_id)
);

CREATE TABLE sim_batter_positions (
  matchup_id        UUID           NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
  player_id         INTEGER        NOT NULL REFERENCES players(mlb_id),
  position_sequence INTEGER        NOT NULL,
  field_position    field_position NOT NULL,
  PRIMARY KEY (matchup_id, player_id, position_sequence)
);

CREATE TABLE sim_pitcher_stats (
  matchup_id        UUID    NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
  team_id           UUID    NOT NULL REFERENCES teams(id),
  player_id         INTEGER NOT NULL REFERENCES players(mlb_id),
  pitching_sequence INTEGER NOT NULL,
  outs_recorded     INTEGER NOT NULL DEFAULT 0,
  h                 INTEGER NOT NULL DEFAULT 0,
  r                 INTEGER NOT NULL DEFAULT 0,
  er                INTEGER NOT NULL DEFAULT 0,
  bb                INTEGER NOT NULL DEFAULT 0,
  k                 INTEGER NOT NULL DEFAULT 0,
  hr                INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (matchup_id, player_id)
);

CREATE TABLE sim_line_score (
  matchup_id UUID    NOT NULL REFERENCES matchups(id) ON DELETE CASCADE,
  team_id    UUID    NOT NULL REFERENCES teams(id),
  inning     INTEGER NOT NULL,
  runs       INTEGER NOT NULL DEFAULT 0,
  hits       INTEGER NOT NULL DEFAULT 0,
  errors     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (matchup_id, team_id, inning)
);


-- ============================================================
-- Indexes
-- ============================================================

-- Required for is_league_member() — evaluated per-row in RLS policies
CREATE INDEX idx_teams_manager_league  ON teams      (manager_id, league_id);

-- FK traversal — common query paths
CREATE INDEX idx_matchups_league_id    ON matchups   (league_id);
CREATE INDEX idx_lineups_matchup_id    ON lineups    (matchup_id);
CREATE INDEX idx_sim_events_matchup_id ON sim_events (matchup_id);


-- ============================================================
-- Row Level Security
-- ============================================================

ALTER TABLE profiles                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE leagues                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE players                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_positions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE roster_players            ENABLE ROW LEVEL SECURITY;
ALTER TABLE matchups                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineups                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE lineup_batting_order      ENABLE ROW LEVEL SECURITY;
ALTER TABLE batter_pre_lock_stats     ENABLE ROW LEVEL SECURITY;
ALTER TABLE batter_post_lock_stats    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pitcher_pre_lock_stats    ENABLE ROW LEVEL SECURITY;
ALTER TABLE pitcher_post_lock_stats   ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_events                ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_event_runner_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_batter_stats          ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_batter_positions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_pitcher_stats         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sim_line_score            ENABLE ROW LEVEL SECURITY;


-- ============================================================
-- RLS Helper Function
-- ============================================================

-- SECURITY DEFINER so the function queries teams with elevated privileges,
-- avoiding RLS recursion. idx_teams_manager_league makes it efficient per-row.
CREATE OR REPLACE FUNCTION is_league_member(p_league_id UUID)
RETURNS BOOLEAN
LANGUAGE sql STABLE SECURITY DEFINER AS $$
  SELECT EXISTS (
    SELECT 1 FROM teams
    WHERE league_id = p_league_id
      AND manager_id = auth.uid()
  );
$$;


-- ============================================================
-- Read Policies (Realtime-enabled tables only)
-- ============================================================

CREATE POLICY "league members can read matchups"
  ON matchups FOR SELECT
  USING (is_league_member(league_id));

CREATE POLICY "league members can read lineups"
  ON lineups FOR SELECT
  USING (is_league_member(
    (SELECT league_id FROM matchups WHERE id = matchup_id)
  ));

CREATE POLICY "league members can read lineup batting order"
  ON lineup_batting_order FOR SELECT
  USING (is_league_member(
    (SELECT m.league_id
     FROM matchups m
     JOIN lineups l ON l.matchup_id = m.id
     WHERE l.id = lineup_id)
  ));


-- ============================================================
-- Trigger: auto-create profile on user registration
-- ============================================================

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  INSERT INTO public.profiles (id, username, display_name, created_at)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'username',
    NEW.raw_user_meta_data->>'display_name',
    NEW.created_at
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();


-- ============================================================
-- Grants
-- ============================================================

-- service_role is used by the API server, sim engine, and data pipeline.
-- It bypasses RLS but still needs object-level privileges when tables are
-- created via raw SQL rather than through the Supabase dashboard.
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- authenticated role needs SELECT on the three Realtime-enabled tables so
-- that Supabase Realtime subscriptions work. RLS policies then control
-- which rows each user can see.
GRANT SELECT ON matchups, lineups, lineup_batting_order TO authenticated;


-- ============================================================
-- Realtime
-- ============================================================
-- Enable Realtime on matchups, lineups, and lineup_batting_order
-- in the Supabase dashboard: Database → Replication → Tables
-- (cannot be done via SQL)
