const state = {
  players: [],
  teams: [],
  pitchers: [],
  datasets: {},
  datasetSources: [],
  sourceCapabilities: [],
  dataNeeds: { missing: [], useful: [] },
  espnEvents: [],
  selectedPlayerId: "",
  selectedPitcherKey: "",
  recentOpponentCode: "",
  boardMode: "batters",
  playerSort: { key: "ops", direction: "desc" },
};

const els = {
  csvFile: document.querySelector("#csvFile"),
  csvType: document.querySelector("#csvType"),
  csvHintTitle: document.querySelector("#csvHintTitle"),
  csvHintDescription: document.querySelector("#csvHintDescription"),
  csvHintColumns: document.querySelector("#csvHintColumns"),
  datasetGuide: document.querySelector("#datasetGuide"),
  uploadLabel: document.querySelector("#uploadLabel"),
  datasetUrl: document.querySelector("#datasetUrl"),
  datasetUrls: document.querySelector("#datasetUrls"),
  urlImportButton: document.querySelector("#urlImportButton"),
  bulkUrlImportButton: document.querySelector("#bulkUrlImportButton"),
  refreshSourcesButton: document.querySelector("#refreshSourcesButton"),
  sourceList: document.querySelector("#sourceList"),
  datasetList: document.querySelector("#datasetList"),
  playerControl: document.querySelector("#playerControl"),
  playerSearch: document.querySelector("#playerSearch"),
  playerSearchResults: document.querySelector("#playerSearchResults"),
  playerSelect: document.querySelector("#playerSelect"),
  teamSearch: document.querySelector("#teamSearch"),
  teamSearchResults: document.querySelector("#teamSearchResults"),
  targetSelect: document.querySelector("#targetSelect"),
  opponentSelect: document.querySelector("#opponentSelect"),
  pitcherControlLabel: document.querySelector("#pitcherControlLabel"),
  pitcherSearch: document.querySelector("#pitcherSearch"),
  pitcherSearchResults: document.querySelector("#pitcherSearchResults"),
  pitcherSelect: document.querySelector("#pitcherSelect"),
  lineControl: document.querySelector("#lineControl"),
  propLine: document.querySelector("#propLine"),
  americanOdds: document.querySelector("#americanOdds"),
  adjustment: document.querySelector("#adjustment"),
  adjustmentValue: document.querySelector("#adjustmentValue"),
  predictButton: document.querySelector("#predictButton"),
  modelRefreshSeason: document.querySelector("#modelRefreshSeason"),
  modelRefreshDate: document.querySelector("#modelRefreshDate"),
  modelRefreshReset: document.querySelector("#modelRefreshReset"),
  modelRefreshTeamLogs: document.querySelector("#modelRefreshTeamLogs"),
  modelRefreshButton: document.querySelector("#modelRefreshButton"),
  modelRefreshStatus: document.querySelector("#modelRefreshStatus"),
  modelRefreshResults: document.querySelector("#modelRefreshResults"),
  cardOneLabel: document.querySelector("#cardOneLabel"),
  cardOneValue: document.querySelector("#cardOneValue"),
  cardTwoLabel: document.querySelector("#cardTwoLabel"),
  cardTwoValue: document.querySelector("#cardTwoValue"),
  cardThreeLabel: document.querySelector("#cardThreeLabel"),
  cardThreeValue: document.querySelector("#cardThreeValue"),
  matchupLabel: document.querySelector("#matchupLabel"),
  playerName: document.querySelector("#playerName"),
  teamLabel: document.querySelector("#teamLabel"),
  gamesLabel: document.querySelector("#gamesLabel"),
  abGameLabel: document.querySelector("#abGameLabel"),
  baLabel: document.querySelector("#baLabel"),
  opsLabel: document.querySelector("#opsLabel"),
  contactLabel: document.querySelector("#contactLabel"),
  team: document.querySelector("#team"),
  games: document.querySelector("#games"),
  abGame: document.querySelector("#abGame"),
  ba: document.querySelector("#ba"),
  ops: document.querySelector("#ops"),
  contact: document.querySelector("#contact"),
  dataAdjustment: document.querySelector("#dataAdjustment"),
  totalAdjustment: document.querySelector("#totalAdjustment"),
  marketImplied: document.querySelector("#marketImplied"),
  marketFairOdds: document.querySelector("#marketFairOdds"),
  marketEv: document.querySelector("#marketEv"),
  marketEdge: document.querySelector("#marketEdge"),
  matchupPa: document.querySelector("#matchupPa"),
  matchupWoba: document.querySelector("#matchupWoba"),
  matchupXwoba: document.querySelector("#matchupXwoba"),
  matchupBarrel: document.querySelector("#matchupBarrel"),
  matchupWhiff: document.querySelector("#matchupWhiff"),
  matchupKRate: document.querySelector("#matchupKRate"),
  matchupHr: document.querySelector("#matchupHr"),
  matchupOps: document.querySelector("#matchupOps"),
  matchupNote: document.querySelector("#matchupNote"),
  matchupPanel: document.querySelector(".matchup-panel"),
  teamMatchupPanel: document.querySelector("#teamMatchupPanel"),
  teamMatchupRecord: document.querySelector("#teamMatchupRecord"),
  teamMatchupWinRate: document.querySelector("#teamMatchupWinRate"),
  teamMatchupLast5: document.querySelector("#teamMatchupLast5"),
  teamMatchupRunDiff: document.querySelector("#teamMatchupRunDiff"),
  teamMatchupRuns: document.querySelector("#teamMatchupRuns"),
  teamMatchupOps: document.querySelector("#teamMatchupOps"),
  teamMatchupHr: document.querySelector("#teamMatchupHr"),
  teamMatchupKRate: document.querySelector("#teamMatchupKRate"),
  teamMatchupNote: document.querySelector("#teamMatchupNote"),
  environmentPanel: document.querySelector("#environmentPanel"),
  envVenue: document.querySelector("#envVenue"),
  envRoof: document.querySelector("#envRoof"),
  envTemp: document.querySelector("#envTemp"),
  envWind: document.querySelector("#envWind"),
  envParkFactor: document.querySelector("#envParkFactor"),
  envHitFactor: document.querySelector("#envHitFactor"),
  envHrFactor: document.querySelector("#envHrFactor"),
  envKFactor: document.querySelector("#envKFactor"),
  environmentNote: document.querySelector("#environmentNote"),
  recentFormPanel: document.querySelector("#recentFormPanel"),
  last5Avg: document.querySelector("#last5Avg"),
  last5Hits: document.querySelector("#last5Hits"),
  last10Avg: document.querySelector("#last10Avg"),
  lastOppAvg: document.querySelector("#lastOppAvg"),
  recentFormNote: document.querySelector("#recentFormNote"),
  recentOpponentSearch: document.querySelector("#recentOpponentSearch"),
  recentOpponentSearchResults: document.querySelector("#recentOpponentSearchResults"),
  recentOpponentRows: document.querySelector("#recentOpponentRows"),
  batterHrPanel: document.querySelector("#batterHrPanel"),
  batterHrTotal: document.querySelector("#batterHrTotal"),
  batterHrPerGame: document.querySelector("#batterHrPerGame"),
  batterHrRate: document.querySelector("#batterHrRate"),
  batterPaPerHr: document.querySelector("#batterPaPerHr"),
  batterHrSlug: document.querySelector("#batterHrSlug"),
  batterMatchupHr: document.querySelector("#batterMatchupHr"),
  batterMatchupBarrel: document.querySelector("#batterMatchupBarrel"),
  pitcherHrAllowedRate: document.querySelector("#pitcherHrAllowedRate"),
  advancedContextPanel: document.querySelector("#advancedContextPanel"),
  advXba: document.querySelector("#advXba"),
  advXslg: document.querySelector("#advXslg"),
  advXwoba: document.querySelector("#advXwoba"),
  advBarrel: document.querySelector("#advBarrel"),
  advHardHit: document.querySelector("#advHardHit"),
  advLast7K: document.querySelector("#advLast7K"),
  advSplit: document.querySelector("#advSplit"),
  advAdjustment: document.querySelector("#advAdjustment"),
  advancedContextNote: document.querySelector("#advancedContextNote"),
  pitcherProfilePanel: document.querySelector("#pitcherProfilePanel"),
  profileEra: document.querySelector("#profileEra"),
  profileWhip: document.querySelector("#profileWhip"),
  profileK9: document.querySelector("#profileK9"),
  profileBb9: document.querySelector("#profileBb9"),
  profileHr9: document.querySelector("#profileHr9"),
  profileH9: document.querySelector("#profileH9"),
  profileKGame: document.querySelector("#profileKGame"),
  profileRunsGame: document.querySelector("#profileRunsGame"),
  pitcherProfileNote: document.querySelector("#pitcherProfileNote"),
  strikeoutPanel: document.querySelector("#strikeoutPanel"),
  pitcherKRate: document.querySelector("#pitcherKRate"),
  opponentKRate: document.querySelector("#opponentKRate"),
  expectedBf: document.querySelector("#expectedBf"),
  expectedIp: document.querySelector("#expectedIp"),
  strikeoutRows: document.querySelector("#strikeoutRows"),
  missingDataList: document.querySelector("#missingDataList"),
  usefulDataList: document.querySelector("#usefulDataList"),
  modelNote: document.querySelector("#modelNote"),
  playerRows: document.querySelector("#playerRows"),
  search: document.querySelector("#search"),
  boardMode: document.querySelector("#boardMode"),
  playerBoardHead: document.querySelector("#playerBoardHead"),
  sortHeaders: document.querySelectorAll(".sort-header"),
  propBoardInputType: document.querySelector("#propBoardInputType"),
  propBoardDate: document.querySelector("#propBoardDate"),
  propBoardRecentGames: document.querySelector("#propBoardRecentGames"),
  propBoardText: document.querySelector("#propBoardText"),
  propBoardButton: document.querySelector("#propBoardButton"),
  propBoardStatus: document.querySelector("#propBoardStatus"),
  propBoardSummary: document.querySelector("#propBoardSummary"),
  propBoardMeta: document.querySelector("#propBoardMeta"),
  propBoardRows: document.querySelector("#propBoardRows"),
  propParlayRows: document.querySelector("#propParlayRows"),
  githubRepository: document.querySelector("#githubRepository"),
  githubButton: document.querySelector("#githubButton"),
  githubStatus: document.querySelector("#githubStatus"),
  githubRepoName: document.querySelector("#githubRepoName"),
  githubRepoMeta: document.querySelector("#githubRepoMeta"),
  githubRunRows: document.querySelector("#githubRunRows"),
  mlbPlayerName: document.querySelector("#mlbPlayerName"),
  mlbSeason: document.querySelector("#mlbSeason"),
  mlbButton: document.querySelector("#mlbButton"),
  mlbStatus: document.querySelector("#mlbStatus"),
  mlbPlayerResult: document.querySelector("#mlbPlayerResult"),
  mlbMeta: document.querySelector("#mlbMeta"),
  mlbGames: document.querySelector("#mlbGames"),
  mlbPa: document.querySelector("#mlbPa"),
  mlbAb: document.querySelector("#mlbAb"),
  mlbHits: document.querySelector("#mlbHits"),
  mlbHr: document.querySelector("#mlbHr"),
  mlbAvg: document.querySelector("#mlbAvg"),
  mlbSlg: document.querySelector("#mlbSlg"),
  mlbOps: document.querySelector("#mlbOps"),
  mlbCommand: document.querySelector("#mlbCommand"),
  mlbCommandPlayer: document.querySelector("#mlbCommandPlayer"),
  mlbCommandOpponent: document.querySelector("#mlbCommandOpponent"),
  mlbCommandTeam: document.querySelector("#mlbCommandTeam"),
  mlbCommandStats: document.querySelector("#mlbCommandStats"),
  mlbCommandGroups: document.querySelector("#mlbCommandGroups"),
  mlbCommandDate: document.querySelector("#mlbCommandDate"),
  mlbCommandGameId: document.querySelector("#mlbCommandGameId"),
  mlbCommandSportId: document.querySelector("#mlbCommandSportId"),
  mlbCommandLeagueId: document.querySelector("#mlbCommandLeagueId"),
  mlbCommandDivisionId: document.querySelector("#mlbCommandDivisionId"),
  mlbCommandAwardId: document.querySelector("#mlbCommandAwardId"),
  mlbCommandVenue: document.querySelector("#mlbCommandVenue"),
  mlbCommandLimit: document.querySelector("#mlbCommandLimit"),
  mlbCommandButton: document.querySelector("#mlbCommandButton"),
  mlbCommandHint: document.querySelector("#mlbCommandHint"),
  mlbCommandOutput: document.querySelector("#mlbCommandOutput"),
  espnDate: document.querySelector("#espnDate"),
  espnScoresButton: document.querySelector("#espnScoresButton"),
  espnTeamSelect: document.querySelector("#espnTeamSelect"),
  espnTeamButton: document.querySelector("#espnTeamButton"),
  espnStatus: document.querySelector("#espnStatus"),
  espnSummary: document.querySelector("#espnSummary"),
  espnMeta: document.querySelector("#espnMeta"),
  espnTeamName: document.querySelector("#espnTeamName"),
  espnTeamAbbr: document.querySelector("#espnTeamAbbr"),
  espnTeamId: document.querySelector("#espnTeamId"),
  espnTeamFallback: document.querySelector("#espnTeamFallback"),
  espnScoreRows: document.querySelector("#espnScoreRows"),
};

