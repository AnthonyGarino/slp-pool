"""
NCAA Tournament Monte Carlo Simulation for SLP Pool
Uses EvanMiya BPR (Bayesian Performance Rating) to simulate the 2026 NCAA
Tournament and estimate pool win probabilities for each entry.

CORRECT 2026 bracket from ESPN/CBS:
  East: Duke(1), UConn(2), Michigan St(3), Kansas(4)
  West: Arizona(1), Purdue(2), Gonzaga(3), Arkansas(4)
  South: Florida(1), Houston(2), Illinois(3), Nebraska(4)
  Midwest: Michigan(1), Iowa St(2), Virginia(3), Alabama(4)
"""

import json
import math
import os
import random
from collections import defaultdict

# ─── EvanMiya BPR Ratings (from data.csv) ─────────────────────────────────────
# BPR = Bayesian Performance Rating — EvanMiya's team strength metric
EVANMIYA_RATINGS = {
    # East Region
    "Duke": 34.54, "UConn": 29.43, "Michigan St": 24.62, "Kansas": 22.40,
    "St. John's": 25.48, "Louisville": 23.38, "UCLA": 18.83, "Ohio St": 19.84,
    "TCU": 15.61, "UCF": 12.32, "South Florida": 12.68, "Northern Iowa": 8.73,
    "Cal Baptist": -1.59, "North Dakota St": 4.12, "Furman": 0.89, "Siena": -0.09,

    # West Region
    "Arizona": 32.06, "Purdue": 28.77, "Gonzaga": 27.71, "Arkansas": 22.89,
    "Wisconsin": 21.43, "BYU": 21.51, "Miami FL": 17.24, "Villanova": 16.75,
    "Utah St": 17.76, "Missouri": 12.88, "High Point": 7.76, "Texas": 16.43,
    "NC State": 16.42, "Kennesaw St": 1.01, "Queens": -1.96, "LIU": -3.90,

    # South Region
    "Florida": 31.71, "Houston": 31.71, "Illinois": 29.97, "Nebraska": 23.69,
    "Vanderbilt": 25.00, "North Carolina": 18.98, "Saint Mary's": 21.00, "Clemson": 16.80,
    "Iowa": 19.79, "McNeese": 11.49, "VCU": 14.63, "Texas A&M": 16.03,
    "Troy": 4.50, "Penn": 0.33, "Idaho": -0.03, "Prairie View": -10.12,
    "Lehigh": -8.72,

    # Midwest Region
    "Michigan": 34.85, "Iowa St": 30.06, "Virginia": 24.48, "Alabama": 17.53,
    "Texas Tech": 22.72, "Tennessee": 23.73, "Kentucky": 20.07, "Georgia": 18.06,
    "Saint Louis": 15.46, "Akron": 10.27, "Santa Clara": 16.20, "SMU": 15.18,
    "Miami OH": 7.13, "Hofstra": 8.27, "Wright St": 1.27, "Tennessee St": 0.32,
    "UMBC": 0.01, "Howard": -1.02,

    # Hawaii (West 4-13 matchup)
    "Hawaii": -1.03,
}

# ─── 2026 NCAA Tournament Bracket (REAL from ESPN/Yahoo) ─────────────────────
# Each region: 8 first-round matchups in standard bracket order
# 1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15
BRACKET = {
    "East": [
        ("Duke", "Siena"),              # 1 vs 16
        ("Ohio St", "TCU"),             # 8 vs 9
        ("St. John's", "Northern Iowa"),# 5 vs 12
        ("Kansas", "Cal Baptist"),      # 4 vs 13
        ("Louisville", "South Florida"),# 6 vs 11
        ("Michigan St", "North Dakota St"),# 3 vs 14
        ("UCLA", "UCF"),                # 7 vs 10
        ("UConn", "Furman"),            # 2 vs 15
    ],
    "West": [
        ("Arizona", "LIU"),             # 1 vs 16
        ("Villanova", "Utah St"),       # 8 vs 9
        ("Wisconsin", "High Point"),    # 5 vs 12
        ("Arkansas", "Hawaii"),         # 4 vs 13 (Hawaii not in EvanMiya, use default)
        ("BYU", "NC State"),            # 6 vs 11 (play-in winner: NC State or Texas)
        ("Gonzaga", "Kennesaw St"),     # 3 vs 14
        ("Miami FL", "Missouri"),       # 7 vs 10
        ("Purdue", "Queens"),           # 2 vs 15
    ],
    "South": [
        ("Florida", "Prairie View"),    # 1 vs 16 (play-in winner)
        ("Clemson", "Iowa"),            # 8 vs 9
        ("Vanderbilt", "McNeese"),      # 5 vs 12
        ("Nebraska", "Troy"),           # 4 vs 13
        ("North Carolina", "VCU"),      # 6 vs 11
        ("Illinois", "Penn"),           # 3 vs 14
        ("Saint Mary's", "Texas A&M"),  # 7 vs 10
        ("Houston", "Idaho"),           # 2 vs 15
    ],
    "Midwest": [
        ("Michigan", "UMBC"),           # 1 vs 16 (play-in winner)
        ("Georgia", "Saint Louis"),     # 8 vs 9
        ("Texas Tech", "Akron"),        # 5 vs 12
        ("Alabama", "Hofstra"),         # 4 vs 13
        ("Tennessee", "SMU"),           # 6 vs 11 (play-in winner: SMU or Miami OH)
        ("Virginia", "Wright St"),      # 3 vs 14
        ("Kentucky", "Santa Clara"),    # 7 vs 10
        ("Iowa St", "Tennessee St"),    # 2 vs 15
    ],
}

