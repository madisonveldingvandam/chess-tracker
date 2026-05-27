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
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics?.session_decay);
  renderPlaySignatures(D.play_signatures);
  renderSessions(D.sessions);
  renderDrillinCards(D);

  function renderKPI(d) {
    const strip = document.getElementById("kpi-strip");
    if (!strip) return;
    const k = d.kpis;
    const lastDelta = (d.sessions && d.sessions.length > 0) ? d.sessions[0].rating_delta : null;
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

  function renderPlaySignatures(rows) {
    if (!document.getElementById("play-signatures-table")) return;
    // Height matches the board panel (~360px) so internal scroll keeps the
    // split block compact and the "Drill in" footer sits right under it.
    // Trimmed to 7 essential columns so the table fits viewport width without
    // horizontal scrolling; deeper stats can return to the board-meta panel
    // or a future per-opening detail view.
    const table = new Tabulator("#play-signatures-table", {
      data: rows, layout: "fitColumns", height: "360px",
      rowFormatter: row => {
        if (row.getData().low_confidence) row.getElement().classList.add("row-low-conf");
      },
      columns: [
        {title: "Conf", field: "low_confidence",
         formatter: c => c.getValue()
           ? `<span class="ind-off">○</span>`
           : `<span class="ind-on">●</span>`,
         width: 60, sorter: (a,b)=> (a?1:0)-(b?1:0)},
        {title: "Opening", field: "display_name", headerFilter: "input"},
        {title: "ECO", field: "eco", width: 70},
        {title: "Color", field: "color", width: 80, headerFilter: "list",
         headerFilterParams: {values: {"":"All", "white":"White", "black":"Black"}}},
        {title: "N", field: "games", width: 60, sorter: "number"},
        {title: "Win%", field: "win_pct", width: 80, sorter: "number", formatter: winPctCell},
        {title: "Form", field: "form", width: 120, formatter: sparkline, headerSort: false},
      ],
      initialSort: [
        {column: "low_confidence", dir: "asc"},
        {column: "games", dir: "desc"},
      ],
    });
    table.on("rowClick", (e, row) => selectSignatureRow(row));
    table.on("tableBuilt", () => {
      const first = table.getRows()[0];
      if (first) selectSignatureRow(first);
    });
  }

  function selectSignatureRow(row) {
    document.querySelectorAll(".tabulator-row.row-selected")
      .forEach(el => el.classList.remove("row-selected"));
    row.getElement().classList.add("row-selected");
    updateBoardPanel(row.getData());
  }

  function updateBoardPanel(data) {
    const board = document.getElementById("board-large");
    const meta = document.getElementById("board-meta");
    if (!board || !meta) return;
    board.innerHTML = boardSquaresHTML(data.play_signature);
    const gap = data.rating_gap;
    const gapStr = gap == null ? "—" : (gap >= 0 ? "+" : "") + gap;
    const tagRow = data.tag ? `<div class="row"><span class="k">Tag</span><span class="v">${data.tag}</span></div>` : "";
    const noteRow = data.note ? `<div class="row"><span class="k">Note</span><span class="v">${data.note}</span></div>` : "";
    meta.innerHTML = `
      <div class="name">${data.display_name}</div>
      <div class="stats">${data.color} · ECO ${data.eco}</div>
      <dl class="detail">
        <div class="row"><span class="k">Games</span><span class="v">${data.games}</span></div>
        <div class="row"><span class="k">Win</span><span class="v">${data.win_pct}%</span></div>
        <div class="row"><span class="k">Flag</span><span class="v">${data.flag_pct}%</span></div>
        <div class="row"><span class="k">Mate</span><span class="v">${data.mate_pct}%</span></div>
        <div class="row"><span class="k">Median len</span><span class="v">${data.med_len}</span></div>
        <div class="row"><span class="k">Avg opp</span><span class="v">${data.avg_opp_rating}</span></div>
        <div class="row"><span class="k">Δ opp</span><span class="v">${gapStr}</span></div>
        ${tagRow}
        ${noteRow}
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

    // Process card: alert when opening_velocity_median < 18
    const velocity = pm.opening_velocity_median;
    const processHeadline = velocity == null ? "—" : `${velocity}s @ 8`;
    const processSub = velocity == null ? "insufficient data" : "Target ≥ 18s";
    const processAlert = velocity != null && velocity < 18;

    // Sessions card: alert when last session was tilted
    const sessionCount = sessions.length;
    const last5 = sessions.slice(0, 5);
    const tiltedCount = last5.filter(s => s.tilt_flag).length;
    const sessionsSub = sessionCount === 0 ? "no sessions"
      : `${tiltedCount} tilted of last 5`;
    const sessionsAlert = sessions.length > 0 && sessions[0].tilt_flag === true;

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
  // grid element (e.g. #board-large) and styles its size via CSS.
  function boardSquaresHTML(fen) {
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
    return cells.join("");
  }
  function winPctCell(cell) {
    const v = cell.getValue();
    const cls = v >= 60 ? "cell-strong" : v <= 35 ? "cell-weak" : "";
    return `<span class="${cls}">${v}%</span>`;
  }
})();