function pct(value) {
  return `${Math.round(value * 100)}%`;
}

function dec(value, digits = 3) {
  return Number(value || 0).toFixed(digits).replace(/^0/, "");
}

function signedNumber(value, digits = 0) {
  const number = Number(value || 0);
  return `${number > 0 ? "+" : ""}${number.toFixed(digits)}`;
}

function american(value) {
  const number = Math.round(Number(value || 0));
  return `${number > 0 ? "+" : ""}${number}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function withActionHeader(options = {}) {
  const next = { ...options };
  if (String(next.method || "GET").toUpperCase() === "POST") {
    const headers = new Headers(next.headers || {});
    headers.set("X-Baseball-Prop-Action", "1");
    next.headers = headers;
  }
  return next;
}

function cleanLookupText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/gi, " ")
    .trim()
    .toLowerCase();
}

const teamAliases = {
  CWS: "CHW",
  KC: "KCR",
  SD: "SDP",
  SF: "SFG",
  TB: "TBR",
  WSH: "WSN",
};

function canonicalTeamCode(value) {
  const code = String(value || "").trim().toUpperCase();
  return teamAliases[code] || code;
}

function teamCode(team) {
  return canonicalTeamCode(team?.abbreviation || team?.code || "");
}

function teamLine(competitor) {
  const team = competitor?.team || {};
  const code = teamCode(team) || "--";
  const score = competitor?.score ?? "--";
  const record = competitor?.record ? ` (${competitor.record})` : "";
  return `${code} ${score}${record}`;
}

function starterLine(competitor) {
  const starter = competitor?.probableStarter;
  return starter?.name ? starter.name : "TBD";
}

function findPitcherOption(starter, team) {
  const starterName = cleanLookupText(starter?.name);
  const code = teamCode(team);
  if (!starterName) return null;
  return state.pitchers.find((pitcher) => {
    const sameName = cleanLookupText(pitcher.pitcher) === starterName;
    const sameTeam = !code || canonicalTeamCode(pitcher.team) === code;
    return sameName && sameTeam;
  }) || state.pitchers.find((pitcher) => cleanLookupText(pitcher.pitcher) === starterName) || null;
}

function isPitcherPropMode() {
  return String(els.targetSelect.value || "").startsWith("pitcher");
}

function isPitcherStrikeoutMode() {
  return els.targetSelect.value === "pitcherStrikeouts";
}

function defaultLineForTarget(target) {
  return {
    hits: "0.5",
    totalBases: "1.5",
    homeRuns: "0.5",
    strikeouts: "0.5",
    pitcherStrikeouts: "4.5",
    pitcherWalks: "1.5",
    pitcherRunsAllowed: "2.5",
    pitcherHitsAllowed: "4.5",
  }[target] || "0.5";
}

function pitcherSummary(pitcher) {
  if (pitcher.strikeoutRate) {
    return `K% ${pct(pitcher.strikeoutRate)}`;
  }
  if (pitcher.strikeouts && pitcher.battersFaced) {
    return `K% ${pct(pitcher.strikeouts / pitcher.battersFaced)}`;
  }
  if (pitcher.battingAverageAllowed) {
    return `BAA ${dec(pitcher.battingAverageAllowed)}`;
  }
  if (pitcher.whip) {
    return `WHIP ${Number(pitcher.whip).toFixed(2)}`;
  }
  return "pitching data";
}

function formatCardValue(card) {
  if (card.format === "percent") {
    return pct(card.value);
  }
  return Number(card.value || 0).toFixed(2);
}

async function api(path, options = {}) {
  const response = await fetch(path, withActionHeader(options));
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function sortPlayers(players) {
  return [...players].sort((a, b) => {
    const key = state.playerSort.key;
    const direction = state.playerSort.direction === "asc" ? 1 : -1;
    const aValue = a[key];
    const bValue = b[key];
    let result = 0;
    if (typeof aValue === "number" || typeof bValue === "number") {
      result = Number(aValue || 0) - Number(bValue || 0);
    } else {
      result = String(aValue || "").localeCompare(String(bValue || ""));
    }
    return result * direction || a.player.localeCompare(b.player);
  });
}

function pitcherBoardMetric(pitcher, key) {
  const innings = Number(pitcher.innings || 0);
  const games = Number(pitcher.games || 0);
  const battersFaced = Number(pitcher.battersFaced || pitcher.plateAppearances || 0);
  const strikeouts = Number(pitcher.strikeouts || 0);
  const walks = Number(pitcher.walks || 0);
  const homeRuns = Number(pitcher.homeRunsAllowed || 0);
  const values = {
    pitcher: pitcher.pitcher || "",
    team: pitcher.team || "",
    games,
    innings,
    era: Number(pitcher.era || 0),
    whip: Number(pitcher.whip || 0),
    strikeoutRate: Number(pitcher.strikeoutRate || (battersFaced ? strikeouts / battersFaced : 0)),
    strikeoutsPerNine: innings ? strikeouts * 9 / innings : 0,
    walksPerNine: innings ? walks * 9 / innings : 0,
    homeRunsPerNine: innings ? homeRuns * 9 / innings : 0,
  };
  return values[key];
}

function sortPitchers(pitchers) {
  return [...pitchers].sort((a, b) => {
    const key = state.playerSort.key;
    const direction = state.playerSort.direction === "asc" ? 1 : -1;
    const aValue = pitcherBoardMetric(a, key);
    const bValue = pitcherBoardMetric(b, key);
    let result = 0;
    if (typeof aValue === "number" || typeof bValue === "number") {
      result = Number(aValue || 0) - Number(bValue || 0);
    } else {
      result = String(aValue || "").localeCompare(String(bValue || ""));
    }
    return result * direction || String(a.pitcher || "").localeCompare(String(b.pitcher || ""));
  });
}

function currentPlayer() {
  return state.players.find((player) => player.player_id === state.selectedPlayerId) || null;
}

function currentPitcher() {
  return state.pitchers.find((pitcher) => pitcher.key === state.selectedPitcherKey || pitcher.key === els.pitcherSelect.value) || null;
}

function selectedTeam() {
  return state.teams.find((team) => team.code === els.opponentSelect.value) || null;
}

function playerLabel(player) {
  return player ? `${player.player} (${player.team})` : "";
}

function pitcherLabel(pitcher) {
  return pitcher ? `${pitcher.pitcher} (${pitcher.team || "--"})` : "";
}

function teamLabel(team) {
  return team ? `${team.code} - ${team.name}` : "";
}

function renderSortHeaders() {
  els.sortHeaders = document.querySelectorAll(".sort-header");
  for (const header of els.sortHeaders) {
    const active = header.dataset.sort === state.playerSort.key;
    header.classList.toggle("active", active);
    header.dataset.direction = active ? (state.playerSort.direction === "asc" ? "^" : "v") : "";
  }
}

function renderPlayerSelect() {
  els.playerSelect.innerHTML = "";
  for (const player of sortPlayers(state.players)) {
    const option = document.createElement("option");
    option.value = player.player_id;
    option.textContent = `${player.player} (${player.team})`;
    els.playerSelect.append(option);
  }
  if (!state.selectedPlayerId && state.players.length) {
    state.selectedPlayerId = sortPlayers(state.players)[0].player_id;
  }
  els.playerSelect.value = state.selectedPlayerId;
  if (!els.playerSearch.value || document.activeElement !== els.playerSearch) {
    els.playerSearch.value = playerLabel(currentPlayer());
  }
  renderPlayerSearchResults();
}

function renderOpponentSelect() {
  els.opponentSelect.innerHTML = "";
  for (const team of state.teams) {
    const option = document.createElement("option");
    option.value = team.code;
    option.textContent = `${team.code} - ${team.name}`;
    els.opponentSelect.append(option);
  }
  if (!els.opponentSelect.value && state.teams.length) {
    els.opponentSelect.value = state.teams[0].code;
  }
  if (!els.teamSearch.value || document.activeElement !== els.teamSearch) {
    els.teamSearch.value = teamLabel(selectedTeam());
  }
  renderTeamSearchResults();
}

function eligiblePitchers() {
  return state.pitchers;
}

function renderPitcherSelect() {
  const previous = state.selectedPitcherKey || els.pitcherSelect.value;
  const pitcherMode = isPitcherPropMode();
  const pitchers = eligiblePitchers();
  els.pitcherSelect.innerHTML = "";
  const neutral = document.createElement("option");
  neutral.value = "";
  neutral.textContent = pitcherMode ? "Choose pitcher" : "Any pitcher";
  els.pitcherSelect.append(neutral);

  for (const pitcher of pitchers) {
    const option = document.createElement("option");
    option.value = pitcher.key;
    option.textContent = `${pitcher.pitcher} (${pitcher.team}) - ${pitcherSummary(pitcher)}`;
    els.pitcherSelect.append(option);
  }
  if (previous && [...els.pitcherSelect.options].some((option) => option.value === previous)) {
    els.pitcherSelect.value = previous;
    state.selectedPitcherKey = previous;
  } else if (pitcherMode && pitchers.length) {
    els.pitcherSelect.value = pitchers[0].key;
    state.selectedPitcherKey = pitchers[0].key;
  } else {
    els.pitcherSelect.value = "";
    state.selectedPitcherKey = "";
  }
  if (!els.pitcherSearch.value || document.activeElement !== els.pitcherSearch) {
    els.pitcherSearch.value = pitcherLabel(currentPitcher());
  }
  renderPitcherSearchResults();
}

function renderModeControls() {
  const pitcherMode = isPitcherPropMode();
  els.playerControl.classList.toggle("hidden", pitcherMode);
  els.pitcherControlLabel.textContent = pitcherMode ? "Pitcher search" : "Pitcher search (optional)";
  els.matchupPanel.classList.toggle("hidden", pitcherMode);
  els.recentFormPanel.classList.toggle("hidden", pitcherMode);
  els.batterHrPanel.classList.toggle("hidden", pitcherMode);
  els.strikeoutPanel.classList.toggle("hidden", !isPitcherStrikeoutMode());
}

function renderSearchList(container, items, selectedValue, onPick) {
  container.innerHTML = "";
  for (const item of items.slice(0, 8)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `search-option ${item.value === selectedValue ? "selected" : ""}`;
    const label = document.createElement("strong");
    label.textContent = item.label;
    const meta = document.createElement("span");
    meta.textContent = item.meta;
    button.append(label, meta);
    button.addEventListener("click", () => onPick(item));
    container.append(button);
  }
  if (!container.children.length) {
    const empty = document.createElement("div");
    empty.className = "source-empty";
    empty.textContent = "No matches";
    container.append(empty);
  }
}

function renderPlayerSearchResults() {
  const query = cleanLookupText(els.playerSearch.value);
  const players = sortPlayers(state.players)
    .filter((player) => {
      if (!query) return true;
      const haystack = cleanLookupText(`${player.player} ${player.team}`);
      return haystack.includes(query);
    })
    .map((player) => ({
      value: player.player_id,
      label: player.player,
      meta: `${player.team} | BA ${dec(player.batting_average)} | HR ${player.home_runs} | OPS ${dec(player.ops)}`,
      player,
    }));
  renderSearchList(els.playerSearchResults, players, state.selectedPlayerId, (item) => {
    state.selectedPlayerId = item.value;
    els.playerSelect.value = item.value;
    els.playerSearch.value = playerLabel(item.player);
    renderPlayerSearchResults();
    renderRows();
    predict();
  });
}

function renderTeamSearchResults() {
  const query = cleanLookupText(els.teamSearch.value);
  const teams = state.teams
    .filter((team) => {
      if (!query) return true;
      const haystack = cleanLookupText(`${team.code} ${team.name}`);
      return haystack.includes(query);
    })
    .map((team) => ({
      value: team.code,
      label: team.code,
      meta: team.name,
      team,
    }));
  renderSearchList(els.teamSearchResults, teams, els.opponentSelect.value, (item) => {
    els.opponentSelect.value = item.value;
    els.teamSearch.value = teamLabel(item.team);
    renderTeamSearchResults();
    renderPitcherSelect();
    predict();
  });
}

function renderPitcherSearchResults() {
  const query = cleanLookupText(els.pitcherSearch.value);
  const pitchers = eligiblePitchers()
    .filter((pitcher) => {
      if (!query) return true;
      const haystack = cleanLookupText(`${pitcher.pitcher} ${pitcher.team}`);
      return haystack.includes(query);
    })
    .map((pitcher) => ({
      value: pitcher.key,
      label: pitcher.pitcher,
      meta: `${pitcher.team || "--"} | ${pitcherSummary(pitcher)}`,
      pitcher,
    }));
  renderSearchList(els.pitcherSearchResults, pitchers, state.selectedPitcherKey || els.pitcherSelect.value, (item) => {
    state.selectedPitcherKey = item.value;
    els.pitcherSelect.value = item.value;
    els.pitcherSearch.value = pitcherLabel(item.pitcher);
    renderPitcherSearchResults();
    predict();
  });
}

const datasetLabels = {
  batting: "Batting",
  opponents: "Opponents",
  gameLogs: "Game logs",
  pitchingGameLogs: "Pitching game logs",
  teamGameLogs: "Team game logs",
  teamBatting: "Team batting",
  baserunning: "Base running",
  pitching: "Pitching",
  battingAgainst: "Batting against",
  teamBattingAgainst: "Team BAA",
  teamAdvancedPitching: "Team adv. pitching",
  playerAdvancedPitching: "Player adv. pitching",
  teamStandardPitching: "Team pitching",
  batterPitcherAdvanced: "Batter vs pitcher",
  statcastQuality: "Statcast quality",
  handednessSplits: "Handedness splits",
  rollingForm: "Rolling form",
  pitchArsenal: "Pitch arsenal",
  gameContext: "Game context",
  ballparkContext: "Ballpark weather",
};

const datasetOrder = [
  "batting",
  "opponents",
  "gameLogs",
  "pitchingGameLogs",
  "teamGameLogs",
  "teamBatting",
  "baserunning",
  "pitching",
  "battingAgainst",
  "teamBattingAgainst",
  "teamAdvancedPitching",
  "playerAdvancedPitching",
  "teamStandardPitching",
  "batterPitcherAdvanced",
  "statcastQuality",
  "handednessSplits",
  "rollingForm",
  "pitchArsenal",
  "gameContext",
  "ballparkContext",
];

const datasetHelp = {
  batting: {
    description: "Player hitting stats for batter hits, total bases, home runs, and batter strikeouts.",
    columns: "Player, Team, G, PA, AB, H, BB, SO, BA, OBP, SLG, OPS",
    placeholder: "https://example.com/player-batting.csv",
  },
  opponents: {
    description: "Opponent or team pitching difficulty allowed by team.",
    columns: "Team/Tm, G, IP, H, BAA/AVG Allowed, ERA, WHIP",
    placeholder: "https://example.com/opponent-pitching.csv",
  },
  gameLogs: {
    description: "Batter game logs by opponent for player-vs-team history.",
    columns: "Player, Opp/Opponent, AB, H",
    placeholder: "https://example.com/team-batting-game-logs.csv",
  },
  pitchingGameLogs: {
    description: "Pitcher game logs by opponent for recent workload, Ks, and run/hit prevention.",
    columns: "Pitcher/Player, Opp/Opponent, IP, H, ER, HR, BB, SO, BF",
    placeholder: "https://example.com/team-pitching-game-logs.csv",
  },
  teamGameLogs: {
    description: "Team-by-team game logs for win rate, runs, OPS, HR, walk, and strikeout matchup context.",
    columns: "Team/Tm or team URL, Date, Opp, Rslt, RS, RA, PA, AB, H, HR, BB, SO, OPS, Opp Starter",
    placeholder: "https://www.baseball-reference.com/teams/tgl.cgi?team=NYY&t=b&year=2026#all_players_standard_batting",
  },
  teamBatting: {
    description: "Team offense context for lineup strength and opponent strikeout tendencies.",
    columns: "Team/Tm, G, PA, AB, H, R, HR, BB, SO, BA, OBP, SLG, OPS, R/G",
    placeholder: "https://example.com/team-batting.csv",
  },
  baserunning: {
    description: "Player speed and running context.",
    columns: "Player, Team/Tm, G, SB, CS, SB%, XBT%, Rbaser",
    placeholder: "https://example.com/player-baserunning.csv",
  },
  pitching: {
    description: "Standard pitcher stats for selectable opposing pitchers and pitcher K props.",
    columns: "Player/Pitcher, Team/Tm, G, GS, IP, H, HR, BB, SO, ERA, WHIP, H9",
    placeholder: "https://www.baseball-reference.com/leagues/majors/2026-standard-pitching.shtml#all_players_standard_pitching",
  },
  battingAgainst: {
    description: "Pitcher batting-against profile for selected opposing pitchers.",
    columns: "Player/Pitcher, Team/Tm, AB, H, BA, OBP, SLG, OPS",
    placeholder: "https://example.com/player-batting-against.csv",
  },
  teamBattingAgainst: {
    description: "Team-level batting average and OPS allowed.",
    columns: "Team/Tm, AB, H, BA, OBP, SLG, OPS",
    placeholder: "https://example.com/team-batting-against.csv",
  },
  teamAdvancedPitching: {
    description: "Team pitching quality and strikeout/walk profile.",
    columns: "Team/Tm, K%, BB%, K-BB%, ERA-, FIP-, SIERA, xFIP, FIP",
    placeholder: "https://example.com/team-advanced-pitching.csv",
  },
  playerAdvancedPitching: {
    description: "Advanced pitcher quality for selected opposing pitchers.",
    columns: "Player/Pitcher, Team/Tm, K%, BB%, K-BB%, ERA-, FIP-, SIERA, xFIP, FIP",
    placeholder: "https://example.com/player-advanced-pitching.csv",
  },
  teamStandardPitching: {
    description: "Team standard pitching environment.",
    columns: "Team/Tm, IP, H, ERA, WHIP, H9, SO, BB",
    placeholder: "https://example.com/team-standard-pitching.csv",
  },
  batterPitcherAdvanced: {
    description: "Exact batter-vs-pitcher history and Statcast-style matchup quality.",
    columns: "Batter, Pitcher, PA, AB, H, HR, SO, BB, wOBA, xwOBA, xBA, xSLG, EV, HardH%, Barrel%, Whiff%",
    placeholder: "https://example.com/batter-vs-pitcher.csv",
  },
  statcastQuality: {
    description: "Saved Statcast quality metrics produced by model refresh for selected batters and pitchers.",
    columns: "Player, Role, Season, PA, H, HR, xBA, xSLG, xwOBA, Barrel%, HardHit%, EV, LA, Whiff%",
    placeholder: "Generated from Baseball Savant refresh",
  },
  handednessSplits: {
    description: "Batter vs LHP/RHP and pitcher vs LHB/RHB context.",
    columns: "Player, Role, Season, Split, PA, H, HR, K%, BB%, wOBA, xwOBA",
    placeholder: "Generated from Baseball Savant refresh",
  },
  rollingForm: {
    description: "Last 7/14/30 day player form for pitch and contact quality.",
    columns: "Player, Role, Window, PA, H, HR, SO, Barrel%, HardHit%, K%",
    placeholder: "Generated from Baseball Savant refresh",
  },
  pitchArsenal: {
    description: "Pitcher pitch-type usage, velocity, whiff, and damage allowed.",
    columns: "Pitcher, Pitch Type, Usage, Velocity, Whiff%, Barrel%, HardHit%, xwOBA",
    placeholder: "Generated from Baseball Savant refresh",
  },
  gameContext: {
    description: "Game-level context for probable starters, venue, status, and teams.",
    columns: "Date, Game, Home, Away, Probables, Venue, Weather/Roof when available",
    placeholder: "Generated from ESPN/MLB refresh",
  },
  ballparkContext: {
    description: "BallparkPal or manual weather-adjusted park environment for hits and home runs.",
    columns: "Date, Home Team, Away Team, Venue, Temperature, Wind MPH, Wind Direction, Roof, Park Factor, HR Factor, Hit Factor",
    placeholder: "https://www.ballparkpal.com/api/docs/ or examples/weather-template.csv",
  },
};

function urlLines(value) {
  return String(value || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function datasetLabel(key) {
  return datasetLabels[key] || key;
}

function renderDatasetGuide() {
  els.datasetGuide.innerHTML = "";
  for (const key of datasetOrder) {
    const help = datasetHelp[key] || {};
    const item = document.createElement("div");
    item.className = "dataset-guide-item";
    item.innerHTML = `
      <strong>${escapeHtml(datasetLabel(key))}</strong>
      <span>${escapeHtml(help.description || "")}</span>
      <em>${escapeHtml(help.columns || "")}</em>
    `;
    item.addEventListener("click", () => {
      const uploadable = [...els.csvType.options].some((option) => option.value === key);
      if (uploadable) {
        els.csvType.value = key;
        updateCsvTypeHelper();
        return;
      }
      els.csvHintTitle.textContent = datasetLabel(key);
      els.csvHintDescription.textContent = help.description || "Generated by model refresh.";
      els.csvHintColumns.textContent = help.columns || "";
      els.datasetUrl.placeholder = help.placeholder || "";
    });
    els.datasetGuide.append(item);
  }
}

function updateCsvTypeHelper() {
  const key = els.csvType.value;
  const help = datasetHelp[key] || {};
  els.csvHintTitle.textContent = datasetLabel(key);
  els.csvHintDescription.textContent = help.description || "Choose a matching CSV or table URL.";
  els.csvHintColumns.textContent = help.columns || "";
  els.datasetUrl.placeholder = help.placeholder || "https://example.com/daily-stats.csv";
  for (const item of els.datasetGuide.children) {
    item.classList.toggle("selected", item.querySelector("strong")?.textContent === datasetLabel(key));
  }
}

function formatSourceTime(value) {
  if (!value) return "Never refreshed";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function shortSourceUrl(value) {
  try {
    const url = new URL(value);
    return `${url.hostname}${url.pathname}`;
  } catch {
    return value;
  }
}

function sourceRefreshLabel(source) {
  return source.autoRefresh === false ? "manual refresh" : "daily auto-refresh";
}

function renderDatasets() {
  els.datasetList.innerHTML = "";
  for (const key of datasetOrder) {
    const dataset = state.datasets[key] || {};
    const item = document.createElement("div");
    item.className = `dataset-pill ${dataset.loaded ? "loaded" : ""}`;
    item.innerHTML = `
      <span>${datasetLabel(key)}</span>
      <strong>${dataset.loaded ? `${dataset.count} rows` : "Not loaded"}</strong>
    `;
    els.datasetList.append(item);
  }
}

function renderDatasetSources() {
  els.sourceList.innerHTML = "";
  if (!state.datasetSources.length) {
    const empty = document.createElement("div");
    empty.className = "source-empty";
    empty.textContent = "No saved dataset URLs yet";
    els.sourceList.append(empty);
    return;
  }

  for (const source of state.datasetSources) {
    const item = document.createElement("div");
    const loaded = source.lastStatus === "loaded";
    item.className = `source-pill ${loaded ? "loaded" : "error"}`;
    const copy = document.createElement("div");
    copy.className = "source-copy";
    const label = document.createElement("strong");
    label.textContent = datasetLabel(source.type);
    const url = document.createElement("span");
    url.className = "source-url";
    url.title = source.url;
    url.textContent = shortSourceUrl(source.url);
    const meta = document.createElement("span");
    meta.textContent = `${loaded ? `${source.lastCount || 0} rows` : source.lastError || "Refresh failed"} - ${formatSourceTime(source.lastImportedAt)} - ${sourceRefreshLabel(source)}`;
    copy.append(label, url, meta);
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.sourceId = source.id;
    button.textContent = "Refresh";
    button.addEventListener("click", () => refreshStoredSources(source.id));
    item.append(copy, button);
    els.sourceList.append(item);
  }
}

function renderDataNeeds() {
  els.missingDataList.innerHTML = "";
  for (const item of state.dataNeeds.missing || []) {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${escapeHtml(item.label)}</strong><span>${escapeHtml(item.reason)}</span>`;
    els.missingDataList.append(li);
  }
  if (!els.missingDataList.children.length) {
    els.missingDataList.innerHTML = "<li><strong>Core files loaded</strong><span>The largest remaining gains are matchup, lineup, park, and weather context.</span></li>";
  }

  els.usefulDataList.innerHTML = "";
  for (const text of state.dataNeeds.useful || []) {
    const li = document.createElement("li");
    li.textContent = text;
    els.usefulDataList.append(li);
  }
}

