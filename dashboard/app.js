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
  renderActionCard(D);
  renderPlanBlock(D.plan_compliance);
  renderMoveQuality(D.move_quality);
  renderMoveQualityByFormat(D.move_quality_by_format, D.format);
  renderFamilyBlock(D.opening_families, "white",
    "#white-families-table", "white-board", "white-board-meta", false);
  renderFamilyBlock(D.opening_families, "black",
    "#black-families-table", "black-board", "black-board-meta", true);
  renderBehavior(D.behavior);
  renderLeaks(D.leak_summary);
  renderRule(D.next_session_rule);
  renderRecentLosses(D.recent_losses);
  renderPuzzleDrill(D.recent_losses);
  renderLossSummary(D);
  renderReviewPicks(D.review_picks);
  renderErrorLog(D.error_log);
  renderProcess(D.process_metrics);
  renderSessionDecay(D.process_metrics?.session_decay);
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
      <a class="refresh-link"
         href="https://github.com/madisonveldingvandam/chess-tracker/actions/workflows/deploy.yml"
         target="_blank" rel="noopener"
         title="Re-run the deploy workflow on GitHub Actions to rebuild this dashboard now">↻ Refresh</a>
    `);
  }

  // Action card: top of index.html only. Shows next-session rule + the top
  // 1-2 leaks so the most actionable info is visible without scrolling.
  // Falls back gracefully if elements are absent (other pages don't have them).
  function renderActionCard(D) {
    const cardRoot = document.getElementById("action-card");
    const leakRoot = document.getElementById("current-leak-inline");
    if (!cardRoot) return;
    const rule = D.next_session_rule;
    if (!rule) { cardRoot.innerHTML = ""; return; }
    cardRoot.innerHTML = `
      <h2>Next session</h2>
      <div class="action-rule">
        <span>${rule.game_cap} games max</span> ·
        <span>${rule.move_10_target_seconds}s left at move 10</span> ·
        <span>Stop if rating drops ${rule.stop_if_rating_drops}</span>
      </div>
      <div class="rule-narrative">${rule.narrative}</div>
    `;
    if (!leakRoot) return;
    const leaks = D.leak_summary || [];
    if (leaks.length === 0) {
      leakRoot.innerHTML = `<div class="leak severity-neutral">No active leaks — all clear.</div>`;
      return;
    }
    leakRoot.innerHTML = leaks.slice(0, 2).map(L => `
      <div class="leak severity-${L.severity}">
        <div class="leak-name">${L.name.replace(/_/g, " ")}</div>
        <div class="leak-evidence">${L.evidence}</div>
        <div class="leak-action">→ ${L.suggested_action}</div>
      </div>
    `).join("");
  }

  // Move quality — engine-derived accuracy/blunders for the current format.
  // Only renders on index.html (where #move-quality-cards exists). All values
  // are server-computed numbers from analysis.aggregate_move_quality — safe to
  // inline. `mq` is null when no engine ran (e.g. --no-analysis).
  function renderMoveQuality(mq) {
    const root = document.getElementById("move-quality-cards");
    if (!root) return;
    if (!mq) {
      root.innerHTML =
        `<p class="mq-empty">Run refresh.py with Stockfish to see move quality.</p>`;
      return;
    }
    const cell = (label, value, sub, alert = false) =>
      `<div class="behavior-card${alert ? " alert" : ""}">
         <div class="bh-label">${label}</div>
         <div class="bh-value">${value}</div>
         <div class="bh-sub">${sub}</div>
       </div>`;
    const ph = mq.acpl_by_phase || {};
    const phSub = ["opening", "middlegame", "endgame"]
      .filter(p => ph[p] != null)
      .map(p => `${p.slice(0, 3)} ${ph[p]}`)
      .join(" · ") || "—";
    root.innerHTML = [
      cell("Accuracy", `${mq.accuracy}%`,
        `${mq.games_analyzed} games · ${mq.moves_analyzed} moves`),
      cell("Blunders / 100 moves", `${mq.blunders_per_100_moves}`,
        `${mq.blunders}B · ${mq.mistakes}M · ${mq.inaccuracies}I`,
        mq.blunders_per_100_moves >= 5),
      cell("Avg cp lost / move", `${mq.avg_cp_loss}`, phSub),
    ].join("");
  }

  // Cross-format comparison — one row per time class that has data. Hidden
  // when fewer than two formats are available (nothing to compare). Values are
  // server-computed numbers; current format is highlighted.
  function renderMoveQualityByFormat(byFmt, currentFmt) {
    const section = document.getElementById("move-quality-by-format");
    const root = document.getElementById("mqf-table");
    if (!section || !root) return;
    const order = ["bullet", "blitz", "rapid", "daily"];
    const rows = order.filter(f => byFmt && byFmt[f]);
    if (rows.length < 2) { section.style.display = "none"; return; }
    const body = rows.map(f => {
      const m = byFmt[f];
      const cur = f === currentFmt;
      return `<tr${cur ? ' class="mqf-current"' : ""}>
        <td>${f}${cur ? " ◂" : ""}</td>
        <td>${m.accuracy}%</td>
        <td>${m.blunders_per_100_moves}</td>
        <td>${m.avg_cp_loss}</td>
        <td>${m.games_analyzed}</td></tr>`;
    }).join("");
    root.innerHTML = `<table class="mqf-table">
      <thead><tr><th>Format</th><th>Accuracy</th><th>Blunders/100</th>
        <th>Avg cp lost</th><th>Games</th></tr></thead>
      <tbody>${body}</tbody></table>`;
  }

  // Plan & adherence — only renders on index.html where the section exists.
  // Each prep opening shows adherence over the last N games + win-rate
  // comparison (on-plan vs deviated). Severity coloring matches the leaks
  // palette (severity-green / severity-yellow / severity-red / severity-neutral).
  function renderPlanBlock(pc) {
    const root = document.getElementById("plan-openings");
    const princRoot = document.getElementById("plan-principles");
    if (!root || !pc) return;
    const openings = pc.openings || [];
    if (openings.length === 0) {
      root.innerHTML = `<p style="color:var(--muted)">No openings in plan. Edit chess_tracker/plan.json to add some.</p>`;
    } else {
      const sideRank = (o) => (o.side === "black" ? 0 : 1);
      const statusRank = (o) => (o.status === "bench" ? 1 : 0);
      const ordered = [...openings].sort((a, b) =>
        sideRank(a) - sideRank(b) || statusRank(a) - statusRank(b));
      let lastSide = null;
      let lastStatus = "active";
      const cardsHtml = ordered.map((o, i) => {
        let prefix = "";
        if (o.side !== lastSide) {
          // close an open bench wrapper from the previous side before its header
          if (lastStatus === "bench") prefix += `</div>`;
          prefix += `<h3 class="plan-side-header">${o.side === "black" ? "As Black" : "As White"}</h3>`;
          lastStatus = "active";
        }
        if (o.status === "bench" && lastStatus !== "bench") {
          prefix += `<div class="plan-bench-label">Bench — studying</div><div class="plan-bench">`;
        }
        lastSide = o.side;
        lastStatus = o.status || "active";
        const vs = o.vs_first_move ? `vs 1.${o.vs_first_move}` : `as ${o.side}`;
        const won = o.win_pct_when_played;
        const dev = o.win_pct_when_deviated;
        const wonStr = won == null ? "—" : `${won}%`;
        const devStr = dev == null ? "—" : `${dev}%`;
        const deltaNote = (won != null && dev != null)
          ? ` <span class="plan-delta">(${won >= dev ? "+" : ""}${(won - dev).toFixed(1)}pp on plan)</span>`
          : "";
        return `
          ${prefix}
          <div class="plan-card severity-${o.severity}">
            <div class="plan-head">
              <span class="plan-vs">${vs}</span>
              <span class="plan-name">${o.name}</span>
              <span class="plan-adherence">${o.adherence_pct}% adherence</span>
            </div>
            <div class="plan-counts">
              ${o.games_on_plan} of ${o.applicable_games} games played on plan
            </div>
            ${(o.gambit_breakdown && Object.keys(o.gambit_breakdown).length)
              ? `<div class="plan-gambits">of on-plan: ${
                  Object.entries(o.gambit_breakdown)
                    .map(([k, v]) => `${v} ${k}`).join(" · ")}</div>`
              : ""}
            <div class="plan-winrates">
              Win when played: <strong>${wonStr}</strong>
              · Win when deviated: <strong>${devStr}</strong>
              ${deltaNote}
            </div>
            <details class="plan-detail">
              <summary>Show moves &amp; plan</summary>
              ${(o.board_lines && o.board_lines.length
                  ? o.board_lines
                  : [{ moves: o.moves, fens: o.fens, ply_labels: o.ply_labels }]
                ).map((bl, j) => `
                ${bl.label ? `<div class="plan-line-label">${bl.label}</div>` : ""}
                <code class="plan-moves">${bl.moves || "—"}</code>
                ${(bl.fens && bl.fens.length > 1) ? `
                <div class="plan-board-wrap">
                  <div id="plan-board-${i}-${j}" class="board-large plan-board"></div>
                  <div class="plan-board-controls">
                    <button type="button" class="plan-step" id="plan-prev-${i}-${j}" aria-label="Previous move">◀</button>
                    <span class="plan-board-cap" id="plan-cap-${i}-${j}"></span>
                    <button type="button" class="plan-step" id="plan-next-${i}-${j}" aria-label="Next move">▶</button>
                  </div>
                </div>` : ""}
              `).join("")}
              <p class="plan-plan">${o.plan || ""}</p>
            </details>
          </div>
        `;
      }).join("");
      root.innerHTML = cardsHtml + (lastStatus === "bench" ? "</div>" : "");
      // Wire up each card's move-by-move board. State (current ply) lives in
      // this closure per card; the board reuses boardSquaresHTML by swapping
      // FENs. Black-defense lines render from Black's perspective.
      ordered.forEach((o, i) => {
        const flip = o.side === "black";
        const lines = (o.board_lines && o.board_lines.length)
          ? o.board_lines
          : [{ fens: o.fens, ply_labels: o.ply_labels }];
        lines.forEach((bl, j) => {
          const fens = bl.fens || [];
          if (fens.length < 2) return;
          const labels = bl.ply_labels || [];
          const boardEl = document.getElementById(`plan-board-${i}-${j}`);
          const capEl = document.getElementById(`plan-cap-${i}-${j}`);
          const prevEl = document.getElementById(`plan-prev-${i}-${j}`);
          const nextEl = document.getElementById(`plan-next-${i}-${j}`);
          if (!boardEl) return;
          let idx = fens.length - 1;  // open on the final position of the line
          const paint = () => {
            boardEl.innerHTML = boardSquaresHTML(fens[idx], flip);
            capEl.textContent = idx === 0
              ? "Start position"
              : `after ${labels[idx - 1]} · move ${idx} of ${fens.length - 1}`;
            prevEl.disabled = idx === 0;
            nextEl.disabled = idx === fens.length - 1;
          };
          prevEl.addEventListener("click", () => { if (idx > 0) { idx--; paint(); } });
          nextEl.addEventListener("click", () => { if (idx < fens.length - 1) { idx++; paint(); } });
          // Defer the first paint: GLYPH is a `const` declared later in this IIFE,
          // so drawing synchronously here would hit the temporal dead zone (same
          // pattern as the puzzle board's deferred select(0)).
          queueMicrotask(paint);
        });
      });
    }
    if (princRoot) {
      const principles = pc.principles || [];
      princRoot.innerHTML = principles.map(p => `<li>${p}</li>`).join("");
    }
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

  // ---- Guided puzzle drill (losses.html) --------------------------------
  // Each loss carries a precomputed `puzzle` (chess_tracker/puzzles.py): the
  // position just before my worst move, my move, and the engine's better move.
  // The board accepts ONLY the engine move; anything else is "the kind of move
  // that lost the game" and reveals the answer. Because exactly one known-legal
  // move is ever applied, applyUci (below) is all the chess logic we need — no
  // move generator, no engine in the browser.
  function renderPuzzleDrill(losses) {
    const root = document.getElementById("puzzle-drill");
    if (!root) return;
    const puzzles = (losses || []).filter(L => L.puzzle);
    if (puzzles.length === 0) {
      root.innerHTML = `<p class="puzzle-empty">No puzzles yet — run refresh.py with Stockfish installed.</p>`;
      return;
    }
    root.innerHTML = `
      <div class="puzzle-list" id="puzzle-list"></div>
      <div class="puzzle-stage">
        <div class="puzzle-board" id="puzzle-board"></div>
        <div class="puzzle-side">
          <div class="puzzle-prompt" id="puzzle-prompt"></div>
          <div class="puzzle-feedback" id="puzzle-feedback"></div>
          <div class="puzzle-controls">
            <button id="puzzle-show">Show answer</button>
            <button id="puzzle-reset">Reset</button>
          </div>
        </div>
      </div>`;

    const listEl = document.getElementById("puzzle-list");
    const boardEl = document.getElementById("puzzle-board");
    const promptEl = document.getElementById("puzzle-prompt");
    const fbEl = document.getElementById("puzzle-feedback");
    listEl.innerHTML = puzzles.map((L, i) => {
      const p = L.puzzle;
      return `<button class="puzzle-item" data-idx="${i}">
        <span class="pi-open">${escapeAttr(L.opening || "Unknown opening")}</span>
        <span class="pi-meta">${escapeAttr(L.loss_type)} · move ${p.fullmove}</span>
      </button>`;
    }).join("");

    const state = {};

    function currentIdx() {
      const active = listEl.querySelector(".puzzle-item.active");
      return active ? +active.dataset.idx : 0;
    }

    function select(i) {
      const p = puzzles[i].puzzle;
      state.puzzle = p;
      state.fen = p.fen_before;
      state.flip = p.side === "black";
      state.sel = null;
      state.solved = false;
      state.revealed = false;
      state.lastMove = null;
      listEl.querySelectorAll(".puzzle-item").forEach(b =>
        b.classList.toggle("active", +b.dataset.idx === i));
      promptEl.innerHTML =
        `<strong>${p.side === "white" ? "White" : "Black"} to move.</strong> ` +
        `You played <span class="bad">${escapeAttr(p.my_move_san)}</span> here — find the move that holds.`;
      fbEl.innerHTML = "";
      drawBoard();
    }

    function drawBoard() {
      const grid = placementToGrid(state.fen.split(" ")[0]);
      const order = [];
      for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) order.push([r, c]);
      if (state.flip) order.reverse();
      const best = state.puzzle.best_move_uci;
      let html = "";
      order.forEach(([r, c], idx) => {
        const sq = FILES[c] + (8 - r);
        const piece = grid[r][c];
        const cls = ["psq", (r + c) % 2 ? "dark" : "light"];
        if (state.sel === sq) cls.push("sel");
        if (state.lastMove && (state.lastMove.from === sq || state.lastMove.to === sq)) cls.push("lastmove");
        if (state.revealed && (best.slice(0, 2) === sq || best.slice(2, 4) === sq)) cls.push("hint");
        let inner = "";
        if (piece) {
          const side = piece === piece.toUpperCase() ? "piece-w" : "piece-b";
          inner += `<span class="${side}">${GLYPH[piece] || ""}</span>`;
        }
        if (idx % 8 === 0) inner += `<span class="coord rank">${8 - r}</span>`;
        if (idx >= 56) inner += `<span class="coord file">${FILES[c]}</span>`;
        html += `<div class="${cls.join(" ")}" data-sq="${sq}">${inner}</div>`;
      });
      boardEl.innerHTML = html;
    }

    function reveal() {
      state.revealed = true;
      drawBoard();
    }

    boardEl.addEventListener("click", (e) => {
      if (state.solved) return;
      const cell = e.target.closest(".psq");
      if (!cell) return;
      const sq = cell.dataset.sq;
      const grid = placementToGrid(state.fen.split(" ")[0]);
      const [r, c] = sqToRC(sq);
      const piece = grid[r][c];
      const whiteToMove = state.puzzle.side === "white";
      const mine = piece && (whiteToMove ? piece === piece.toUpperCase() : piece === piece.toLowerCase());

      if (state.sel === null) {
        if (mine) { state.sel = sq; drawBoard(); }
        return;
      }
      if (sq === state.sel) { state.sel = null; drawBoard(); return; }

      let uci = state.sel + sq;
      const [sr, sc] = sqToRC(state.sel);
      const selPiece = grid[sr][sc];
      const lastRank = whiteToMove ? "8" : "1";
      if (selPiece && selPiece.toLowerCase() === "p" && sq[1] === lastRank) uci += "q";

      const best = state.puzzle.best_move_uci;
      if (uci === best || (best.length === 5 && uci === best.slice(0, 4) + "q")) {
        state.fen = applyUci(state.fen, best);
        state.lastMove = { from: best.slice(0, 2), to: best.slice(2, 4) };
        state.sel = null;
        state.solved = true;
        drawBoard();
        fbEl.innerHTML = `<span class="ok">✓ Correct — ${escapeAttr(state.puzzle.best_move_san)} holds the position.</span>`;
      } else {
        state.sel = null;
        reveal();
        fbEl.innerHTML =
          `<span class="bad">✗ That's the kind of move that lost the game.</span> ` +
          `The move that holds was <strong>${escapeAttr(state.puzzle.best_move_san)}</strong> (highlighted).`;
      }
    });

    listEl.addEventListener("click", (e) => {
      const b = e.target.closest(".puzzle-item");
      if (b) select(+b.dataset.idx);
    });
    document.getElementById("puzzle-show").onclick = () => {
      if (!state.solved) reveal();
      fbEl.innerHTML = `Best move: <strong>${escapeAttr(state.puzzle.best_move_san)}</strong> (highlighted).`;
    };
    document.getElementById("puzzle-reset").onclick = () => select(currentIdx());

    // Defer the first paint: GLYPH/FILES are `const`s declared later in this
    // IIFE, so drawing synchronously here would hit the temporal dead zone.
    queueMicrotask(() => select(0));
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
        {title: "Games", field: "games", width: 75, sorter: "number"},
        {title: "Δ Rating", field: "sum_rating_delta", width: 90, sorter: "number", formatter: ratingDeltaCell},
        {title: "Win%", field: "win_pct", width: 75, sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", width: 75, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 75, sorter: "number"},
        {title: "#Vars", field: "variation_count", width: 70, sorter: "number"},
        {title: "Form", field: "form", width: 110, formatter: sparkline, headerSort: false},
      ],
      initialSort: [{column: "sum_rating_delta", dir: "asc"}],
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
        {title: "Variation", field: "variation", headerFilter: "input", minWidth: 220,
         formatter: c => c.getValue() || `<span class="ind-off">main line</span>`},
        {title: "ECO", field: "eco", width: 65},
        {title: "Games", field: "games", width: 75, sorter: "number"},
        {title: "Δ Rating", field: "sum_rating_delta", width: 90, sorter: "number", formatter: ratingDeltaCell},
        {title: "Win%", field: "win_pct", width: 75, sorter: "number", formatter: winPctCell},
        {title: "Flag%", field: "flag_pct", width: 75, sorter: "number"},
        {title: "Mate%", field: "mate_pct", width: 75, sorter: "number"},
        {title: "Form", field: "form", width: 110, formatter: sparkline, headerSort: false},
      ],
      initialSort: [{column: "sum_rating_delta", dir: "asc"}],
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
  //
  // File/rank coordinates are drawn Lichess-style inside the edge squares of
  // the *displayed* orientation: rank digits down the left column, file letters
  // along the bottom row. Because labelling keys off display position (post
  // flip), the a1-corner stays bottom-left for White and top-right for Black.
  function boardSquaresHTML(fen, flip = false) {
    if (!fen) return "";
    const cells = [];  // {r, f, inner} in board order (rank 8 first)
    let r = 0;
    for (const row of fen.split(" ")[0].split("/")) {
      let f = 0;
      for (const ch of row) {
        if (ch >= "1" && ch <= "8") {
          for (let i = 0; i < +ch; i++) { cells.push({ r, f, inner: "" }); f++; }
        } else {
          const side = ch === ch.toUpperCase() ? "piece-w" : "piece-b";
          cells.push({ r, f, inner: `<span class="${side}">${GLYPH[ch] || ""}</span>` });
          f++;
        }
      }
      r++;
    }
    if (flip) cells.reverse();
    return cells.map((c, idx) => {
      const sq = (c.r + c.f) % 2 ? "dark" : "light";
      let inner = c.inner;
      if (idx % 8 === 0) inner += `<span class="coord rank">${8 - c.r}</span>`;
      if (idx >= 56) inner += `<span class="coord file">${FILES[c.f]}</span>`;
      return `<div class="${sq}">${inner}</div>`;
    }).join("");
  }

  // ---- FEN / move helpers for the puzzle drill --------------------------
  const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];
  // FEN piece-placement -> 8x8 grid. grid[0] is rank 8 (top), grid[7] is rank 1.
  function placementToGrid(placement) {
    return placement.split("/").map(row => {
      const cells = [];
      for (const ch of row) {
        if (ch >= "1" && ch <= "8") for (let i = 0; i < +ch; i++) cells.push(null);
        else cells.push(ch);
      }
      return cells;
    });
  }
  function gridToPlacement(grid) {
    return grid.map(row => {
      let out = "", empty = 0;
      for (const cell of row) {
        if (cell === null) { empty++; continue; }
        if (empty) { out += empty; empty = 0; }
        out += cell;
      }
      return out + (empty || "");
    }).join("/");
  }
  // square name (e.g. "e4") -> [row, file] with row 0 = rank 8.
  function sqToRC(sq) {
    return [8 - +sq[1], FILES.indexOf(sq[0])];
  }
  // Apply ONE known-legal UCI move to a FEN, returning the new FEN. Handles
  // captures, promotion, castling (moves the rook too) and en passant. Safe
  // because we only ever feed it the engine's best move.
  function applyUci(fen, uci) {
    const parts = fen.split(" ");
    const grid = placementToGrid(parts[0]);
    const [fr, ff] = sqToRC(uci.slice(0, 2));
    const [tr, tf] = sqToRC(uci.slice(2, 4));
    const piece = grid[fr][ff];
    const isWhite = piece === piece.toUpperCase();
    if (piece.toLowerCase() === "p" && ff !== tf && grid[tr][tf] === null) {
      grid[fr][tf] = null;  // en passant: captured pawn is on from-rank, to-file
    }
    if (piece.toLowerCase() === "k" && Math.abs(tf - ff) === 2) {
      if (tf > ff) { grid[fr][5] = grid[fr][7]; grid[fr][7] = null; }  // O-O
      else         { grid[fr][3] = grid[fr][0]; grid[fr][0] = null; }  // O-O-O
    }
    const promo = uci[4];
    grid[tr][tf] = promo ? (isWhite ? promo.toUpperCase() : promo.toLowerCase()) : piece;
    grid[fr][ff] = null;
    parts[0] = gridToPlacement(grid);
    parts[1] = isWhite ? "b" : "w";  // flip side to move (render reads placement only)
    return parts.join(" ");
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

  function renderLossSummary(D) {
    const root = document.getElementById("loss-summary-cards");
    const bucketsRoot = document.getElementById("mate-buckets");
    if (!root) return;
    const losses = D.recent_losses || [];
    if (losses.length === 0) {
      root.innerHTML = `<p style="color:var(--muted)">No losses in window.</p>`;
      if (bucketsRoot) bucketsRoot.innerHTML = "";
      return;
    }
    const byType = {};
    losses.forEach(L => { byType[L.loss_type] = (byType[L.loss_type] || 0) + 1; });
    const pct = (n) => `${Math.round(100 * n / losses.length)}%`;
    const cell = (label, value, sub) =>
      `<div class="behavior-card">
         <div class="bh-label">${label}</div>
         <div class="bh-value">${value}</div>
         <div class="bh-sub">${sub}</div>
       </div>`;
    root.innerHTML = [
      cell("Losses in window", String(losses.length), ""),
      cell("Timeouts", `${byType.timeout || 0}`, pct(byType.timeout || 0)),
      cell("Mates", `${byType.checkmated || 0}`, pct(byType.checkmated || 0)),
      cell("Abandoned", `${byType.abandoned || 0}`, pct(byType.abandoned || 0)),
    ].join("");

    if (bucketsRoot) {
      const mb = (D.behavior && D.behavior.mate_loss_buckets) || [];
      if (mb.length === 0) {
        bucketsRoot.innerHTML = `<p style="color:var(--muted)">No mate losses yet.</p>`;
      } else {
        new Tabulator("#mate-buckets", {
          data: mb, layout: "fitColumns",
          columns: [
            {title: "Side", field: "side"},
            {title: "Length", field: "bucket"},
            {title: "Count", field: "count", sorter: "number"},
          ],
          initialSort: [{column: "count", dir: "desc"}],
        });
      }
    }
  }

  function renderReviewPicks(picks) {
    const root = document.getElementById("review-picks-list");
    if (!root) return;
    if (!picks || picks.length === 0) {
      root.innerHTML = `<li style="color:var(--muted)">No recent losses to review.</li>`;
      return;
    }
    const label = {
      biggest_loss: "Biggest single-game rating loss",
      timeout: "Most recent timeout",
      fast_mate: "Most recent fast mate (≤15 moves)",
    };
    root.innerHTML = picks.map(p => {
      const delta = p.rating_delta == null ? "" :
        ` (${p.rating_delta > 0 ? "+" : ""}${p.rating_delta} rating)`;
      return `<li>
        <strong>${label[p.kind] || p.kind}</strong>${delta} —
        <a href="${escapeAttr(p.url)}" target="_blank">${p.loss_type}, ${p.moves} moves</a>
        <div style="color:var(--muted);font-size:0.9rem">${p.question}</div>
      </li>`;
    }).join("");
  }

  function winPctCell(cell) {
    const v = cell.getValue();
    const cls = v >= 60 ? "cell-strong" : v <= 35 ? "cell-weak" : "";
    return `<span class="${cls}">${v}%</span>`;
  }
  function ratingDeltaCell(cell) {
    const v = cell.getValue();
    if (v == null) return "—";
    const cls = v <= -20 ? "cell-weak" : v >= 20 ? "cell-strong" : "";
    return `<span class="${cls}">${v >= 0 ? "+" : ""}${v}</span>`;
  }
})();
