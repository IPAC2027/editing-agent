"""The review desk page.

One HTML document, served from the local machine, with no external requests —
no web fonts, no CDN, no analytics. An editor may be working on a train or
behind a lab firewall, and a review tool that needs the internet to render is a
review tool that sometimes does not.

Written for someone who does not program. Rules the markup and copy follow:

* Nothing visible says ``FMT-UNIT-02``. Every card leads with what changed in
  words, and why JACoW cares. The check id is available in small grey type for
  the one editor in ten who wants to cite it in a mail to the tool's author.
* Work is sorted by *who has to act*: your decisions, then what only the author
  can fix, then things noted for the record.
* Every destructive-looking action is reversible and says so. Finishing a paper
  can be undone; the author's own files are never written.
* The keyboard works, because an editor doing forty papers will not reach for
  the mouse forty times per paper.
"""

from __future__ import annotations

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JACoW review desk</title>
<!-- Inline so the page makes no network request whatsoever: an editor may be
     working offline, and a 404 in the console is one more thing to explain. -->
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23255a7a'/%3E%3Cpath d='M8 10h16M8 16h16M8 22h10' stroke='white' stroke-width='2.5' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
:root{
  --ink:#16191d; --ink2:#48525c; --muted:#78838d;
  --paper:#f2f5f6; --surface:#ffffff; --surface2:#eef1f3; --surface3:#e4e9ec;
  --rule:#d6dbdf; --rule2:#e7ebee;
  --accent:#255a7a; --accent2:#2c6b91; --accent-soft:#e2edf3; --on-accent:#ffffff;
  --good:#1c7a4a; --good-soft:#e2f3e9;
  --warn:#8f6f08; --warn-soft:#faf1d8;
  --bad:#9c2135;  --bad-soft:#fbe9ec;
  --shadow:0 1px 2px rgba(20,24,28,.07), 0 10px 26px -18px rgba(20,24,28,.3);
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
  --radius:7px;
}
@media (prefers-color-scheme:dark){:root{
  --ink:#e8ecef; --ink2:#a8b2ba; --muted:#7b858e;
  --paper:#0f1317; --surface:#171c21; --surface2:#1e242a; --surface3:#262d34;
  --rule:#2c343b; --rule2:#232a30;
  --accent:#79b0d1; --accent2:#8ec0de; --accent-soft:#1a2a35; --on-accent:#0d1216;
  --good:#39a06f; --good-soft:#14261d;
  --warn:#c19a3c; --warn-soft:#2a2313;
  --bad:#d6607a;  --bad-soft:#2a161a;
  --shadow:0 1px 2px rgba(0,0,0,.5), 0 10px 26px -18px rgba(0,0,0,.8);
}}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);
     -webkit-font-smoothing:antialiased}
button,input,textarea,select{font:inherit;color:inherit}
a{color:var(--accent);text-underline-offset:2px}
[hidden]{display:none!important}

/* ---------- shell ---------- */
.top{position:sticky;top:0;z-index:30;background:var(--surface);
     border-bottom:1px solid var(--rule);box-shadow:0 1px 0 rgba(0,0,0,.02)}
.top-in{max-width:1180px;margin:0 auto;padding:11px 20px;display:flex;
        align-items:center;gap:16px;flex-wrap:wrap}
.brand{font-weight:650;font-size:1rem;letter-spacing:-.01em;white-space:nowrap}
.brand small{display:block;font-weight:400;font-size:.76rem;color:var(--muted);
             letter-spacing:0}
.top-spacer{flex:1}
.who{display:flex;align-items:center;gap:7px;font-size:.85rem;color:var(--ink2);
      white-space:nowrap}
.who input{width:150px;padding:5px 8px;border:1px solid var(--rule);
           border-radius:5px;background:var(--surface2)}
main{max-width:1180px;margin:0 auto;padding:22px 20px 90px}

/* ---------- generic bits ---------- */
h1{font-size:1.35rem;margin:0 0 4px;letter-spacing:-.015em}
h2{font-size:1.02rem;margin:0 0 3px;letter-spacing:-.005em}
h3{font-size:.94rem;margin:0 0 4px}
p{margin:0 0 .85em}
.sub{color:var(--ink2);font-size:.9rem;margin:0 0 16px;max-width:76ch}
.muted{color:var(--muted)}
.mono{font-family:var(--mono)}
.tiny{font-size:.75rem}
.card{background:var(--surface);border:1px solid var(--rule);
      border-radius:var(--radius);box-shadow:var(--shadow)}
.pad{padding:16px 18px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.stack{display:grid;gap:12px}

button{border:1px solid var(--rule);background:var(--surface2);border-radius:6px;
       padding:8px 13px;cursor:pointer;font-size:.88rem;line-height:1.2}
button:hover{border-color:var(--accent)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button:disabled{opacity:.5;cursor:default}
button.primary{background:var(--accent);border-color:var(--accent);
       color:var(--on-accent);font-weight:600}
button.primary:hover{background:var(--accent2);border-color:var(--accent2);
       color:var(--on-accent)}
button.yes{background:var(--good-soft);border-color:var(--good);color:var(--good);font-weight:550}
button.no{background:var(--bad-soft);border-color:var(--bad);color:var(--bad);font-weight:550}
button.plain{background:transparent;border-color:transparent;color:var(--accent);
             padding:4px 6px;text-decoration:underline}
button.big{padding:11px 18px;font-size:.95rem}

.pill{display:inline-flex;align-items:center;gap:6px;font-size:.75rem;font-weight:600;
      padding:3px 9px;border-radius:20px;background:var(--surface3);color:var(--ink2);
      white-space:nowrap}
.pill.new{background:var(--surface3);color:var(--ink2)}
.pill.in_review{background:var(--accent-soft);color:var(--accent)}
.pill.done{background:var(--good-soft);color:var(--good)}
.pill.needs_author{background:var(--warn-soft);color:var(--warn)}
.pill.count{background:var(--surface3);font-family:var(--mono);font-weight:500}

.bar{height:7px;border-radius:4px;background:var(--surface3);overflow:hidden}
.bar span{display:block;height:100%;background:var(--good);transition:width .3s}

/* ---------- worklist ---------- */
.wl-head{display:flex;align-items:flex-end;gap:20px;flex-wrap:wrap;margin-bottom:18px}
.wl-progress{min-width:230px;flex:1}
.wl-progress .lab{display:flex;justify-content:space-between;font-size:.82rem;
                  color:var(--ink2);margin-bottom:6px}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.filters button{padding:6px 12px;font-size:.83rem;border-radius:20px}
.filters button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);
                                     color:var(--on-accent)}
table.wl{width:100%;border-collapse:collapse;background:var(--surface);
         border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden}
table.wl th{font-size:.73rem;text-transform:uppercase;letter-spacing:.06em;
            color:var(--muted);font-weight:600;text-align:left;
            padding:10px 14px;background:var(--surface2);
            border-bottom:1px solid var(--rule);white-space:nowrap}
table.wl td{padding:11px 14px;border-bottom:1px solid var(--rule2);vertical-align:middle}
table.wl tr:last-child td{border-bottom:0}
table.wl tbody tr{cursor:pointer}
table.wl tbody tr:hover{background:var(--surface2)}
.pid{font-family:var(--mono);font-weight:600;font-size:.88rem}
.ttl{color:var(--ink2);font-size:.86rem;max-width:38ch;overflow:hidden;
     text-overflow:ellipsis;white-space:nowrap}
.num{text-align:right;font-family:var(--mono);font-size:.86rem;font-variant-numeric:tabular-nums}
.num.zero{color:var(--muted)}
.num.attn{color:var(--bad);font-weight:600}
.num.todo{color:var(--accent);font-weight:600}

/* ---------- paper ---------- */
.paper-head{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap;margin-bottom:6px}
.paper-head .grow{flex:1;min-width:260px}
.crumb{background:none;border:0;color:var(--accent);padding:0;font-size:.85rem;
       cursor:pointer;text-decoration:underline;margin-bottom:8px}