function renderModelRefreshResults(results = []) {
  els.modelRefreshResults.innerHTML = "";
  for (const result of results.slice(0, 8)) {
    const item = document.createElement("div");
    const status = result.status || result.source || "done";
    item.className = `refresh-result ${String(status).includes("error") ? "error" : "loaded"}`;
    const count = result.count ?? result.statcastRows ?? result.storedCount ?? "";
    const countText = count !== "" ? ` (${count} rows)` : "";
    item.innerHTML = `
      <strong>${escapeHtml(result.task || "Refresh task")}</strong>
      <span>${escapeHtml(result.error || `${status}${countText}`)}</span>
    `;
    els.modelRefreshResults.append(item);
  }
  if (!els.modelRefreshResults.children.length) {
    const empty = document.createElement("div");
    empty.className = "source-empty";
    empty.textContent = "Choose a batter, pitcher, team, or date to refresh.";
    els.modelRefreshResults.append(empty);
  }
}

async function refreshModelData() {
  const params = new URLSearchParams({
    season: els.modelRefreshSeason.value || String(new Date().getFullYear()),
    playerId: isPitcherPropMode() ? "" : state.selectedPlayerId,
    pitcherKey: state.selectedPitcherKey || els.pitcherSelect.value,
    pitcherName: currentPitcher()?.pitcher || els.pitcherSearch.value || "",
    opponent: els.opponentSelect.value,
    date: els.modelRefreshDate.value,
    reset: els.modelRefreshReset.checked ? "1" : "0",
    teamLogs: els.modelRefreshTeamLogs.checked ? "1" : "0",
  });
  if (!params.get("playerId") && !params.get("pitcherKey") && !params.get("opponent") && !params.get("date")) {
    els.modelRefreshStatus.textContent = "Pick a player, pitcher, team, or game date first.";
    renderModelRefreshResults([]);
    return;
  }

  els.modelRefreshButton.disabled = true;
  els.modelRefreshStatus.textContent = "Refreshing model data from MLB, Savant, ESPN, and BallparkPal...";
  try {
    const payload = await api(`/api/model-data/refresh?${params.toString()}`, { method: "POST" });
    state.datasets = payload.datasets || state.datasets;
    state.datasetSources = payload.datasetSources || state.datasetSources;
    state.pitchers = payload.pitchers || state.pitchers;
    state.sourceCapabilities = payload.sourceCapabilities?.capabilities || state.sourceCapabilities;
    state.dataNeeds = payload.dataNeeds || state.dataNeeds;
    const results = payload.results || [];
    const errors = results.filter((result) => String(result.status || "").includes("error") || result.error);
    const loaded = results.length - errors.length;
    els.modelRefreshStatus.textContent = errors.length
      ? `${loaded} refresh tasks finished, ${errors.length} need attention.`
      : `${loaded} refresh task${loaded === 1 ? "" : "s"} finished and saved.`;
    renderModelRefreshResults(results);
    await loadPlayers();
  } catch (error) {
    els.modelRefreshStatus.textContent = error.message;
    renderModelRefreshResults([{ task: "Model data refresh", status: "error", error: error.message }]);
  } finally {
    els.modelRefreshButton.disabled = false;
  }
}

