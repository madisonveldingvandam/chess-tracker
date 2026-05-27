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
  renderSessionDecay(D.process_metrics.session_decay);
  renderPlaySignatures(D.play_signatures);
  renderSessions(D.sessions);

  function renderKPI(d) {
    const k = d.kpis;
    document.getElementById("kpi-strip").innerHTML = `
      <div class="kpi"><span class="kpi-label">Rating</span>
        <span class="kpi-value">${k.current_rating ?? "—"}</span></div>
      <div class="kpi"><span class="kpi-label">Games total</span>
        <span class="kpi-value">${k.games_total}</span></div>
      <div class="kpi"><span class="kpi-label">Recent form</span>
        <span class="kpi-value${k.recent_form_win_pct >= 50 ? " accent" : ""}">${k.recent_form_win_pct}%</span></div>
      <div class="kpi"><span class="kpi-label">Generated</span>
        <span class="kpi-value" style="font-size:0.9rem">${new Date(d.generated_at).toLocaleString()}</span></div>
    `;
  }

  function renderLeaks(leaks) {
    const root = document.getElementById("leak-list");
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
    new Tabulator("#play-signatures-table", {
      data: rows, layout: "fitDataStretch",
      rowFormatter: row => {
        if (row.getData().low_confidence) row.getElement().classList.add("row-low-conf");
      },
      columns: [
        {title: "Conf", field: "low_confidence",
         formatter: c => c.getValue()
           ? `<span class="ind-off">○</span>`
           : `<span class="ind-on">●</span>`,
         width: 60, sorter: (a,b)=> (a?1:0)-(b?1:0)},
        {title: "Board@8", field: "play_signature", formatter: boardCell,
         width: 136, headerSort: false},
        {title: "Opening", field: "display_name", widthGrow: 3, headerFilter: "input"},
        {title: "ECO", field: "eco", width: 70},
        {title: "Color", field: "color", width: 80, headerFilter: "list",
         headerFilterParams: {values: {"":"All", "white":"White", "black":"Black"}}},
        {title: "N", field: "games", width: 60, sorter: "number"},
        {title: "Win%", field: "win_pct", width: 80, sorter: "number", formatter: winPctCell},
        {title: "Form", field: "form", width: 120, formatter: sparkline, headerSort: false},
        {title: "Flag%", field: "flag_pct", width: 80, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 80, sorter: "number"},
        {title: "MedLen", field: "med_len", width: 80, sorter: "number"},
        {title: "AvgOpp", field: "avg_opp_rating", width: 90, sorter: "number"},
        {title: "Δ-opp", field: "rating_gap", width: 80, sorter: "number"},
        {title: "Tag", field: "tag", width: 100, headerFilter: "input"},
        {title: "Note", field: "note", widthGrow: 2},
      ],
      initialSort: [
        {column: "low_confidence", dir: "asc"},
        {column: "games", dir: "desc"},
      ],
    });
  }

  function renderSessions(rows) {
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

  function sparkline(cell) {
    const arr = cell.getValue() || [];
    return `<span class="sparkline">${
      arr.map(r => `<span class="spark-bar spark-${r}"></span>`).join("")
    }</span>`;
  }
  const GLYPH = {
    K:"♔", Q:"♕", R:"♖", B:"♗", N:"♘", P:"♙",
    k:"♚", q:"♛", r:"♜", b:"♝", n:"♞", p:"♟︎",
  };
  function boardCell(cell) {
    const fen = cell.getValue();
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
          cells.push(`<div class="${(r+f)%2 ? "dark" : "light"}">${GLYPH[ch] || ""}</div>`);
          f++;
        }
      }
      r++;
    }
    return `<div class="board">${cells.join("")}</div>`;
  }
  function winPctCell(cell) {
    const v = cell.getValue();
    const cls = v >= 60 ? "cell-strong" : v <= 35 ? "cell-weak" : "";
    return `<span class="${cls}">${v}%</span>`;
  }
})();
