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
    "Duke": 34.88, "UConn": 27.61, "Michigan St": 24.45, "Kansas": 22.24,
    "St. John's": 25.51, "Louisville": 22.27, "UCLA": 20.34, "Ohio St": 20.93,
    "TCU": 16.13, "UCF": 11.23, "South Florida": 15.82, "Northern Iowa": 10.59,
    "Cal Baptist": 3.83, "North Dakota St": 4.21, "Furman": 0.97, "Siena": -0.06,

    # West Region
    "Arizona": 32.01, "Purdue": 30.26, "Gonzaga": 25.81, "Arkansas": 23.82,
    "Wisconsin": 22.39, "BYU": 16.40, "Miami FL": 18.68, "Villanova": 15.36,
    "Utah St": 18.02, "Missouri": 14.42, "High Point": 8.62, "Texas": 17.08,
    "NC State": 16.30, "Kennesaw St": 0.77, "Queens": -1.80, "LIU": -3.30,

    # South Region
    "Florida": 31.39, "Houston": 30.94, "Illinois": 28.01, "Nebraska": 22.36,
    "Vanderbilt": 24.02, "North Carolina": 14.76, "Saint Mary's": 20.56, "Clemson": 16.56,
    "Iowa": 20.16, "McNeese": 10.67, "VCU": 16.18, "Texas A&M": 16.04,
    "Troy": 4.52, "Penn": 0.93, "Idaho": 0.02, "Prairie View": -10.18,
    "Lehigh": -8.64,

    # Midwest Region
    "Michigan": 34.52, "Iowa St": 29.50, "Virginia": 24.13, "Alabama": 23.23,
    "Texas Tech": 18.28, "Tennessee": 23.53, "Kentucky": 20.22, "Georgia": 18.26,
    "Saint Louis": 17.65, "Akron": 11.12, "Santa Clara": 16.83, "SMU": 16.50,
    "Miami OH": 8.44, "Hofstra": 9.98, "Wright St": 1.27, "Tennessee St": 0.46,
    "UMBC": 0.02, "Howard": -1.02,

    # Hawaii (West 4-13 matchup)
    "Hawaii": 3.34,
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
    # Per-sim data for client-side multi-filter
    all_team_list = sorted(EVANMIYA_RATINGS.keys())
    team_to_idx = {t: i for i, t in enumerate(all_team_list)}
    sim_adv = []   # team advancement strings (one char per team: '.'=no wins, '0'-'5'=max round won)
    sim_top8 = []  # top-8 entry names per sim

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

        # Track individual finish positions 1-8
        for pos in range(min(8, len(ranked))):
            position_counts[ranked[pos][0]][pos] += 1

        for name, _ in ranked[:3]:
            top3_counts[name] += 1
        for name, _ in ranked[:8]:
            top8_counts[name] += 1

        # Per-sim storage for multi-filter
        adv = ['.'] * len(all_team_list)
        for team, rounds in all_wins.items():
            idx = team_to_idx.get(team)
            if idx is not None:
                adv[idx] = str(max(rounds))
        sim_adv.append(''.join(adv))
        sim_top8.append([ranked[i][0] for i in range(min(8, len(ranked)))])

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
    update_placements_html(position_counts, NUM_SIMS, sim_adv, sim_top8, all_team_list)