function boardPercent(value) {
  if (value === null || value === undefined || value === "") return "--";
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function renderPropBoardRows(rows = []) {
  els.propBoardRows.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6">Paste an odds board, then run the analyzer.</td>`;
    els.propBoardRows.append(row);
    return;
  }
  for (const pick of rows.slice(0, 25)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(pick.selection || "--")}</td>
      <td>${escapeHtml(american(pick.odds))}</td>
      <td>${escapeHtml(boardPercent(pick.model_probability))}</td>
      <td>${escapeHtml(signedNumber(Number(pick.edge || 0) * 100, 1))} pts</td>
      <td>${escapeHtml(signedNumber(pick.expected_value_per_unit, 2))}u</td>
      <td>$${Number(pick["payout_$10"] || 0).toFixed(2)}</td>
    `;
    els.propBoardRows.append(row);
  }
}

function renderPropParlays(rows = []) {
  els.propParlayRows.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="6">No parlay candidates yet.</td>`;
    els.propParlayRows.append(row);
    return;
  }
  for (const parlay of rows.slice(0, 20)) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(parlay.selections || "--")}</td>
      <td>${escapeHtml(parlay.legs || "--")}</td>
      <td>${escapeHtml(boardPercent(parlay.model_probability))}</td>
      <td>${escapeHtml(signedNumber(Number(parlay.edge || 0) * 100, 1))} pts</td>
      <td>${escapeHtml(signedNumber(parlay.expected_value_per_unit, 2))}u</td>
      <td>$${Number(parlay["payout_$10"] || 0).toFixed(2)}</td>
    `;
    els.propParlayRows.append(row);
  }
}

async function analyzePropBoard() {
  const oddsText = els.propBoardText.value.trim();
  if (!oddsText) {
    els.propBoardStatus.textContent = "Missing odds";
    els.propBoardMeta.textContent = "Paste a prop odds CSV or strikeout ladder OCR text first.";
    renderPropBoardRows([]);
    renderPropParlays([]);
    return;
  }
  els.propBoardButton.disabled = true;
  els.propBoardStatus.textContent = "Analyzing board";
  els.propBoardMeta.textContent = "Loading schedule context and running model probabilities...";
  try {
    const payload = await api("/api/prop-board/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inputType: els.propBoardInputType.value,
        date: els.propBoardDate.value || "today",
        recentGames: els.propBoardRecentGames.value || "5",
        oddsText,
      }),
    });
    els.propBoardStatus.textContent = "Board analyzed";
    els.propBoardSummary.textContent = `${payload.analyzedCount} of ${payload.propCount} props ranked`;
    const warnings = payload.warnings?.length ? ` ${payload.warnings.length} warning(s).` : "";
    els.propBoardMeta.textContent = `${payload.date} | ${payload.scheduleCount} scheduled game(s).${warnings} Report: ${payload.reportPaths?.report || "not written"}`;
    renderPropBoardRows(payload.bestValue || []);
    renderPropParlays(payload.parlays || []);
  } catch (error) {
    els.propBoardStatus.textContent = "Analyzer error";
    els.propBoardSummary.textContent = "Board analysis failed";
    els.propBoardMeta.textContent = error.message;
    renderPropBoardRows([]);
    renderPropParlays([]);
  } finally {
    els.propBoardButton.disabled = false;
  }
}

function renderRows() {
  const query = els.search.value.trim().toLowerCase();
  state.boardMode = els.boardMode.value || "batters";
  renderBoardHeader();
  renderSortHeaders();
  els.playerRows.innerHTML = "";
  if (state.boardMode === "pitchers") {
    renderPitcherBoardRows(query);
    return;
  }
  if (state.boardMode === "both") {
    renderCombinedBoardRows(query);
    return;
  }
  const rows = sortPlayers(state.players)
    .filter((player) => !query || player.player.toLowerCase().includes(query) || player.team.toLowerCase().includes(query))
    .slice(0, 250);

  for (const player of rows) {
    const row = document.createElement("tr");
    row.className = player.player_id === state.selectedPlayerId ? "selected" : "";
    row.innerHTML = `
      <td>${escapeHtml(player.player)}</td>
      <td>${escapeHtml(player.team)}</td>
      <td>${escapeHtml(player.games)}</td>
      <td>${escapeHtml(player.at_bats)}</td>
      <td>${escapeHtml(player.hits)}</td>
      <td>${escapeHtml(dec(player.batting_average))}</td>
      <td>${escapeHtml(dec(player.ops))}</td>
      <td>${escapeHtml(player.home_runs || 0)}</td>
    `;
    row.addEventListener("click", () => {
      state.selectedPlayerId = player.player_id;
      els.playerSelect.value = player.player_id;
      els.playerSearch.value = playerLabel(player);
      renderPlayerSearchResults();
      renderRows();
      predict();
    });
    els.playerRows.append(row);
  }
}

function sortButton(key, label) {
  return `<button class="sort-header" type="button" data-sort="${key}">${label}</button>`;
}

function renderBoardHeader() {
  if (state.boardMode === "pitchers") {
    els.playerBoardHead.innerHTML = `
      <tr>
        <th>${sortButton("pitcher", "Pitcher")}</th>
        <th>${sortButton("team", "Team")}</th>
        <th>${sortButton("games", "G")}</th>
        <th>${sortButton("innings", "IP")}</th>
        <th>${sortButton("era", "ERA")}</th>
        <th>${sortButton("whip", "WHIP")}</th>
        <th>${sortButton("strikeoutRate", "K%")}</th>
        <th>${sortButton("strikeoutsPerNine", "K/9")}</th>
        <th>${sortButton("walksPerNine", "BB/9")}</th>
        <th>${sortButton("homeRunsPerNine", "HR/9")}</th>
      </tr>
    `;
    return;
  }
  if (state.boardMode === "both") {
    els.playerBoardHead.innerHTML = `
      <tr>
        <th>${sortButton("type", "Type")}</th>
        <th>${sortButton("name", "Name")}</th>
        <th>${sortButton("team", "Team")}</th>
        <th>${sortButton("games", "G")}</th>
        <th>${sortButton("volume", "AB/IP")}</th>
        <th>${sortButton("primary", "H/SO")}</th>
        <th>${sortButton("rateOne", "BA/ERA")}</th>
        <th>${sortButton("rateTwo", "OPS/WHIP")}</th>
        <th>${sortButton("power", "HR/K%")}</th>
      </tr>
    `;
    return;
  }
  els.playerBoardHead.innerHTML = `
    <tr>
      <th>${sortButton("player", "Batter")}</th>
      <th>${sortButton("team", "Team")}</th>
      <th>${sortButton("games", "G")}</th>
      <th>${sortButton("at_bats", "AB")}</th>
      <th>${sortButton("hits", "H")}</th>
      <th>${sortButton("batting_average", "BA")}</th>
      <th>${sortButton("ops", "OPS")}</th>
      <th>${sortButton("home_runs", "HR")}</th>
    </tr>
  `;
}

function renderPitcherBoardRows(query) {
  const rows = sortPitchers(state.pitchers)
    .filter((pitcher) => !query || cleanLookupText(`${pitcher.pitcher} ${pitcher.team}`).includes(cleanLookupText(query)))
    .slice(0, 250);
  for (const pitcher of rows) {
    const row = document.createElement("tr");
    row.className = pitcher.key === state.selectedPitcherKey ? "selected" : "";
    row.innerHTML = `
      <td>${escapeHtml(pitcher.pitcher)}</td>
      <td>${escapeHtml(pitcher.team || "--")}</td>
      <td>${escapeHtml(pitcher.games || 0)}</td>
      <td>${escapeHtml(Number(pitcher.innings || 0).toFixed(1))}</td>
      <td>${escapeHtml(formatMaybeNumber(pitcher.era, 2))}</td>
      <td>${escapeHtml(formatMaybeNumber(pitcher.whip, 3))}</td>
      <td>${escapeHtml(formatMaybeRate(pitcherBoardMetric(pitcher, "strikeoutRate")))}</td>
      <td>${escapeHtml(formatMaybeNumber(pitcherBoardMetric(pitcher, "strikeoutsPerNine"), 2))}</td>
      <td>${escapeHtml(formatMaybeNumber(pitcherBoardMetric(pitcher, "walksPerNine"), 2))}</td>
      <td>${escapeHtml(formatMaybeNumber(pitcherBoardMetric(pitcher, "homeRunsPerNine"), 2))}</td>
    `;
    row.addEventListener("click", () => {
      state.selectedPitcherKey = pitcher.key;
      els.pitcherSelect.value = pitcher.key;
      els.pitcherSearch.value = pitcherLabel(pitcher);
      renderPitcherSearchResults();
      renderRows();
      predict();
    });
    els.playerRows.append(row);
  }
}

function combinedBoardRows() {
  const batters = state.players.map((player) => ({
    type: "Batter",
    name: player.player,
    team: player.team,
    games: player.games,
    volume: player.at_bats,
    primary: player.hits,
    rateOne: player.batting_average,
    rateTwo: player.ops,
    power: player.home_runs,
    raw: player,
  }));
  const pitchers = state.pitchers.map((pitcher) => ({
    type: "Pitcher",
    name: pitcher.pitcher,
    team: pitcher.team || "",
    games: Number(pitcher.games || 0),
    volume: Number(pitcher.innings || 0),
    primary: Number(pitcher.strikeouts || 0),
    rateOne: Number(pitcher.era || 0),
    rateTwo: Number(pitcher.whip || 0),
    power: pitcherBoardMetric(pitcher, "strikeoutRate"),
    raw: pitcher,
  }));
  return [...batters, ...pitchers];
}

function sortCombinedRows(rows) {
  const key = state.playerSort.key;
  const direction = state.playerSort.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const aValue = a[key];
    const bValue = b[key];
    let result = 0;
    if (typeof aValue === "number" || typeof bValue === "number") {
      result = Number(aValue || 0) - Number(bValue || 0);
    } else {
      result = String(aValue || "").localeCompare(String(bValue || ""));
    }
    return result * direction || a.name.localeCompare(b.name);
  });
}

function renderCombinedBoardRows(query) {
  const rows = sortCombinedRows(combinedBoardRows())
    .filter((item) => !query || cleanLookupText(`${item.type} ${item.name} ${item.team}`).includes(cleanLookupText(query)))
    .slice(0, 300);
  for (const item of rows) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(item.type)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.team || "--")}</td>
      <td>${escapeHtml(item.games || 0)}</td>
      <td>${escapeHtml(Number(item.volume || 0).toFixed(item.type === "Pitcher" ? 1 : 0))}</td>
      <td>${escapeHtml(Number(item.primary || 0).toFixed(0))}</td>
      <td>${escapeHtml(item.type === "Pitcher" ? formatMaybeNumber(item.rateOne, 2) : dec(item.rateOne))}</td>
      <td>${escapeHtml(item.type === "Pitcher" ? formatMaybeNumber(item.rateTwo, 3) : dec(item.rateTwo))}</td>
      <td>${escapeHtml(item.type === "Pitcher" ? formatMaybeRate(item.power) : Number(item.power || 0))}</td>
    `;
    row.addEventListener("click", () => {
      if (item.type === "Pitcher") {
        state.selectedPitcherKey = item.raw.key;
        els.pitcherSelect.value = item.raw.key;
        els.pitcherSearch.value = pitcherLabel(item.raw);
        renderPitcherSearchResults();
      } else {
        state.selectedPlayerId = item.raw.player_id;
        els.playerSelect.value = item.raw.player_id;
        els.playerSearch.value = playerLabel(item.raw);
        renderPlayerSearchResults();
      }
      renderRows();
      predict();
    });
    els.playerRows.append(row);
  }
}