.summary{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0 18px}
.chip{background:var(--surface);border:1px solid var(--rule);border-radius:6px;
      padding:8px 12px;min-width:96px}
.chip b{display:block;font-family:var(--mono);font-size:1.3rem;line-height:1.1;
        font-variant-numeric:tabular-nums}
.chip span{font-size:.75rem;color:var(--muted)}
.chip.attn b{color:var(--bad)} .chip.todo b{color:var(--accent)}
.chip.ok b{color:var(--good)}

.tabs{display:flex;gap:2px;border-bottom:1px solid var(--rule);margin-bottom:20px;
      overflow-x:auto}
.tabs button{border:0;background:none;border-bottom:2px solid transparent;
             border-radius:0;padding:10px 14px;color:var(--ink2);white-space:nowrap}
.tabs button[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent);
                                   font-weight:600}
.tabs .n{font-family:var(--mono);font-size:.78rem;color:var(--muted);margin-left:5px}

/* suggestion / finding cards */
.item{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
      padding:15px 17px;margin-bottom:11px;position:relative}
.item.focus{box-shadow:0 0 0 2px var(--accent)}
.item.accepted{border-left:4px solid var(--good)}
.item.rejected{border-left:4px solid var(--bad);opacity:.72}
.item.handled{opacity:.6}
.item.applied{border-left:4px solid var(--rule)}
.item.reverted{border-left:4px solid var(--warn)}
.decided.applied{color:var(--muted)} .decided.reverted{color:var(--warn)}
.autobox{margin:0 0 11px}
.autobox>summary{cursor:pointer;list-style:none;display:flex;gap:9px;align-items:baseline;
                 padding:11px 14px;border:1px solid var(--rule);border-radius:var(--radius);
                 background:var(--surface2);font-size:.9rem}
.autobox>summary::-webkit-details-marker{display:none}
.autobox>summary::before{content:"▸";color:var(--muted)}
.autobox[open]>summary::before{content:"▾"}
.autobox>summary b{font-weight:600}
.autobox>summary .sub2{color:var(--ink2);font-size:.85rem}
.autobox .inner{margin:11px 0 0 7px;padding-left:14px;border-left:2px solid var(--rule)}
.autobox .inner>.why{margin-bottom:11px}
.autobox .item{background:var(--surface2)}
.item-top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}
.item-top h3{margin:0;flex:1 1 18ch}
.where{font-family:var(--mono);font-size:.78rem;color:var(--muted);white-space:nowrap}
.why{color:var(--ink2);font-size:.9rem;margin:0 0 11px;max-width:80ch}
.ba{display:grid;gap:6px;margin-bottom:12px}
@media(min-width:820px){.ba{grid-template-columns:1fr 1fr;gap:8px}}
.ba>div{font-family:var(--mono);font-size:.83rem;padding:9px 11px;border-radius:6px;
        white-space:pre-wrap;word-break:break-word;overflow-x:auto}
.ba .lab{font-family:var(--sans);font-size:.72rem;text-transform:uppercase;
         letter-spacing:.06em;display:block;margin-bottom:4px;opacity:.75;font-weight:600}
.ba .was{background:var(--bad-soft);color:var(--bad)}
.ba .now{background:var(--good-soft);color:var(--good)}
.acts{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.decided{display:flex;align-items:center;gap:9px;font-size:.88rem;font-weight:550}
.decided.accepted{color:var(--good)} .decided.rejected{color:var(--bad)}
.notebox{margin-top:11px}
.notebox summary{cursor:pointer;font-size:.83rem;color:var(--accent);
                 list-style:none;display:inline-flex;gap:5px;align-items:center}
.notebox summary::-webkit-details-marker{display:none}
.notebox summary::before{content:"✎";font-size:.9em}
.notebox[open] summary{margin-bottom:7px}
textarea{width:100%;min-height:66px;padding:9px 11px;border:1px solid var(--rule);
         border-radius:6px;background:var(--surface2);resize:vertical;font-size:.88rem}
input[type=text]{width:100%;padding:9px 11px;border:1px solid var(--rule);
                 border-radius:6px;background:var(--surface2)}
.hasnote{margin-top:9px;background:var(--warn-soft);border-left:3px solid var(--warn);
         padding:8px 11px;border-radius:0 5px 5px 0;font-size:.86rem}
.hasnote b{font-weight:600}
.checkid{font-family:var(--mono);font-size:.7rem;color:var(--muted)}

.bulk{display:flex;gap:8px;align-items:center;flex-wrap:wrap;
      background:var(--surface);border:1px solid var(--rule);border-radius:6px;
      padding:10px 13px;margin-bottom:14px}
.bulk .lab{font-size:.84rem;color:var(--ink2);margin-right:2px}
.bulk button{font-size:.83rem;padding:6px 11px}
.group{margin-bottom:26px}
.group>h2{margin-bottom:2px}
.group>p{font-size:.87rem;color:var(--ink2);margin-bottom:13px;max-width:78ch}
.sevdot{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none}
.sevdot.error{background:var(--bad)} .sevdot.warning{background:var(--warn)}
.sevdot.info{background:var(--muted)}

/* source viewer */
.srctools{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:11px}
.srctools input[type=text]{width:auto;flex:1 1 180px;min-width:140px;padding:7px 10px}
.srctools button{padding:6px 11px;font-size:.83rem}
.srctools button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);
                                      color:var(--on-accent)}
.srcline.hit .tx{background:var(--warn-soft)}
.srcnote{font-size:.87rem;color:var(--ink2);margin-bottom:12px}
.src{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
     overflow:auto;max-height:62vh;font-family:var(--mono);font-size:.82rem}
.srcline{display:flex;gap:0;border-bottom:1px solid transparent}
.srcline:hover{background:var(--surface2)}
.srcline .ln{flex:none;width:56px;text-align:right;padding:3px 10px 3px 0;color:var(--muted);
             user-select:none;background:var(--surface2);border-right:1px solid var(--rule2)}
.srcline .tx{flex:1;padding:3px 12px;white-space:pre-wrap;word-break:break-word;
             cursor:text;min-height:1.5em}
.srcline.changed .ln{background:var(--good-soft);color:var(--good)}
.srcline.mine .ln{background:var(--warn-soft);color:var(--warn);font-weight:700}
.srcedit{padding:11px 12px;background:var(--surface2);border-top:1px solid var(--rule)}
.srcedit textarea{font-family:var(--mono);font-size:.84rem;min-height:52px}

/* letter */
.letter textarea{min-height:340px;font-family:var(--mono);font-size:.85rem}

/* files */
.filelist{display:grid;gap:8px}
.filerow{display:flex;gap:12px;align-items:center;background:var(--surface);
         border:1px solid var(--rule);border-radius:6px;padding:11px 14px}
.filerow .grow{flex:1}
.filerow .nm{font-family:var(--mono);font-size:.78rem;color:var(--muted)}

/* footer action bar */
.footbar{position:fixed;bottom:0;left:0;right:0;background:var(--surface);
         border-top:1px solid var(--rule);z-index:25;
         box-shadow:0 -2px 14px -8px rgba(0,0,0,.3)}
.footbar-in{max-width:1180px;margin:0 auto;padding:11px 20px;display:flex;gap:12px;
            align-items:center;flex-wrap:wrap}
.footbar .status{font-size:.86rem;color:var(--ink2);flex:1;min-width:200px}

/* dialog */
dialog{border:1px solid var(--rule);border-radius:10px;background:var(--surface);
       color:var(--ink);max-width:560px;width:calc(100vw - 40px);padding:0;
       box-shadow:0 20px 60px -20px rgba(0,0,0,.5)}
dialog::backdrop{background:rgba(10,14,18,.5)}
.dlg-in{padding:20px 22px}
.dlg-in h2{margin-bottom:10px}
.dlg-in ul{margin:0 0 16px;padding-left:20px;font-size:.9rem;color:var(--ink2)}
.dlg-in ul li{margin-bottom:4px}
.dlg-acts{display:flex;gap:9px;justify-content:flex-end;flex-wrap:wrap;
          border-top:1px solid var(--rule);padding:14px 22px;background:var(--surface2);
          border-radius:0 0 10px 10px}
