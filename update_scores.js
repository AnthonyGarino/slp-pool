// update_scores.js
// Uses ESPN standings + team records to calculate SLP fantasy pool scores
// Run with: node update_scores.js

const https = require('https');
const fs    = require('fs');
const path  = require('path');

const DATA_PATH = path.join(__dirname, 'data.json');
const HTML_PATH = path.join(__dirname, 'index.html');
const SEASON    = '2026';

// ── ESPN Conference Group IDs ──────────────────────────────────────────
// All 31 active D1 conferences — pre-load standings for conf tournament detection
const CONF_GROUPS = {
  'America East':   1,
  ACC:              2,
  'A-10':           3,
  'Big East':       4,
  'Big Sky':        5,
  'Big South':      6,
  'Big Ten':        7,
  'Big 12':         8,
  'Big West':       9,
  CAA:              10,
  'C-USA':          11,
  'Ivy League':     12,
  MAAC:             13,
  MAC:              14,
  MEAC:             16,
  MVC:              18,
  NEC:              19,
  OVC:              20,
  'Patriot League': 22,
  SEC:              23,
  SoCon:            24,
  Southland:        25,
  SWAC:             26,
  'Sun Belt':       27,
  WCC:              29,
  WAC:              30,
  'Mountain West':  44,
  'Horizon League': 45,
  ASUN:             46,
  'Summit League':  49,
  AAC:              62,
};

// ── Manual name map: data.json name → ESPN team ID ────────────────────
const MANUAL_MAP = {
  'Uconn':               '41',
  'St Johns':            '2599',
  'St Bonaventure':      '179',
  'St Thomas MN':        '2900',
  'Saint Josephs':       '2603',
  'Saint Louis':         '139',
  'Saint Marys':         '2608',
  'Saint Peters':        '2612',
  'St Francis PA':       '2598',
  'CS Bakersfield':      '2934',
  'CS Fullerton':        '2239',
  'CS Northridge':       '2463',
  'Cal Poly':            '13',
  'SE Louisiana':        '2545',
  'Missouri State':      '2623',
  'SE Missouri State':   '2546',
  'SIU Edwardsville':    '2565',
  'Middle Tenn State':   '2393',
  'Ole Miss':            '145',
  'IPFW':                '2870',
  'IU Indy':             '85',
  'LIU Brooklyn':        '112358',
  'MD Eastern Shore':    '2378',
  'UL Monroe':           '2433',
  'Appalachian State':   '2026',
  'Texas A&M-CC':        '357',
  'Texas A&M-Commerce':  null,   // Not in ESPN D1
  'Queens NC':           null,   // Not in ESPN D1
  'LaSalle':             '2352',
  'Umass':               '113',
  'Umass Lowell':        '2349',
  'Utah Valley State':   '3084',
  'Incarnate Word':      '2916',
  'Sam Houston':         '2534',
  'Stephen F Austin':    '2617',
  'Arkansas Pine Bluff': '2029',
  'Green Bay':           '2739',
  'Omaha':               '2437',
  'Depaul':              '305',
  'DePaul':              '305',
  'UCF':                 '2116',
  'UAB':                 '2473',
  'VCU':                 '2670',
  'VMI':                 '2678',
  'UIC':                 '2285',
  'NJIT':                '2885',
  'UNLV':                '2439',
  'UTEP':                '2638',
  'UTSA':                '2636',
  'Umass Lowell':        '2349',
  'UNC Asheville':       '2427',
  'UNC Greensboro':      '2430',
  'UNC Wilmington':      '350',
  'UC Davis':            '302',
  'UC Irvine':           '300',
  'UC Santa Barbara':    '301',
  'Houston Christian':   '2277',
  'West Georgia':        '2698',
  'Merrimack':           '2771',
  // Teams whose ESPN name doesn't match by normalization
  'North Carolina State': '152',
  'McNeese State':       '2377',
  'San Jose State':      '23',
  'Grambling State':     '2755',
  'Nicholls State':      '2447',
  'Lindenwood':          null,   // New D1 team, not yet in ESPN database
  // Additional mappings for Excel team names
  'Miami OH':            '193',   // Miami (OH) RedHawks
  'American U':          '44',    // American University Eagles
  'Penn':                '219',   // Pennsylvania Quakers
  'East Texas A&M':      '2837',  // East Texas A&M Lions
  'Little Rock':         '2031',  // Little Rock Trojans
  'Prairie View':        '2504',  // Prairie View A&M Panthers
  'Gardner-Webb':        '2241',  // Gardner-Webb Bulldogs
  'East Tennessee State':'2193',  // ETSU Buccaneers
  'Charleston':          '232',   // College of Charleston
  'Loyola Chicago':      '2350',  // Loyola Chicago Ramblers
  'Chicago State':       '2130',  // Chicago State Cougars
  'CCSU':                '2115',  // Central Connecticut State
  'Bethune-Cookman':     '2065',  // Bethune-Cookman Wildcats
  'Southern Indiana':    '88',    // Southern Indiana Screaming Eagles
  'IU Indianapolis (IUPUI)': '85',// IU Indianapolis
};