function renderAll() {
  renderPlayerSelect();
  renderOpponentSelect();
  renderModeControls();
  renderPitcherSelect();
  renderDatasets();
  renderDatasetSources();
  renderDataNeeds();
  renderRows();
}

async function loadPlayers() {
  const payload = await api("/api/players");
  state.players = payload.players;
  state.teams = payload.teams;
  state.pitchers = payload.pitchers || [];
  state.datasets = payload.datasets || {};
  state.datasetSources = payload.datasetSources || payload.sources || [];
  state.sourceCapabilities = payload.sourceCapabilities?.capabilities || state.sourceCapabilities;
  state.dataNeeds = payload.dataNeeds || state.dataNeeds;
  renderAll();
  if (state.players.length) {
    await predict();
  }
}

async function uploadCsv(file) {
  const text = await file.text();
  const params = new URLSearchParams({
    type: els.csvType.value,
    filename: file.name,
  });
  const payload = await api(`/api/upload?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "text/csv; charset=utf-8" },
    body: text,
  });
  if (payload.players) {
    state.players = payload.players;
    state.selectedPlayerId = "";
  }
  if (payload.pitchers) {
    state.pitchers = payload.pitchers;
  }
  state.datasets = payload.datasets || state.datasets;
  state.datasetSources = payload.datasetSources || payload.sources || state.datasetSources;
  els.uploadLabel.textContent = `${file.name} loaded. ${payload.count} total ${els.csvType.options[els.csvType.selectedIndex].text.toLowerCase()} rows`;
  renderAll();
  await predict();
}

async function uploadFiles(files) {
  const uploaded = [];
  for (const file of files) {
    await uploadCsv(file);
    uploaded.push(file.name);
  }
  if (uploaded.length > 1) {
    els.uploadLabel.textContent = `${uploaded.length} files loaded as ${els.csvType.options[els.csvType.selectedIndex].text.toLowerCase()}`;
  }
}

async function importOneDatasetUrl(url) {
  const params = new URLSearchParams({
    type: els.csvType.value,
    url,
  });
  const payload = await api(`/api/import-url?${params.toString()}`, { method: "POST" });
  if (payload.players) state.players = payload.players;
  if (payload.pitchers) state.pitchers = payload.pitchers;
  state.datasets = payload.datasets || state.datasets;
  state.datasetSources = payload.datasetSources || payload.sources || state.datasetSources;
  return payload;
}

async function importDatasetUrl() {
  const urls = urlLines(els.datasetUrl.value);
  if (!urls.length) {
    els.uploadLabel.textContent = "Paste a CSV or HTML table URL first";
    return;
  }
  els.urlImportButton.disabled = true;
  els.bulkUrlImportButton.disabled = true;
  els.uploadLabel.textContent = "Loading dataset URL...";
  try {
    const payload = await importOneDatasetUrl(urls[0]);
    await loadPlayers();
    els.uploadLabel.textContent = `${payload.count} rows loaded and URL saved`;
  } catch (error) {
    els.uploadLabel.textContent = error.message;
  } finally {
    els.urlImportButton.disabled = false;
    els.bulkUrlImportButton.disabled = false;
  }
}

async function importDatasetUrls() {
  const urls = [...new Set(urlLines(els.datasetUrls.value))];
  if (!urls.length) {
    els.uploadLabel.textContent = "Paste one or more dataset URLs first";
    return;
  }
  els.urlImportButton.disabled = true;
  els.bulkUrlImportButton.disabled = true;
  const failures = [];
  let loaded = 0;
  try {
    for (const [index, url] of urls.entries()) {
      els.uploadLabel.textContent = `Loading ${index + 1} of ${urls.length} ${datasetLabel(els.csvType.value)} URLs...`;
      try {
        await importOneDatasetUrl(url);
        loaded += 1;
      } catch (error) {
        failures.push({ url, error: error.message });
      }
    }
    await loadPlayers();
    els.uploadLabel.textContent = failures.length
      ? `${loaded} URLs loaded, ${failures.length} failed. First error: ${failures[0].error}`
      : `${loaded} ${datasetLabel(els.csvType.value)} URL${loaded === 1 ? "" : "s"} loaded and saved`;
  } finally {
    els.urlImportButton.disabled = false;
    els.bulkUrlImportButton.disabled = false;
  }
}

async function refreshStoredSources(sourceId = "all") {
  if (!state.datasetSources.length) {
    els.uploadLabel.textContent = "No saved dataset URLs to refresh";
    return;
  }
  els.refreshSourcesButton.disabled = true;
  els.uploadLabel.textContent = sourceId === "all" ? "Refreshing saved dataset URLs..." : "Refreshing saved dataset URL...";
  try {
    const params = new URLSearchParams({ id: sourceId });
    const payload = await api(`/api/refresh-sources?${params.toString()}`, { method: "POST" });
    state.datasets = payload.datasets || state.datasets;
    state.pitchers = payload.pitchers || state.pitchers;
    state.datasetSources = payload.sources || state.datasetSources;
    await loadPlayers();
    const failures = (payload.results || []).filter((result) => result.status !== "loaded");
    const loaded = (payload.results || []).length - failures.length;
    els.uploadLabel.textContent = failures.length
      ? `${loaded} URL refreshes loaded, ${failures.length} need attention`
      : `${loaded} saved URL${loaded === 1 ? "" : "s"} refreshed`;
  } catch (error) {
    els.uploadLabel.textContent = error.message;
  } finally {
    els.refreshSourcesButton.disabled = false;
  }
}

function renderCards(cards) {
  els.cardOneLabel.textContent = cards[0]?.label || "Chance";
  els.cardOneValue.textContent = cards[0] ? formatCardValue(cards[0]) : "--";
  els.cardTwoLabel.textContent = cards[1]?.label || "Expected";
  els.cardTwoValue.textContent = cards[1] ? formatCardValue(cards[1]) : "--";
  els.cardThreeLabel.textContent = cards[2]?.label || "Chance";
  els.cardThreeValue.textContent = cards[2] ? formatCardValue(cards[2]) : "--";
}

function renderMarket(market) {
  if (!market) {
    els.marketImplied.textContent = "--";
    els.marketFairOdds.textContent = "--";
    els.marketEv.textContent = "--";
    els.marketEdge.textContent = "--";
    return;
  }
  els.marketImplied.textContent = pct(market.impliedProbability);
  els.marketFairOdds.textContent = american(market.fairAmerican);
  els.marketEv.textContent = `${signedNumber(market.expectedValuePerUnit, 2)}u`;
  els.marketEdge.textContent = `${signedNumber(market.edge * 100, 1)} pts`;
}

function formatMaybeRate(value) {
  if (value === null || value === undefined || value === "") return "--";
  return pct(value);
}

function formatMaybeNumber(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "--";
  return Number(value).toFixed(digits);
}

function setBatterDetailLabels() {
  els.teamLabel.textContent = "Team";
  els.gamesLabel.textContent = "Games";
  els.abGameLabel.textContent = "AB/G";
  els.baLabel.textContent = "BA";
  els.opsLabel.textContent = "OPS";
  els.contactLabel.textContent = "Contact";
}

function setPitcherDetailLabels() {
  els.teamLabel.textContent = "Team";
  els.gamesLabel.textContent = "Games";
  els.abGameLabel.textContent = "IP/App";
  els.baLabel.textContent = "K%";
  els.opsLabel.textContent = "Opp K%";
  els.contactLabel.textContent = "Batters";
}

function renderRecentForm(recent) {
  if (!recent?.available) {
    els.last5Avg.textContent = "--";
    els.last5Hits.textContent = "--";
    els.last10Avg.textContent = "--";
    els.lastOppAvg.textContent = "--";
    els.recentFormNote.textContent = "Upload player-level game logs to unlock last 5, last 10, and last 5 vs opponent context.";
    renderRecentOpponentRows([]);
    return;
  }
  const last5 = recent.last5 || {};
  const last10 = recent.last10 || {};
  const opp = recent.last5VsOpponent || {};
  els.last5Avg.textContent = last5.atBats ? dec(last5.battingAverage) : "--";
  els.last5Hits.textContent = last5.games ? Number(last5.hitRate || 0).toFixed(2) : "--";
  els.last10Avg.textContent = last10.atBats ? dec(last10.battingAverage) : "--";
  els.lastOppAvg.textContent = opp.atBats ? dec(opp.battingAverage) : "--";
  els.recentFormNote.textContent = `${last5.games || 0} recent games, ${last10.games || 0} last-10 games, and ${opp.games || 0} recent games vs selected opponent are available.`;
  renderRecentOpponentRows(recent.last5VsOpponentEntries || []);
}

function renderRecentOpponentRows(entries = []) {
  els.recentOpponentRows.innerHTML = "";
  if (!entries.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="8">No saved games found for this batter against that opponent.</td>`;
    els.recentOpponentRows.append(row);
    return;
  }
  for (const entry of entries) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(entry.date || "--")}</td>
      <td>${escapeHtml(entry.opponent || "--")}</td>
      <td>${escapeHtml(entry.plateAppearances || 0)}</td>
      <td>${escapeHtml(entry.atBats || 0)}</td>
      <td>${escapeHtml(entry.hits || 0)}</td>
      <td>${escapeHtml(entry.homeRuns || 0)}</td>
      <td>${escapeHtml(entry.strikeouts || 0)}</td>
      <td>${escapeHtml(entry.totalBases || 0)}</td>
    `;
    els.recentOpponentRows.append(row);
  }
}

function renderRecentOpponentSearchResults() {
  const query = cleanLookupText(els.recentOpponentSearch.value);
  const teams = state.teams
    .filter((team) => {
      if (!query) return true;
      return cleanLookupText(`${team.code} ${team.name}`).includes(query);
    })
    .map((team) => ({
      value: team.code,
      label: team.code,
      meta: team.name,
      team,
    }));
  renderSearchList(els.recentOpponentSearchResults, teams, state.recentOpponentCode, (item) => {
    state.recentOpponentCode = item.value;
    els.recentOpponentSearch.value = teamLabel(item.team);
    renderRecentOpponentSearchResults();
    loadRecentOpponent(item.value);
  });
}

async function loadRecentOpponent(opponentCode) {
  const player = currentPlayer();
  if (!player || !opponentCode) return;
  try {
    const params = new URLSearchParams({ playerId: player.player_id, opponent: opponentCode });
    const payload = await api(`/api/player-recent?${params.toString()}`);
    const recent = payload.recent || {};
    renderRecentForm(recent);
  } catch (error) {
    els.recentFormNote.textContent = error.message;
    renderRecentOpponentRows([]);
  }
}

function renderBatterHrProfile(profile) {
  if (!profile) return;
  els.batterHrTotal.textContent = profile.homeRuns ?? "--";
  els.batterHrPerGame.textContent = formatMaybeNumber(profile.homeRunsPerGame, 2);
  els.batterHrRate.textContent = formatMaybeRate(profile.homeRunRate);
  els.batterPaPerHr.textContent = profile.plateAppearancesPerHomeRun ? Number(profile.plateAppearancesPerHomeRun).toFixed(1) : "--";
  els.batterHrSlug.textContent = profile.slugging ? dec(profile.slugging) : "--";
  els.batterMatchupHr.textContent = profile.matchupHomeRuns ?? "--";
  els.batterMatchupBarrel.textContent = formatMaybeRate(profile.matchupBarrelRate);
  els.pitcherHrAllowedRate.textContent = formatMaybeRate(profile.allowedHomeRunRate);
}

function renderTeamMatchup(matchup) {
  const direct = matchup?.direct || {};
  const last5 = matchup?.last5 || {};
  if (!matchup || (!direct.games && !matchup.overall?.games)) {
    els.teamMatchupRecord.textContent = "--";
    els.teamMatchupWinRate.textContent = "--";
    els.teamMatchupLast5.textContent = "--";
    els.teamMatchupRunDiff.textContent = "--";
    els.teamMatchupRuns.textContent = "--";
    els.teamMatchupOps.textContent = "--";
    els.teamMatchupHr.textContent = "--";
    els.teamMatchupKRate.textContent = "--";
    els.teamMatchupNote.textContent = "Load team game logs to show win rate and advanced team matchup context.";
    return;
  }
  els.teamMatchupRecord.textContent = direct.games ? `${direct.wins}-${direct.losses}` : "--";
  els.teamMatchupWinRate.textContent = direct.games ? pct(direct.winRate) : "--";
  els.teamMatchupLast5.textContent = last5.games ? `${last5.wins}-${last5.losses}` : "--";
  els.teamMatchupRunDiff.textContent = direct.games ? signedNumber(direct.runDifferentialPerGame, 2) : "--";
  els.teamMatchupRuns.textContent = direct.games ? Number(direct.runsPerGame || 0).toFixed(2) : "--";
  els.teamMatchupOps.textContent = direct.ops ? dec(direct.ops) : "--";
  els.teamMatchupHr.textContent = direct.games ? Number(direct.homeRunsPerGame || 0).toFixed(2) : "--";
  els.teamMatchupKRate.textContent = direct.strikeoutRate ? pct(direct.strikeoutRate) : "--";
  const overall = matchup.overall || {};
  els.teamMatchupNote.textContent = direct.games
    ? `${matchup.note} Overall ${matchup.team}: ${overall.wins || 0}-${overall.losses || 0}, ${overall.runsPerGame || 0} R/G, ${overall.ops ? dec(overall.ops) : "--"} OPS.`
    : `${matchup.note} Overall ${matchup.team}: ${overall.wins || 0}-${overall.losses || 0}, ${overall.runsPerGame || 0} R/G.`;
}

function factorText(value) {
  if (!value) return "--";
  const pctDelta = (Number(value) - 1) * 100;
  return `${signedNumber(pctDelta, 1)}%`;
}

function renderEnvironment(environment) {
  if (!environment?.available) {
    els.envVenue.textContent = "--";
    els.envRoof.textContent = "--";
    els.envTemp.textContent = "--";
    els.envWind.textContent = "--";
    els.envParkFactor.textContent = "--";
    els.envHitFactor.textContent = "--";
    els.envHrFactor.textContent = "--";
    els.envKFactor.textContent = "--";
    els.environmentNote.textContent = "Refresh a game date or import BallparkPal/weather rows to blend park factor, roof, wind, and temperature into predictions.";
    return;
  }
  els.envVenue.textContent = environment.venue || environment.city || "--";
  els.envRoof.textContent = environment.roof || "--";
  els.envTemp.textContent = environment.temperature ? `${Number(environment.temperature).toFixed(0)}F` : "--";
  els.envWind.textContent = environment.windMph ? `${Number(environment.windMph).toFixed(0)} mph ${environment.windDirection || ""}`.trim() : "--";
  els.envParkFactor.textContent = factorText(environment.parkFactor);
  els.envHitFactor.textContent = factorText(environment.hitFactor);
  els.envHrFactor.textContent = factorText(environment.homeRunFactor);
  els.envKFactor.textContent = factorText(environment.strikeoutFactor);
  const source = environment.source || "saved context";
  els.environmentNote.textContent = `${source}: ${environment.game || "selected matchup"}${environment.weather ? `, ${environment.weather}` : ""}. Park and weather are blended into hit, HR, run, and K factors.`;
}

function renderAdvancedContext(context, role = "batter") {
  const quality = context?.quality || {};
  const rolling = context?.rolling || {};
  const last7 = rolling["7"] || rolling[7] || {};
  const split = context?.handedness || {};
  if (!context || (!Object.keys(quality).length && !Object.keys(rolling).length && !Object.keys(split).length)) {
    els.advXba.textContent = "--";
    els.advXslg.textContent = "--";
    els.advXwoba.textContent = "--";
    els.advBarrel.textContent = "--";
    els.advHardHit.textContent = "--";
    els.advLast7K.textContent = "--";
    els.advSplit.textContent = "--";
    els.advAdjustment.textContent = "--";
    els.advancedContextNote.textContent = "Run model data refresh for selected players to populate Savant quality, rolling form, and handedness split inputs.";
    return;
  }
  els.advXba.textContent = quality.xba ? dec(quality.xba) : "--";
  els.advXslg.textContent = quality.xslg ? dec(quality.xslg) : "--";
  els.advXwoba.textContent = quality.xwoba ? dec(quality.xwoba) : "--";
  els.advBarrel.textContent = formatMaybeRate(quality.barrelRate);
  els.advHardHit.textContent = formatMaybeRate(quality.hardHitRate);
  els.advLast7K.textContent = formatMaybeRate(last7.strikeoutRate);
  els.advSplit.textContent = split.split ? `${role === "pitcher" ? "vs " : "vs P"}${split.split}` : context.pitcherHand ? `vs P${context.pitcherHand}` : "--";
  els.advAdjustment.textContent = `${signedNumber(context.totalAdjustment || 0, 1)}%`;
  const pa = quality.plateAppearances || 0;
  els.advancedContextNote.textContent = `${role === "pitcher" ? "Pitcher" : "Batter"} Statcast context uses ${pa} PA/pitches of saved quality data plus rolling 7/14/30-day form${split.split ? ` and ${split.label || split.split} split` : ""}.`;
}

function renderPitcherProfile(profile) {
  if (!profile?.pitcher) {
    els.profileEra.textContent = "--";
    els.profileWhip.textContent = "--";
    els.profileK9.textContent = "--";
    els.profileBb9.textContent = "--";
    els.profileHr9.textContent = "--";
    els.profileH9.textContent = "--";
    els.profileKGame.textContent = "--";
    els.profileRunsGame.textContent = "--";
    els.pitcherProfileNote.textContent = "Choose an opposing pitcher or pitcher prop to see run prevention, strikeout, walk, and HR indicators.";
    return;
  }
  els.profileEra.textContent = formatMaybeNumber(profile.era, 2);
  els.profileWhip.textContent = formatMaybeNumber(profile.whip, 3);
  els.profileK9.textContent = formatMaybeNumber(profile.strikeoutsPerNine, 2);
  els.profileBb9.textContent = formatMaybeNumber(profile.walksPerNine, 2);
  els.profileHr9.textContent = formatMaybeNumber(profile.homeRunsPerNine, 2);
  els.profileH9.textContent = formatMaybeNumber(profile.hitsPerNine, 2);
  els.profileKGame.textContent = formatMaybeNumber(profile.strikeoutsPerGame, 2);
  els.profileRunsGame.textContent = formatMaybeNumber(profile.runsAllowedPerGame, 2);
  const recent = profile.recentVsOpponent || {};
  els.pitcherProfileNote.textContent = recent.games
    ? `${profile.pitcher} has ${recent.games} saved pitching log game(s) in this matchup context.`
    : `${profile.pitcher} profile uses season and uploaded pitching tables.`;
}

function renderBatterPrediction(payload) {
  const player = payload.player;
  const cards = payload.prediction.cards || [];
  renderCards(cards);
  setBatterDetailLabels();
  els.matchupLabel.textContent = `${player.team} vs ${payload.opponent.name}`;
  els.playerName.textContent = player.player;
  els.team.textContent = player.team;
  els.games.textContent = player.games;
  els.abGame.textContent = payload.inputs.abPerGame.toFixed(2);
  els.ba.textContent = dec(player.batting_average);
  els.ops.textContent = dec(player.ops);
  els.contact.textContent = pct(payload.inputs.contactRate);
  const dataAdjustment =
    (payload.opponent.opponentDataAdjustment || 0) +
    (payload.opponent.teamPitchingAdjustment || 0) +
    (payload.opponent.gameLogAdjustment || 0) +
    (payload.opponent.pitcherAdjustment || 0) +
    (payload.opponent.pitchingGameLogAdjustment || 0) +
    (payload.opponent.teamBattingAdjustment || 0) +
    (payload.opponent.teamGameLogAdjustment || 0) +
    (payload.opponent.advancedBatterAdjustment || 0) +
    (payload.opponent.advancedPitcherAdjustment || 0) +
    (payload.opponent.environmentAdjustment || 0);
  els.dataAdjustment.textContent = `${dataAdjustment.toFixed(1)}%`;
  els.totalAdjustment.textContent = `${payload.opponent.totalAdjustment.toFixed(1)}%`;
  renderMarket(payload.prediction.market);
  renderMatchup(payload.opponent.batterPitcher);
  renderTeamMatchup(payload.opponent.teamMatchup);
  renderEnvironment(payload.opponent.environment || payload.profiles?.environment);
  renderAdvancedContext(payload.opponent.advancedBatter || payload.profiles?.advancedBatter, "batter");
  state.recentOpponentCode = payload.opponent.code || state.recentOpponentCode;
  if (!els.recentOpponentSearch.value || document.activeElement !== els.recentOpponentSearch) {
    els.recentOpponentSearch.value = teamLabel(selectedTeam());
  }
  renderRecentOpponentSearchResults();
  renderRecentForm(payload.recent);
  renderBatterHrProfile(payload.profiles?.batterHomeRuns);
  renderPitcherProfile(payload.profiles?.pitcher);
  els.modelNote.textContent = `${payload.prediction.market?.verdict || "Market view"}: ${payload.note}`;
  renderRows();
}

function renderPitcherStrikeoutPrediction(payload) {
  const pitcher = payload.pitcher;
  const cards = payload.prediction.cards || [];
  renderCards(cards);
  setPitcherDetailLabels();
  if (payload.target === "pitcherWalks") {
    els.baLabel.textContent = "BB%";
    els.opsLabel.textContent = "Opp BB%";
  } else if (payload.target === "pitcherRunsAllowed") {
    els.baLabel.textContent = "R/IP";
    els.opsLabel.textContent = "Opp R/G";
  } else if (payload.target === "pitcherHitsAllowed") {
    els.baLabel.textContent = "H rate";
    els.opsLabel.textContent = "Opp AVG";
  }
  els.matchupLabel.textContent = `${pitcher.team || "--"} pitcher vs ${payload.opponent.name}`;
  els.playerName.textContent = pitcher.pitcher;
  els.team.textContent = pitcher.team || "--";
  els.games.textContent = pitcher.games || "--";
  els.abGame.textContent = payload.inputs.expectedInnings.toFixed(2);
  const primaryRate =
    payload.inputs.pitcherStrikeoutRate ??
    payload.inputs.pitcherWalkRate ??
    payload.inputs.pitcherHitRate ??
    payload.inputs.pitcherRunsPerInning ??
    0;
  const opponentRate =
    payload.inputs.opponentStrikeoutRate ??
    payload.inputs.opponentWalkRate ??
    payload.inputs.opponentHitRate ??
    payload.inputs.opponentRunsPerGame ??
    0;
  els.ba.textContent = payload.target === "pitcherRunsAllowed" ? Number(primaryRate).toFixed(2) : pct(primaryRate);
  els.ops.textContent = payload.target === "pitcherRunsAllowed" ? Number(opponentRate).toFixed(2) : pct(opponentRate);
  els.contact.textContent = payload.inputs.expectedBattersFaced.toFixed(1);
  els.dataAdjustment.textContent = `${(
    (payload.opponent.advancedAdjustment || 0) +
    (payload.opponent.teamGameLogAdjustment || 0) +
    (payload.opponent.advancedPitcherAdjustment || 0) +
    (payload.opponent.environmentAdjustment || 0)
  ).toFixed(1)}%`;
  els.totalAdjustment.textContent = `${payload.opponent.totalAdjustment.toFixed(1)}%`;
  renderMarket(payload.prediction.market);
  els.pitcherKRate.textContent = pct(payload.inputs.pitcherStrikeoutRate || payload.inputs.pitcherWalkRate || payload.inputs.pitcherHitRate || 0);
  els.opponentKRate.textContent = pct(payload.inputs.opponentStrikeoutRate || payload.inputs.opponentWalkRate || payload.inputs.opponentHitRate || 0);
  els.expectedBf.textContent = payload.inputs.expectedBattersFaced.toFixed(1);
  els.expectedIp.textContent = payload.inputs.expectedInnings.toFixed(2);
  renderStrikeoutTargets(payload.opponent.playerMatchups || []);
  renderTeamMatchup(payload.opponent.teamMatchup);
  renderEnvironment(payload.opponent.environment);
  renderAdvancedContext(payload.opponent.advancedPitcher, "pitcher");
  renderPitcherProfile(payload.profile);
  els.modelNote.textContent = `${payload.prediction.market?.verdict || "Market view"}: ${payload.note}`;
}

function renderStrikeoutTargets(matchups) {
  els.strikeoutRows.innerHTML = "";
  if (!matchups.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="5">Upload batter/player stats for the opponent team to see player-level K targets.</td>`;
    els.strikeoutRows.append(row);
    return;
  }
  for (const matchup of matchups) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(matchup.player)}</td>
      <td>${escapeHtml(Number(matchup.plateAppearancesPerGame || 0).toFixed(2))}</td>
      <td>${escapeHtml(pct(matchup.batterStrikeoutRate))}</td>
      <td>${escapeHtml(pct(matchup.matchupStrikeoutRate))}</td>
      <td>${escapeHtml(pct(matchup.probabilityOnePlus))}</td>
    `;
    els.strikeoutRows.append(row);
  }
}

async function predict() {
  renderModeControls();
  renderPitcherSelect();
  if (isPitcherPropMode()) {
    if (!els.pitcherSelect.value) {
      els.modelNote.textContent = "Upload or choose a pitcher to run the pitcher prop model.";
      return;
    }
    const params = new URLSearchParams({
      target: els.targetSelect.value,
      opponent: els.opponentSelect.value,
      pitcherKey: els.pitcherSelect.value,
      adjustment: els.adjustment.value,
      line: els.propLine.value || defaultLineForTarget(els.targetSelect.value),
      odds: els.americanOdds.value || "-110",
      date: els.modelRefreshDate.value || "",
    });
    const payload = await api(`/api/predict-pitcher?${params.toString()}`);
    renderPitcherStrikeoutPrediction(payload);
    return;
  }

  const playerId = els.playerSelect.value;
  if (!playerId) return;
  state.selectedPlayerId = playerId;
  const params = new URLSearchParams({
    playerId,
    target: els.targetSelect.value,
    opponent: els.opponentSelect.value,
    pitcherKey: els.pitcherSelect.value,
    adjustment: els.adjustment.value,
    line: els.propLine.value || defaultLineForTarget(els.targetSelect.value),
    odds: els.americanOdds.value || "-110",
    date: els.modelRefreshDate.value || "",
  });
  const payload = await api(`/api/predict?${params.toString()}`);
  renderBatterPrediction(payload);
}

function renderMatchup(matchup) {
  if (!matchup || !Number(matchup.plateAppearances || 0)) {
    els.matchupPa.textContent = "--";
    els.matchupWoba.textContent = "--";
    els.matchupXwoba.textContent = "--";
    els.matchupBarrel.textContent = "--";
    els.matchupWhiff.textContent = "--";
    els.matchupKRate.textContent = "--";
    els.matchupHr.textContent = "--";
    els.matchupOps.textContent = "--";
    els.matchupNote.textContent = matchup
      ? `${matchup.batter} vs ${matchup.pitcher} is saved, but there are no recorded plate appearances yet.`
      : "No exact advanced batter-vs-pitcher matchup found for this selection.";
    return;
  }

  const kRate = matchup.plateAppearances ? matchup.strikeouts / matchup.plateAppearances : 0;
  els.matchupPa.textContent = matchup.plateAppearances || "--";
  els.matchupWoba.textContent = matchup.woba ? dec(matchup.woba) : "--";
  els.matchupXwoba.textContent = matchup.xwoba ? dec(matchup.xwoba) : "--";
  els.matchupBarrel.textContent = matchup.barrelRate ? pct(matchup.barrelRate) : "--";
  els.matchupWhiff.textContent = matchup.whiffRate ? pct(matchup.whiffRate) : "--";
  els.matchupKRate.textContent = kRate ? pct(kRate) : "--";
  els.matchupHr.textContent = matchup.homeRuns ?? "--";
  els.matchupOps.textContent = matchup.ops ? dec(matchup.ops) : "--";
  els.matchupNote.textContent = `${matchup.batter} vs ${matchup.pitcher} exact matchup is being blended into the selected prop.`;
}

function renderGithubRuns(runs) {
  els.githubRunRows.innerHTML = "";
  if (!runs.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="5">No recent workflow runs found.</td>`;
    els.githubRunRows.append(row);
    return;
  }
  for (const run of runs) {
    const row = document.createElement("tr");
    const runUrl = safeExternalUrl(run.url);
    const runName = escapeHtml(run.name || "--");
    row.innerHTML = `
      <td>${runUrl ? `<a href="${escapeHtml(runUrl)}" target="_blank" rel="noreferrer">${runName}</a>` : runName}</td>
      <td>${escapeHtml(run.status || "--")}</td>
      <td>${escapeHtml(run.conclusion || "--")}</td>
      <td>${escapeHtml(run.branch || "--")}</td>
      <td>${escapeHtml(run.commitSha || "--")}</td>
    `;
    els.githubRunRows.append(row);
  }
}

