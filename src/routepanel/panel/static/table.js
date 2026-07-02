// src/routepanel/panel/static/table.js
// Progressive enhancement for the Domain Rules table: filter by hiding rows,
// sort by reordering DOM nodes. No network, no innerHTML rebuild.
(function () {
  let ospfFilter = "any";
  let sortKey = "name";   // name | ips | sync
  let sortDir = 1;        // 1 asc, -1 desc

  function els() {
    return {
      q: document.getElementById("q"),
      exit: document.getElementById("exitFilter"),
      tbody: document.getElementById("rows"),
      count: document.getElementById("count"),
      empty: document.getElementById("empty"),
      total: document.getElementById("rule-total"),
    };
  }

  function apply() {
    const e = els();
    if (!e.tbody) return;
    const rows = Array.from(e.tbody.querySelectorAll("tr"));
    const q = (e.q ? e.q.value : "").trim().toLowerCase();
    const ex = e.exit ? e.exit.value : "";

    let visible = 0;
    rows.forEach((tr) => {
      let show = true;
      if (ex && tr.dataset.exit !== ex) show = false;
      if (ospfFilter === "on" && tr.dataset.ospf !== "1") show = false;
      if (ospfFilter === "off" && tr.dataset.ospf !== "0") show = false;
      if (q && tr.dataset.search.indexOf(q) === -1) show = false;
      tr.style.display = show ? "" : "none";
      if (show) visible++;
    });

    const sorted = rows.slice().sort((a, b) => {
      let x, y;
      if (sortKey === "ips") { x = +a.dataset.ips; y = +b.dataset.ips; }
      else if (sortKey === "sync") { x = a.dataset.sync; y = b.dataset.sync; }
      else { x = a.dataset.name; y = b.dataset.name; }
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });
    sorted.forEach((tr) => e.tbody.appendChild(tr));

    if (e.count) {
      const total = e.total ? +e.total.value : rows.length;
      e.count.textContent = visible + " of " + total + " shown";
    }
    if (e.empty) e.empty.style.display = visible ? "none" : "block";

    document.querySelectorAll("th.sortable").forEach((th) => {
      const on = th.dataset.k === sortKey;
      th.classList.toggle("sorted", on);
      const a = th.querySelector(".arrow");
      if (a) a.textContent = on ? (sortDir > 0 ? "▲" : "▼") : "↕";
    });
  }

  window.setOspf = function (v) {
    ospfFilter = v;
    document.querySelectorAll("#ospfSeg button").forEach((b) =>
      b.classList.toggle("on", b.dataset.v === v));
    apply();
  };

  window.sortBy = function (k) {
    if (sortKey === k) sortDir *= -1; else { sortKey = k; sortDir = 1; }
    apply();
  };

  window.initDomainTable = function () {
    const e = els();
    if (!e.tbody) return;
    if (e.q) e.q.addEventListener("input", apply);
    if (e.exit) e.exit.addEventListener("change", apply);
    apply();
  };

  document.addEventListener("DOMContentLoaded", function () {
    if (document.getElementById("rows")) window.initDomainTable();
  });
})();
