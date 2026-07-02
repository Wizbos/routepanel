// src/routepanel/panel/static/app.js
async function apiPost(url, data) {
  const r = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function apiPut(url, data) {
  const r = await fetch(url, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function apiDelete(url) {
  const r = await fetch(url, {method: "DELETE"});
  if (!r.ok) throw new Error(await r.text());
}

function pickLibrary(domains, cidrs) {
  const ta = document.getElementById("domains-input");
  if (ta) ta.value = (domains || []).join("\n");
  const ca = document.getElementById("cidrs-input");
  if (ca) ca.value = (cidrs || []).join("\n");
}
