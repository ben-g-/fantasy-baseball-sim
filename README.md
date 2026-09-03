# Fantasy Baseball Sim

A season-long fantasy baseball platform where weekly head-to-head matchups are resolved by simulating an actual 9-inning game between the two managers' rosters. Each manager sets a starting lineup and starting pitcher ahead of two weekly lock deadlines; an automated AI manager handles all in-game decisions (bullpen usage, pinch hitters, stolen base attempts), and each simulated game gets an LLM-generated recap.

In most fantasy sports platforms, a team is directly awarded points for the players' real-life stats. Here, the players' real-life performances are the basis for estimating probabilities of outcomes of situations that arise in the simulated game.

**Stack:** Vue 3 + TypeScript (web client) · Node.js/Express (API) · Python/FastAPI (sim engine) · PostgreSQL via Supabase (data + auth + realtime)

## License

Copyright (c) 2026 Ben Gottesman. All rights reserved.

This repository is shared publicly for portfolio and demonstration purposes only. No license is granted to use, copy, modify, or distribute this code.