def update_placements_html(position_counts, NUM_SIMS, sim_adv, sim_top8, all_team_list):
    """Rewrite placements.html with fresh sim data + multi-condition filter."""
    site_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(site_dir, "placements.html")

    # Build baseline entries
    entries_data = []
    sorted_pos = sorted(position_counts.items(),
                        key=lambda x: sum(x[1].values()), reverse=True)
    for name, positions in sorted_pos:
        vals = [round(positions.get(p, 0) / NUM_SIMS * 100, 2) for p in range(8)]
        top8 = round(sum(positions.get(p, 0) for p in range(8)) / NUM_SIMS * 100, 1)
        if top8 >= 1.0:
            entries_data.append({"name": name, "p": vals, "top8": top8})
    entries_data.sort(key=lambda x: x["top8"], reverse=True)
    baseline_json = json.dumps(entries_data[:15])

    # Build entry index for compact sim storage
    entry_count = defaultdict(int)
    for t8 in sim_top8:
        for name in t8:
            entry_count[name] += 1
    relevant_entries = sorted(
        [n for n, c in entry_count.items() if c / NUM_SIMS >= 0.005],
        key=lambda n: entry_count[n], reverse=True
    )
    entry_to_idx = {n: i for i, n in enumerate(relevant_entries)}

    # Convert sim_top8 to index arrays
    top8_idx = []
    for t8 in sim_top8:
        top8_idx.append([entry_to_idx.get(n, -1) for n in t8[:8]])

    # JSON data for client-side filtering
    teams_json = json.dumps(all_team_list)
    entries_json = json.dumps(relevant_entries)
    adv_json = json.dumps(sim_adv)
    top8_json = json.dumps(top8_idx)

    # Team options sorted by BPR for dropdown
    teams_by_bpr = sorted(all_team_list,
                          key=lambda t: EVANMIYA_RATINGS.get(t, 0), reverse=True)
    team_opts_js = json.dumps([
        {"idx": all_team_list.index(t), "name": t,
         "bpr": round(EVANMIYA_RATINGS.get(t, 0), 1)}
        for t in teams_by_bpr
    ])

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
  .sub {{ text-align: center; font-size: 0.85rem; color: #888; margin-bottom: 16px; }}
  .sub a {{ color: #4FC3F7; text-decoration: none; }}
  .filters {{ max-width: 900px; margin: 0 auto 16px; }}
  .filter-row {{ display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
  select {{ font-size: 0.9rem; padding: 6px 12px; border-radius: 8px; border: 1px solid #444;
           background: #1a1d27; color: #e0e0e0; cursor: pointer; }}
  .filter-label {{ color: #888; font-size: 0.85rem; }}
  .filter-info {{ text-align: center; font-size: 0.8rem; color: #4FC3F7; margin-bottom: 12px; }}
  .filter-btns {{ text-align: center; margin-bottom: 8px; }}
  .add-btn, .reset-btn {{ font-size: 0.8rem; color: #888; cursor: pointer; background: none; border: 1px solid #444;
               padding: 4px 10px; border-radius: 12px; margin: 0 4px; }}
  .add-btn:hover, .reset-btn:hover {{ color: #e0e0e0; border-color: #888; }}
  .remove-btn {{ font-size: 0.9rem; color: #666; cursor: pointer; background: none; border: none; padding: 2px 6px; }}
  .remove-btn:hover {{ color: #ff6b6b; }}
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

<div class="filters">
  <div id="filterRows"></div>
  <div class="filter-btns">
    <button class="add-btn" onclick="addFilter()">+ Add condition</button>
    <button class="reset-btn" onclick="resetFilters()">Reset</button>
  </div>
</div>

<div id="filterInfo" class="filter-info"></div>

<div class="table-wrap">
  <h2 id="tableTitle">Top 8 Finish Probabilities (% of simulations)</h2>
  <table>
    <thead>
      <tr>
        <th style="min-width:160px">Entry</th>
        <th>1st</th><th>2nd</th><th>3rd</th><th>4th</th>
        <th>5th</th><th>6th</th><th>7th</th><th>8th</th>
        <th>Top 8</th>
      </tr>
    </thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<p class="source">
  Powered by <a href="https://evanmiya.com" target="_blank">EvanMiya</a> BPR ratings
</p>

<script>
const BASELINE = {baseline_json};
const TEAMS = {teams_json};
const ENTRIES = {entries_json};
const ADV = {adv_json};
const TOP8 = {top8_json};
const TEAM_OPTS = {team_opts_js};
const ROUND_LABELS = ["R64","R32","S16","E8","F4","Champ"];
const ROUND_NAMES = {{"R64":"Round of 64","R32":"Round of 32","S16":"Sweet 16",
                      "E8":"Elite 8","F4":"Final Four","Champ":"Championship"}};

let filters = [];

function heatColor(val) {{
  if (val === 0) return 'transparent';
  let i = Math.min(val / 30, 1);
  let r = Math.round(255 * i), g = Math.round(180 * i), b = Math.round(50 * i * 0.3);
  return `rgba(${{r}},${{g}},${{b}},${{(0.15 + i * 0.55).toFixed(2)}})`;
}}

function buildRows(data) {{
  return data.map(d => {{
    let cells = d.p.map(v => {{
      let bg = heatColor(v);
      let display = v > 0 ? v.toFixed(1) + '%' : '\u2014';
      return `<td class="heat-cell" style="background:${{bg}}">${{display}}</td>`;
    }}).join('');
    return `<tr><td style="font-weight:600">${{d.name}}</td>${{cells}}<td style="font-weight:600">${{d.top8.toFixed(1)}}%</td></tr>`;
  }}).join('\\n');
}}

function teamOptions() {{
  return '<option value="">select team...</option>' +
    TEAM_OPTS.map(t => `<option value="${{t.idx}}">${{t.name}} (BPR ${{t.bpr >= 0 ? '+' : ''}}${{t.bpr}})</option>`).join('');
}}

function roundOptions() {{
  return '<option value="">select round...</option>' +
    ROUND_LABELS.map((r, i) => `<option value="${{i}}">${{ROUND_NAMES[r]}}</option>`).join('');
}}

function addFilter() {{
  filters.push({{teamIdx: -1, type: 'wins', round: -1}});
  renderFilterRows();
}}

function removeFilter(idx) {{
  filters.splice(idx, 1);
  renderFilterRows();
  applyFilters();
}}

function updateFilter(idx, field, val) {{
  filters[idx][field] = field === 'type' ? val : parseInt(val);
  applyFilters();
}}

function renderFilterRows() {{
  const container = document.getElementById('filterRows');
  if (filters.length === 0) {{
    container.innerHTML = '';
    return;
  }}
  container.innerHTML = filters.map((f, i) => {{
    return `<div class="filter-row">
      <span class="filter-label">${{i === 0 ? 'What if' : 'AND'}}</span>
      <select onchange="updateFilter(${{i}},'teamIdx',this.value)">${{teamOptions().replace('value="' + f.teamIdx + '"', 'value="' + f.teamIdx + '" selected')}}</select>
      <select onchange="updateFilter(${{i}},'type',this.value)">
        <option value="wins"${{f.type==='wins'?' selected':''}}>wins</option>
        <option value="loses"${{f.type==='loses'?' selected':''}}>eliminated before</option>
      </select>
      <select onchange="updateFilter(${{i}},'round',this.value)">${{roundOptions().replace('value="' + f.round + '"', 'value="' + f.round + '" selected')}}</select>
      <button class="remove-btn" onclick="removeFilter(${{i}})">\u2715</button>
    </div>`;
  }}).join('');
}}

function applyFilters() {{
  const active = filters.filter(f => f.teamIdx >= 0 && f.round >= 0);
  const info = document.getElementById('filterInfo');

  if (active.length === 0) {{
    document.getElementById('tableBody').innerHTML = buildRows(BASELINE);
    info.textContent = '';
    document.getElementById('tableTitle').textContent = 'Top 8 Finish Probabilities (% of simulations)';
    return;
  }}

  // Filter sims
  const counts = new Array(ENTRIES.length).fill(null).map(() => new Array(8).fill(0));
  let n = 0;

  for (let s = 0; s < ADV.length; s++) {{
    let match = true;
    for (const f of active) {{
      const c = ADV[s].charAt(f.teamIdx);
      const maxRound = c === '.' ? -1 : parseInt(c);
      if (f.type === 'wins' && maxRound < f.round) {{ match = false; break; }}
      if (f.type === 'loses' && maxRound >= f.round) {{ match = false; break; }}
    }}
    if (!match) continue;
    n++;
    for (let p = 0; p < 8; p++) {{
      const ei = TOP8[s][p];
      if (ei >= 0) counts[ei][p]++;
    }}
  }}

  if (n === 0) {{
    document.getElementById('tableBody').innerHTML = '<tr><td colspan="10" style="text-align:center;color:#888;padding:20px">No simulations match these conditions</td></tr>';
    info.textContent = '0 matching simulations';
    document.getElementById('tableTitle').textContent = 'No matching simulations';
    return;
  }}

  const data = [];
  for (let i = 0; i < ENTRIES.length; i++) {{
    const total = counts[i].reduce((a,b) => a+b, 0);
    if (total / n >= 0.01) {{
      data.push({{
        name: ENTRIES[i],
        p: counts[i].map(v => +(v/n*100).toFixed(2)),
        top8: +(total/n*100).toFixed(1)
      }});
    }}
  }}
  data.sort((a,b) => b.top8 - a.top8);
  document.getElementById('tableBody').innerHTML = buildRows(data.slice(0, 15));

  // Build description
  const desc = active.map(f => {{
    const tname = TEAMS[f.teamIdx];
    const rname = ROUND_NAMES[ROUND_LABELS[f.round]];
    return f.type === 'wins' ? `${{tname}} wins ${{rname}}` : `${{tname}} eliminated before ${{rname}}`;
  }}).join(' + ');
  info.textContent = `Showing ${{n.toLocaleString()}} simulations where ${{desc}}`;
  document.getElementById('tableTitle').textContent = desc;
}}

function resetFilters() {{
  filters = [];
  renderFilterRows();
  document.getElementById('tableBody').innerHTML = buildRows(BASELINE);
  document.getElementById('filterInfo').textContent = '';
  document.getElementById('tableTitle').textContent = 'Top 8 Finish Probabilities (% of simulations)';
}}

// Initial render
document.getElementById('tableBody').innerHTML = buildRows(BASELINE);
</script>
</body>
</html>'''

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nUpdated {html_path}")


if __name__ == "__main__":
    main()