// ── Helpers ───────────────────────────────────────────────────────────
function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'Mozilla/5.0' } }, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        try { resolve(JSON.parse(d)); }
        catch (e) { resolve(null); }
      });
    }).on('error', () => resolve(null));
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function normalize(s) {
  return (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
}

// ── Step 1: Build ESPN team-name → id map ─────────────────────────────
async function buildTeamIdMap(allNames) {
  const espnData = await get(
    'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams?limit=500'
  );
  const espnTeams = espnData.sports[0].leagues[0].teams.map(t => t.team);

  const idMap = {};
  const unmapped = [];

  for (const name of allNames) {
    // 1. Manual map
    if (name in MANUAL_MAP) {
      idMap[name] = MANUAL_MAP[name];  // may be null for non-D1
      continue;
    }

    const norm = normalize(name);

    // 2. Exact shortDisplayName match
    let match = espnTeams.find(t => normalize(t.shortDisplayName) === norm);
    // 3. displayName starts with name
    if (!match) match = espnTeams.find(t => normalize(t.displayName).startsWith(norm + ' '));
    // 4. displayName contains name
    if (!match) match = espnTeams.find(t => normalize(t.displayName).includes(norm));
    // 5. abbreviation match
    if (!match) match = espnTeams.find(t => t.abbreviation && normalize(t.abbreviation) === norm);

    if (match) {
      idMap[name] = match.id;
    } else {
      unmapped.push(name);
      idMap[name] = null;
    }
  }

  if (unmapped.length) {
    console.log(`  ⚠  Could not map ${unmapped.length} teams (will score 0): ${unmapped.join(', ')}`);
  }

  return idMap;
}

// ── Step 2: Build conference standings cache ───────────────────────────
// Returns { groupId: { teamId: { confW, confL, overallW, overallL } } }
async function buildStandingsCache(groupIds) {
  const cache = {};

  for (const gid of groupIds) {
    const d = await get(
      `https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings?group=${gid}`
    );
    if (!d || !d.standings || !d.standings.entries) continue;

    cache[gid] = {};
    for (const entry of d.standings.entries) {
      const tid = entry.team.id;
      const getStat = type => {
        const s = entry.stats.find(x => x.type === type || (x.name === type && !x.type.includes('_')));
        return s ? s.value : 0;
      };
      // Overall stats are the first group (no prefix), conf stats have vsconf_ prefix
      const overallW  = (entry.stats.find(s => s.type === 'wins')         || {value:0}).value;
      const overallL  = (entry.stats.find(s => s.type === 'losses')       || {value:0}).value;
      const confW     = (entry.stats.find(s => s.type === 'vsconf_wins')  || {value:0}).value;
      const confL     = (entry.stats.find(s => s.type === 'vsconf_losses')|| {value:0}).value;
      const confWPct  = (entry.stats.find(s => s.type === 'vsconf_winpercent') || {value: confW > 0 ? confW/(confW+confL) : 0}).value;
      cache[gid][tid] = { overallW, overallL, confW, confL, confWPct,
                          displayName: entry.team.displayName };
    }
    await sleep(80);
  }
  return cache;
}

// ── Step 3: For a given ESPN team ID, find which group it's in ─────────
// First check the cached groups, then fetch the team page for unknowns
const teamGroupCache = {};

async function getTeamGroup(teamId, standingsCache) {
  if (teamGroupCache[teamId]) return teamGroupCache[teamId];

  // Check already-loaded standings
  for (const [gid, teams] of Object.entries(standingsCache)) {
    if (teams[teamId]) {
      teamGroupCache[teamId] = Number(gid);
      return Number(gid);
    }
  }

  // Fetch team page to get groups.id
  const d = await get(
    `https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/${teamId}`
  );
  if (!d || !d.team || !d.team.groups) return null;
  const gid = Number(d.team.groups.id);
  teamGroupCache[teamId] = gid;

  // Fetch this group's standings if not cached
  if (!standingsCache[gid]) {
    const sd = await get(
      `https://site.api.espn.com/apis/v2/sports/basketball/mens-college-basketball/standings?group=${gid}`
    );
    if (sd && sd.standings && sd.standings.entries) {
      standingsCache[gid] = {};
      for (const entry of sd.standings.entries) {
        const tid     = entry.team.id;
        const overallW  = (entry.stats.find(s => s.type === 'wins')          || {value:0}).value;
        const overallL  = (entry.stats.find(s => s.type === 'losses')        || {value:0}).value;
        const confW     = (entry.stats.find(s => s.type === 'vsconf_wins')   || {value:0}).value;
        const confL     = (entry.stats.find(s => s.type === 'vsconf_losses') || {value:0}).value;
        const confWPct  = (entry.stats.find(s => s.type === 'vsconf_winpercent') || {value: confW > 0 ? confW/(confW+confL) : 0}).value;
        standingsCache[gid][tid] = { overallW, overallL, confW, confL, confWPct,
                                     displayName: entry.team.displayName };
      }
    }
    await sleep(80);
  }
  return gid;
}

// ── Step 4: Calculate score for one team ──────────────────────────────
async function calcTeamScore(dataName, espnId, standingsCache) {
  if (!espnId) return { points: 0, detail: 'unmapped' };

  // Find group and record
  const gid = await getTeamGroup(espnId, standingsCache);
  if (!gid || !standingsCache[gid] || !standingsCache[gid][espnId]) {
    // Fallback: fetch team record directly
    const td = await get(
      `https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/${espnId}`
    );
    if (!td || !td.team) return { points: 0, detail: 'no data' };
    const overall = td.team.record && td.team.record.items && td.team.record.items[0];
    if (!overall) return { points: 0, detail: 'no record' };
    const overallW = overall.stats.find(s => s.name === 'wins')   ? overall.stats.find(s => s.name === 'wins').value   : 0;
    // No conf split available → treat all as non-conf
    const pts = overallW * 1;
    return { points: pts, overallW, confW: 0, nonConfW: overallW, gid: null };
  }

  const rec = standingsCache[gid][espnId];
  const nonConfW = Math.max(0, rec.overallW - rec.confW);

  let pts = (rec.confW * 2) + (nonConfW * 1);

  return {
    points:   pts,
    overallW: rec.overallW,
    confW:    rec.confW,
    confL:    rec.confL,
    nonConfW,
    confWPct: rec.confWPct,
    gid,
  };
}

// ── Step 5: Conference tournament points (post-season) ────────────────
// Classifies post-season games by checking event name for "NCAA" keyword.
// Conf tournament: wins vs same-conf opponents in non-NCAA post-season games
// NCAA tournament: seeding + per-round win bonuses
async function calcPostSeasonPoints(espnId, gid, standingsCache) {
  const empty = { confTournWins: 0, confTournTitle: false, ncaaSeeding: 0, ncaaWins: 0, ncaaWinCount: 0, recentGames: [], nextGame: null };
  if (!espnId) return empty;

  const sched = await get(
    `https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/${espnId}/schedule?season=${SEASON}`
  );
  if (!sched || !sched.events) return empty;

  // ── Extract last 5 completed games + next upcoming game ──
  const allEvents = sched.events;
  const completedGames = allEvents
    .filter(e => e.competitions && e.competitions[0] && e.competitions[0].status && e.competitions[0].status.type.completed)
    .sort((a, b) => new Date(b.date) - new Date(a.date))
    .slice(0, 5)
    .reverse();

  const recentGames = completedGames.map(ev => {
    const comp = ev.competitions[0];
    const me  = comp.competitors.find(c => c.id === espnId);
    const opp = comp.competitors.find(c => c.id !== espnId);
    const myScore  = me && me.score ? (me.score.displayValue || me.score.value || me.score) : '?';
    const oppScore = opp && opp.score ? (opp.score.displayValue || opp.score.value || opp.score) : '?';
    return {
      result:   me && me.winner ? 'W' : 'L',
      opponent: (opp && opp.team && opp.team.shortDisplayName) || '?',
      score:    `${myScore}-${oppScore}`,
    };
  });

  const upcoming = allEvents
    .filter(e => e.competitions && e.competitions[0] && e.competitions[0].status && !e.competitions[0].status.type.completed && new Date(e.date) > new Date())
    .sort((a, b) => new Date(a.date) - new Date(b.date));
  const nextEv = upcoming[0] || null;
  let nextGame = null;
  if (nextEv && nextEv.competitions && nextEv.competitions[0]) {
    const comp = nextEv.competitions[0];
    const opp  = comp.competitors ? comp.competitors.find(c => c.id !== espnId) : null;
    nextGame = {
      opponent: (opp && opp.team && opp.team.shortDisplayName) || 'TBD',
      date:     new Date(nextEv.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    };
  }

  // Build set of teammate IDs (same conference)
  const confTeamIds = new Set(
    gid && standingsCache[gid] ? Object.keys(standingsCache[gid]) : []
  );

  // Find post-season events: ESPN seasonType 3, OR regular-season events
  // with notes indicating a conference tournament/championship (ESPN often classifies
  // conf tournament games as seasonType 2). Notes patterns seen in practice:
  //   "West Coast Conference Tournament - Semifinal"
  //   "ACC Men's Basketball Tournament - Quarterfinal"
  //   "Big East Tournament - Final"
  // Date filter: only after Feb 15 to avoid early-season events like "Baha Mar Championship".
  const confTournCutoff = new Date(`${SEASON}-02-15`);
  const postSeasonEvents = sched.events.filter(e => {
    if (e.seasonType && e.seasonType.id === '3') return true;
    // Check notes for conference tournament/championship indicators (after Feb 15 only)
    if (new Date(e.date) >= confTournCutoff) {
      const notes = (e.competitions && e.competitions[0] && e.competitions[0].notes &&
                     e.competitions[0].notes[0] && e.competitions[0].notes[0].headline) || '';
      // Match "championship" OR "Tournament -" (the dash distinguishes conf tournaments
      // from the National Invitation Tournament which has no dash in its notes)
      if (/championship|tournament\s*[-–]/i.test(notes)) return true;
    }
    return false;
  });

  let confTournWins  = 0;
  let confTournLast  = null; // 'W' or 'L' for last conf-tourn game
  let wonChampGame   = false; // true only if won a game with "Final" or "Championship Game" in notes
  let ncaaWins       = 0;
  let ncaaSeed       = 0;
  let isPlayInTeam   = false; // true if team played in First Four
  let wonPlayIn      = false; // true if team won their First Four game

  for (const ev of postSeasonEvents) {
    const comp    = ev.competitions[0];
    if (!comp || !comp.status || !comp.status.type.completed) continue;

    const me  = comp.competitors.find(c => c.id === espnId);
    const opp = comp.competitors.find(c => c.id !== espnId);
    if (!me || !opp) continue;

    const oppId   = opp.id;
    const iWon    = me.winner === true;

    // Classify: check event name/notes for "NCAA" to distinguish from conf tournament
    const evName  = (ev.name || '').toLowerCase();
    const evNotes = ((comp.notes && comp.notes[0] && comp.notes[0].headline) || '').toLowerCase();
    const isNCAA  = evName.includes('ncaa') || evNotes.includes('ncaa');
    const isFirstFour = isNCAA && evNotes.includes('first four');

    if (isNCAA) {
      // Get seed — check multiple possible ESPN fields
      if (!ncaaSeed) {
        if (me.curatedRank && me.curatedRank.current) ncaaSeed = me.curatedRank.current;
        else if (me.seed) ncaaSeed = me.seed;
      }

      if (isFirstFour) {
        // Play-in game: no win points, but track result for seeding eligibility
        isPlayInTeam = true;
        if (iWon) wonPlayIn = true;
      } else {
        // Regular NCAA tournament game
        if (iWon) ncaaWins++;
      }
    } else if (confTeamIds.has(oppId) || /championship|tournament\s*[-–]/i.test(evNotes)) {
      // Conference tournament game: either same-conf opponent in post-season,
      // or notes indicate a conference tournament/championship game
      if (iWon) {
        confTournWins++;
        // Check if this was the championship/final game
        // Match "Final" as a standalone word (not "Semifinal" or "Quarterfinal")
        if (/\bfinal\b/i.test(evNotes) || evNotes.includes('championship game')) {
          wonChampGame = true;
        }
      }
      confTournLast = iWon ? 'W' : 'L';
    }
    // else: other post-season games (NIT, CBI, etc.) — no points
  }

  // Conf tournament title: won the championship game (Final) of the tournament.
  // wonChampGame is set when the team wins a game with "Final" or "Championship Game"
  // in the notes. Fallback: confTournLast === 'W' for seasonType 3 events that
  // may not have descriptive notes (combined with most-wins check in main loop).
  const confTournTitle = wonChampGame;

  // NCAA seeding points (only if we actually have a seed, i.e. tournament started)
  // Play-in teams only get seeding points if they won their First Four game
  const seedPts = ncaaSeed === 0 ? 0 :
                  (isPlayInTeam && !wonPlayIn) ? 0 :
                  ncaaSeed === 1 ? 8 :
                  ncaaSeed <= 4  ? 6 :
                  ncaaSeed <= 8  ? 4 :
                  ncaaSeed <= 16 ? 2 : 0;

  // NCAA win points by round (count of wins → round)
  const roundPts = [2, 4, 6, 8, 10, 12];
  let ncaaWinPts = 0;
  for (let i = 0; i < Math.min(ncaaWins, 6); i++) ncaaWinPts += roundPts[i];

  return {
    confTournWins,
    confTournTitle,
    ncaaSeeding: seedPts,
    ncaaWins:    ncaaWinPts,
    ncaaWinCount: ncaaWins,   // raw count (for deducting from base)
    ncaaSeed,
    recentGames,
    nextGame,
  };
}

// ── MAIN ──────────────────────────────────────────────────────────────
async function main() {
  console.log('\n🏀 SLP Score Updater — Season 2025-26\n');

  // Load data.json
  const data = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));

  // Collect all unique team names
  const allNames = new Set();
  for (const entry of data.entries) {
    for (const pick of Object.values(entry.picks)) allNames.add(pick.team);
    for (const wc of entry.wildcards)              allNames.add(wc.team);
  }
  console.log(`📋 ${allNames.size} unique teams to score`);

  // Build team name → ESPN ID map
  console.log('🔍 Mapping team names to ESPN IDs...');
  const idMap = await buildTeamIdMap(allNames);

  // Pre-load standings for the 5 contest conferences
  console.log('📊 Fetching conference standings for all 31 D1 conferences...');
  const standingsCache = await buildStandingsCache(Object.values(CONF_GROUPS));

  // Calculate score for each unique team
  console.log('⚙️  Calculating scores for all teams...');
  const teamScore  = {};   // name → { points, confTournTitle, ... }
  const processed  = new Set();
  let count = 0;

  for (const name of allNames) {
    if (processed.has(name)) continue;
    processed.add(name);

    const espnId = idMap[name];
    const reg    = await calcTeamScore(name, espnId, standingsCache);
    const gid    = reg.gid || null;

    // Post-season (conf tournament + NCAA) — only fetch if needed
    let post = { confTournWins: 0, confTournTitle: false, ncaaSeeding: 0, ncaaWins: 0, ncaaWinCount: 0 };
    if (espnId) {
      post = await calcPostSeasonPoints(espnId, gid, standingsCache);
      await sleep(60);   // gentle rate limiting
    }

    const confTournWinPts = post.confTournWins * 2;  // +2 per conf tourn win
    const ncaaPts         = post.ncaaSeeding + post.ncaaWins;

    // ESPN overallW includes post-season wins (conf tournament + NCAA),
    // so subtract them from base to avoid double-counting with bonus pts.
    // Post-season wins should ONLY score via their bonus categories, not also as regular wins.
    const postSeasonWins = post.confTournWins + post.ncaaWinCount;
    const adjustedBase = reg.points - (postSeasonWins * 1);  // remove 1pt per post-season win

    teamScore[name] = {
      basePoints:     adjustedBase,
      confTournWinPts,
      confTournTitlePts: 0,   // determined per-conference below
      ncaaPts,
      ncaaSeedPts:    post.ncaaSeeding,   // separated for breakdown tooltip
      ncaaWinPts:     post.ncaaWins,      // separated for breakdown tooltip
      totalPreTitle:  adjustedBase + confTournWinPts + ncaaPts,
      confW:          reg.confW  || 0,
      confL:          reg.confL  || 0,
      confWPct:       reg.confWPct || 0,
      gid,
      espnId,
      confTournWins:  post.confTournWins,
      confTournTitle: post.confTournTitle,  // per-team flag (won last + has wins)
      recentGames:    post.recentGames || [],
      nextGame:       post.nextGame || null,
    };

    count++;
    if (count % 20 === 0) console.log(`   ... ${count}/${allNames.size} done`);
  }

  // ── Determine conference regular-season title holders per group ──────
  // Use full standings data — not just picked teams — so the true conference
  // leader is found even if that team wasn't picked by anyone.
  const confLeaders = {};   // gid → maxWPct
  for (const [gidStr, teams] of Object.entries(standingsCache)) {
    const gid = Number(gidStr);
    for (const [tid, rec] of Object.entries(teams)) {
      if (rec.confWPct > 0 && (!confLeaders[gid] || rec.confWPct > confLeaders[gid])) {
        confLeaders[gid] = rec.confWPct;
      }
    }
  }

  // Count ALL teams in each conference that share the lead (not just picked teams),
  // so tie-breaking (+3 vs +2) reflects the actual conference standings.
  const confTitleCount = {};   // gid → number of teams tied for best WPct
  for (const [gidStr, teams] of Object.entries(standingsCache)) {
    const gid = Number(gidStr);
    if (!confLeaders[gid]) continue;
    for (const [tid, rec] of Object.entries(teams)) {
      if (rec.confWPct > 0 && rec.confWPct === confLeaders[gid]) {
        confTitleCount[gid] = (confTitleCount[gid] || 0) + 1;
      }
    }
  }

  // Clinch detection: award title points when the outcome is decided.
  // Uses max games played in the conference as a proxy for total schedule length.
  // Two cases: (A) sole leader who can't be caught even in worst case,
  //            (B) tied leaders who have all finished their conference schedule.
  const confClinched = {};
  for (const [gidStr, teams] of Object.entries(standingsCache)) {
    const gid = Number(gidStr);
    if (!confLeaders[gid]) { confClinched[gid] = false; continue; }

    const leaderWPct = confLeaders[gid];
    const tiedCount  = confTitleCount[gid] || 1;
    let maxGamesPlayed = 0;
    for (const rec of Object.values(teams)) {
      const gp = rec.confW + rec.confL;
      if (gp > maxGamesPlayed) maxGamesPlayed = gp;
    }

    if (tiedCount > 1) {
      // Multiple teams tied for the lead — clinch only if ALL tied leaders
      // have completed their conference schedule (no remaining games)
      let allDone = true;
      for (const [tid, rec] of Object.entries(teams)) {
        if (rec.confWPct === leaderWPct) {
          const gp = rec.confW + rec.confL;
          if (gp < maxGamesPlayed) { allDone = false; break; }
        }
      }
      confClinched[gid] = allDone;
    } else {
      // Sole leader — clinch if no chaser can catch the leader's WORST case.
      // Leader's worst case: they lose all remaining games.
      const leaderRec = Object.values(teams).find(r => r.confWPct === leaderWPct);
      const leaderGP  = leaderRec.confW + leaderRec.confL;
      const leaderWorstW = leaderRec.confW;  // loses all remaining
      // Leader's worst WPct when all teams have played maxGamesPlayed games
      const leaderWorstWPct = maxGamesPlayed > 0 ? leaderWorstW / maxGamesPlayed : 0;

      let anyoneCanCatch = false;
      for (const [tid, rec] of Object.entries(teams)) {
        if (rec.confWPct === leaderWPct) continue;
        const gp        = rec.confW + rec.confL;
        const remaining = Math.max(0, maxGamesPlayed - gp);
        const bestPossible = maxGamesPlayed > 0 ? (rec.confW + remaining) / maxGamesPlayed : 0;
        if (bestPossible >= leaderWorstWPct) { anyoneCanCatch = true; break; }
      }
      confClinched[gid] = !anyoneCanCatch;
    }
  }

  // Check if conference tournament has started (any picked team with confTournWins > 0)
  const confTournStarted = {};
  for (const [name, sc] of Object.entries(teamScore)) {
    if (sc.gid && (sc.confTournWins || 0) > 0) {
      confTournStarted[sc.gid] = true;
    }
  }
  console.log('  Conf titles clinched (group IDs):', Object.keys(confClinched).filter(g => confClinched[Number(g)]).join(', ') || 'none');
  console.log('  Conf tournaments started (group IDs):', Object.keys(confTournStarted).join(', ') || 'none');

  // Award conf title bonus if clinched OR tournament has started.
  // Tie rules: sole winner = +5, 2-way tie = +3 each, 3+ way tie = +2 each
  for (const [name, sc] of Object.entries(teamScore)) {
    const gid        = sc.gid;
    const isTitle    = gid && sc.confWPct > 0 && sc.confWPct === confLeaders[gid];
    const titleLocked = confClinched[gid] || confTournStarted[gid] || false;

    if (isTitle && titleLocked) {
      const tiedCount = confTitleCount[gid] || 1;
      sc.confTitlePts = tiedCount === 1 ? 5 : tiedCount === 2 ? 3 : 2;
      console.log(`  🏆 Conf title: ${name} (group ${gid}, WPct ${sc.confWPct.toFixed(3)}, ${tiedCount}-way${tiedCount > 1 ? ' tie → +' + sc.confTitlePts : ' → +5'})`);
    } else {
      sc.confTitlePts = 0;
      if (isTitle && !titleLocked && Object.values(CONF_GROUPS).includes(sc.gid)) {
        console.log(`  ⏳ Conf leader (pending): ${name} (group ${gid}, WPct ${sc.confWPct.toFixed(3)})`);
      }
    }
    sc.totalPoints = sc.totalPreTitle + sc.confTitlePts + sc.confTournTitlePts;
  }

  // ── Determine conference tournament champions per group ──────────────
  // The champion is the team with the most conf tournament wins who also
  // won their last conf tournament game. Only one team per conference.
  const confTournChampions = {};  // gid → { name, wins }
  for (const [name, sc] of Object.entries(teamScore)) {
    if (!sc.gid || !sc.confTournTitle) continue;  // didn't win last game
    const gid = sc.gid;
    if (!confTournChampions[gid] || sc.confTournWins > confTournChampions[gid].wins) {
      confTournChampions[gid] = { name, wins: sc.confTournWins };
    }
  }
  // Award +5 conf tournament title to confirmed champions
  for (const [gid, champ] of Object.entries(confTournChampions)) {
    const sc = teamScore[champ.name];
    sc.confTournTitlePts = 5;
    sc.totalPoints += 5;
    console.log(`  🏆 Conf tourn champ: ${champ.name} (group ${gid}, ${champ.wins} wins)`);
  }

  // ── Build team breakdowns for frontend tooltip ─────────────────────
  data.teamBreakdowns = {};
  for (const [name, sc] of Object.entries(teamScore)) {
    data.teamBreakdowns[name] = {
      confW:             sc.confW,
      nonConfW:          sc.basePoints - (sc.confW * 2),
      confTitlePts:      sc.confTitlePts || 0,
      confTournWinPts:   sc.confTournWinPts || 0,
      confTournTitlePts: sc.confTournTitlePts || 0,
      ncaaSeedPts:       sc.ncaaSeedPts || 0,
      ncaaWinPts:        sc.ncaaWinPts || 0,
      totalPoints:       sc.totalPoints,
      recentGames:       sc.recentGames || [],
      nextGame:          sc.nextGame || null,
    };
  }
  console.log(`📊 Built scoring breakdowns for ${Object.keys(data.teamBreakdowns).length} teams`);

  // ── Save previous ranks for movement tracking ───────────────────────
  // Rank entries by current score before overwriting
  const prevSorted = [...data.entries].sort((a, b) => (b.score || 0) - (a.score || 0));
  let prevRank = 1;
  prevSorted.forEach((e, i) => {
    const prevScore = e.score || 0;
    if (i > 0 && prevScore < (prevSorted[i-1].score || 0)) prevRank = i + 1;
    e.previousRank = prevRank;
  });

  // ── Update entries in data.json ───────────────────────────────────────
  console.log('\n✏️  Updating data.json entries...');
  let totalUpdated = 0;

  for (const entry of data.entries) {
    let entryScore = 0;

    // Update conference picks
    for (const [conf, pick] of Object.entries(entry.picks)) {
      const sc = teamScore[pick.team];
      const pts = sc ? sc.totalPoints : 0;
      pick.points = pts;
      entryScore += pts;
    }

    // Update wildcards — score all 6, then drop the 1 lowest
    for (const wc of entry.wildcards) {
      const sc = teamScore[wc.team];
      wc.points = sc ? sc.totalPoints : 0;
      wc.counts = true;  // reset
    }

    // Find the lowest-scoring wildcard and mark it as dropped
    if (entry.wildcards.length > 0) {
      let minPts = Infinity, minIdx = -1;
      entry.wildcards.forEach((wc, i) => {
        if (wc.points < minPts) { minPts = wc.points; minIdx = i; }
      });
      if (minIdx >= 0) entry.wildcards[minIdx].counts = false;
    }

    // Sum only the 5 wildcards that count
    for (const wc of entry.wildcards) {
      if (wc.counts) entryScore += wc.points;
    }

    entry.score = entryScore;
    totalUpdated++;
  }

  // Sort entries by score descending
  data.entries.sort((a, b) => b.score - a.score);

  // Update lastUpdated
  const today = new Date();
  data.lastUpdated = today.toISOString().slice(0, 10);

  console.log(`✅ Updated ${totalUpdated} entries`);

  // ── Save data.json ────────────────────────────────────────────────────
  const jsonStr = JSON.stringify(data);
  fs.writeFileSync(DATA_PATH, JSON.stringify(data, null, 2), 'utf8');
  console.log('💾 Saved data.json');

  // ── Re-embed into index.html ──────────────────────────────────────────
  // Use brace-counting to find and replace the entire const DATA = {...}; block
  // This correctly handles multi-line old data AND single-line new data
  let html = fs.readFileSync(HTML_PATH, 'utf8');

  const constDataMarker = 'const DATA = ';
  const startIdx = html.indexOf(constDataMarker);
  if (startIdx >= 0) {
    const jsonStart = startIdx + constDataMarker.length;
    // Count braces to find the matching closing brace
    let depth = 0, pos = jsonStart;
    while (pos < html.length) {
      if (html[pos] === '{')      depth++;
      else if (html[pos] === '}') { depth--; if (depth === 0) { pos++; break; } }
      pos++;
    }
    // Skip optional semicolon after closing brace
    if (html[pos] === ';') pos++;
    // Replace from constDataMarker to end of old JSON (including any trailing `;`)
    html = html.slice(0, startIdx) + constDataMarker + jsonStr + ';' + html.slice(pos);
    fs.writeFileSync(HTML_PATH, html, 'utf8');
    console.log('💾 Re-embedded data into index.html');
  } else {
    console.warn('⚠  Could not find const DATA in index.html — HTML not updated');
  }

  // ── Print top 10 ──────────────────────────────────────────────────────
  console.log('\n🏅 TOP 10 SCORES\n' + '═'.repeat(50));
  const top10 = data.entries.slice(0, 10);
  top10.forEach((e, i) => {
    console.log(`${String(i+1).padStart(2)}. ${e.name.padEnd(30)} ${String(e.score).padStart(4)} pts`);
  });
  console.log('═'.repeat(50));
  console.log(`\n✅ Done! Last updated: ${data.lastUpdated}\n`);
}

main().catch(err => { console.error('Fatal:', err); process.exit(1); });
