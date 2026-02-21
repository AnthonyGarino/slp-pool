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
// Discovered by probing the standings API
const CONF_GROUPS = {
  ACC:        2,
  'Big East': 4,
  'Big Ten':  7,
  'Big 12':   8,
  SEC:        23,
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
// Once conf tournaments start, each win vs same-conf opponent in type-3 = +2
// Champion (most wins in type-3 same-conf games AND won final) = +5 bonus
// NCAA tournament seeding + wins also computed here
async function calcPostSeasonPoints(espnId, gid, standingsCache) {
  if (!espnId) return { confTournWins: 0, confTournTitle: false, ncaaSeeding: 0, ncaaWins: 0 };

  const sched = await get(
    `https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams/${espnId}/schedule?season=${SEASON}`
  );
  if (!sched || !sched.events) return { confTournWins: 0, confTournTitle: false, ncaaSeeding: 0, ncaaWins: 0 };

  // Build set of teammate IDs (same conference)
  const confTeamIds = new Set(
    gid && standingsCache[gid] ? Object.keys(standingsCache[gid]) : []
  );

  const postSeasonEvents = sched.events.filter(e => e.seasonType && e.seasonType.id === '3');

  let confTournWins  = 0;
  let confTournLast  = null; // 'W' or 'L' for last conf-tourn game
  let ncaaWins       = 0;
  let ncaaSeed       = 0;

  for (const ev of postSeasonEvents) {
    const comp    = ev.competitions[0];
    if (!comp || !comp.status || !comp.status.type.completed) continue;

    const me  = comp.competitors.find(c => c.id === espnId);
    const opp = comp.competitors.find(c => c.id !== espnId);
    if (!me || !opp) continue;

    const oppId   = opp.id;
    const iWon    = me.winner === true;
    const sameConf = confTeamIds.has(oppId);

    if (sameConf) {
      // Conference tournament game
      if (iWon) confTournWins++;
      confTournLast = iWon ? 'W' : 'L';
    } else {
      // NCAA tournament game
      if (iWon) ncaaWins++;
      // Get seed from team record if available
      if (!ncaaSeed && me.curatedRank && me.curatedRank.current) {
        ncaaSeed = me.curatedRank.current;
      }
    }
  }

  // Try to get playoff seed from team record
  if (!ncaaSeed && gid && standingsCache[gid] && standingsCache[gid][espnId]) {
    // Not available until Selection Sunday
  }

  // Conf tournament title: won last conf-tourn game and won 3+ games (most common conf tourn length)
  const confTournTitle = confTournLast === 'W' && confTournWins >= 1;

  // NCAA seeding points (only if we actually have a seed, i.e. tournament started)
  const seedPts = ncaaSeed === 0 ? 0 :
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
    ncaaSeed,
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
  console.log('📊 Fetching conference standings for ACC, Big East, Big Ten, Big 12, SEC...');
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
    let post = { confTournWins: 0, confTournTitle: false, ncaaSeeding: 0, ncaaWins: 0 };
    if (espnId) {
      post = await calcPostSeasonPoints(espnId, gid, standingsCache);
      await sleep(60);   // gentle rate limiting
    }

    const confTitlePts   = 0;  // determined per-conference below
    const confTournPts   = (post.confTournWins * 2) + (post.confTournTitle ? 5 : 0);
    const ncaaPts        = post.ncaaSeeding + post.ncaaWins;

    teamScore[name] = {
      basePoints:     reg.points,
      confTournPts,
      ncaaPts,
      totalPreTitle:  reg.points + confTournPts + ncaaPts,
      confW:          reg.confW  || 0,
      confL:          reg.confL  || 0,
      confWPct:       reg.confWPct || 0,
      gid,
      espnId,
      confTournWins:  post.confTournWins,
      confTournTitle: post.confTournTitle,
    };

    count++;
    if (count % 20 === 0) console.log(`   ... ${count}/${allNames.size} done`);
  }

  // ── Determine conference regular-season title holders per group ──────
  // For each conference group that appears, find highest confWPct
  const confLeaders = {};   // gid → maxWPct
  for (const [name, sc] of Object.entries(teamScore)) {
    const gid = sc.gid;
    if (!gid) continue;
    if (!confLeaders[gid] || sc.confWPct > confLeaders[gid]) {
      confLeaders[gid] = sc.confWPct;
    }
  }

  // Check if conference tournament has started (any team with confTournWins > 0)
  // Only award +5 title bonus after regular season is clinched
  const confTournStarted = {};
  for (const [name, sc] of Object.entries(teamScore)) {
    if (sc.gid && (sc.confTournWins || 0) > 0) {
      confTournStarted[sc.gid] = true;
    }
  }
  console.log('  Conf tournaments started (group IDs):', Object.keys(confTournStarted).join(', ') || 'none');

  // Award conf title bonus (+5) to leaders — only if conf tournament has started
  for (const [name, sc] of Object.entries(teamScore)) {
    const gid    = sc.gid;
    const isTitle = gid && sc.confWPct > 0 && sc.confWPct === confLeaders[gid];
    const tournOver = confTournStarted[gid] || false;
    sc.confTitlePts = (isTitle && tournOver) ? 5 : 0;
    sc.totalPoints  = sc.totalPreTitle + sc.confTitlePts;
    if (isTitle && tournOver) console.log(`  🏆 Conf title: ${name} (group ${gid}, WPct ${sc.confWPct.toFixed(3)})`);
    if (isTitle && !tournOver && sc.gid && Object.values(CONF_GROUPS).includes(sc.gid)) {
      // Only log pending for the 5 main pool conferences to reduce noise
      console.log(`  ⏳ Conf leader (pending): ${name} (group ${gid}, WPct ${sc.confWPct.toFixed(3)})`);
    }
  }

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