fieldset{border:1px solid var(--rule);border-radius:6px;padding:11px 13px;margin:0 0 14px}
legend{font-size:.8rem;color:var(--muted);padding:0 5px}
label.opt{display:flex;gap:9px;align-items:flex-start;font-size:.9rem;margin-bottom:8px;
          cursor:pointer}
label.opt:last-child{margin-bottom:0}
label.opt input{margin-top:3px}
label.opt span small{display:block;color:var(--muted);font-size:.82rem}

/* toast */
.toast{position:fixed;left:50%;transform:translateX(-50%);bottom:76px;z-index:60;
       background:var(--ink);color:var(--paper);padding:11px 18px;border-radius:22px;
       font-size:.88rem;box-shadow:0 8px 24px -8px rgba(0,0,0,.5);max-width:calc(100vw - 40px)}
.toast.bad{background:var(--bad);color:#fff}

.empty{background:var(--surface);border:1px dashed var(--rule);border-radius:var(--radius);
       padding:34px 22px;text-align:center;color:var(--ink2)}
.empty b{display:block;font-size:1rem;color:var(--ink);margin-bottom:5px}
.keyhint{font-size:.8rem;color:var(--muted);margin-bottom:14px}
kbd{font-family:var(--mono);font-size:.75rem;border:1px solid var(--rule);
    border-bottom-width:2px;border-radius:4px;padding:1px 5px;background:var(--surface2)}
#llmBadge{margin-left:10px;padding:1px 7px;border:1px solid var(--rule);border-radius:9px;
         font-variant-numeric:tabular-nums;white-space:nowrap}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--rule);
      border-top-color:var(--accent);border-radius:50%;animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>

<div class="top"><div class="top-in">
  <div class="brand">JACoW review desk<small id="rootName">&nbsp;</small><small id="llmBadge" hidden></small></div>
  <div class="top-spacer"></div>
  <label class="who">Your name
    <input id="editorName" type="text" placeholder="e.g. A. Editor" autocomplete="name">
  </label>
</div></div>

<main>
  <section id="viewWorklist"></section>
  <section id="viewPaper" hidden></section>
</main>

<div class="footbar" id="footbar" hidden><div class="footbar-in">
  <div class="status" id="footStatus"></div>
  <button id="btnPrev">← Previous paper</button>
  <button id="btnNext">Next paper →</button>
  <button class="primary big" id="btnFinish">Finish this paper</button>
</div></div>

<dialog id="dlgFinish"><form method="dialog"><div class="dlg-in">
  <h2>Finish this paper?</h2>
  <div id="finishSummary"></div>
  <fieldset><legend>How does it leave your desk?</legend>
    <label class="opt"><input type="radio" name="closeStatus" value="done" checked>
      <span>Finished — ready for the proceedings
      <small>Nothing further is needed from the author.</small></span></label>
    <label class="opt"><input type="radio" name="closeStatus" value="needs_author">
      <span>Send back to the author
      <small>The letter lists what they need to fix.</small></span></label>
  </fieldset>
  <p class="tiny muted">This writes your reviewed files and the letter. Nothing the
  author sent is changed, and you can reopen the paper afterwards.</p>
</div><div class="dlg-acts">
  <button value="cancel">Not yet</button>
  <button class="primary" value="ok" id="btnFinishGo">Finish paper</button>
</div></form></dialog>

<dialog id="dlgDone"><div class="dlg-in">
  <h2 id="doneTitle">Paper finished</h2>
  <div id="doneBody"></div>
</div><div class="dlg-acts">
  <button id="btnBackToList">Back to the list</button>
  <button class="primary" id="btnGoNext">Open the next paper</button>
</div></dialog>

<script>
(() => {
"use strict";

/* ------------------------------------------------------------------ state */
const S = {
  root:"", editor:"", papers:[], filter:"all",
  folder:null, paper:null, tab:"decisions", cursor:0, job:null,
  showApplied:false,
};

const $  = (s, r=document) => r.querySelector(s);
const el = (t, cls, txt) => { const n=document.createElement(t);
  if(cls) n.className=cls; if(txt!=null) n.textContent=txt; return n; };
const esc = (s) => String(s==null?"":s);

function toast(msg, bad){
  const t = el("div","toast"+(bad?" bad":""),msg);
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), bad?5200:2400);
}

async function api(path, body){
  const opts = body===undefined ? {} :
    {method:"POST", headers:{"Content-Type":"application/json"},
     body:JSON.stringify(body)};
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch(_) {}
  if(!res.ok || (data && data.error)){
    throw new Error((data && data.error) || ("Request failed ("+res.status+")"));
  }
  return data;
}

/* ------------------------------------------------------------- worklist */
const FILTERS = [
  ["all","All papers"], ["todo","Still to do"], ["new","Not started"],
  ["in_review","In progress"], ["done","Finished"],
];

function matchesFilter(p){
  if(S.filter==="all") return true;
  if(S.filter==="todo") return p.status!=="done";
  return p.status===S.filter;
}