# Play-in games (simulated before R64)
PLAY_IN_GAMES = [
    # 11 West: Texas vs NC State (winner faces BYU)
    {"region": "West", "slot": 4, "teams": ("Texas", "NC State")},
    # 11 Midwest: SMU vs Miami OH (winner faces Tennessee)
    {"region": "Midwest", "slot": 4, "teams": ("SMU", "Miami OH")},
    # 16 South: Prairie View vs Lehigh (winner faces Florida)
    {"region": "South", "slot": 0, "teams": ("Prairie View", "Lehigh")},
    # 16 Midwest: UMBC vs Howard (winner faces Michigan)
    {"region": "Midwest", "slot": 0, "teams": ("UMBC", "Howard")},
]

# All tournament teams should have BPR ratings from data.csv

# Final Four pairings: East vs West, South vs Midwest
FF_MATCHUPS = [("East", "West"), ("South", "Midwest")]

# ─── Scoring ─────────────────────────────────────────────────────────────────
# Points for each round WIN. Seed points already in current scores.
ROUND_POINTS = [2, 4, 6, 8, 10, 12]  # R64, R32, S16, E8, F4, Championship

# ─── Team Name Mapping: data.json names → bracket/EvanMiya names ──────────────
NAME_MAP = {
    "Michigan State": "Michigan St",
    "Ohio State": "Ohio St",
    "Iowa State": "Iowa St",
    "Oklahoma State": "Oklahoma St",
    "NC State": "NC State",
    "North Carolina State": "NC State",
    "N.C. State": "NC State",
    "St Johns": "St. John's",
    "Uconn": "UConn",
    "McNeese State": "McNeese",
    "Stephen F Austin": "SFA",
    "Miami (Ohio)": "Miami OH",
    "Miami (OH)": "Miami OH",
    "San Diego State": "San Diego St",
    "San Diego St": "San Diego St",
    "Boise State": "Boise St",
    "Utah State": "Utah St",
    "Florida State": "Florida St",
    "Saint Marys": "Saint Mary's",
    "Texas Tech": "Texas Tech",
    "Texas A&M": "Texas A&M",
    "North Dakota State": "North Dakota St",
    "Kennesaw State": "Kennesaw St",
    "Tennessee State": "Tennessee St",
    "South Florida": "South Florida",
    "Miami": "Miami FL",
    "Vanderbilt": "Vanderbilt",
    "Saint Louis": "Saint Louis",
    "Akron": "Akron",
    "High Point": "High Point",
    "Northern Iowa": "Northern Iowa",
    "Cal Baptist": "Cal Baptist",
    "California Baptist": "Cal Baptist",
    "North Carolina A&T": "NC A&T",
    "Villanova": "Villanova",
    "SFA": "SFA",
    "Wright State": "Wright St",
    "Hofstra": "Hofstra",
    "Santa Clara": "Santa Clara",
    "Idaho": "Idaho",
    "Troy": "Troy",
    "Prairie View": "Prairie View",
    "Lehigh": "Lehigh",
    "LIU": "LIU",
    "Queens": "Queens",
    "Penn": "Penn",
    "UMBC": "UMBC",
    "Howard": "Howard",
    "UCF": "UCF",
    "Furman": "Furman",
    "Siena": "Siena",
    "Gonzaga": "Gonzaga",
}


def normalize(name):
    """Map data.json team name to bracket/EvanMiya name."""
    return NAME_MAP.get(name, name)


def win_prob(team_a, team_b):
    """Win probability for team_a vs team_b using EvanMiya BPR.

    BPR diff maps to expected scoring margin similarly to BPR:
      expected_margin = BPR_diff × 0.67  (scale to ~67 possessions/game)
      P(A wins) = Phi(expected_margin / game_sigma)
      game_sigma ≈ 11 is the std dev of actual scoring margins in CBB.
    """
    a_bpr = EVANMIYA_RATINGS.get(team_a)
    b_bpr = EVANMIYA_RATINGS.get(team_b)
    if a_bpr is None or b_bpr is None:
        return 0.5
    bpr_diff = a_bpr - b_bpr
    expected_margin = bpr_diff * 0.67
    GAME_SIGMA = 11.0
    return 0.5 * (1.0 + math.erf(expected_margin / (GAME_SIGMA * math.sqrt(2))))


def sim_game(team_a, team_b, rng):
    """Simulate one game, return winner."""
    return team_a if rng.random() < win_prob(team_a, team_b) else team_b


def sim_region(matchups, rng):
    """Simulate a region R64 through E8. Returns (champion, wins_dict).
    wins_dict: team -> list of round indices (0=R64, 1=R32, 2=S16, 3=E8)."""
    wins = defaultdict(list)

    # R64
    r64 = []
    for team_a, team_b in matchups:
        w = sim_game(team_a, team_b, rng)
        wins[w].append(0)
        r64.append(w)

    # R32
    r32 = []
    for i in range(0, 8, 2):
        w = sim_game(r64[i], r64[i + 1], rng)
        wins[w].append(1)
        r32.append(w)

    # S16
    s16 = []
    for i in range(0, 4, 2):
        w = sim_game(r32[i], r32[i + 1], rng)
        wins[w].append(2)
        s16.append(w)

    # E8
    champ = sim_game(s16[0], s16[1], rng)
    wins[champ].append(3)

    return champ, wins