async function checkGithubRepo() {
  const repository = els.githubRepository.value.trim();
  if (!repository) {
    els.githubStatus.textContent = "Missing repo";
    els.githubRepoName.textContent = "Enter owner/repo";
    els.githubRepoMeta.textContent = "Example: octocat/Hello-World";
    renderGithubRuns([]);
    return;
  }
  els.githubButton.disabled = true;
  els.githubStatus.textContent = "Connecting";
  try {
    const payload = await api(`/api/github?repository=${encodeURIComponent(repository)}`);
    const repo = payload.repository || {};
    els.githubStatus.textContent = payload.authenticated ? "Connected with token" : "Connected public API";
    els.githubRepoName.textContent = repo.fullName || repository;
    els.githubRepoMeta.textContent = `${repo.visibility || "repo"} | ${repo.defaultBranch || "branch"} | ${repo.language || "code"} | ${repo.openIssues ?? 0} open issues | rate left ${payload.rateLimitRemaining ?? "--"}`;
    renderGithubRuns(payload.workflowRuns || []);
  } catch (error) {
    els.githubStatus.textContent = "GitHub error";
    els.githubRepoName.textContent = repository;
    els.githubRepoMeta.textContent = error.message;
    renderGithubRuns([]);
  } finally {
    els.githubButton.disabled = false;
  }
}