function renderWorklist(){
  const host = $("#viewWorklist");
  host.innerHTML = "";
  $("#viewPaper").hidden = true; host.hidden = false;
  $("#footbar").hidden = true;

  const done  = S.papers.filter(p=>p.status==="done").length;
  const total = S.papers.length;
  const unprepared = S.papers.filter(p=>!p.screened).length;

  const head = el("div","wl-head");
  const left = el("div"); left.style.flex="1 1 300px";
  left.appendChild(el("h1", null, "Papers to review"));
  left.appendChild(el("p","sub",
    total ? "Open a paper to work through it. Your place is kept as you go."
          : "No submissions found in this folder."));
  head.appendChild(left);

  if(total){
    const prog = el("div","wl-progress");
    const lab = el("div","lab");
    lab.appendChild(el("span",null,done+" of "+total+" finished"));
    lab.appendChild(el("span","muted", Math.round(done/total*100)+"%"));
    prog.appendChild(lab);
    const bar = el("div","bar"); const fill = el("span");
    fill.style.width = (total? done/total*100 : 0)+"%"; bar.appendChild(fill);
    prog.appendChild(bar);
    head.appendChild(prog);
  }
  host.appendChild(head);

  if(unprepared){
    const box = el("div","card pad"); box.style.marginBottom="18px";
    box.appendChild(el("h2",null, unprepared+" paper"+(unprepared===1?"":"s")+" not prepared yet"));
    box.appendChild(el("p","sub",
      "The agent needs to read each paper once before you can review it. This "
      +"takes a few seconds per paper and only happens once."));
    const b = el("button","primary","Prepare "+(unprepared===1?"it":"them")+" now");
    b.onclick = () => prepare({all:true});
    box.appendChild(b);
    host.appendChild(box);
  }

  if(S.job && !S.job.finished){
    const box = el("div","card pad"); box.style.marginBottom="18px";
    const r = el("div","row");
    r.appendChild(el("span","spin"));
    r.appendChild(el("span",null, S.job.label+" — "+S.job.done+" of "+S.job.total
      + (S.job.current? " (now: "+S.job.current+")" : "")));
    box.appendChild(r);
    host.appendChild(box);
  }

  if(!total) return;

  const filters = el("div","filters");
  FILTERS.forEach(([key,label])=>{
    const n = S.papers.filter(p=>{const o=S.filter;S.filter=key;
      const m=matchesFilter(p);S.filter=o;return m;}).length;
    const b = el("button",null,label+(n?" ("+n+")":""));
    b.setAttribute("aria-pressed", S.filter===key ? "true":"false");
    b.onclick = () => { S.filter=key; renderWorklist(); };
    filters.appendChild(b);
  });
  host.appendChild(filters);

  const rows = S.papers.filter(matchesFilter);
  if(!rows.length){
    const e = el("div","empty");
    e.appendChild(el("b",null,"Nothing here"));
    e.appendChild(el("div",null,"No papers match this filter."));
    host.appendChild(e); return;
  }

  const table = el("table","wl");
  const thead = el("thead");
  const htr = el("tr");
  ["Paper","Title","Status","To decide","Must fix","Your notes",""]
    .forEach((h,i)=>{ const th=el("th",null,h);
      if(i>=3&&i<=5) th.style.textAlign="right"; htr.appendChild(th); });
  thead.appendChild(htr); table.appendChild(thead);

  const tbody = el("tbody");
  rows.forEach(p=>{
    const tr = el("tr");
    tr.onclick = () => openPaper(p.folder);
    tr.tabIndex = 0;
    tr.onkeydown = (e) => { if(e.key==="Enter"){ e.preventDefault(); openPaper(p.folder); } };

    const c1 = el("td"); c1.appendChild(el("div","pid",p.paper_id));
    if(p.kind==="word") c1.appendChild(el("div","tiny muted","Word"));
    tr.appendChild(c1);

    const c2 = el("td"); const t=el("div","ttl", p.title || p.name);
    t.title = p.title || p.name; c2.appendChild(t); tr.appendChild(c2);

    const c3 = el("td");
    c3.appendChild(el("span","pill "+(p.screened?p.status:"new"),
      p.screened? p.status_word : "Not prepared"));
    tr.appendChild(c3);

    const mk = (v, cls) => { const td=el("td","num "+(v?cls:"zero"),
      p.screened? String(v) : "—"); return td; };
    tr.appendChild(mk(p.to_decide,"todo"));
    tr.appendChild(mk(p.must_fix,"attn"));
    tr.appendChild(mk(p.my_notes,""));

    const c7 = el("td"); c7.style.textAlign="right";
    const b = el("button",null, p.screened ? (p.status==="done"?"Review again":"Open") : "Prepare");
    b.onclick = (e) => { e.stopPropagation();
      if(p.screened) openPaper(p.folder); else prepare({folder:p.folder}); };
    c7.appendChild(b); tr.appendChild(c7);

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  host.appendChild(table);
}

/* -------------------------------------------------------------- prepare */
async function prepare(opts){
  try{
    const res = await api("/api/prepare", opts);
    if(!res.job){ toast(res.message || "Nothing to prepare"); return; }
    S.job = res.job; renderWorklist(); pollJob();
  }catch(err){ toast(err.message, true); }
}

async function pollJob(){
  if(!S.job) return;
  try{
    const job = await api("/api/job?id="+encodeURIComponent(S.job.id));
    S.job = job;
    if(job.finished){
      S.job = null;
      if(job.errors && job.errors.length){
        toast(job.errors.length+" paper(s) could not be prepared — see the list", true);
      } else { toast("Ready to review"); }
      await loadWorklist();
      if(S.folder) await openPaper(S.folder); else renderWorklist();
      return;
    }
    if(!S.folder) renderWorklist();
    setTimeout(pollJob, 900);
  }catch(err){ S.job=null; toast(err.message, true); }
}

/* ---------------------------------------------------------------- paper */
const TABS = [
  ["decisions","Your decisions"],
  ["problems","Problems"],
  ["mine","Your notes"],
  ["source","The paper"],
  ["letter","Letter to the author"],
  ["files","Files"],
];

async function openPaper(folder){
  try{
    const data = await api("/api/paper?folder="+encodeURIComponent(folder));
    S.folder = folder; S.paper = data; S.cursor = 0;
    if(!data.screened){ renderUnprepared(); return; }
    renderPaper();
    window.scrollTo({top:0});
  }catch(err){ toast(err.message, true); }
}

function renderUnprepared(){
  const host = $("#viewPaper");
  $("#viewWorklist").hidden = true; host.hidden = false; $("#footbar").hidden = true;
  host.innerHTML = "";
  const back = el("button","crumb","← All papers"); back.onclick = backToList;
  host.appendChild(back);
  host.appendChild(el("h1",null,S.paper.paper_id));
  const e = el("div","empty");
  e.appendChild(el("b",null,"Not prepared yet"));
  e.appendChild(el("div",null,S.paper.message||""));
  const b = el("button","primary big","Prepare this paper");
  b.style.marginTop="16px";
  b.onclick = () => prepare({folder:S.folder});
  e.appendChild(b);
  host.appendChild(e);
}

function renderPaper(){
  const p = S.paper;
  const host = $("#viewPaper");
  $("#viewWorklist").hidden = true; host.hidden = false; $("#footbar").hidden = false;
  host.innerHTML = "";

  const back = el("button","crumb","← All papers"); back.onclick = backToList;
  host.appendChild(back);

  const head = el("div","paper-head");
  const grow = el("div","grow");
  const h1 = el("h1"); h1.appendChild(el("span","pid",p.paper_id));
  h1.appendChild(document.createTextNode("  "));
  grow.appendChild(h1);
  grow.appendChild(el("p","sub", p.title || p.name));
  head.appendChild(grow);
  const right = el("div","row");
  right.appendChild(el("span","pill "+p.status, p.status_word));
  if(p.build) right.appendChild(el("span","pill count", p.build));
  head.appendChild(right);
  host.appendChild(head);

  const c = p.counts;
  const sum = el("div","summary");
  const chip = (n,label,cls) => { const d=el("div","chip "+(cls||""));
    d.appendChild(el("b",null,String(n))); d.appendChild(el("span",null,label));
    return d; };
  sum.appendChild(chip(c.applied,"already corrected","ok"));
  if(c.reverted) sum.appendChild(chip(c.reverted,"you put back","attn"));
  sum.appendChild(chip(c.to_decide,"need your decision", c.to_decide?"todo":""));
  sum.appendChild(chip(c.must_fix,"must be fixed", c.must_fix?"attn":""));
  sum.appendChild(chip(c.my_notes + c.my_edits,"your notes & edits"));
  host.appendChild(sum);

  const tabs = el("div","tabs");
  TABS.forEach(([key,label])=>{
    const b = el("button",null,label);
    const n = {decisions:c.to_decide, problems:c.must_fix+c.worth_a_look,
               mine:c.my_notes+c.my_edits}[key];
    if(n) b.appendChild(el("span","n",String(n)));
    b.setAttribute("aria-selected", S.tab===key?"true":"false");
    b.onclick = () => { S.tab=key; S.cursor=0; renderPaper(); };
    tabs.appendChild(b);
  });
  host.appendChild(tabs);

  const body = el("div");
  host.appendChild(body);
  ({decisions:tabDecisions, problems:tabProblems, mine:tabMine,
    source:tabSource, letter:tabLetter, files:tabFiles}[S.tab])(body);

  updateFoot();
}

function updateFoot(){
  const p = S.paper, c = p.counts;
  const parts = [];
  if(c.to_decide) parts.push(c.to_decide+" still to decide");
  else parts.push("all decisions made");
  if(c.must_fix) parts.push(c.must_fix+" for the author");
  $("#footStatus").textContent = parts.join(" · ");
  const i = S.papers.findIndex(x=>x.folder===S.folder);
  $("#btnPrev").disabled = i<=0;
  $("#btnNext").disabled = i<0 || i>=S.papers.length-1;
  $("#btnFinish").textContent = p.status==="done" ? "Finish again" : "Finish this paper";
}

function backToList(){
  S.folder=null; S.paper=null;
  loadWorklist().then(renderWorklist);
}

/* ------------------------------------------------- tab: your decisions */

/* The corrections the agent made without asking.  Collapsed, because on a
   normal paper there are eight of them and they are all the same spacing fix
   — but present and reversible, because "we did not ask you" must not mean
   "you cannot say no". */
function appliedSection(host){
  const list = S.paper.applied || [];
  if(!list.length) return;
  const back = list.filter(a=>a.decision==="reverted").length;

  const det = el("details","autobox");
  det.open = S.showApplied || back>0;
  det.ontoggle = () => { S.showApplied = det.open; };

  const sum = el("summary");
  sum.appendChild(el("b",null,(list.length-back)+" correction"
    +(list.length-back===1?"":"s")+" already applied"));
  sum.appendChild(el("span","sub2", back
    ? back+" put back as the author wrote it"
    : "nothing needed from you — open this to check or undo any of them"));
  det.appendChild(sum);

  const inner = el("div","inner");
  inner.appendChild(el("p","why",
    "These are the corrections the agent makes the same way every time, with no "
    +"judgement involved, so it does not ask. If one of them is wrong for this "
    +"paper, put it back — the reviewed file and the letter to the author both "
    +"follow what you choose here."));
  list.forEach(a=>inner.appendChild(appliedCard(a)));
  det.appendChild(inner);
  host.appendChild(det);
}

function appliedCard(a){
  const item = el("div","item "+a.decision);

  const top = el("div","item-top");
  top.appendChild(el("h3",null,a.heading));
  if(a.line_label) top.appendChild(el("span","where",a.line_label));
  item.appendChild(top);
  item.appendChild(el("p","why", a.why));

  const ba = el("div","ba");
  const was = el("div","was"); was.appendChild(el("span","lab","As submitted"));
  was.appendChild(document.createTextNode(a.before));
  const now = el("div","now");
  now.appendChild(el("span","lab", a.decision==="reverted" ? "Was corrected to"
                                                           : "Corrected to"));
  now.appendChild(document.createTextNode(a.after || "(removed)"));
  ba.appendChild(was); ba.appendChild(now);
  item.appendChild(ba);

  const acts = el("div","acts");
  if(a.decision==="reverted"){
    acts.appendChild(el("div","decided reverted","↩ Put back as submitted"));
    const redo = el("button","plain","apply it again");
    redo.onclick = () => decide(a.id,"undecided");
    acts.appendChild(redo);
  } else {
    acts.appendChild(el("div","decided applied","✓ Applied"));
    const undo = el("button","no","Put back as submitted");
    undo.onclick = () => decide(a.id,"reverted");
    acts.appendChild(undo);
  }
  const id = el("span","checkid"); id.textContent = a.check_id;
  id.title = (a.rule||"") + (a.detail? "\n\n"+a.detail : "");
  acts.appendChild(el("span",null," ")); acts.appendChild(id);
  item.appendChild(acts);

  if(a.decision==="reverted"){
    const hint = el("p","why");
    hint.style.marginTop = "9px";
    hint.textContent = "The author's own wording stands. If they should be told "
      + "about it, add it under Your notes — the letter no longer mentions this.";
    item.appendChild(hint);
  }

  if(a.note){
    const n = el("div","hasnote");
    n.appendChild(el("b",null,"Your note: "));
    n.appendChild(document.createTextNode(a.note));
    item.appendChild(n);
  }
  item.appendChild(noteEditor(a.note, a.id, "edit"));
  return item;
}

function tabDecisions(host){
  const list = S.paper.decisions;
  appliedSection(host);
  if(!list.length){
    const e = el("div","empty");
    e.appendChild(el("b",null,"Nothing to decide"));
    e.appendChild(el("div",null,
      "Every correction the agent was confident about is already applied — they "
      +"are listed above, and any of them can be put back. Anything it was not "
      +"confident about is under Problems."));
    host.appendChild(e); return;
  }
  const undec = list.filter(d=>d.decision==="undecided").length;
  const g = el("div","group");
  g.appendChild(el("h2",null,"Accept or reject each change"));
  g.appendChild(el("p",null,
    "Each card is one piece of text. Accepting changes only that. Rejecting "
    +"leaves it exactly as the author wrote it. "
    +(undec? undec+" left to decide." : "All decided — you can change any of them.")));
  const hint = el("div","keyhint");
  hint.innerHTML = 'Keyboard: <kbd>a</kbd> accept · <kbd>r</kbd> reject '
    + '· <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>n</kbd> add a note';
  g.appendChild(hint);
  host.appendChild(g);

  /* Three authors written out in full are three separate changes, correctly —
     but an editor wants to answer them once.  Offer a bulk action for any
     kind of change that appears more than once and is still undecided. */
  const kinds = new Map();
  list.forEach(d=>{
    if(d.decision!=="undecided") return;
    if(!kinds.has(d.check_id)) kinds.set(d.check_id, {heading:d.heading, ids:[]});
    kinds.get(d.check_id).ids.push(d.id);
  });
  const repeated = [...kinds.values()].filter(k=>k.ids.length>1);
  if(repeated.length){
    const bulk = el("div","bulk");
    bulk.appendChild(el("span","lab","Same kind of change, more than once:"));
    repeated.forEach(k=>{
      const yes = el("button","yes","Accept all "+k.ids.length+" · "+k.heading.toLowerCase());
      yes.onclick = () => decideMany(k.ids,"accepted");
      const no = el("button","no","Keep all as submitted");
      no.onclick = () => decideMany(k.ids,"rejected");
      bulk.appendChild(yes); bulk.appendChild(no);
    });
    host.appendChild(bulk);
  }

  list.forEach((d,i)=>host.appendChild(decisionCard(d,i)));
}

function decisionCard(d, index){
  const item = el("div","item "+(d.decision!=="undecided"?d.decision:"")
    + (index===S.cursor?" focus":""));
  item.dataset.index = index;

  const top = el("div","item-top");
  top.appendChild(el("h3",null,d.heading));
  if(d.line) top.appendChild(el("span","where","line "+d.line));
  else if(d.kind==="reorder") top.appendChild(el("span","where","reference list"));
  item.appendChild(top);

  item.appendChild(el("p","why", d.why));

  const ba = el("div","ba");
  const was = el("div","was"); was.appendChild(el("span","lab","As submitted"));
  was.appendChild(document.createTextNode(d.before));
  const now = el("div","now"); now.appendChild(el("span","lab","Proposed"));
  now.appendChild(document.createTextNode(d.after || "(removed)"));
  ba.appendChild(was); ba.appendChild(now);
  item.appendChild(ba);

  const acts = el("div","acts");
  if(d.decision==="undecided"){
    const yes = el("button","yes","Accept");
    yes.onclick = () => decide(d.id,"accepted");
    const no = el("button","no","Keep as submitted");
    no.onclick = () => decide(d.id,"rejected");
    acts.appendChild(yes); acts.appendChild(no);
  } else {
    const badge = el("div","decided "+d.decision,
      d.decision==="accepted" ? "✓ Accepted" : "✗ Kept as submitted");
    acts.appendChild(badge);
    const undo = el("button","plain","change");
    undo.onclick = () => decide(d.id,"undecided");
    acts.appendChild(undo);
  }
  const why = el("span","checkid"); why.textContent = d.check_id;
  why.title = (d.rule||"") + (d.detail? "\n\n"+d.detail : "");
  acts.appendChild(el("span",null," ")); acts.appendChild(why);
  item.appendChild(acts);

  if(d.note){
    const n = el("div","hasnote");
    n.appendChild(el("b",null,"Your note: "));
    n.appendChild(document.createTextNode(d.note));
    item.appendChild(n);
  }
  item.appendChild(noteEditor(d.note, d.id, "edit"));
  return item;
}

function noteEditor(current, id, kind){
  const det = el("details","notebox");
  if(kind==="edit") det.dataset.noteFor = id;
  det.appendChild(el("summary",null, current? "Edit your note" : "Add a note"));
  const ta = el("textarea");
  ta.value = current || "";
  ta.placeholder = "Why you decided this, or anything a colleague should know.";
  det.appendChild(ta);
  const row = el("div","row"); row.style.marginTop="8px";
  const save = el("button","primary","Save note");
  save.onclick = async () => {
    try{
      if(kind==="edit") await api("/api/edit-note",{folder:S.folder,id,note:ta.value});
      else await api("/api/finding",{folder:S.folder,key:id,note:ta.value});
      toast("Note saved");
      await refresh();
    }catch(err){ toast(err.message, true); }
  };
  row.appendChild(save);
  det.appendChild(row);
  return det;
}

async function decide(id, decision){
  try{
    S.paper = await api("/api/decide",{folder:S.folder,id,decision});
    const list = S.paper.decisions;
    if(decision==="reverted"){
      S.showApplied = true;      /* keep the section the editor is working in open */
    }else if(decision!=="undecided"){
      const next = list.findIndex((d,i)=> i>S.cursor && d.decision==="undecided");
      S.cursor = next>=0 ? next : Math.min(S.cursor+1, Math.max(0,list.length-1));
    }
    renderPaper();
    focusCursor();
  }catch(err){ toast(err.message, true); }
}

async function decideMany(ids, decision){
  try{
    for(const id of ids){
      S.paper = await api("/api/decide",{folder:S.folder,id,decision});
    }
    const next = S.paper.decisions.findIndex(d=>d.decision==="undecided");
    S.cursor = next>=0 ? next : 0;
    renderPaper();
    toast(ids.length+(decision==="accepted"?" accepted":" kept as submitted"));
  }catch(err){ toast(err.message, true); }
}

function focusCursor(){
  const node = document.querySelector('.item[data-index="'+S.cursor+'"]');
  if(node) node.scrollIntoView({block:"center", behavior:"smooth"});
}

/* ------------------------------------------------------ tab: problems */
const OWNER_GROUPS = [
  ["author","Only the author can fix these",
   "The agent will not touch these, because fixing them needs information it "
   +"does not have. They go into the letter unless you tick them off."],
  ["editor","For you to check",
   "Judgement calls and things the agent could not verify."],
  ["tool","For the record",
   "What the agent did, and which checks could not run. Nothing to do here."],
];

function tabProblems(host){
  const all = S.paper.findings;
  if(!all.length){
    const e = el("div","empty");
    e.appendChild(el("b",null,"No problems found"));
    e.appendChild(el("div",null,"Nothing was flagged on this paper."));
    host.appendChild(e); return;
  }
  OWNER_GROUPS.forEach(([owner,title,blurb])=>{
    const items = all.filter(f=>f.owner===owner);
    if(!items.length) return;
    const g = el("div","group");
    g.appendChild(el("h2",null,title+" ("+items.length+")"));
    g.appendChild(el("p",null,blurb));
    items.forEach(f=>g.appendChild(findingCard(f)));
    host.appendChild(g);
  });
}

function findingCard(f){
  const item = el("div","item"+(f.handled?" handled":""));
  const top = el("div","item-top");
  top.appendChild(el("span","sevdot "+f.severity));
  top.appendChild(el("h3",null,f.heading));
  if(f.line) top.appendChild(el("span","where","line "+f.line));
  top.appendChild(el("span","pill count", f.severity_word));
  item.appendChild(top);

  item.appendChild(el("p","why", f.why));
  if(f.detail){
    const d = el("p","why"); d.style.color="var(--ink)";
    d.textContent = f.detail; item.appendChild(d);
  }
  if(f.original){
    const ba = el("div","ba"); ba.style.gridTemplateColumns="1fr";
    const was = el("div","was"); was.appendChild(el("span","lab","In the paper"));
    was.appendChild(document.createTextNode(f.original));
    ba.appendChild(was);
    if(f.suggested){
      const now = el("div","now"); now.appendChild(el("span","lab","Suggested"));
      now.appendChild(document.createTextNode(f.suggested)); ba.appendChild(now);
    }
    item.appendChild(ba);
  }

  const acts = el("div","acts");
  const lab = el("label","opt"); lab.style.margin="0";
  const cb = el("input"); cb.type="checkbox"; cb.checked=!!f.handled;
  cb.onchange = async () => {
    try{ await api("/api/finding",{folder:S.folder,key:f.key,handled:cb.checked});
      await refresh(); }catch(err){ toast(err.message,true); cb.checked=!cb.checked; }
  };
  lab.appendChild(cb);
  lab.appendChild(el("span",null, f.owner==="author"
    ? "I have handled this — leave it out of the letter"
    : "I have checked this"));
  acts.appendChild(lab);
  const cid = el("span","checkid"); cid.textContent = f.check_id; acts.appendChild(cid);
  item.appendChild(acts);

  if(f.note){
    const n = el("div","hasnote");
    n.appendChild(el("b",null,"Your note: "));
    n.appendChild(document.createTextNode(f.note));
    item.appendChild(n);
  }
  item.appendChild(noteEditor(f.note, f.key, "finding"));
  return item;
}

/* --------------------------------------------------- tab: your notes */
function tabMine(host){
  const g = el("div","group");
  g.appendChild(el("h2",null,"Something you found yourself"));
  g.appendChild(el("p",null,
    "The agent only checks what it knows how to check. Anything else you spot "
    +"goes here, and it will appear in the letter to the author."));

  const form = el("div","card pad");
  const f1 = el("div"); f1.style.marginBottom="11px";
  f1.appendChild(el("label","tiny muted","What did you find?"));
  const ta = el("textarea");
  ta.placeholder = "e.g. Figure 3 is unreadable at print size.";
  f1.appendChild(ta); form.appendChild(f1);

  const f2 = el("div"); f2.style.marginBottom="11px";
  f2.appendChild(el("label","tiny muted","Where? (optional)"));
  const where = el("input"); where.type="text";
  where.placeholder = "e.g. Figure 3, reference 7, page 2";
  f2.appendChild(where); form.appendChild(f2);

  const f3 = el("div","row"); f3.style.marginBottom="11px";
  const sev = el("select");
  [["must_fix","Must be fixed"],["worth_a_look","Worth a look"],
   ["note","Just a note"]].forEach(([v,l])=>{
    const o = el("option",null,l); o.value=v; sev.appendChild(o);
  });
  sev.value="worth_a_look";
  sev.style.padding="8px 10px"; sev.style.borderRadius="6px";
  sev.style.border="1px solid var(--rule)"; sev.style.background="var(--surface2)";
  f3.appendChild(sev);
  const forAuthorLab = el("label","opt"); forAuthorLab.style.margin="0";
  const forAuthor = el("input"); forAuthor.type="checkbox"; forAuthor.checked=true;
  forAuthorLab.appendChild(forAuthor);
  forAuthorLab.appendChild(el("span",null,"Tell the author"));
  f3.appendChild(forAuthorLab);
  form.appendChild(f3);

  const add = el("button","primary","Add this");
  add.onclick = async () => {
    if(!ta.value.trim()){ toast("Write what you found first", true); return; }
    try{
      const res = await api("/api/my-note",{folder:S.folder,text:ta.value,
        where:where.value, severity:sev.value, for_author:forAuthor.checked});
      S.paper = res.paper; toast("Added"); renderPaper();
    }catch(err){ toast(err.message,true); }
  };
  form.appendChild(add);
  g.appendChild(form);
  host.appendChild(g);

  if(S.paper.my_notes.length){
    const g2 = el("div","group");
    g2.appendChild(el("h2",null,"What you have found ("+S.paper.my_notes.length+")"));
    S.paper.my_notes.forEach(n=>{
      const item = el("div","item");
      const top = el("div","item-top");
      top.appendChild(el("h3",null,n.text));
      if(n.where) top.appendChild(el("span","where",n.where));
      top.appendChild(el("span","pill count",
        {must_fix:"Must be fixed",worth_a_look:"Worth a look",note:"Note"}[n.severity]||n.severity));
      item.appendChild(top);
      const meta = el("p","why", n.for_author
        ? "This will appear in the letter to the author."
        : "Kept for the record only — not sent to the author.");
      item.appendChild(meta);
      const acts = el("div","acts");
      const del = el("button","plain","remove");
      del.onclick = async () => {
        try{ S.paper = await api("/api/my-note/delete",{folder:S.folder,id:n.id});
          renderPaper(); }catch(err){ toast(err.message,true); }
      };
      acts.appendChild(del); item.appendChild(acts);
      g2.appendChild(item);
    });
    host.appendChild(g2);
  }

  if(S.paper.my_edits.length){
    const g3 = el("div","group");
    g3.appendChild(el("h2",null,"Lines you changed yourself ("+S.paper.my_edits.length+")"));
    g3.appendChild(el("p",null,"These are applied on top of the accepted corrections."));
    S.paper.my_edits.forEach(m=>{
      const item = el("div","item");
      const top = el("div","item-top");
      top.appendChild(el("h3",null,"Line "+m.line));
      item.appendChild(top);
      const ba = el("div","ba");
      const was = el("div","was"); was.appendChild(el("span","lab","Was"));
      was.appendChild(document.createTextNode(m.before));
      const now = el("div","now"); now.appendChild(el("span","lab","You wrote"));
      now.appendChild(document.createTextNode(m.after));
      ba.appendChild(was); ba.appendChild(now); item.appendChild(ba);
      if(m.note) { const n=el("div","hasnote");
        n.appendChild(el("b",null,"Your note: "));
        n.appendChild(document.createTextNode(m.note)); item.appendChild(n); }
      const acts = el("div","acts");
      const del = el("button","plain","undo this change");
      del.onclick = async () => {
        try{ S.paper = await api("/api/my-edit/delete",{folder:S.folder,id:m.id});
          toast("Undone"); renderPaper(); }catch(err){ toast(err.message,true); }
      };
      acts.appendChild(del); item.appendChild(acts);
      g3.appendChild(item);
    });
    host.appendChild(g3);
  }

  const g4 = el("div","group");
  g4.appendChild(el("h2",null,"A note about the whole paper"));
  g4.appendChild(el("p",null,"Added to the end of the letter to the author."));
  const box = el("div","card pad");
  const pta = el("textarea"); pta.value = S.paper.paper_note || "";
  pta.placeholder = "Anything you want to say about the paper as a whole.";
  box.appendChild(pta);
  const savep = el("button","primary","Save"); savep.style.marginTop="9px";
  savep.onclick = async () => {
    try{ await api("/api/paper-note",{folder:S.folder,note:pta.value});
      toast("Saved"); await refresh(); }catch(err){ toast(err.message,true); }
  };
  box.appendChild(savep);
  g4.appendChild(box);
  host.appendChild(g4);
}

/* -------------------------------------------------------- tab: source */
function tabSource(host){
  const src = S.paper.source;
  const g = el("div","group");
  g.appendChild(el("h2",null,"The paper as it stands"));
  g.appendChild(el("p",null, src.note || ""));
  host.appendChild(g);

  if(!src.editable) return;

  /* A LaTeX file opens on twenty lines of preamble that mean nothing to an
     editor.  These controls put them where the content is: the parts of the
     paper they know by name, the lines that changed, or a word they remember. */
  const tools = el("div","srctools");
  const jumps = [
    ["Title",      (l)=>/\\title\s*\{/.test(l.text)],
    ["Authors",    (l)=>/\\author\s*\{/.test(l.text)],
    ["Body",       (l)=>/\\begin\s*\{document\}|\\maketitle/.test(l.text)],
    ["References", (l)=>/\\begin\s*\{thebibliography\}|\\printbibliography|REFERENCES/.test(l.text)],
    ["First change", (l)=>l.changed || l.mine],
  ];
  jumps.forEach(([label,test])=>{
    const target = src.lines.find(test);
    if(!target) return;
    const b = el("button",null,label);
    b.onclick = () => scrollBoxTo(box, target.n, true);
    tools.appendChild(b);
  });

  const onlyChanged = el("button",null,"Only changed lines");
  onlyChanged.setAttribute("aria-pressed","false");
  onlyChanged.onclick = () => {
    const on = onlyChanged.getAttribute("aria-pressed")!=="true";
    onlyChanged.setAttribute("aria-pressed", on?"true":"false");
    box.querySelectorAll(".srcline").forEach(node=>{
      const keep = !on || node.classList.contains("changed") || node.classList.contains("mine");
      node.hidden = !keep;
    });
  };
  tools.appendChild(onlyChanged);

  const find = el("input"); find.type="text";
  find.placeholder = "Find a word in the paper…";
  find.oninput = () => {
    const q = find.value.trim().toLowerCase();
    let first = null;
    box.querySelectorAll(".srcline").forEach(node=>{
      const hit = q && node.querySelector(".tx").textContent.toLowerCase().includes(q);
      node.classList.toggle("hit", !!hit);
      if(hit && !first) first = node;
    });
    if(first) scrollBoxTo(box, first.dataset.n, false);
  };
  tools.appendChild(find);
  host.appendChild(tools);

  const box = el("div","src");
  src.lines.forEach(line=>{
    const row = el("div","srcline"
      + (line.mine?" mine":"") + (line.changed?" changed":""));
    row.dataset.n = line.n;
    row.appendChild(el("div","ln", String(line.n)));
    const tx = el("div","tx", line.text || " ");
    row.appendChild(tx);
    tx.onclick = () => openLineEditor(row, line);
    box.appendChild(row);
  });
  host.appendChild(box);

  const legend = el("p","tiny muted"); legend.style.marginTop="10px";
  legend.textContent = "Green line numbers were corrected by the agent. "
    + "Orange ones you changed yourself. Click any line to edit it.";
  host.appendChild(legend);

  // Land on the first change rather than on the preamble.
  const firstChange = src.lines.find(l=>l.changed||l.mine);
  if(firstChange){
    requestAnimationFrame(()=>scrollBoxTo(box, firstChange.n, false));
  }
}

/* Scroll the source pane itself.  scrollIntoView would also scroll the page,
   pushing the tabs and the paper's own heading off the top of the window —
   which is disorienting when you only asked to jump within one panel. */
function scrollBoxTo(box, lineNumber, smooth){
  const node = box.querySelector('.srcline[data-n="'+lineNumber+'"]');
  if(!node) return;
  const top = node.offsetTop - box.clientHeight/2 + node.offsetHeight/2;
  box.scrollTo({top: Math.max(0, top), behavior: smooth ? "smooth" : "auto"});
}

function openLineEditor(row, line){
  if(row.nextSibling && row.nextSibling.classList
     && row.nextSibling.classList.contains("srcedit")) return;
  const box = el("div","srcedit");
  const ta = el("textarea"); ta.value = line.text;
  ta.spellcheck = false;
  box.appendChild(ta);
  const nt = el("input"); nt.type="text";
  nt.placeholder = "Why (optional) — goes into your review record";
  nt.style.marginTop="8px";
  box.appendChild(nt);
  const acts = el("div","row"); acts.style.marginTop="9px";
  const save = el("button","primary","Save this line");
  save.onclick = async () => {
    if(ta.value === line.text){ toast("That line is unchanged", true); return; }
    try{
      const res = await api("/api/my-edit",{folder:S.folder,line:line.n,
        before:line.text, after:ta.value, note:nt.value});
      S.paper = res.paper; toast("Line saved"); renderPaper();
    }catch(err){ toast(err.message,true); }
  };
  const cancel = el("button",null,"Cancel");
  cancel.onclick = () => box.remove();
  acts.appendChild(save); acts.appendChild(cancel);
  box.appendChild(acts);
  row.after(box);
  ta.focus();
}

/* -------------------------------------------------------- tab: letter */
function tabLetter(host){
  const g = el("div","group letter");
  g.appendChild(el("h2",null,"Letter to the author"));
  g.appendChild(el("p",null,
    "Written for you from your decisions and notes. Edit it however you like — "
    +"it is saved with the paper and written to a file when you finish."));

  const box = el("div","card pad");
  const ta = el("textarea");
  ta.value = S.paper.letter_override || S.paper.letter;
  box.appendChild(ta);
  const acts = el("div","row"); acts.style.marginTop="10px";
  const save = el("button","primary","Save my wording");
  save.onclick = async () => {
    try{ await api("/api/letter",{folder:S.folder,letter:ta.value});
      toast("Letter saved"); await refresh(); }catch(err){ toast(err.message,true); }
  };
  const reset = el("button",null,"Start again from the automatic version");
  reset.onclick = async () => {
    try{ const r = await api("/api/letter",{folder:S.folder,reset:true});
      ta.value = r.letter; toast("Reset"); await refresh(); }
    catch(err){ toast(err.message,true); }
  };
  const copy = el("button",null,"Copy to clipboard");
  copy.onclick = async () => {
    try{ await navigator.clipboard.writeText(ta.value); toast("Copied"); }
    catch(_){ ta.select(); toast("Press Ctrl-C / ⌘-C to copy"); }
  };
  acts.appendChild(save); acts.appendChild(reset); acts.appendChild(copy);
  box.appendChild(acts);
  g.appendChild(box);
  host.appendChild(g);
}

/* --------------------------------------------------------- tab: files */
function tabFiles(host){
  const g = el("div","group");
  g.appendChild(el("h2",null,"Files for this paper"));
  g.appendChild(el("p",null,
    "Everything the agent wrote sits beside the author's own files, which are "
    +"never changed."));
  const list = el("div","filelist");
  if(!S.paper.files.length){
    g.appendChild(el("div","empty","Nothing written yet."));
  }
  S.paper.files.forEach(f=>{
    const row = el("div","filerow");
    const grow = el("div","grow");
    grow.appendChild(el("div",null,f.label));
    grow.appendChild(el("div","nm",f.name+"  ·  "+Math.max(1,Math.round(f.size/1024))+" kB"));
    row.appendChild(grow);
    const a = el("a"); a.href = "/file?folder="+encodeURIComponent(S.folder)
      +"&name="+encodeURIComponent(f.name);
    a.target = "_blank"; a.rel="noopener";
    const b = el("button",null,"Open"); a.appendChild(b);
    row.appendChild(a);
    list.appendChild(row);
  });
  g.appendChild(list);
  host.appendChild(g);

  if(S.paper.lookups && S.paper.lookups.length){
    const g2 = el("div","group");
    g2.appendChild(el("h2",null,"Which checks could run"));
    g2.appendChild(el("p",null,
      "Some checks need to look something up online. If a service could not be "
      +"reached, the agent says so instead of guessing."));
    S.paper.lookups.forEach(s=>{
      const row = el("div","filerow");
      const grow = el("div","grow");
      grow.appendChild(el("div",null,s.service));
      grow.appendChild(el("div","nm", s.reachable ? "answered"
        : (s.attempted ? "could not be reached" : "not needed")));
      row.appendChild(grow);
      row.appendChild(el("span","pill "+(s.reachable?"done":(s.attempted?"needs_author":"new")),
        s.reachable?"ok":(s.attempted?"offline":"—")));
      g2.appendChild(row);
    });
    host.appendChild(g2);
  }
}

/* ------------------------------------------------------------- finish */
$("#btnFinish").onclick = () => {
  const c = S.paper.counts;
  const box = $("#finishSummary");
  box.innerHTML = "";
  const ul = el("ul");
  const add = (t) => ul.appendChild(el("li",null,t));
  add(c.applied+" correction(s) applied automatically");
  add(c.accepted+" suggestion(s) accepted, "+c.rejected+" kept as submitted");
  if(c.to_decide) add(c.to_decide+" suggestion(s) still undecided — these will be "
    +"left as the author wrote them");
  if(c.must_fix) add(c.must_fix+" problem(s) for the author");
  if(c.my_notes) add(c.my_notes+" note(s) of your own");
  if(c.my_edits) add(c.my_edits+" line(s) you changed yourself");
  box.appendChild(ul);
  const radios = document.getElementsByName("closeStatus");
  radios[c.must_fix || c.my_notes ? 1 : 0].checked = true;
  $("#dlgFinish").showModal();
};

$("#dlgFinish").addEventListener("close", async (e) => {
  if($("#dlgFinish").returnValue !== "ok") return;
  const status = [...document.getElementsByName("closeStatus")]
    .find(r=>r.checked).value;
  try{
    const res = await api("/api/close",{folder:S.folder,status,editor:S.editor});
    const body = $("#doneBody"); body.innerHTML = "";
    $("#doneTitle").textContent = status==="done"
      ? "Finished — ready for the proceedings"
      : "Sent back to the author";
    body.appendChild(el("p",null,"Written next to the author's files:"));
    const ul = el("ul");
    res.written.forEach(n=>ul.appendChild(el("li",null,n)));
    body.appendChild(ul);
    body.appendChild(el("p","tiny muted",
      "You can reopen this paper at any time; nothing is locked."));
    await loadWorklist();
    $("#dlgDone").showModal();
  }catch(err){ toast(err.message, true); }
});

$("#btnBackToList").onclick = () => { $("#dlgDone").close(); backToList(); };
$("#btnGoNext").onclick = () => { $("#dlgDone").close(); goRelative(1, true); };

/* ---------------------------------------------------------- navigation */
function goRelative(delta, preferUnfinished){
  let i = S.papers.findIndex(x=>x.folder===S.folder);
  if(i<0) { backToList(); return; }
  if(preferUnfinished){
    for(let k=i+1;k<S.papers.length;k++){
      if(S.papers[k].status!=="done"){ openPaper(S.papers[k].folder); return; }
    }
    for(let k=0;k<i;k++){
      if(S.papers[k].status!=="done"){ openPaper(S.papers[k].folder); return; }
    }
    toast("Every paper is finished"); backToList(); return;
  }
  const j = i+delta;
  if(j<0 || j>=S.papers.length) return;
  openPaper(S.papers[j].folder);
}
$("#btnPrev").onclick = () => goRelative(-1);
$("#btnNext").onclick = () => goRelative(1);

document.addEventListener("keydown", (e)=>{
  if(e.metaKey||e.ctrlKey||e.altKey) return;
  const t = e.target;
  if(t && (t.tagName==="INPUT"||t.tagName==="TEXTAREA"||t.tagName==="SELECT")) return;
  if(document.querySelector("dialog[open]")) return;
  if(!S.paper || S.tab!=="decisions") return;
  const list = S.paper.decisions;
  if(!list.length) return;
  const cur = list[S.cursor];
  if(e.key==="a" && cur){ e.preventDefault(); decide(cur.id,"accepted"); }
  else if(e.key==="r" && cur){ e.preventDefault(); decide(cur.id,"rejected"); }
  else if(e.key==="j"||e.key==="ArrowDown"){ e.preventDefault();
    S.cursor=Math.min(S.cursor+1,list.length-1); renderPaper(); focusCursor(); }
  else if(e.key==="k"||e.key==="ArrowUp"){ e.preventDefault();
    S.cursor=Math.max(S.cursor-1,0); renderPaper(); focusCursor(); }
  else if(e.key==="n"){
    const node = document.querySelector('.item[data-index="'+S.cursor+'"] .notebox');
    if(node){ e.preventDefault(); node.open=true; node.querySelector("textarea").focus(); }
  }
});

/* -------------------------------------------------------------- boot */
async function refresh(){
  if(!S.folder) return;
  S.paper = await api("/api/paper?folder="+encodeURIComponent(S.folder));
  renderPaper();
}

async function loadWorklist(){
  const data = await api("/api/worklist");
  S.papers = data.papers;
}

const nameInput = $("#editorName");
let nameTimer = null;
nameInput.addEventListener("input", ()=>{
  clearTimeout(nameTimer);
  nameTimer = setTimeout(async ()=>{
    S.editor = nameInput.value.trim();
    try{ await api("/api/editor",{editor:S.editor}); }catch(_){}
  }, 500);
});

(async function boot(){
  try{
    const setup = await api("/api/setup");
    S.root = setup.root; S.editor = setup.editor || "";
    $("#rootName").textContent = setup.root;
    const llm = setup.llm || {};
    if(llm.enabled){
      const badge = $("#llmBadge");
      badge.textContent = "model: " + llm.model;
      badge.title = "A local model at " + llm.base_url + " helps with sentence case "
        + "and hides findings it judges to be false positives. It is never allowed "
        + "to supply a fact such as a DOI, year, volume or page range.";
      badge.hidden = false;
    }
    nameInput.value = S.editor;
    if((setup.jobs||[]).length){ S.job = setup.jobs[0]; pollJob(); }
    await loadWorklist();
    renderWorklist();
    if(!S.editor) nameInput.focus();
  }catch(err){
    document.body.innerHTML = '<main><div class="empty"><b>Could not start</b>'
      + '<div>'+err.message+'</div></div></main>';
  }
})();

})();
</script>
</body>
</html>
"""