def sim_tournament(rng):
    """Simulate full tournament including play-in games.
    Returns (champion, all_wins)."""
    all_wins = defaultdict(list)

    # Build a mutable copy of the bracket for this sim
    bracket = {}
    for region, matchups in BRACKET.items():
        bracket[region] = list(matchups)

    # Simulate play-in games first
    for playin in PLAY_IN_GAMES:
        t1, t2 = playin["teams"]
        winner = sim_game(t1, t2, rng)
        # Replace the placeholder in the bracket
        region = playin["region"]
        slot = playin["slot"]
        old_matchup = bracket[region][slot]
        # The play-in winner replaces the placeholder team
        # The placeholder is the second team (lower seed) in the matchup
        bracket[region][slot] = (old_matchup[0], winner)

    region_champs = {}
    for region, matchups in bracket.items():
        champ, wins = sim_region(matchups, rng)
        region_champs[region] = champ
        for team, rounds in wins.items():
            all_wins[team].extend(rounds)

    # Final Four
    ff_winners = []
    for region_a, region_b in FF_MATCHUPS:
        a, b = region_champs[region_a], region_champs[region_b]
        w = sim_game(a, b, rng)
        all_wins[w].append(4)
        ff_winners.append(w)

    # Championship
    champion = sim_game(ff_winners[0], ff_winners[1], rng)
    all_wins[champion].append(5)

    return champion, all_wins


def calc_bonus(entry_teams, all_wins):
    """Sum tournament round-win points for an entry's teams."""
    pts = 0
    for team in entry_teams:
        for r in all_wins.get(team, []):
            pts += ROUND_POINTS[r]
    return pts


def load_entries(data_path):
    """Load pool entries from data.json. Returns {name: {score, teams}}."""
    with open(data_path, "r") as f:
        data = json.load(f)

    entries = {}
    for e in data["entries"]:
        teams = []
        for conf, pick in e["picks"].items():
            teams.append(normalize(pick["team"]))
        for wc in e["wildcards"]:
            if wc.get("counts", True):
                teams.append(normalize(wc["team"]))
        entries[e["name"]] = {"score": e["score"], "teams": teams}
    return entries