function renderMlbBatting(batting = {}) {
  els.mlbGames.textContent = batting.games || "--";
  els.mlbPa.textContent = batting.plateAppearances || "--";
  els.mlbAb.textContent = batting.atBats || "--";
  els.mlbHits.textContent = batting.hits || "--";
  els.mlbHr.textContent = batting.homeRuns || "--";
  els.mlbAvg.textContent = batting.battingAverage ? dec(batting.battingAverage) : "--";
  els.mlbSlg.textContent = batting.slugging ? dec(batting.slugging) : "--";
  els.mlbOps.textContent = batting.ops ? dec(batting.ops) : "--";
}

async function checkMlbStatus() {
  try {
    const payload = await api("/api/mlb/status");
    els.mlbStatus.textContent = payload.installed ? "Package ready" : "Install needed";
    els.mlbMeta.textContent = payload.installed
      ? `${payload.package} is installed from ${payload.repository}`
      : `${payload.installCommand} | ${payload.repository}`;
  } catch (error) {
    els.mlbStatus.textContent = "Status error";
    els.mlbMeta.textContent = error.message;
  }
}

async function lookupMlbPlayer() {
  const name = els.mlbPlayerName.value.trim();
  if (!name) {
    els.mlbStatus.textContent = "Missing player";
    els.mlbPlayerResult.textContent = "Enter a player name";
    els.mlbMeta.textContent = "Example: Aaron Judge";
    renderMlbBatting();
    return;
  }
  els.mlbButton.disabled = true;
  els.mlbStatus.textContent = "Loading MLB data";
  try {
    const params = new URLSearchParams({
      name,
      season: els.mlbSeason.value || String(new Date().getFullYear()),
    });
    const payload = await api(`/api/mlb/player?${params.toString()}`);
    const player = payload.player || {};
    els.mlbStatus.textContent = payload.source;
    els.mlbPlayerResult.textContent = player.name || name;
    const stored = payload.stored || {};
    els.mlbMeta.textContent = `${payload.season} | ${player.currentTeam || "team unknown"} | ${player.primaryPosition || "position unknown"} | ${stored.action || "stored"} in batting data`;
    renderMlbBatting(payload.batting || {});
    if (stored.playerId) {
      state.selectedPlayerId = stored.playerId;
      await loadPlayers();
    }
  } catch (error) {
    els.mlbStatus.textContent = "MLB lookup error";
    els.mlbPlayerResult.textContent = name;
    els.mlbMeta.textContent = error.message;
    renderMlbBatting();
  } finally {
    els.mlbButton.disabled = false;
  }
}

const mlbCommandPresets = {
  playerStats: { stats: "season,career", groups: "hitting,pitching", hint: "Runs get_people_id, then get_player_stats with selected stats/groups." },
  teamStats: { stats: "season,seasonAdvanced", groups: "hitting", hint: "Runs get_team_id, then get_team_stats." },
  expectedStats: { stats: "expectedStatistics", groups: "hitting", hint: "Expected AVG/SLG style Statcast expected statistics." },
  vsPlayerStats: { stats: "vsPlayer", groups: "hitting", hint: "Requires Player and Opposing player." },
  hotColdZones: { stats: "hotColdZones", groups: "hitting", hint: "Returns zone splits for the selected hitter." },
  schedule: { hint: "Requires Date. Returns games and game IDs for that day." },
  game: { hint: "Requires Game ID. Returns game weather and current linescore summary." },
  playByPlay: { hint: "Requires Game ID. Returns play-by-play object." },
  lineScore: { hint: "Requires Game ID. Returns line score object." },
  boxScore: { hint: "Requires Game ID. Returns box score object." },
  gamepace: { hint: "Requires Season. Returns pace-of-game metrics." },
  people: { hint: "Uses Sport ID, normally 1 for MLB, and Limit for output size." },
  peopleId: { hint: "Requires Player. Returns matching MLB person IDs." },
  team: { hint: "Requires Team name or ID. Returns team and venue metadata." },
  teamRoster: { hint: "Requires Team name or ID. Returns player roster." },
  teamCoaches: { hint: "Requires Team name or ID. Returns coach roster." },
  draft: { hint: "Uses Season as draft year." },
  awards: { hint: "Requires Award ID, for example RETIREDUNI_108." },
  venue: { hint: "Requires Venue name or ID." },
  division: { hint: "Requires Division ID, for example 200." },
  league: { hint: "Requires League ID, for example 103." },
  season: { hint: "Uses Season field." },
  standings: { hint: "Requires League ID and Season. AL is 103, NL is 104." },
};

