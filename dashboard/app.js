// dashboard/app.js
// Trust boundary: leak.evidence, leak.suggested_action, rule.narrative,
// and suggested_entry.title are server-constructed in metrics.py from
// numeric inputs and hardcoded f-strings — safe to inline into HTML.
// game_url comes from Chess.com's API — escape before inlining.
(function() {
  const escapeAttr = s => String(s).replace(/[&"<>]/g,
    c => ({"&":"&amp;","\"":"&quot;","<":"&lt;",">":"&gt;"}[c]));
  const D = window.DATA;
  if (!D) {
    document.body.innerHTML = "<p style='padding:2rem'>No data. Run refresh.py.</p>";
    return;
  }
  renderKPI(D);
  renderBehavior(D.behavior);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics?.session_decay);
  renderFamilyBlock(D.opening_families, "white",
    "#white-families-table", "white-board", "white-board-meta", false);
  renderFamilyBlock(D.opening_families, "black",
    "#black-families-table", "black-board", "black-board-meta", true);
  renderOpeningDetail(D);
  renderSessions(D.sessions);
  renderDrillinCards(D);

  function renderKPI(d) {
    const strip = document.getElementById("kpi-strip");
    if (!strip) return;
    const k = d.kpis;
    const lastDelta = (d.sessions && d.sessions.length > 0)
      ? d.sessions[d.sessions.length - 1].rating_delta
      : null;
    const lastStr = lastDelta == null ? "—" : (lastDelta >= 0 ? "+" : "") + lastDelta;
    strip.insertAdjacentHTML('beforeend', `
      <div class="kpi"><span class="kpi-label">Rating</span>
        <span class="kpi-value">${k.current_rating ?? "—"}</span></div>
      <div class="kpi"><span class="kpi-label">Games</span>
        <span class="kpi-value">${k.games_total}</span></div>
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value${k.recent_form_win_pct >= 50 ? " accent" : ""}">${k.recent_form_win_pct}%</span></div>
      <div class="kpi"><span class="kpi-label">Last session</span>
        <span class="kpi-value">${lastStr}</span></div>
      <div class="kpi"><span class="kpi-label">Updated</span>
        <span class="kpi-value" style="font-size:0.9rem">${new Date(d.generated_at).toLocaleString()}</span></div>
    `);
  }

  function renderLeaks(leaks) {
    const root = document.getElementById("leak-list");
    if (!root) return;
    if (!leaks || leaks.length === 0) {
      root.innerHTML = `<p style="color:var(--muted)">No leaks detected in the last 30 games.</p>`;
      return;
    }
    root.innerHTML = leaks.map(L => `
      <div class="leak severity-${L.severity}">
        <div class="leak-name">${L.name.replace(/_/g, " ")}</div>
        <div class="leak-evidence">${L.evidence}</div>
        <div class="leak-action">→ ${L.suggested_action}</div>
      </div>
    `).join("");
  }

  function renderRule(rule) {
    const root = document.getElementById("next-rule");
    if (!root) return;
    root.innerHTML = `
      <dl class="rule-block">
        <dt>Game cap</dt><dd>${rule.game_cap}</dd>
        <dt>Move-10 target</dt><dd>${rule.move_10_target_seconds}s left</dd>
        <dt>Stop if</dt><dd>rating drops ${rule.stop_if_rating_drops} in a session</dd>
      </dl>
      <div class="rule-narrative">${rule.narrative}</div>
    `;
  }

  function renderRecentLosses(losses) {
    if (!document.getElementById("losses-table")) return;
    new Tabulator("#losses-table", {
      data: losses, layout: "fitDataStretch", pagination: false,
      columns: [
        {title: "Opening", field: "opening", widthGrow: 2},
        {title: "Loss", field: "loss_type"},
        {title: "Moves", field: "moves", sorter: "number"},
        {title: "Clock", field: "final_clock", sorter: "number"},
        {title: "OppΔ", field: "opp_rating_diff", sorter: "number"},
        {title: "Suggested entry", field: "suggested_entry",
         formatter: c => c.getValue().title, widthGrow: 3},
        {title: "Game", field: "game_url",
         formatter: c => `<a href="${escapeAttr(c.getValue())}" target="_blank">open</a>`},
      ],
    });
    const copyBtn = document.getElementById("copy-suggestions");
    if (losses.length === 0) {
      copyBtn.style.display = "none";
      return;
    }
    copyBtn.onclick = () => {
      const entries = losses.map(L => L.suggested_entry);
      const payload = JSON.stringify(entries, null, 2);
      navigator.clipboard.writeText(payload)
        .catch(() => { console.log(payload); alert("Copy failed — payload logged to console."); });
    };
  }

  function renderErrorLog(rows) {
    if (!document.getElementById("error-log-table")) return;
    new Tabulator("#error-log-table", {
      data: rows, layout: "fitDataStretch",
      placeholder: "No entries yet. Paste from suggestions above into data/annotations.json.",
      columns: [
        {title: "Title", field: "title"},
        {title: "Pattern", field: "pattern"},
        {title: "# Games", field: "game_refs",
         formatter: c => (c.getValue() || []).length, sorter: "number"},
        {title: "Created", field: "created"},
      ],
    });
  }

  function renderProcess(pm) {
    if (!document.getElementById("process-block")) return;
    const fmt = v => v === null || v === undefined ? "—" : v;
    document.getElementById("process-block").innerHTML = `
      <div class="process-grid">
        <div class="process-card"><div class="pm-label">Reserve @ move 10 (median)</div><div class="pm-value">${fmt(pm.reserve_move_10_median)}s</div></div>
        <div class="process-card"><div class="pm-label">Reserve @ move 20 (median)</div><div class="pm-value">${fmt(pm.reserve_move_20_median)}s</div></div>
        <div class="process-card"><div class="pm-label">Opening velocity (median s on my first 8 moves)</div><div class="pm-value">${fmt(pm.opening_velocity_median)}s</div></div>
        <div class="process-card"><div class="pm-label">Time-burn delta (early − late)</div><div class="pm-value">${fmt(pm.time_burn_delta)}</div></div>
        <div class="process-card"><div class="pm-label">Outlasted-but-flagged</div><div class="pm-value">${pm.outlasted_but_flagged_count}</div></div>
      </div>
    `;
  }

  function renderSessionDecay(rows) {
    if (!document.getElementById("session-decay-table")) return;
    new Tabulator("#session-decay-table", {
      data: rows, layout: "fitColumns",
      columns: [
        {title: "Games in session", field: "bucket"},
        {title: "N", field: "games", sorter: "number"},
        {title: "Win%", field: "win_pct", sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", sorter: "number"},
        {title: "Mate%", field: "mate_pct", sorter: "number"},
      ],
    });
  }

  // Tier-1 family block on index.html — table + board panel. One row per
  // (family, color). Click row to update the board to the family's canonical
  // (most-played) position. Double-click row, or click "→ View variations"
  // in the meta panel, to drill into opening.html.
  function renderFamilyBlock(families, color, tableSelector, boardId, metaId, flip) {
    if (!document.querySelector(tableSelector)) return;
    const rows = (families || []).filter(r => r.color === color);
    const table = new Tabulator(tableSelector, {
      data: rows, layout: "fitColumns", height: "540px",
      columns: [
        {title: "Opening", field: "family", headerFilter: "input", minWidth: 180},
        {title: "Games", field: "games", width: 80, sorter: "number"},
        {title: "Win%", field: "win_pct", width: 80, sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", width: 80, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 80, sorter: "number"},
        {title: "#Vars", field: "variation_count", width: 75, sorter: "number"},
        {title: "Form", field: "form", width: 120, formatter: sparkline, headerSort: false},
      ],
      initialSort: [{column: "games", dir: "desc"}],
    });
    table.on("rowClick", (e, row) => selectFamilyRow(row, boardId, metaId, flip));
    table.on("rowDblClick", (e, row) => drillIntoFamily(row.getData()));
    table.on("tableBuilt", () => {
      const first = table.getRows()[0];
      if (first) selectFamilyRow(first, boardId, metaId, flip);
    });
  }

  function selectFamilyRow(row, boardId, metaId, flip) {
    const tableEl = row.getElement().closest(".tabulator");
    if (tableEl) {
      tableEl.querySelectorAll(".tabulator-row.row-selected")
        .forEach(el => el.classList.remove("row-selected"));
    }
    row.getElement().classList.add("row-selected");
    updateFamilyBoard(row.getData(), boardId, metaId, flip);
  }

  function drillIntoFamily(d) {
    const qs = `family=${encodeURIComponent(d.family)}&color=${encodeURIComponent(d.color)}`;
    window.location.href = `opening.html?${qs}`;
  }

  function updateFamilyBoard(data, boardId, metaId, flip) {
    const board = document.getElementById(boardId);
    const meta = document.getElementById(metaId);
    if (!board || !meta) return;
    board.innerHTML = boardSquaresHTML(data.canonical_play_signature, flip);
    const gap = data.rating_gap;
    const gapStr = gap == null ? "—" : (gap >= 0 ? "+" : "") + gap;
    const qs = `family=${encodeURIComponent(data.family)}&color=${encodeURIComponent(data.color)}`;
    meta.innerHTML = `
      <div class="name">${data.family}</div>
      <div class="stats">${data.color} · ECO ${data.eco} · ${data.variation_count} variation${data.variation_count === 1 ? "" : "s"}</div>
      <dl class="detail">
        <div class="row"><span class="k">Games</span><span class="v">${data.games}</span></div>
        <div class="row"><span class="k">Win</span><span class="v">${data.win_pct}%</span></div>
        <div class="row"><span class="k">Flag</span><span class="v">${data.flag_pct}%</span></div>
        <div class="row"><span class="k">Mate</span><span class="v">${data.mate_pct}%</span></div>
        <div class="row"><span class="k">Median len</span><span class="v">${data.med_len}</span></div>
        <div class="row"><span class="k">Avg opp</span><span class="v">${data.avg_opp_rating}</span></div>
        <div class="row"><span class="k">Δ opp</span><span class="v">${gapStr}</span></div>
      </dl>
      <a class="drill-link" href="opening.html?${qs}">→ View ${data.variation_count} variation${data.variation_count === 1 ? "" : "s"}</a>
    `;
  }

  // Tier-2 view on opening.html — one row per unique named variation within
  // one family-color combo. The board panel shows the canonical (most-played)
  // position for the selected variation. Reads ?family=...&color=... from
  // the URL and filters opening_variations.
  function renderOpeningDetail(D) {
    const tableEl = document.getElementById("opening-variations-table");
    if (!tableEl) return;
    const params = new URLSearchParams(window.location.search);
    const family = params.get("family");
    const color = params.get("color");
    if (!family || !color) {
      tableEl.innerHTML = `<p style="padding:1rem;color:var(--muted)">No opening selected. <a href="index.html">Pick one from the repertoire</a>.</p>`;
      return;
    }
    const rows = (D.opening_variations || []).filter(
      r => r.family === family && r.color === color);
    const totalGames = rows.reduce((a, r) => a + r.games, 0);
    const title = document.getElementById("opening-title");
    if (title) {
      const colorLabel = color.charAt(0).toUpperCase() + color.slice(1);
      title.textContent = `${family} as ${colorLabel} — ${totalGames} games across ${rows.length} variation${rows.length === 1 ? "" : "s"}`;
    }
    if (rows.length === 0) {
      tableEl.innerHTML = `<p style="padding:1rem;color:var(--muted)">No games found for ${family} (${color}).</p>`;
      return;
    }
    const flip = color === "black";
    const table = new Tabulator("#opening-variations-table", {
      data: rows, layout: "fitColumns", height: "540px",
      columns: [
        {title: "Variation", field: "variation", headerFilter: "input", minWidth: 240,
         formatter: c => c.getValue() || `<span class="ind-off">main line</span>`},
        {title: "ECO", field: "eco", width: 70},
        {title: "Games", field: "games", width: 80, sorter: "number"},
        {title: "Win%", field: "win_pct", width: 80, sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", width: 80, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 80, sorter: "number"},
        {title: "Form", field: "form", width: 120, formatter: sparkline, headerSort: false},
      ],
      initialSort: [{column: "games", dir: "desc"}],
    });
    table.on("rowClick", (e, row) => selectOpeningRow(row, flip));
    table.on("tableBuilt", () => {
      const first = table.getRows()[0];
      if (first) selectOpeningRow(first, flip);
    });
  }

  function selectOpeningRow(row, flip) {
    document.querySelectorAll("#opening-variations-table .tabulator-row.row-selected")
      .forEach(el => el.classList.remove("row-selected"));
    row.getElement().classList.add("row-selected");
    updateOpeningBoard(row.getData(), flip);
  }

  function updateOpeningBoard(data, flip) {
    const board = document.getElementById("opening-board");
    const meta = document.getElementById("opening-board-meta");
    if (!board || !meta) return;
    board.innerHTML = boardSquaresHTML(data.canonical_play_signature, flip);
    const gap = data.rating_gap;
    const gapStr = gap == null ? "—" : (gap >= 0 ? "+" : "") + gap;
    const variationLabel = data.variation || "main line";
    const positionsLabel = data.position_count > 1
      ? `${data.position_count} positions reached via transpositions`
      : `single canonical position`;
    meta.innerHTML = `
      <div class="name">${variationLabel}</div>
      <div class="stats">${data.color} · ECO ${data.eco} · ${positionsLabel}</div>
      <dl class="detail">
        <div class="row"><span class="k">Games</span><span class="v">${data.games}</span></div>
        <div class="row"><span class="k">Win</span><span class="v">${data.win_pct}%</span></div>
        <div class="row"><span class="k">Flag</span><span class="v">${data.flag_pct}%</span></div>
        <div class="row"><span class="k">Mate</span><span class="v">${data.mate_pct}%</span></div>
        <div class="row"><span class="k">Median len</span><span class="v">${data.med_len}</span></div>
        <div class="row"><span class="k">Avg opp</span><span class="v">${data.avg_opp_rating}</span></div>
        <div class="row"><span class="k">Δ opp</span><span class="v">${gapStr}</span></div>
      </dl>
    `;
  }

  function renderSessions(rows) {
    if (!document.getElementById("sessions-table")) return;
    new Tabulator("#sessions-table", {
      data: rows, layout: "fitDataStretch",
      columns: [
        {title: "Start", field: "start"},
        {title: "Games", field: "games", sorter: "number"},
        {title: "Span (min)", field: "duration_minutes", sorter: "number"},
        {title: "W", field: "wins", sorter: "number"},
        {title: "L", field: "losses", sorter: "number"},
        {title: "D", field: "draws", sorter: "number"},
        {title: "Δ Rating", field: "rating_delta", sorter: "number",
         formatter: c => {
           const v = c.getValue();
           const cls = v <= -50 ? "cell-weak" : v >= 30 ? "cell-strong" : "";
           return `<span class="${cls}">${v >= 0 ? "+" : ""}${v}</span>`;
         }},
        {title: "Tilt", field: "tilt_flag", width: 80,
         formatter: c => c.getValue() ? `<span class="ind-on">●</span>` : ""},
      ],
      initialSort: [{column: "start", dir: "desc"}],
    });
  }

  function renderDrillinCards(D) {
    const root = document.getElementById("drillin-cards");
    if (!root) return;
    const leaks = D.leak_summary || [];
    const losses = D.recent_losses || [];
    const sessions = D.sessions || [];
    const pm = D.process_metrics || {};

    // Leaks card: alert when any critical leak exists
    const critical = leaks.find(L => L.severity === "critical");
    const firstWarn = leaks.find(L => L.severity === "warn");
    const worstName = critical ? critical.name : (firstWarn ? firstWarn.name : null);
    const leaksAlert = critical != null;
    const leaksSub = leaks.length === 0 ? "all clear"
      : worstName ? `Worst: ${worstName.replace(/_/g, " ")}`
      : `${leaks.length} active`;

    // Recent losses card: alert when count >= 10
    const lossCounts = {};
    losses.forEach(L => { lossCounts[L.loss_type] = (lossCounts[L.loss_type] || 0) + 1; });
    const topLossTypes = Object.entries(lossCounts).sort((a, b) => b[1] - a[1]).slice(0, 2);
    const lossesSub = losses.length === 0 ? "none in last 30"
      : topLossTypes.map(([t, n]) => `${n} ${t}`).join(", ");
    const lossesAlert = losses.length >= 10;

    // Process card: alert when opening_velocity_median > 8 (seconds spent
    // on first 8 moves; matches the leak detector's "time_burn_opening"
    // threshold of >8s). Lower velocity = faster opening play = better.
    const velocity = pm.opening_velocity_median;
    const processHeadline = velocity == null ? "—" : `${velocity}s @ 8`;
    const processSub = velocity == null ? "insufficient data" : "Target ≤ 8s";
    const processAlert = velocity != null && velocity > 8;

    // Sessions card: alert when most-recent session was tilted.
    // sessions are stored chronologically (oldest first); use slice(-5) and
    // [length-1] to read the latest entries.
    const sessionCount = sessions.length;
    const last5 = sessions.slice(-5);
    const tiltedCount = last5.filter(s => s.tilt_flag).length;
    const sessionsSub = sessionCount === 0 ? "no sessions"
      : `${tiltedCount} tilted of last 5`;
    const lastSession = sessions.length > 0 ? sessions[sessions.length - 1] : null;
    const sessionsAlert = lastSession != null && lastSession.tilt_flag === true;

    root.innerHTML = [
      card("Leaks", `${leaks.length} active`, leaksSub, "leaks.html", leaksAlert),
      card("Recent losses", `${losses.length}`, lossesSub, "losses.html", lossesAlert),
      card("Process", processHeadline, processSub, "process.html", processAlert),
      card("Sessions", `${sessionCount} total`, sessionsSub, "sessions.html", sessionsAlert),
    ].join("");
  }

  function card(label, headline, sub, href, alert) {
    return `<a class="card${alert ? " alert" : ""}" href="${href}">
      <div class="label">${label}</div>
      <div class="headline">${headline}</div>
      <div class="sub">${sub}</div>
    </a>`;
  }

  function sparkline(cell) {
    const arr = cell.getValue() || [];
    return `<span class="sparkline">${
      arr.map(r => `<span class="spark-bar spark-${r}"></span>`).join("")
    }</span>`;
  }
  // Use the *filled* Unicode glyph set for BOTH sides so each piece is a
  // solid silhouette. Color (piece-w / piece-b) distinguishes the side —
  // matches how chess.com and Lichess render at small sizes.
  const GLYPH = {
    K:"♚", Q:"♛", R:"♜", B:"♝", N:"♞", P:"♟︎",
    k:"♚", q:"♛", r:"♜", b:"♝", n:"♞", p:"♟︎",
  };
  // Returns just the 64 square <div>s for a FEN. Caller provides the wrapping
  // grid element and styles its size via CSS. When `flip` is true, the board
  // renders from Black's perspective (a1 at top-right, h8 at bottom-left) —
  // achieved by reversing the cells array, which swaps both ranks and files
  // in one step. Square colors stay correct because a square's color is a
  // property of its FEN coordinates, not its display position.
  function boardSquaresHTML(fen, flip = false) {
    if (!fen) return "";
    const cells = [];
    let r = 0;
    for (const row of fen.split(" ")[0].split("/")) {
      let f = 0;
      for (const ch of row) {
        if (ch >= "1" && ch <= "8") {
          for (let i = 0; i < +ch; i++) {
            cells.push(`<div class="${(r+f)%2 ? "dark" : "light"}"></div>`);
            f++;
          }
        } else {
          const sq = (r+f)%2 ? "dark" : "light";
          const side = ch === ch.toUpperCase() ? "piece-w" : "piece-b";
          cells.push(`<div class="${sq}"><span class="${side}">${GLYPH[ch] || ""}</span></div>`);
          f++;
        }
      }
      r++;
    }
    if (flip) cells.reverse();
    return cells.join("");
  }
  function renderBehavior(b) {
    const root = document.getElementById("behavior-cards");
    if (!root || !b) return;
    const ls = b.loss_streaks || {};
    const rg = b.revenge_gap || {};
    const dd = (b.daily_drawdown || []).slice(-7);  // last 7 days
    const tod = (b.time_of_day || []);
    const todWorst = [...tod].sort((a, b) => a.mean_session_delta - b.mean_session_delta)[0];
    const todBest = [...tod].sort((a, b) => b.mean_session_delta - a.mean_session_delta)[0];

    const cell = (label, value, sub, alert=false) =>
      `<div class="behavior-card${alert ? " alert" : ""}">
         <div class="bh-label">${label}</div>
         <div class="bh-value">${value}</div>
         <div class="bh-sub">${sub}</div>
       </div>`;

    const cards = [];
    cards.push(cell(
      "Current loss streak",
      String(ls.current_loss_streak ?? 0),
      ls.current_timeout_loss_streak
        ? `${ls.current_timeout_loss_streak} of them on time`
        : "",
      (ls.current_loss_streak ?? 0) >= 3
    ));
    cards.push(cell(
      "Longest loss streak (24h)",
      String(ls.longest_loss_streak_24h ?? 0),
      ls.longest_timeout_loss_streak_24h
        ? `timeout streak: ${ls.longest_timeout_loss_streak_24h}`
        : "",
      (ls.longest_loss_streak_24h ?? 0) >= 5
    ));
    const gap = rg.revenge_gap;
    cards.push(cell(
      "Revenge gap",
      gap == null ? "—" : `${gap > 0 ? "+" : ""}${gap}pp`,
      `${rg.wins_after_loss}/${rg.games_after_loss} after losses vs ${rg.wins_after_win}/${rg.games_after_win} after wins`,
      gap != null && gap <= -8
    ));
    const worstDay = dd.length ? dd.reduce((acc, d) =>
      d.max_drawdown < acc.max_drawdown ? d : acc, dd[0]) : null;
    cards.push(cell(
      "Worst day this week",
      worstDay ? `${worstDay.max_drawdown}` : "—",
      worstDay ? `${worstDay.date} (${worstDay.games} games)` : "",
      worstDay && worstDay.max_drawdown <= -50
    ));
    cards.push(cell(
      "Best time-of-day",
      todBest ? `${String(todBest.hour).padStart(2, "0")}:00` : "—",
      todBest ? `mean session Δ ${todBest.mean_session_delta > 0 ? "+" : ""}${todBest.mean_session_delta}` : ""
    ));
    cards.push(cell(
      "Worst time-of-day",
      todWorst ? `${String(todWorst.hour).padStart(2, "0")}:00` : "—",
      todWorst ? `mean session Δ ${todWorst.mean_session_delta > 0 ? "+" : ""}${todWorst.mean_session_delta}` : "",
      todWorst && todWorst.mean_session_delta <= -20
    ));
    root.innerHTML = cards.join("");
  }

  function winPctCell(cell) {
    const v = cell.getValue();
    const cls = v >= 60 ? "cell-strong" : v <= 35 ? "cell-weak" : "";
    return `<span class="${cls}">${v}%</span>`;
  }
})();
