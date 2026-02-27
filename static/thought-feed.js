/**
 * ArkainBrain — Live Thought Feed
 * Renders structured ##EV:{json}## events + fallback text parsing
 * into an animated agent activity feed.
 *
 * Reads config from #jobData data-* attributes.
 */
(function () {
  var jd = document.getElementById("jobData");
  if (!jd) return;

  var JID = jd.dataset.jobId;
  var iSt = jd.dataset.status;
  var cAt = jd.dataset.created;

  var tf = document.getElementById("tf");
  var rl = document.getElementById("rawLog");
  var fw = document.getElementById("fw");
  var asc = true;
  var dn = iSt === "complete" || iSt === "failed";
  var sr = false;
  var M = { ok: 0, wr: 0, er: 0, oo: 0, ln: 0 };

  // ── Scroll / raw toggle ──
  fw.addEventListener("scroll", function () {
    asc = fw.scrollHeight - fw.scrollTop - fw.clientHeight < 80;
  });
  window._sBot = function () {
    fw.scrollTop = fw.scrollHeight;
    asc = true;
  };
  window._tRaw = function () {
    sr = !sr;
    fw.style.display = sr ? "none" : "block";
    rl.style.display = sr ? "block" : "none";
    document.getElementById("rawBtn").style.color = sr ? "var(--accent)" : "";
  };

  // ── Elapsed timer ──
  var t0 = cAt
    ? new Date(cAt + (cAt.indexOf("Z") < 0 ? "Z" : "")).getTime()
    : Date.now();
  function tick() {
    var d = Math.floor((Date.now() - t0) / 1000);
    var s = d % 60;
    var m = Math.floor(d / 60) % 60;
    var h = Math.floor(d / 3600);
    document.getElementById("elapsed").textContent = h
      ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
      : m + ":" + String(s).padStart(2, "0");
  }
  tick();
  if (!dn) setInterval(tick, 1000);

  // ── Stage timeline ──
  var ord = ["preflight", "research", "design", "art", "production", "package"];
  var aI = -1;
  var nm = {
    "Pre-Flight": "preflight",
    Initialize: "preflight",
    "Market Research": "research",
    Research: "research",
    Design: "design",
    Math: "design",
    Mood: "art",
    Art: "art",
    Production: "production",
    Compliance: "production",
    Assembly: "package",
    PDF: "package",
    Package: "package",
  };
  function setSt(n) {
    for (var k in nm) {
      if (n.indexOf(k) !== -1) {
        var t = nm[k],
          i = ord.indexOf(t);
        if (i > aI) {
          aI = i;
          document.querySelectorAll(".pl-stage").forEach(function (e, j) {
            e.classList.remove("active", "done");
            if (j < i) e.classList.add("done");
            else if (j === i) e.classList.add("active");
          });
        }
        break;
      }
    }
  }
  function allD() {
    document.querySelectorAll(".pl-stage").forEach(function (e) {
      e.classList.remove("active");
      e.classList.add("done");
    });
  }
  function uM() {
    document.getElementById("mOk").textContent = M.ok;
    document.getElementById("mWr").textContent = M.wr;
    document.getElementById("mEr").textContent = M.er;
    document.getElementById("mOo").textContent = M.oo;
    document.getElementById("mLn").textContent = M.ln + " events";
  }

  // ── Helpers ──
  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function agC(key, task, typing) {
    var map = {
      r: ["research", "Research Agent"],
      m: ["math", "Math Agent"],
      d: ["design", "Design Agent"],
      l: ["legal", "Legal Agent"],
      p: ["producer", "Producer"],
      q: ["qa", "QA Agent"],
    };
    var a = map[key] || map.p;
    var dots = typing
      ? '<span class="atyp"><span></span><span></span><span></span></span>'
      : "";
    return (
      '<div class="ev-agent"><div class="aav aav-' +
      a[0] +
      '"></div><div class="abody"><div class="aname an-' +
      a[0] +
      '">' +
      a[1] +
      dots +
      '</div><div class="atask">' +
      esc(task) +
      "</div></div></div>"
    );
  }

  // ── Structured event parser ──
  function pEV(e) {
    switch (e.t) {
      case "stage_start":
        setSt(e.name || "");
        return (
          '<div class="ev-stage">' +
          (e.icon || "&#9654;") +
          '&ensp;<span class="sn">Stage ' +
          (e.num !== undefined ? e.num : "") +
          "</span>&ensp;" +
          esc(e.name || "") +
          (e.desc
            ? '<span class="sd">' + esc(e.desc) + "</span>"
            : "") +
          "</div>"
        );
      case "stage_done":
        M.ok++;
        setSt(e.name || "");
        return (
          '<div class="ev-ok">&#10003; ' +
          esc(e.name || "Stage") +
          " complete" +
          (e.loops ? " &mdash; " + e.loops + " OODA loop(s)" : "") +
          "</div>"
        );
      case "agent_start":
        var k = "p";
        if (e.agent) {
          var al = e.agent.toLowerCase();
          if (al.indexOf("research") >= 0) k = "r";
          else if (al.indexOf("math") >= 0) k = "m";
          else if (al.indexOf("design") >= 0) k = "d";
          else if (al.indexOf("legal") >= 0 || al.indexOf("compliance") >= 0)
            k = "l";
          else if (al.indexOf("qa") >= 0 || al.indexOf("adversarial") >= 0)
            k = "q";
        }
        return agC(k, e.task || "Working...", true);
      case "agent_done":
        M.ok++;
        return (
          '<div class="ev-ok">&#10003; ' +
          esc(e.agent || "Agent") +
          " finished</div>"
        );
      case "ooda_start":
        M.oo = Math.max(M.oo, e.loop || 0);
        return (
          '<div class="ev-ooda"><div class="ooda-s"></div><span class="ooda-b">OODA ' +
          (e.loop || "") +
          " / " +
          (e.max || 3) +
          '</span><span style="color:var(--text);font-size:12px">' +
          (e.phase === "revision"
            ? "Revising based on blockers"
            : "Checking convergence") +
          "</span></div>"
        );
      case "ooda_result":
        return (
          '<div class="ev-or ' +
          (e.converged ? "pass" : "fail") +
          '">' +
          (e.converged ? "&#10003; Converged" : "&#8634; Not converged") +
          " after loop " +
          (e.loop || "?") +
          (e.blockers ? " &mdash; " + e.blockers + " blocker(s)" : "") +
          "</div>"
        );
      case "parallel_start":
        var h =
          '<div class="ev-par"><div style="font-weight:500;color:var(--text-bright)">&#9889; Parallel Execution</div><div class="ptracks">';
        (e.tasks || []).forEach(function (t) {
          h +=
            '<span class="ptrack"><span class="pdot"></span>' +
            esc(t) +
            "</span>";
        });
        return h + "</div></div>";
      case "metric":
        return (
          '<span class="ev-met">' +
          (e.label || e.key) +
          ': <span class="mv">' +
          (e.key === "cost" ? "$" : "") +
          e.value +
          "</span></span>"
        );
      case "blocker":
        M.er++;
        return (
          '<div class="ev-er">&#128680; BLOCKER: ' +
          esc(e.msg || "") +
          "</div>"
        );
      case "warn":
        M.wr++;
        return '<div class="ev-wr">&#9888; ' + esc(e.msg || "") + "</div>";
      case "info":
        return (
          '<div class="ev" style="color:var(--text-muted)">' +
          esc(e.msg || "") +
          "</div>"
        );
    }
    return null;
  }

  // ── Fallback plain text parser ──
  function pTxt(raw) {
    // Strip Rich console markup: [bold cyan], [/bold], [green], etc.
    var t = raw.replace(/\[\/?[a-z_ ]+\]/gi, "").trim();
    if (!t || t.length < 2) return null;

    if (/Stage\s*\d/i.test(t)) {
      setSt(t);
      M.ok++;
      return '<div class="ev-stage">' + esc(t) + "</div>";
    }
    if (
      t.indexOf("OODA") >= 0 &&
      (t.indexOf("Loop") >= 0 || t.indexOf("Convergence") >= 0)
    ) {
      M.oo++;
      return (
        '<div class="ev-ooda"><div class="ooda-s"></div><span class="ooda-b">OODA</span><span style="color:var(--text);font-size:12px">' +
        esc(t) +
        "</span></div>"
      );
    }
    if (t.indexOf("CONVERGED") >= 0) {
      M.ok++;
      return '<div class="ev-or pass">' + esc(t) + "</div>";
    }
    if (t.indexOf("PARALLEL") >= 0) {
      return (
        '<div class="ev-par"><div style="font-weight:500;color:var(--text-bright)">' +
        esc(t) +
        "</div></div>"
      );
    }
    if (t.indexOf("complete") >= 0 && t.indexOf("FAIL") < 0) {
      M.ok++;
      setSt(t);
      return '<div class="ev-ok">' + esc(t) + "</div>";
    }
    if (t.indexOf("BLOCKER") >= 0) {
      M.er++;
      return '<div class="ev-er">' + esc(t) + "</div>";
    }
    if (t.indexOf("FAILED") >= 0 || t.indexOf("ERROR") >= 0) {
      M.er++;
      return '<div class="ev-er">' + esc(t) + "</div>";
    }
    if (t.indexOf("WARN") >= 0) {
      M.wr++;
      return '<div class="ev-wr">' + esc(t) + "</div>";
    }
    if (t.indexOf("Skipping") >= 0 || t.indexOf("Auto-approv") >= 0) {
      return '<div class="ev-dim">' + esc(t) + "</div>";
    }
    if (t.indexOf("[JOB COMPLETE]") >= 0) {
      allD();
      return '<div class="ev-done success">Pipeline Complete</div>';
    }
    if (t.indexOf("[JOB FAILED]") >= 0) {
      return '<div class="ev-done fail">Pipeline Failed</div>';
    }

    // Collapsible long lines — built as DOM node to avoid innerHTML onclick issues
    if (t.length > 120) {
      var el = document.createElement("div");
      el.className = "ev-th";
      el.textContent = t;
      el.onclick = function () {
        this.classList.toggle("exp");
      };
      return el;
    }

    if (t.length > 3) {
      return (
        '<div class="ev" style="color:var(--text-muted);font-size:11.5px">' +
        esc(t) +
        "</div>"
      );
    }
    return null;
  }

  // ── Line router ──
  function pLine(raw) {
    var m = raw.match(/^##EV:(.+)##$/);
    if (m) {
      try {
        return pEV(JSON.parse(m[1]));
      } catch (x) {
        /* malformed JSON, fall through */
      }
    }
    return pTxt(raw);
  }

  // ── Append parsed result to fragment ──
  function addToFeed(result, frag) {
    if (!result) return;
    // DOM node (from collapsible long lines)
    if (result instanceof HTMLElement) {
      frag.appendChild(result);
      return;
    }
    // HTML string
    var tmp = document.createElement("div");
    tmp.innerHTML = result;
    while (tmp.firstChild) frag.appendChild(tmp.firstChild);
  }

  // ── Completion helpers ──
  function stopTimer() {
    var dot = document.getElementById("timerDot");
    if (dot) dot.classList.add("stopped");
  }
  function addFilesBtn() {
    var ab = document.getElementById("actionBtns");
    if (ab && ab.innerHTML.indexOf("/files") === -1) {
      ab.innerHTML +=
        '<a href="/job/' +
        JID +
        '/files" class="btn btn-primary btn-sm">View Files</a>';
    }
  }

  // ── Status poller (3s) ──
  var sp = setInterval(function () {
    if (dn) {
      clearInterval(sp);
      return;
    }
    fetch("/api/status/" + JID)
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        var b = document.getElementById("jobStatus");
        var s = document.getElementById("jobStage");
        if (d.current_stage) {
          s.textContent = d.current_stage;
          s.className = "stage-shimmer";
          setSt(d.current_stage);
        }
        if (d.status !== b.textContent) {
          b.textContent = d.status;
          b.className =
            "badge badge-" +
            (d.status === "complete"
              ? "complete"
              : d.status === "failed"
              ? "failed"
              : d.status === "running"
              ? "running"
              : "queued");
          if (d.status === "complete") {
            dn = true;
            s.className = "";
            s.textContent = "Done";
            stopTimer();
            allD();
            addFilesBtn();
          }
          if (d.status === "failed") {
            dn = true;
            s.className = "";
            stopTimer();
          }
        }
      })
      .catch(function () {});
  }, 3000);

  // ── Log poller (2s) ──
  var cur = 0,
    ld = false;
  function poll() {
    if (ld) return;
    fetch("/api/logs/" + JID + "?after=" + cur)
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        var fg = document.createDocumentFragment();
        d.lines.forEach(function (ln) {
          rl.textContent += ln + "\n";
          M.ln++;
          addToFeed(pLine(ln), fg);
        });
        tf.appendChild(fg);
        cur = d.cursor;
        if (asc && d.lines.length) window._sBot();
        if (d.lines.length) uM();
        if (d.done) {
          ld = true;
          dn = true;
          stopTimer();
          if (d.status === "complete" && !tf.querySelector(".ev-done")) {
            var x = document.createElement("div");
            x.className = "ev-done success";
            x.textContent = "Pipeline Complete";
            tf.appendChild(x);
            allD();
            var b = document.getElementById("jobStatus");
            b.className = "badge badge-complete";
            b.textContent = "complete";
            addFilesBtn();
          }
          if (d.status === "failed" && !tf.querySelector(".ev-done")) {
            var y = document.createElement("div");
            y.className = "ev-done fail";
            y.textContent = "Pipeline Failed";
            tf.appendChild(y);
            var b2 = document.getElementById("jobStatus");
            b2.className = "badge badge-failed";
            b2.textContent = "failed";
          }
        }
      })
      .catch(function () {});
  }
  poll();
  setInterval(poll, 2000);
})();