function applyMlbCommandPreset() {
  const preset = mlbCommandPresets[els.mlbCommand.value] || {};
  if (preset.stats) els.mlbCommandStats.value = preset.stats;
  if (preset.groups) els.mlbCommandGroups.value = preset.groups;
  els.mlbCommandHint.textContent = preset.hint || "Fill the fields needed for this MLB StatsAPI command.";
}

function compactCommandPayload(payload) {
  if (payload.raw && JSON.stringify(payload.raw).length > 20000) {
    return {
      ...payload,
      raw: {
        note: "Raw payload was large; use the endpoint directly if you need the complete object.",
        keys: Object.keys(payload.raw),
      },
    };
  }
  return payload;
}

async function runMlbCommand() {
  els.mlbCommandButton.disabled = true;
  els.mlbCommandOutput.textContent = "Loading...";
  els.mlbStatus.textContent = "Running command";
  try {
    const params = new URLSearchParams({
      command: els.mlbCommand.value,
      player: els.mlbCommandPlayer.value,
      opposingPlayer: els.mlbCommandOpponent.value,
      team: els.mlbCommandTeam.value,
      stats: els.mlbCommandStats.value,
      groups: els.mlbCommandGroups.value,
      date: els.mlbCommandDate.value,
      gameId: els.mlbCommandGameId.value,
      sportId: els.mlbCommandSportId.value,
      leagueId: els.mlbCommandLeagueId.value,
      divisionId: els.mlbCommandDivisionId.value,
      awardId: els.mlbCommandAwardId.value,
      venue: els.mlbCommandVenue.value,
      season: els.mlbSeason.value || String(new Date().getFullYear()),
      limit: els.mlbCommandLimit.value || "25",
    });
    const payload = await api(`/api/mlb/command?${params.toString()}`);
    els.mlbStatus.textContent = "Command complete";
    els.mlbPlayerResult.textContent = `MLB command: ${payload.command}`;
    els.mlbMeta.textContent = "Result rendered below as JSON.";
    els.mlbCommandOutput.textContent = JSON.stringify(compactCommandPayload(payload), null, 2);
  } catch (error) {
    els.mlbStatus.textContent = "Command error";
    els.mlbMeta.textContent = error.message;
    els.mlbCommandOutput.textContent = JSON.stringify({ error: error.message }, null, 2);
  } finally {
    els.mlbCommandButton.disabled = false;
  }
}

function espnDateParam() {
  if (!els.espnDate.value) return "";
  return els.espnDate.value.replaceAll("-", "");
}

async function applyEspnMatchup(eventId, side) {
  const event = state.espnEvents.find((item) => item.id === eventId);
  if (!event) return;

  const selected = event[side] || {};
  const opponent = side === "away" ? event.home : event.away;
  const selectedTeamCode = teamCode(selected.team);
  const opponentTeamCode = teamCode(opponent?.team);
  const pitcherSide = isPitcherPropMode() ? selected : opponent;
  const pitcherOption = findPitcherOption(pitcherSide?.probableStarter, pitcherSide?.team);

  if (opponentTeamCode) {
    els.opponentSelect.value = opponentTeamCode;
    const team = state.teams.find((item) => item.code === opponentTeamCode);
    els.teamSearch.value = teamLabel(team);
  }
  renderPitcherSelect();
  if (pitcherOption) {
    els.pitcherSelect.value = pitcherOption.key;
    state.selectedPitcherKey = pitcherOption.key;
    els.pitcherSearch.value = pitcherLabel(pitcherOption);
  }

  const selectedStarter = starterLine(selected);
  const opponentStarter = starterLine(opponent);
  const matchupText = isPitcherPropMode()
    ? `${selectedStarter} vs ${opponentTeamCode || "opponent"}`
    : `${selectedTeamCode || "team"} bats vs ${opponentStarter}`;
  els.espnStatus.textContent = "Matchup applied";
  els.espnMeta.textContent = pitcherOption
    ? `${matchupText}. Pitcher matched in uploaded data.`
    : `${matchupText}. Probable starter not matched in uploaded pitcher data.`;
  await predict();
}

function renderEspnScores(events) {
  els.espnScoreRows.innerHTML = "";
  if (!events.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="7">No ESPN games found for this date.</td>`;
    els.espnScoreRows.append(row);
    return;
  }
  for (const event of events) {
    const away = event.away || {};
    const home = event.home || {};
    const row = document.createElement("tr");
    const eventId = event.id || "";
    const awayCode = teamCode(away.team) || "Away";
    const homeCode = teamCode(home.team) || "Home";
    row.innerHTML = `
      <td>${escapeHtml(event.shortName || event.name)}</td>
      <td>${escapeHtml(event.status?.detail || "--")}</td>
      <td>${escapeHtml(teamLine(away))}</td>
      <td>${escapeHtml(teamLine(home))}</td>
      <td class="probables-cell">
        <span>${escapeHtml(awayCode)}: ${escapeHtml(starterLine(away))}</span>
        <span>${escapeHtml(homeCode)}: ${escapeHtml(starterLine(home))}</span>
      </td>
      <td>${escapeHtml(event.venue || event.city || "--")}</td>
      <td>
        <div class="mini-actions">
          <button class="mini-button" type="button" data-event-id="${escapeHtml(eventId)}" data-side="away">${escapeHtml(awayCode)}</button>
          <button class="mini-button" type="button" data-event-id="${escapeHtml(eventId)}" data-side="home">${escapeHtml(homeCode)}</button>
        </div>
      </td>
    `;
    for (const button of row.querySelectorAll("[data-event-id]")) {
      button.addEventListener("click", () => applyEspnMatchup(button.dataset.eventId, button.dataset.side));
    }
    els.espnScoreRows.append(row);
  }
}

function renderEspnTeam(teamPayload) {
  const team = teamPayload.team || {};
  els.espnTeamName.textContent = team.displayName || "--";
  els.espnTeamAbbr.textContent = team.abbreviation || "--";
  els.espnTeamId.textContent = team.id || "--";
  els.espnTeamFallback.textContent = teamPayload.fallbackUsed ? "Yes" : "No";
}

async function loadEspnTeams() {
  try {
    const payload = await api("/api/espn/teams");
    els.espnTeamSelect.innerHTML = "";
    for (const team of payload.teams || []) {
      const option = document.createElement("option");
      option.value = team.abbreviation || team.id;
      option.textContent = `${team.abbreviation} - ${team.displayName}`;
      els.espnTeamSelect.append(option);
    }
    els.espnStatus.textContent = "Teams loaded";
    els.espnMeta.textContent = `${payload.count} ESPN MLB teams available.`;
  } catch (error) {
    els.espnStatus.textContent = "ESPN teams error";
    els.espnMeta.textContent = error.message;
  }
}

async function loadEspnScores() {
  els.espnScoresButton.disabled = true;
  els.espnStatus.textContent = "Loading scores";
  try {
    const params = new URLSearchParams();
    const date = espnDateParam();
    if (date) params.set("dates", date);
    const payload = await api(`/api/espn/scoreboard?${params.toString()}`);
    state.espnEvents = payload.events || [];
    els.espnStatus.textContent = "Scores loaded";
    els.espnSummary.textContent = `${payload.count} MLB games`;
    els.espnMeta.textContent = payload.day?.date ? `Scoreboard date ${payload.day.date}` : payload.endpoint;
    renderEspnScores(state.espnEvents);
  } catch (error) {
    state.espnEvents = [];
    els.espnStatus.textContent = "ESPN scores error";
    els.espnMeta.textContent = error.message;
    renderEspnScores([]);
  } finally {
    els.espnScoresButton.disabled = false;
  }
}

async function loadEspnTeam() {
  const team = els.espnTeamSelect.value;
  if (!team) return;
  els.espnTeamButton.disabled = true;
  els.espnStatus.textContent = "Loading team";
  try {
    const payload = await api(`/api/espn/teams/${encodeURIComponent(team)}`);
    els.espnStatus.textContent = "Team loaded";
    els.espnSummary.textContent = payload.team?.displayName || team;
    els.espnMeta.textContent = payload.fallbackUsed
      ? "Specific route resolved through the all-teams fallback."
      : payload.endpoint;
    renderEspnTeam(payload);
  } catch (error) {
    els.espnStatus.textContent = "ESPN team error";
    els.espnMeta.textContent = error.message;
  } finally {
    els.espnTeamButton.disabled = false;
  }
}

els.csvFile.addEventListener("change", async (event) => {
  const files = [...event.target.files];
  if (!files.length) return;
  try {
    await uploadFiles(files);
  } catch (error) {
    els.uploadLabel.textContent = error.message;
  }
});

els.playerSearch.addEventListener("input", renderPlayerSearchResults);
els.playerSearch.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    const first = els.playerSearchResults.querySelector(".search-option");
    if (first) first.click();
  }
});
els.teamSearch.addEventListener("input", renderTeamSearchResults);
els.teamSearch.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    const first = els.teamSearchResults.querySelector(".search-option");
    if (first) first.click();
  }
});
els.recentOpponentSearch.addEventListener("input", renderRecentOpponentSearchResults);
els.recentOpponentSearch.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    const first = els.recentOpponentSearchResults.querySelector(".search-option");
    if (first) first.click();
  }
});
els.pitcherSearch.addEventListener("input", renderPitcherSearchResults);
els.pitcherSearch.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    const first = els.pitcherSearchResults.querySelector(".search-option");
    if (first) first.click();
  }
});
els.playerSelect.addEventListener("change", () => {
  state.selectedPlayerId = els.playerSelect.value;
  els.playerSearch.value = playerLabel(currentPlayer());
  predict();
});
els.targetSelect.addEventListener("change", () => {
  els.propLine.value = defaultLineForTarget(els.targetSelect.value);
  renderModeControls();
  renderPitcherSelect();
  predict();
});
els.opponentSelect.addEventListener("change", () => {
  els.teamSearch.value = teamLabel(selectedTeam());
  renderPitcherSelect();
  predict();
});
els.pitcherSelect.addEventListener("change", () => {
  state.selectedPitcherKey = els.pitcherSelect.value;
  els.pitcherSearch.value = pitcherLabel(currentPitcher());
  predict();
});
els.propLine.addEventListener("change", predict);
els.americanOdds.addEventListener("change", predict);
els.predictButton.addEventListener("click", predict);
els.modelRefreshButton.addEventListener("click", refreshModelData);
els.propBoardButton.addEventListener("click", analyzePropBoard);
els.search.addEventListener("input", renderRows);
els.boardMode.addEventListener("change", () => {
  state.boardMode = els.boardMode.value;
  state.playerSort =
    state.boardMode === "pitchers"
      ? { key: "strikeoutRate", direction: "desc" }
      : state.boardMode === "both"
        ? { key: "rateTwo", direction: "desc" }
        : { key: "ops", direction: "desc" };
  renderRows();
});
els.csvType.addEventListener("change", updateCsvTypeHelper);
els.urlImportButton.addEventListener("click", importDatasetUrl);
els.bulkUrlImportButton.addEventListener("click", importDatasetUrls);
els.refreshSourcesButton.addEventListener("click", () => refreshStoredSources());
els.datasetUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    importDatasetUrl();
  }
});
els.playerBoardHead.addEventListener("click", (event) => {
  const header = event.target.closest(".sort-header");
  if (!header) return;
  const key = header.dataset.sort;
  if (state.playerSort.key === key) {
    state.playerSort.direction = state.playerSort.direction === "asc" ? "desc" : "asc";
  } else {
    state.playerSort.key = key;
    state.playerSort.direction = ["player", "pitcher", "team", "name", "type"].includes(key) ? "asc" : "desc";
  }
  renderRows();
});
els.githubButton.addEventListener("click", checkGithubRepo);
els.githubRepository.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    checkGithubRepo();
  }
});
els.mlbButton.addEventListener("click", lookupMlbPlayer);
els.mlbPlayerName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    lookupMlbPlayer();
  }
});
els.mlbCommand.addEventListener("change", applyMlbCommandPreset);
els.mlbCommandButton.addEventListener("click", runMlbCommand);
els.espnScoresButton.addEventListener("click", loadEspnScores);
els.espnTeamButton.addEventListener("click", loadEspnTeam);
els.adjustment.addEventListener("input", () => {
  els.adjustmentValue.textContent = els.adjustment.value;
});
els.adjustment.addEventListener("change", predict);

loadPlayers().catch((error) => {
  els.modelNote.textContent = error.message;
});
renderDatasetGuide();
updateCsvTypeHelper();
checkMlbStatus();
applyMlbCommandPreset();
loadEspnTeams();
loadEspnScores();
renderPropBoardRows([]);
renderPropParlays([]);
