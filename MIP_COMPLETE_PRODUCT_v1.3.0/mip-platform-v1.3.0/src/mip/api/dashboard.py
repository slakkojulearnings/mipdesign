from __future__ import annotations


def dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mainframe Intelligence Platform</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#172033;background:#f5f7fb}
body{margin:0}.top{background:#102a43;color:white;padding:1.2rem 2rem}.top h1{margin:0;font-size:1.5rem}
main{max-width:1200px;margin:1.5rem auto;padding:0 1rem}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem}
.card,.panel{background:white;border:1px solid #dbe3ec;border-radius:12px;padding:1rem;box-shadow:0 2px 8px rgba(16,42,67,.06)}
.value{font-size:2rem;font-weight:700;margin-top:.4rem}h2{margin-top:2rem}table{border-collapse:collapse;width:100%}
th,td{text-align:left;border-bottom:1px solid #e6ebf1;padding:.6rem}input,button{font:inherit;padding:.65rem;border-radius:8px;border:1px solid #b8c4d1}
input{width:min(600px,70%)}button{background:#1769aa;color:white;border-color:#1769aa;cursor:pointer}pre{white-space:pre-wrap;max-height:420px;overflow:auto;background:#f7f9fc;padding:1rem;border-radius:8px}
a{color:#1769aa}.status{font-weight:700}.ok{color:#1b7f4b}.warn{color:#a05a00}.fail{color:#b42318}
</style>
</head>
<body>
<header class="top"><h1>Mainframe Intelligence Platform</h1><div>Evidence-backed repository intelligence</div></header>
<main>
<div id="cards" class="cards"></div>
<h2>Repository Validation</h2><div id="validation" class="panel">Loading…</div>
<h2>Root Programs</h2><div class="panel"><table><thead><tr><th>Name</th><th>Source</th><th>Confidence</th></tr></thead><tbody id="roots"></tbody></table></div>
<h2>Ask MIP</h2><div class="panel"><input id="question" value="Which jobs execute CUST001?"><button onclick="ask()">Ask</button><pre id="answer">Use a deterministic supported question.</pre></div>
<p><a href="/docs">OpenAPI documentation</a></p>
</main>
<script>
const esc = value => String(value ?? '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
async function load(){
 const stats=await fetch('/stats').then(r=>r.json()); const run=stats.run||{};
 const values=[['Files',run.file_count||0],['Parsed',run.parsed_count||0],['Assets',run.asset_count||0],['Relationships',run.relationship_count||0],['Issues',run.issue_count||0]];
 document.getElementById('cards').innerHTML=values.map(([k,v])=>`<div class="card"><div>${esc(k)}</div><div class="value">${esc(v)}</div></div>`).join('');
 const validation=await fetch('/validation').then(r=>r.json()); const cls=validation.status==='PASS'?'ok':validation.status==='WARN'?'warn':'fail';
 document.getElementById('validation').innerHTML=`<span class="status ${cls}">${esc(validation.status)}</span><pre>${esc(JSON.stringify(validation.checks,null,2))}</pre>`;
 const roots=await fetch('/roots').then(r=>r.json()); document.getElementById('roots').innerHTML=roots.map(x=>`<tr><td>${esc(x.technical_name)}</td><td>${esc(x.source_path)}</td><td>${esc(x.confidence)}</td></tr>`).join('');
}
async function ask(){const q=document.getElementById('question').value;const data=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})}).then(r=>r.json());document.getElementById('answer').textContent=JSON.stringify(data,null,2)}
load();
</script>
</body></html>"""