def main():
    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
    entries = load_entries(data_path)
    tourney_teams = set(EVANMIYA_RATINGS.keys())
    # Also add play-in teams
    for pi in PLAY_IN_GAMES:
        for t in pi["teams"]:
            tourney_teams.add(t)

    print(f"Tournament teams (inc. play-in): {len(tourney_teams)}")
    print(f"Pool entries: {len(entries)}")

    # Verify all bracket teams have EvanMiya ratings
    all_bracket_teams = set()
    for region, matchups in BRACKET.items():
        for a, b in matchups:
            all_bracket_teams.add(a)
            all_bracket_teams.add(b)
    for pi in PLAY_IN_GAMES:
        for t in pi["teams"]:
            all_bracket_teams.add(t)

    missing = all_bracket_teams - set(EVANMIYA_RATINGS.keys())
    if missing:
        print(f"\n⚠ WARNING: Missing EvanMiya ratings for: {missing}")
        print("  These teams will use 50/50 win probability.")

    # ─── Show top entries and their tournament teams ─────────────────────────
    print("\n" + "=" * 72)
    print("TOP 15 ENTRIES — TOURNAMENT TEAMS OWNED")
    print("=" * 72)
    sorted_entries = sorted(entries.items(), key=lambda x: x[1]["score"], reverse=True)
    for name, info in sorted_entries[:15]:
        in_t = [t for t in info["teams"] if t in tourney_teams]
        print(f"  {name:<30s} (score: {info['score']:>3d})  NCAA: {in_t}")

    # ─── Monte Carlo ─────────────────────────────────────────────────────────
    NUM_SIMS = 50_000
    rng = random.Random(42)

    win_counts = defaultdict(int)
    top3_counts = defaultdict(int)
    top8_counts = defaultdict(int)
    position_counts = defaultdict(lambda: defaultdict(int))  # entry -> position -> count
    champ_counts = defaultdict(int)
    donut_wins_given_champ = defaultdict(int)
    champ_total_given = defaultdict(int)
    team_round_counts = defaultdict(lambda: defaultdict(int))  # team -> round -> count
    # Rooting guide: track ALL entries' wins conditioned on team advancing each round
    # team_advance_count[team][round] = how many sims team won that round
    # entry_wins_given_advance[entry][team][round] = count of entry wins when team won that round
    team_advance_count = defaultdict(lambda: defaultdict(int))
    entry_wins_given_advance = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    print(f"\nRunning {NUM_SIMS:,} simulations...")

    for sim in range(NUM_SIMS):
        if (sim + 1) % 10_000 == 0:
            print(f"  {sim + 1:,} / {NUM_SIMS:,}")

        champion, all_wins = sim_tournament(rng)
        champ_counts[champion] += 1
        champ_total_given[champion] += 1

        # Track team round advancement
        for team, rounds in all_wins.items():
            for r in rounds:
                team_round_counts[team][r] += 1

        # Score all entries
        final = {}
        for name, info in entries.items():
            final[name] = info["score"] + calc_bonus(info["teams"], all_wins)

        # Rank (break ties alphabetically for determinism)
        ranked = sorted(final.items(), key=lambda x: (-x[1], x[0]))
        pool_winner = ranked[0][0]
        win_counts[pool_winner] += 1

        # Rooting guide: for each team that won rounds, track pool winner
        for team, rounds in all_wins.items():
            for r in rounds:
                team_advance_count[team][r] += 1
                entry_wins_given_advance[pool_winner][team][r] += 1

        # Track individual finish positions 1-8
        for pos in range(min(8, len(ranked))):
            position_counts[ranked[pos][0]][pos] += 1

        for name, _ in ranked[:3]:
            top3_counts[name] += 1
        for name, _ in ranked[:8]:
            top8_counts[name] += 1

        if pool_winner == "Donut Holes":
            donut_wins_given_champ[champion] += 1

    # ═════════════════════════════════════════════════════════════════════════
    # RESULTS
    # ═════════════════════════════════════════════════════════════════════════

    print("\n" + "=" * 72)
    print(f"  SLP POOL MONTE CARLO RESULTS — {NUM_SIMS:,} simulations")
    print("=" * 72)

    # 1. Pool win probabilities
    print("\n" + "-" * 72)
    print("POOL WIN PROBABILITIES")
    print("-" * 72)
    sorted_wins = sorted(win_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, count) in enumerate(sorted_wins[:35], 1):
        pct = count / NUM_SIMS * 100
        score = entries[name]["score"]
        in_t = len([t for t in entries[name]["teams"] if t in tourney_teams])
        print(f"  {rank:>2}. {name:<30s} {pct:6.2f}%  "
              f"(curr: {score}, {in_t} NCAA teams)")

    # 2. Top 3 finish
    print("\n" + "-" * 72)
    print("TOP 3 FINISH PROBABILITIES")
    print("-" * 72)
    sorted_t3 = sorted(top3_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, count) in enumerate(sorted_t3[:20], 1):
        pct = count / NUM_SIMS * 100
        score = entries[name]["score"]
        print(f"  {rank:>2}. {name:<30s} {pct:6.2f}%  (curr: {score})")

    # 3. Top 8 finish
    print("\n" + "-" * 72)
    print("TOP 8 FINISH PROBABILITIES")
    print("-" * 72)
    sorted_t8 = sorted(top8_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, count) in enumerate(sorted_t8[:25], 1):
        pct = count / NUM_SIMS * 100
        score = entries[name]["score"]
        print(f"  {rank:>2}. {name:<30s} {pct:6.2f}%  (curr: {score})")

    # 4. NCAA Champion frequency
    print("\n" + "-" * 72)
    print("NCAA CHAMPIONSHIP PROBABILITIES")
    print("-" * 72)
    sorted_champs = sorted(champ_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (team, count) in enumerate(sorted_champs, 1):
        pct = count / NUM_SIMS * 100
        em = EVANMIYA_RATINGS.get(team, 0)
        if pct >= 0.01:
            print(f"  {rank:>2}. {team:<20s} {pct:6.2f}%  (BPR: {em:+.2f})")

    # 5. Donut Holes conditional analysis
    dh_overall = win_counts.get("Donut Holes", 0) / NUM_SIMS * 100
    print("\n" + "-" * 72)
    print(f"DONUT HOLES CONDITIONAL WIN PROBABILITY  (overall: {dh_overall:.2f}%)")
    print("-" * 72)

    cond_data = []
    for team, total in sorted_champs:
        dh_w = donut_wins_given_champ.get(team, 0)
        cond = dh_w / total * 100 if total > 0 else 0.0
        overall = total / NUM_SIMS * 100
        cond_data.append((team, cond, overall, total, dh_w))

    # Sort by conditional win %
    cond_data.sort(key=lambda x: x[1], reverse=True)

    for team, cond, overall, total, dh_w in cond_data:
        if overall >= 0.01:
            bar = "#" * int(cond / 2)
            print(f"  {team:<20s}  DH wins pool {cond:5.1f}%  "
                  f"(champ prob {overall:5.2f}%, n={total:>5d})  {bar}")

    # 6. Rooting guide
    print("\n" + "-" * 72)
    print("DONUT HOLES ROOTING GUIDE")
    print("-" * 72)

    dh_tourney = [t for t in entries["Donut Holes"]["teams"] if t in tourney_teams]
    dh_non = [t for t in entries["Donut Holes"]["teams"] if t not in tourney_teams]
    print(f"\n  Donut Holes teams IN tournament:  {dh_tourney}")
    print(f"  Donut Holes teams NOT in tourney: {dh_non}")

    print("\n  BEST scenarios (root FOR these champions):")
    for team, cond, overall, total, dh_w in cond_data:
        if overall >= 0.05 and cond >= dh_overall:
            print(f"    {team:<20s}  -> DH pool win {cond:5.1f}%  "
                  f"(champ {overall:.2f}%)")

    print("\n  WORST scenarios (root AGAINST these champions):")
    worst = [(t, c, o, n, d) for t, c, o, n, d in cond_data if o >= 0.05]
    worst.sort(key=lambda x: x[1])
    for team, cond, overall, total, dh_w in worst:
        if cond < dh_overall:
            print(f"    {team:<20s}  -> DH pool win {cond:5.1f}%  "
                  f"(champ {overall:.2f}%)")

    # 7. Expected points per tournament team
    print("\n" + "-" * 72)
    print("EXPECTED TOURNAMENT POINTS BY TEAM (top 25)")
    print("-" * 72)

    team_pts = defaultdict(float)
    rng2 = random.Random(999)
    for _ in range(NUM_SIMS):
        _, all_wins = sim_tournament(rng2)
        for team, rounds in all_wins.items():
            for r in rounds:
                team_pts[team] += ROUND_POINTS[r]

    sorted_pts = sorted(team_pts.items(), key=lambda x: x[1], reverse=True)
    for rank, (team, total) in enumerate(sorted_pts[:25], 1):
        avg = total / NUM_SIMS
        em = EVANMIYA_RATINGS.get(team, 0)
        # Show which entries own this team
        owners = [n for n, info in entries.items()
                  if team in info["teams"]][:5]
        owner_str = ", ".join(owners) if owners else "(nobody)"
        print(f"  {rank:>2}. {team:<20s} {avg:5.1f} pts  "
              f"(BPR {em:+.2f})  owners: {owner_str}")

    # 8. Head-to-head: Donut Holes vs top competitors
    print("\n" + "-" * 72)
    print("DONUT HOLES HEAD-TO-HEAD vs TOP COMPETITORS")
    print("-" * 72)

    dh_score = entries["Donut Holes"]["score"]
    competitors = sorted_entries[:12]
    for name, info in competitors:
        if name == "Donut Holes":
            continue
        gap = dh_score - info["score"]
        dh_w = win_counts.get("Donut Holes", 0)
        comp_w = win_counts.get(name, 0)
        their_t = [t for t in info["teams"] if t in tourney_teams]
        print(f"  vs {name:<28s} gap: {gap:+3d}  "
              f"DH win: {dh_w/NUM_SIMS*100:5.2f}%  "
              f"them: {comp_w/NUM_SIMS*100:5.2f}%  "
              f"their NCAA: {their_t}")

    # 9. Team round advancement (for championship odds chart)
    round_names = ["R32", "S16", "E8", "F4", "Final", "Champ"]
    print("\n" + "-" * 72)
    print("TEAM ROUND ADVANCEMENT PROBABILITIES")
    print("-" * 72)
    print(f"  {'Team':<20s} {'R32':>6s} {'S16':>6s} {'E8':>6s} {'F4':>6s} {'Final':>6s} {'Champ':>6s}")
    sorted_teams = sorted(team_round_counts.items(),
                          key=lambda x: x[1].get(5, 0), reverse=True)
    for team, rounds in sorted_teams:
        vals = [rounds.get(r, 0) / NUM_SIMS * 100 for r in range(6)]
        if vals[0] >= 0.1:  # only show teams that win at least one game
            print(f"  {team:<20s} {vals[0]:6.1f} {vals[1]:6.1f} {vals[2]:6.1f} "
                  f"{vals[3]:6.1f} {vals[4]:6.1f} {vals[5]:6.1f}")

    # 10. JSON output for HTML charts
    print("\n" + "-" * 72)
    print("JSON_TEAM_DATA_START")
    team_json = []
    for team, rounds in sorted_teams:
        vals = [round(rounds.get(r, 0) / NUM_SIMS * 100, 2) for r in range(6)]
        if vals[0] >= 0.1:
            team_json.append({"name": team, "rounds": vals})
    print(json.dumps(team_json))
    print("JSON_TEAM_DATA_END")

    print("\nJSON_POSITION_DATA_START")
    pos_json = []
    sorted_pos = sorted(position_counts.items(),
                        key=lambda x: sum(x[1].values()), reverse=True)
    for name, positions in sorted_pos:
        vals = [round(positions.get(p, 0) / NUM_SIMS * 100, 2) for p in range(8)]
        top8 = round(sum(positions.get(p, 0) for p in range(8)) / NUM_SIMS * 100, 1)
        if top8 >= 1.0:
            pos_json.append({"name": name, "p": vals, "top8": top8})
    print(json.dumps(pos_json))
    print("JSON_POSITION_DATA_END")

    # Auto-update placements.html with fresh sim data
    update_placements_html(position_counts, NUM_SIMS)

    # Build rooting guide page
    update_rooting_html(team_advance_count, entry_wins_given_advance,
                        win_counts, entries, NUM_SIMS)


def update_placements_html(position_counts, NUM_SIMS):
    """Rewrite placements.html with fresh sim data."""
    site_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(site_dir, "placements.html")

    # Build top-15 entries by top8 %
    entries_data = []
    sorted_pos = sorted(position_counts.items(),
                        key=lambda x: sum(x[1].values()), reverse=True)
    for name, positions in sorted_pos:
        vals = [round(positions.get(p, 0) / NUM_SIMS * 100, 2) for p in range(8)]
        top8 = round(sum(positions.get(p, 0) for p in range(8)) / NUM_SIMS * 100, 1)
        if top8 >= 10.0:
            entries_data.append({"name": name, "p": vals, "top8": top8})
    entries_data.sort(key=lambda x: x["top8"], reverse=True)
    entries_data = entries_data[:15]

    # Build JS data lines
    js_lines = []
    for d in entries_data:
        p_str = ",".join(f"{v:.2f}" for v in d["p"])
        js_lines.append(
            f'  {{ name: "{d["name"]}", '
            f'p: [{p_str}], top8: {d["top8"]:.1f} }}')
    js_data = ",\n".join(js_lines)

    # Build table rows with inline heatmap styling
    def heat_color(val):
        if val == 0:
            return 'transparent'
        intensity = min(val / 30, 1)
        r = int(255 * intensity)
        g = int(180 * intensity)
        b = int(50 * intensity * 0.3)
        return f'rgba({r},{g},{b},{0.15 + intensity * 0.55:.2f})'

    table_rows = ""
    for d in entries_data:
        cells = ""
        for v in d["p"]:
            bg = heat_color(v)
            display = f'{v:.1f}%' if v > 0 else '\u2014'
            cells += f'<td class="heat-cell" style="background:{bg}">{display}</td>'
        table_rows += (
            f'<tr><td style="font-weight:600">{d["name"]}</td>'
            f'{cells}'
            f'<td style="font-weight:600">{d["top8"]:.1f}%</td></tr>\n'
        )

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLP Pool \u2013 Placement Distribution</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }}
  h1 {{ text-align: center; font-size: 1.6rem; margin-bottom: 4px; color: #fff; }}
  .sub {{ text-align: center; font-size: 0.85rem; color: #888; margin-bottom: 24px; }}
  .table-wrap {{ max-width: 900px; margin: 0 auto; overflow-x: auto; background: #1a1d27; border-radius: 12px; padding: 20px; }}
  .table-wrap h2 {{ font-size: 1rem; color: #ccc; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th, td {{ padding: 8px 12px; text-align: right; border-bottom: 1px solid #2a2d3a; }}
  th {{ background: #1a1d27; color: #aaa; font-weight: 600; position: sticky; top: 0; }}
  th:first-child, td:first-child {{ text-align: left; }}
  tr:hover td {{ background: #1e2130; }}
  .heat-cell {{ border-radius: 4px; }}
  .nav {{ text-align: center; margin-bottom: 20px; }}
  .nav a {{ color: #4FC3F7; text-decoration: none; margin: 0 12px; font-size: 0.9rem; }}
  .nav a:hover {{ text-decoration: underline; }}
  .source {{ text-align: center; font-size: 0.75rem; color: #555; margin-top: 16px; }}
  .source a {{ color: #4FC3F7; text-decoration: none; }}
</style>
</head>
<body>

<div class="nav">
  <a href="index.html">&larr; Standings</a>
  <a href="championship.html">NCAA Championship Odds</a>
</div>

<h1>SLP Pool \u2013 Placement Distribution</h1>
<p class="sub">{NUM_SIMS:,} Monte Carlo simulations using <a href="https://evanmiya.com" target="_blank" style="color:#4FC3F7;text-decoration:none">EvanMiya</a> BPR ratings &bull; NCAA 2-4-6-8-10-12 scoring</p>

<div class="table-wrap">
  <h2>Top 8 Finish Probabilities (% of simulations)</h2>
  <table>
    <thead>
      <tr>
        <th style="min-width:160px">Entry</th>
        <th>1st</th><th>2nd</th><th>3rd</th><th>4th</th>
        <th>5th</th><th>6th</th><th>7th</th><th>8th</th>
        <th>Top 8</th>
      </tr>
    </thead>
    <tbody>
{table_rows}    </tbody>
  </table>
</div>

<p class="source">
  Powered by <a href="https://evanmiya.com" target="_blank">EvanMiya</a> BPR ratings
</p>

</body>
</html>'''

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nUpdated {html_path}")


def update_rooting_html(team_advance_count, entry_wins_given_advance,
                        win_counts, entries, NUM_SIMS):
    """Build rooting guide HTML page — filterable by entry."""
    site_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(site_dir, "rooting.html")

    # Get top 15 entries by overall win%
    sorted_entries = sorted(win_counts.items(), key=lambda x: x[1], reverse=True)
    top_entries = [name for name, _ in sorted_entries[:15]]
    overall_pct = {name: count / NUM_SIMS * 100 for name, count in win_counts.items()}

    # Get all tournament teams sorted by BPR
    all_teams = sorted(team_advance_count.keys(),
                       key=lambda t: EVANMIYA_RATINGS.get(t, 0), reverse=True)

    round_labels = ["R64", "R32", "S16", "E8", "F4", "Champ"]

    # Build JSON data: { entry: { team: { round: {if_win, if_lose, swing} } } }
    guide_data = {}
    for entry in top_entries:
        entry_data = {}
        for team in all_teams:
            team_rounds = {}
            for r in range(6):
                adv_count = team_advance_count[team].get(r, 0)
                if adv_count < 50:
                    continue
                not_adv_count = NUM_SIMS - adv_count
                wins_if_adv = entry_wins_given_advance[entry][team].get(r, 0)
                wins_total = win_counts.get(entry, 0)
                wins_if_not = wins_total - wins_if_adv
                pct_if_adv = wins_if_adv / adv_count * 100 if adv_count > 0 else 0
                pct_if_not = wins_if_not / not_adv_count * 100 if not_adv_count > 0 else 0
                swing = pct_if_adv - pct_if_not
                team_rounds[round_labels[r]] = {
                    "w": round(pct_if_adv, 2),
                    "l": round(pct_if_not, 2),
                    "s": round(swing, 2)
                }
            if team_rounds:
                entry_data[team] = team_rounds
        guide_data[entry] = entry_data

    # Build entry options for dropdown
    entry_options = "\n".join(
        f'<option value="{e}">{e} ({overall_pct.get(e, 0):.1f}%)</option>'
        for e in top_entries
    )

    # Pre-compute JSON strings
    data_json = json.dumps(guide_data)
    overall_json = json.dumps({name: round(overall_pct.get(name, 0), 2) for name in top_entries})

    # Get all teams list for JS
    teams_in_data = [t for t in all_teams if any(t in guide_data[e] for e in top_entries)]
    teams_json = json.dumps(teams_in_data)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLP Pool \u2013 Scenario Builder</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0f1117; color: #e0e0e0; padding: 24px; }}
  h1 {{ text-align: center; font-size: 1.6rem; margin-bottom: 4px; color: #fff; }}
  .sub {{ text-align: center; font-size: 0.85rem; color: #888; margin-bottom: 20px; }}
  .nav {{ text-align: center; margin-bottom: 20px; }}
  .nav a {{ color: #4FC3F7; text-decoration: none; margin: 0 12px; font-size: 0.9rem; }}
  .nav a:hover {{ text-decoration: underline; }}
  .controls {{ text-align: center; margin-bottom: 16px; }}
  select {{ font-size: 1rem; padding: 8px 16px; border-radius: 8px; border: 1px solid #444;
           background: #1a1d27; color: #e0e0e0; cursor: pointer; min-width: 280px; }}

  /* Scenario panel */
  .scenario-panel {{ max-width: 1000px; margin: 0 auto 16px; background: #1a1d27; border-radius: 12px; padding: 16px 20px; }}
  .scenario-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
  .scenario-header h2 {{ font-size: 1rem; color: #ccc; }}
  .win-pct {{ font-size: 1.8rem; font-weight: 700; color: #4FC3F7; }}
  .win-pct .delta {{ font-size: 1rem; margin-left: 8px; }}
  .win-pct .delta.up {{ color: #4CAF50; }}
  .win-pct .delta.down {{ color: #ef5350; }}
  .scenarios-list {{ display: flex; flex-wrap: wrap; gap: 6px; min-height: 28px; }}
  .scenario-chip {{ display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px;
                    border-radius: 16px; font-size: 0.78rem; cursor: pointer; }}
  .chip-positive {{ background: rgba(76,175,80,0.25); color: #4CAF50; border: 1px solid rgba(76,175,80,0.4); }}
  .chip-negative {{ background: rgba(239,83,80,0.25); color: #ef5350; border: 1px solid rgba(239,83,80,0.4); }}
  .chip-x {{ font-size: 0.7rem; opacity: 0.7; }}
  .clear-btn {{ font-size: 0.78rem; color: #888; cursor: pointer; background: none; border: 1px solid #444;
               padding: 4px 10px; border-radius: 12px; }}
  .clear-btn:hover {{ color: #e0e0e0; border-color: #888; }}
  .no-scenarios {{ color: #555; font-size: 0.82rem; font-style: italic; }}

  /* Table */
  .table-wrap {{ max-width: 1000px; margin: 0 auto; overflow-x: auto; background: #1a1d27; border-radius: 12px; padding: 20px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th, td {{ padding: 6px 10px; text-align: right; border-bottom: 1px solid #2a2d3a; white-space: nowrap; }}
  th {{ background: #1a1d27; color: #aaa; font-weight: 600; position: sticky; top: 0; }}
  th:first-child, td:first-child {{ text-align: left; }}
  tr:hover td {{ background: #1e2130; }}
  td.clickable {{ cursor: pointer; border-radius: 4px; transition: outline 0.1s; }}
  td.clickable:hover {{ outline: 2px solid #4FC3F7; }}
  td.selected {{ outline: 2px solid #FFD54F !important; }}
  .positive {{ color: #4CAF50; font-weight: 600; }}
  .negative {{ color: #ef5350; font-weight: 600; }}
  .neutral {{ color: #555; }}
  .source {{ text-align: center; font-size: 0.75rem; color: #555; margin-top: 16px; }}
  .source a {{ color: #4FC3F7; text-decoration: none; }}
  .no-data {{ text-align: center; color: #666; padding: 40px; font-size: 0.9rem; }}
  .help {{ text-align: center; font-size: 0.75rem; color: #666; margin-top: 8px; }}
</style>
</head>
<body>

<div class="nav">
  <a href="index.html">&larr; Standings</a>
  <a href="placements.html">Placement Distribution</a>
  <a href="championship.html">Championship Odds</a>
</div>

<h1>SLP Pool \u2013 Scenario Builder</h1>
<p class="sub">Click cells to build scenarios &bull; {NUM_SIMS:,} sims</p>

<div class="controls">
  <select id="entrySelect" onchange="resetAndRender()">
    <option value="">Select an entry...</option>
    {entry_options}
  </select>
</div>

<div id="scenarioPanel" style="display:none" class="scenario-panel">
  <div class="scenario-header">
    <h2>Win Probability</h2>
    <div class="win-pct">
      <span id="adjPct">--</span>
      <span id="adjDelta" class="delta"></span>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:10px">
    <div id="scenariosList" class="scenarios-list">
      <span class="no-scenarios">Click any cell below to add a scenario</span>
    </div>
    <button id="clearBtn" class="clear-btn" onclick="clearScenarios()" style="display:none">Clear all</button>
  </div>
</div>

<div id="content" class="table-wrap">
  <p class="no-data">Select an entry to build scenarios</p>
</div>

<p class="source">
  Powered by <a href="https://evanmiya.com" target="_blank">EvanMiya</a> BPR ratings
</p>

<script>
const DATA = {data_json};
const OVERALL = {overall_json};
const TEAMS = {teams_json};
const ROUNDS = ["R64", "R32", "S16", "E8", "F4", "Champ"];
const RN = {{"R64":"R64","R32":"R32","S16":"S16","E8":"E8","F4":"F4","Champ":"Title"}};

let scenarios = [];  // [{{team, round, swing, win_pct}}]
let currentEntry = '';

function swingBg(v) {{
  if (Math.abs(v) < 0.3) return 'transparent';
  let i = Math.min(Math.abs(v) / 12, 1);
  if (v > 0) return `rgba(76,175,80,${{(0.12 + i*0.5).toFixed(2)}})`;
  return `rgba(239,83,80,${{(0.12 + i*0.5).toFixed(2)}})`;
}}

function scenarioKey(team, rnd) {{ return team + '|' + rnd; }}

function toggleScenario(team, rnd) {{
  const key = scenarioKey(team, rnd);
  const idx = scenarios.findIndex(s => s.key === key);
  if (idx >= 0) {{
    scenarios.splice(idx, 1);
  }} else {{
    const ed = DATA[currentEntry];
    if (!ed[team] || !ed[team][rnd]) return;
    const d = ed[team][rnd];
    scenarios.push({{ key, team, round: rnd, swing: d.s, win_pct: d.w }});
  }}
  updatePanel();
  updateCellHighlights();
}}

function clearScenarios() {{
  scenarios = [];
  updatePanel();
  updateCellHighlights();
}}

function updatePanel() {{
  const base = OVERALL[currentEntry];
  const totalSwing = scenarios.reduce((sum, s) => sum + s.swing, 0);
  const adjusted = Math.max(0, Math.min(100, base + totalSwing));

  document.getElementById('adjPct').textContent = adjusted.toFixed(1) + '%';
  const deltaEl = document.getElementById('adjDelta');
  if (scenarios.length > 0) {{
    const sign = totalSwing >= 0 ? '+' : '';
    deltaEl.textContent = `(${{sign}}${{totalSwing.toFixed(1)}}%)`;
    deltaEl.className = 'delta ' + (totalSwing >= 0 ? 'up' : 'down');
  }} else {{
    deltaEl.textContent = '(baseline)';
    deltaEl.className = 'delta';
  }}

  const listEl = document.getElementById('scenariosList');
  const clearEl = document.getElementById('clearBtn');
  if (scenarios.length === 0) {{
    listEl.innerHTML = '<span class="no-scenarios">Click any cell below to add a scenario</span>';
    clearEl.style.display = 'none';
  }} else {{
    clearEl.style.display = '';
    listEl.innerHTML = scenarios.map(s => {{
      const cls = s.swing >= 0 ? 'chip-positive' : 'chip-negative';
      const sign = s.swing >= 0 ? '+' : '';
      return `<span class="scenario-chip ${{cls}}" onclick="toggleScenario('${{s.team}}','${{s.round}}')" `
        + `title="Click to remove">`
        + `${{s.team}} ${{RN[s.round]}} (${{sign}}${{s.swing.toFixed(1)}}%) <span class="chip-x">\u2715</span></span>`;
    }}).join('');
    if (scenarios.length > 1) {{
      listEl.innerHTML += '<span style="color:#888;font-size:0.7rem;margin-left:4px">(approx. for multiple)</span>';
    }}
  }}
}}

function updateCellHighlights() {{
  document.querySelectorAll('td.clickable').forEach(td => {{
    const key = td.dataset.key;
    td.classList.toggle('selected', scenarios.some(s => s.key === key));
  }});
}}

function resetAndRender() {{
  scenarios = [];
  renderEntry();
}}

function renderEntry() {{
  currentEntry = document.getElementById('entrySelect').value;
  const content = document.getElementById('content');
  const panel = document.getElementById('scenarioPanel');
  if (!currentEntry || !DATA[currentEntry]) {{
    content.innerHTML = '<p class="no-data">Select an entry to build scenarios</p>';
    panel.style.display = 'none';
    return;
  }}

  panel.style.display = '';
  updatePanel();

  const ed = DATA[currentEntry];

  // Find max swing per team
  let teamSwings = {{}};
  for (const team of TEAMS) {{
    if (!ed[team]) continue;
    let maxAbs = 0;
    for (const rnd of ROUNDS) {{
      if (ed[team][rnd]) {{
        let a = Math.abs(ed[team][rnd].s);
        if (a > maxAbs) maxAbs = a;
      }}
    }}
    teamSwings[team] = maxAbs;
  }}

  const sortedTeams = Object.keys(teamSwings).sort((a,b) => teamSwings[b] - teamSwings[a]);
  const relevantTeams = sortedTeams.filter(t => teamSwings[t] >= 0.3);

  let html = '<table><thead><tr><th style="min-width:130px">Team</th>';
  for (const rnd of ROUNDS) html += `<th>${{RN[rnd]}}</th>`;
  html += '<th>Peak</th></tr></thead><tbody>';

  for (const team of relevantTeams) {{
    const td = ed[team];
    html += `<tr><td style="font-weight:600">${{team}}</td>`;
    let peak = 0;
    for (const rnd of ROUNDS) {{
      if (td[rnd]) {{
        const s = td[rnd].s;
        if (Math.abs(s) > Math.abs(peak)) peak = s;
        const cls = s > 0.3 ? 'positive' : s < -0.3 ? 'negative' : 'neutral';
        const arrow = s > 0.3 ? '\u25B2' : s < -0.3 ? '\u25BC' : '';
        const key = scenarioKey(team, rnd);
        const sel = scenarios.some(sc => sc.key === key) ? ' selected' : '';
        html += `<td class="clickable ${{cls}}${{sel}}" style="background:${{swingBg(s)}}" `;
        html += `data-key="${{key}}" onclick="toggleScenario('${{team}}','${{rnd}}')" `;
        html += `title="${{team}} wins ${{RN[rnd]}}:  ${{td[rnd].w.toFixed(1)}}%&#10;${{team}} loses ${{RN[rnd]}}: ${{td[rnd].l.toFixed(1)}}%">`;
        html += `${{arrow}}${{s > 0 ? '+' : ''}}${{s.toFixed(1)}}%</td>`;
      }} else {{
        html += '<td class="neutral">\u2014</td>';
      }}
    }}
    const pcls = peak > 0.3 ? 'positive' : peak < -0.3 ? 'negative' : 'neutral';
    html += `<td class="${{pcls}}" style="font-weight:700">${{peak > 0 ? '+' : ''}}${{peak.toFixed(1)}}%</td>`;
    html += '</tr>';
  }}

  html += '</tbody></table>';
  html += '<p class="help">Click cells to add/remove scenarios. Swings are additive estimates.</p>';
  content.innerHTML = html;
}}
</script>
</body>
</html>'''

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Updated {html_path}")


if __name__ == "__main__":
    main()
