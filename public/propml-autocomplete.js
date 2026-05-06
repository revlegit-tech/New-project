(() => {
  const $ = (selector) => document.querySelector(selector);

  const state = {
    players: [],
    teams: [],
    loaded: false,
  };

  const fields = [
    {
      input: "#propMlPlayer",
      type: "player",
      label: "Player",
    },
    {
      input: "#propMlPitcher",
      type: "player",
      label: "Pitcher",
    },
    {
      input: "#propMlTeam",
      type: "team",
      label: "Team",
    },
    {
      input: "#propMlOpponent",
      type: "team",
      label: "Opponent",
    },
  ];

  function normalize(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[^\w\s]/g, "")
      .replace(/\s+/g, " ");
  }

  function title(value) {
    return String(value || "")
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  async function getJson(path) {
    const response = await fetch(path);
    const text = await response.text();

    let payload;
    try {
      payload = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(`Endpoint returned non-JSON. Status ${response.status}. First text: ${text.slice(0, 120)}`);
    }

    if (!response.ok) {
      throw new Error(payload.error || `Request failed ${response.status}`);
    }

    return payload;
  }

  function asArray(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload.players)) return payload.players;
    if (Array.isArray(payload.teams)) return payload.teams;
    if (Array.isArray(payload.data)) return payload.data;
    if (Array.isArray(payload.rows)) return payload.rows;
    return [];
  }

  function playerName(row) {
    return (
      row.name ||
      row.fullName ||
      row.player ||
      row.playerName ||
      row.displayName ||
      row.label ||
      ""
    );
  }

  function playerTeam(row) {
    return (
      row.team ||
      row.teamAbbr ||
      row.team_abbr ||
      row.currentTeam ||
      row.mlbTeam ||
      ""
    );
  }

  function teamAbbr(row) {
    return (
      row.abbreviation ||
      row.abbr ||
      row.team ||
      row.teamAbbr ||
      row.code ||
      row.id ||
      ""
    );
  }

  function teamName(row) {
    return (
      row.name ||
      row.displayName ||
      row.teamName ||
      row.location ||
      row.shortDisplayName ||
      teamAbbr(row)
    );
  }

  function uniqueBy(items, keyFn) {
    const seen = new Set();
    const out = [];

    for (const item of items) {
      const key = normalize(keyFn(item));
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }

    return out;
  }

  async function loadData() {
    if (state.loaded) return;

    try {
      const [playersPayload, teamsPayload] = await Promise.allSettled([
        getJson("/api/players"),
        getJson("/api/espn/teams"),
      ]);

      if (playersPayload.status === "fulfilled") {
        const rawPlayers = asArray(playersPayload.value);
        state.players = uniqueBy(
          rawPlayers
            .map((row) => ({
              type: "player",
              name: playerName(row),
              team: playerTeam(row),
              raw: row,
            }))
            .filter((row) => row.name),
          (row) => `${row.name}-${row.team}`
        );
      }

      if (teamsPayload.status === "fulfilled") {
        const rawTeams = asArray(teamsPayload.value);
        state.teams = uniqueBy(
          rawTeams
            .map((row) => ({
              type: "team",
              abbr: teamAbbr(row),
              name: teamName(row),
              raw: row,
            }))
            .filter((row) => row.abbr || row.name),
          (row) => `${row.abbr}-${row.name}`
        );
      }

      state.loaded = true;
    } catch (error) {
      console.warn("Autocomplete data load failed", error);
    }
  }

  function makeBox(input) {
    const existing = input.parentElement?.querySelector(".propml-autocomplete-results");
    if (existing) return existing;

    const box = document.createElement("div");
    box.className = "propml-autocomplete-results hidden";
    input.insertAdjacentElement("afterend", box);
    return box;
  }

  function clearBox(box) {
    box.innerHTML = "";
    box.classList.add("hidden");
  }

  function startsWithScore(query, text) {
    const nQuery = normalize(query);
    const nText = normalize(text);

    if (!nQuery || !nText) return 0;
    if (nText.startsWith(nQuery)) return 100;
    if (nText.split(" ").some((part) => part.startsWith(nQuery))) return 80;
    if (nText.includes(nQuery)) return 40;
    return 0;
  }

  function playerMatches(query) {
    return state.players
      .map((row) => {
        const score = Math.max(
          startsWithScore(query, row.name),
          startsWithScore(query, row.team)
        );

        return { ...row, score };
      })
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
      .slice(0, 12);
  }

  function teamMatches(query) {
    return state.teams
      .map((row) => {
        const score = Math.max(
          startsWithScore(query, row.abbr),
          startsWithScore(query, row.name)
        );

        return { ...row, score };
      })
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score || a.abbr.localeCompare(b.abbr))
      .slice(0, 12);
  }

  function fillInput(input, config, item) {
    if (config.type === "team") {
      input.value = item.abbr || item.name || "";
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }

    input.value = title(item.name || "");
    input.dispatchEvent(new Event("change", { bubbles: true }));

    // Helpful auto-fill: if selecting a player and team is empty, fill team.
    if (config.input === "#propMlPlayer") {
      const teamInput = $("#propMlTeam");
      if (teamInput && !teamInput.value && item.team) {
        teamInput.value = String(item.team).toUpperCase();
        teamInput.dispatchEvent(new Event("change", { bubbles: true }));
      }
    }
  }

  function renderResults(input, config, box, query) {
    const items = config.type === "team" ? teamMatches(query) : playerMatches(query);

    box.innerHTML = "";

    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "propml-autocomplete-empty";
      empty.textContent = query ? "No matches found" : "Start typing to search";
      box.appendChild(empty);
      box.classList.remove("hidden");
      return;
    }

    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "propml-autocomplete-item";

      if (config.type === "team") {
        button.innerHTML = `
          <strong>${item.abbr || "--"}</strong>
          <span>${item.name || ""}</span>
        `;
      } else {
        button.innerHTML = `
          <strong>${title(item.name)}</strong>
          <span>${item.team ? item.team.toUpperCase() : "Player"}</span>
        `;
      }

      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
        fillInput(input, config, item);
        clearBox(box);
      });

      box.appendChild(button);
    }

    box.classList.remove("hidden");
  }

  function attachAutocomplete(config) {
    const input = $(config.input);
    if (!input || input.dataset.propMlAutocomplete === "1") return;

    input.dataset.propMlAutocomplete = "1";
    input.autocomplete = "off";

    const label = input.closest("label");
    if (label) label.classList.add("propml-autocomplete-wrap");

    const box = makeBox(input);

    input.addEventListener("focus", async () => {
      await loadData();
      renderResults(input, config, box, input.value);
    });

    input.addEventListener("input", async () => {
      await loadData();
      renderResults(input, config, box, input.value);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        clearBox(box);
      }
    });

    document.addEventListener("mousedown", (event) => {
      if (!box.contains(event.target) && event.target !== input) {
        clearBox(box);
      }
    });
  }

  function addQuickHint() {
    const propPanel = $("#propMlPredictButton")?.closest("details");
    if (!propPanel || $("#propMlAutocompleteHint")) return;

    const body = $(".model-refresh-body", propPanel);
    if (!body) return;

    const hint = document.createElement("p");
    hint.id = "propMlAutocompleteHint";
    hint.className = "model-note propml-autocomplete-hint";
    hint.textContent =
      "Tip: type the first letter of a player, pitcher, team, or opponent to pick from available saved data.";

    body.prepend(hint);
  }

  function init() {
    fields.forEach(attachAutocomplete);
    addQuickHint();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
