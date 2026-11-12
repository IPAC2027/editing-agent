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
.toplink{color:var(--accent);text-decoration:none;font-size:14px;margin-left:18px}
.toplink:hover{text-decoration:underline}
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
.pill.who-you{background:var(--good-soft);color:var(--good)}
.pill.who-other{background:var(--warn-soft);color:var(--warn)}
.pill.who-nobody{background:var(--surface3);color:var(--ink2)}
.pill.claim-mine{background:var(--good-soft);color:var(--good)}
.pill.claim-other{background:var(--warn-soft);color:var(--warn)}
td .pill + .pill{margin-left:4px}
.pill.ta-differs,.pill.ta-changed{background:var(--warn-soft);color:var(--warn)}
.pill.ta-waiting{background:var(--accent-soft);color:var(--accent)}
.pill.ta-due{background:var(--bad-soft);color:var(--bad)}
.pill.ta-applied{background:var(--accent-soft);color:var(--accent)}
.pill.ta-match,.pill.ta-done{background:var(--good-soft);color:var(--good)}
.pill.ta-unknown,.pill.ta-replied{background:var(--surface3);color:var(--ink2)}
.pill.st-good{background:var(--good-soft);color:var(--good)}
.pill.st-bad{background:var(--bad-soft);color:var(--bad)}
.pill.st-warn{background:var(--warn-soft);color:var(--warn)}
.pill.st-info{background:var(--accent-soft);color:var(--accent)}
.pill.st-none{background:var(--surface3);color:var(--ink2)}
.cell-sub{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
          overflow:hidden;font-size:.72rem;line-height:1.3;color:var(--ink2);margin-top:3px;
          max-width:150px}
.cell-sub.bad-text{color:var(--bad)}
.manage-wrap{overflow-x:auto}
.wl.manage td,.wl.manage th{padding-left:8px;padding-right:8px}
.wl.manage td{font-size:.86rem}
.wl.manage .ttl{max-width:200px}

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
.bad-text{color:var(--bad)}
.num.todo{color:var(--accent);font-weight:600}
table.wl tr.theirs td{color:var(--muted)}
.wl-indico{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:.82rem;
           color:var(--ink2);margin:0 0 14px}
.held{display:flex;gap:4px 12px;align-items:baseline;flex-wrap:wrap;margin:10px 0 14px;
      padding:10px 14px;border-radius:var(--radius);border-left:3px solid var(--rule);
      background:var(--surface2);font-size:.88rem}
.held.other{background:var(--warn-soft);border-left-color:var(--warn)}
.held.you{background:var(--good-soft);border-left-color:var(--good)}
.held a{color:var(--accent)}
table.cmp{width:100%;border-collapse:collapse;font-size:.88rem;margin:4px 0 16px}
table.cmp th{text-align:left;font-weight:600;color:var(--muted);width:9.5em;
             padding:5px 12px 5px 0;vertical-align:top}
table.cmp td{padding:5px 0;vertical-align:top}
ul.people{list-style:none;padding:0;margin:4px 0 14px}
ul.people li{padding:5px 0;font-size:.88rem;border-bottom:1px solid var(--rule2)}
ul.people li:last-child{border-bottom:0}
ul.people .tag{font-size:.72rem;font-weight:600;padding:1px 8px;border-radius:9px;margin-left:8px}
.tag.both{background:var(--good-soft);color:var(--good)}
.tag.to-indico{background:var(--accent-soft);color:var(--accent)}
.tag.to-paper{background:var(--warn-soft);color:var(--warn)}

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

/* wide pages: the paper's source and the reference list use the whole window */
main.wide{max-width:none;padding-left:18px;padding-right:18px}
.tabs .n.attn{color:var(--bad);font-weight:700}
.tabs .n.soft{font-family:var(--sans)}
select{padding:7px 10px;border-radius:6px;border:1px solid var(--rule);background:var(--surface2)}
.where.link{cursor:pointer;text-decoration:underline;color:var(--accent)}
.modbox{margin-top:10px;padding:10px 12px;background:var(--surface2);border:1px solid var(--rule);
        border-radius:6px}
.modbox textarea{font-family:var(--mono);font-size:.84rem}
.setaside{margin:0 0 16px;border-left:4px solid var(--accent)}
.setaside b{display:block;margin-bottom:4px}
.mailtext{font-family:var(--mono);font-size:.84rem;min-height:320px}
.names-cols{display:grid;gap:4px 28px}
@media(min-width:900px){.names-cols{grid-template-columns:1fr 1fr}}

/* the paper: source left, review or PDF right, like an online LaTeX editor */
.ol{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(340px,1fr);gap:14px;
    align-items:start}
@media(max-width:1000px){.ol{grid-template-columns:1fr}}
.ol-box{max-height:none;height:calc(100vh - 290px);min-height:380px}
.ol-side{background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius);
         display:flex;flex-direction:column;height:calc(100vh - 290px);min-height:380px}
.ol-side.solo{height:calc(100vh - 330px)}
.side-tabs{display:flex;border-bottom:1px solid var(--rule);flex:none}
.side-tabs button{flex:1;border:0;border-radius:0;background:none;padding:10px;
                  border-bottom:2px solid transparent;color:var(--ink2)}
.side-tabs button[aria-selected="true"]{border-bottom-color:var(--accent);color:var(--ink);
                                        font-weight:600}
.side-body{flex:1;overflow:auto;padding:12px 12px 4px;position:relative}
.side-body.pdf{padding:0;display:flex;flex-direction:column;overflow:hidden}
.side-body .item{padding:12px 13px}
.side-body .ba{grid-template-columns:1fr!important}
.side-body .group>h2{font-size:.95rem}
.pdfbar{display:flex;gap:8px;align-items:center;padding:8px 10px;
        border-bottom:1px solid var(--rule2);flex-wrap:wrap;flex:none}
.pdfbar select{flex:1;min-width:160px}
.pdfframe{flex:1;width:100%;border:0;background:#525659;min-height:300px}
.secsel{max-width:220px}
.legend{margin-top:8px}
.lgx{font-family:var(--mono);padding:0 3px;border-radius:3px}
.lgx del{background:var(--bad-soft);color:var(--bad)}
.lgx ins{background:var(--good-soft);color:var(--good);text-decoration:none}
.lgx.ok{background:var(--good-soft);box-shadow:inset 0 -2px 0 var(--good)}
.lgx.own{background:var(--warn-soft);box-shadow:inset 0 -2px 0 var(--warn)}
.sg{border-radius:3px;cursor:pointer}
.sg.undecided del{background:var(--bad-soft);color:var(--bad);text-decoration:line-through;
                  text-decoration-color:var(--bad)}
.sg.undecided ins{background:var(--good-soft);color:var(--good);text-decoration:none;
                  font-weight:650}
.sg.applied,.sg.accepted{background:var(--good-soft);box-shadow:inset 0 -2px 0 var(--good)}
.sg.rejected,.sg.reverted{text-decoration:underline dotted var(--muted);
                          text-underline-offset:3px}
.sg.own{background:var(--warn-soft);box-shadow:inset 0 -2px 0 var(--warn)}
.sg.ref{opacity:.82}
.sg.focus{outline:2px solid var(--accent);outline-offset:1px}
.sg:hover{filter:brightness(.96)}
.srcline.pending .ln{background:var(--accent-soft);color:var(--accent);font-weight:700}
.srcline .ln.flag{box-shadow:inset 3px 0 0 var(--bad)}
.srcline.flash .tx{animation:fl 1.4s ease-out}
@keyframes fl{from{background:var(--warn-soft)}to{background:transparent}}

/* the reference list: as written | what it becomes */
.reflegend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.82rem;color:var(--ink2);
           margin:-4px 0 4px}
.reflegend .lg{display:inline-flex;gap:7px;align-items:center}
.reflegend i{width:12px;height:12px;border-radius:3px;display:inline-block;background:var(--surface3)}
.reflegend .fixed i{background:var(--good)} .reflegend .problem i{background:var(--bad)}
.ref{background:var(--surface);border:1px solid var(--rule);border-left:5px solid var(--rule);
     border-radius:var(--radius);padding:11px 14px 12px;margin-bottom:10px}
.ref.fixed{border-left-color:var(--good)}
.ref.problem{border-left-color:var(--bad)}
.ref.own{border-left-color:var(--warn)}
.ref.kept{opacity:.72}
.ref.focus{box-shadow:0 0 0 2px var(--accent)}
.ref-top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin-bottom:8px}
.ref-top .num{font-family:var(--mono);font-weight:700}
.ref-top .kind{font-size:.8rem;color:var(--ink2)}
.ref-top .decided{font-size:.82rem}
.ref-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:860px){.ref-grid{grid-template-columns:1fr}}
.ref-grid .lab{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;
               color:var(--muted);font-weight:650;margin-bottom:3px}
.reftext{font-family:var(--mono);font-size:.81rem;line-height:1.5;white-space:pre-wrap;
         word-break:break-word;padding:8px 10px;border-radius:6px;background:var(--surface2);
         min-height:2.4em}
.ref.fixed .res .reftext{background:var(--good-soft)}
.ref.problem .res .reftext{background:var(--bad-soft)}
.ref.own .res .reftext{background:var(--warn-soft)}
.reftext .del{background:var(--bad-soft);color:var(--bad);text-decoration:line-through;
              border-radius:2px}
.reftext .ins{color:var(--good);font-weight:700;text-decoration:underline;
              text-decoration-color:var(--good);text-underline-offset:2px}
.ref.problem .reftext .ins{color:var(--bad);text-decoration-color:var(--bad)}
.reftext.muted-box{font-family:var(--sans);color:var(--ink2);font-size:.86rem}
.reftext .nearest{font-family:var(--mono);font-size:.8rem;margin-top:6px;color:var(--ink)}
.prints{font-size:.84rem;margin-top:6px;color:var(--ink2)}
.refmeta{font-size:.85rem;color:var(--ink2);margin-top:9px;display:grid;gap:3px}
.refmeta .missing{color:var(--bad);font-weight:600}
.refmeta .prob{display:block}
.refmeta .prob .sevdot{margin-right:4px;vertical-align:middle}
.refmeta label.inline{font-size:.78rem;color:var(--muted);margin-left:8px;cursor:pointer}
.ref .acts{margin-top:10px}

/* tags */
.tagrow{margin-bottom:10px}
.tagc{display:inline-block;font-family:var(--mono);font-size:.8rem;font-weight:650;
      padding:2px 9px;border-radius:12px;background:var(--surface3);color:var(--ink)}
.tagc.small{font-size:.72rem;padding:1px 7px}
.tagc.red{background:#f6d5da;color:#7d1426} .tagc.orange{background:#fbe0c8;color:#7a3d06}
.tagc.yellow{background:#f7edc0;color:#5f4b00} .tagc.violet{background:#e6dcf5;color:#4a2a7a}
.tagc.pink{background:#f8d9ea;color:#7a1f52} .tagc.green{background:#d3efdf;color:#13603a}
.tagc.brown{background:#eadfd3;color:#5a3d22}
.tagfams{display:grid;gap:6px}
.tagfam>summary{cursor:pointer;padding:6px 0;font-size:.9rem}
.tagopt{margin:4px 0 6px 6px}

.reprepare{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:18px}
.reprepare .grow{flex:1;min-width:260px}
ul.dropped{flex-basis:100%;margin:4px 0 0;padding-left:20px;font-size:.84rem}

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
  <a class="toplink" href="/references">Check a reference list</a>
  <div class="top-spacer"></div>
  <label class="who" id="whoName">Your name
    <input id="editorName" type="text" placeholder="e.g. A. Editor" autocomplete="name"
           list="indicoEditors">
    <datalist id="indicoEditors"></datalist>
  </label>
  <span class="who" id="whoIndico" hidden></span>
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
  <button id="btnQaFail" hidden>QA failed…</button>
  <button class="primary big" id="btnQaPass" hidden>QA passed</button>
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

<dialog id="dlgGiveUp"><form method="dialog"><div class="dlg-in">
  <h2 id="giveUpTitle">Give up this paper?</h2>
  <p>Your work so far goes to the chief editor's desk first. Then the paper is
  free for another editor to take, and the chief editor is told.</p>
  <label class="tiny muted" for="giveUpReason">Why? (optional; the chief editor
  sees it)</label>
  <textarea id="giveUpReason" rows="3" maxlength="500"
    placeholder="e.g. a conflict of interest, or no time this week"></textarea>
  <p class="tiny muted">You can still read your copy until you next start the desk.</p>
</div><div class="dlg-acts">
  <button value="cancel">Keep working</button>
  <button class="primary" value="ok">Give it up</button>
</div></form></dialog>

<dialog id="dlgQaFail"><form method="dialog"><div class="dlg-in">
  <h2 id="qaFailTitle">Fail the QA of this paper?</h2>
  <p>It goes back to the editors: any editor can take it to re-edit, and sees
  what you write here. After the re-edit it comes back for QA.</p>
  <label class="tiny muted" for="qaFailNote">What needs fixing? (required)</label>
  <textarea id="qaFailNote" rows="4" maxlength="2000" required
    placeholder="e.g. reference 7 still has no DOI; the Fig. 3 caption is not in sentence case"></textarea>
</div><div class="dlg-acts">
  <button value="cancel" formnovalidate>Not yet</button>
  <button class="primary" value="ok">Fail the QA</button>
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
  root:"", editor:"", papers:[], filter:"all", whose:"any", indico:null,
  folder:null, paper:null, tab:"names", cursor:0, job:null, refFilter:"all", side:"review",
  showApplied:false, givenUpSeen:new Set(), givenUpPrimed:false,
  chief:null, chiefPapers:null, chiefLoading:false, chiefError:"", chiefListOpen:null,
  sharing:null, pool:null, poolPapers:null, poolYou:null, poolError:"", poolShow:"edit", manageShow:"all",
  account:null, indicoSync:null,
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
  if(res.status===409 && data && data.claim && S.paper){
    // Another desk is editing this paper: show who, without a reload that
    // would throw away what the editor was typing.
    S.paper.claim = data.claim; showClaim();
  }
  if(!res.ok || (data && data.error)){
    throw new Error((data && data.error) || ("Request failed ("+res.status+")"));
  }
  return data;
}

/* ---------------------------------------------- who is editing a paper */
/* A paper is claimed by an editor's first change, so two desks on a shared
   folder never write over each other. Indico still decides whose paper it is. */
function claimNotice(c){
  if(S.pool && c) return poolClaimNotice(c);
  const box = el("div","held claim");
  box.id = "claimBox";
  if(!c){ box.hidden = true; return box; }
  if(c.state==="mine"){
    box.classList.add("you");
    box.appendChild(el("b",null,"You are editing this paper."));
    box.appendChild(el("span",null,"Other editors see it as taken until you "
      +"finish it or let it go."));
    const go = el("button","plain","Let it go");
    go.onclick = () => claimAction("release");
    box.appendChild(go);
  } else {
    box.classList.add("other");
    box.appendChild(el("b",null,c.who+" is editing this paper."));
    box.appendChild(el("span",null,"You can read everything, but your changes "
      +"are not saved while they have it."));
    if(c.since) box.appendChild(el("span","tiny muted","Since "+when(c.since)
      +(c.machine ? " · on "+c.machine : "")));
    const take = el("button","plain","Take it over");
    take.onclick = () => {
      if(!confirm("Take "+(S.paper.paper_id||"this paper")+" over from "+c.who+"?\n\n"
        +"Do this only if they have finished with it or agreed. Their saved work "
        +"stays; any change they make after this is refused.")) return;
      claimAction("take_over");
    };
    box.appendChild(take);
  }
  return box;
}

/* On a desk joined to the chief's, the claim that counts is on the chief's
   desk; this copy is either still the editor's or given back. */
function poolClaimNotice(c){
  const box = el("div","held claim"); box.id = "claimBox";
  const s = (S.paper && S.paper.sync) || {};
  const qa = s.mode==="qa", q = (S.paper && S.paper.qa) || {};
  if(c.state==="mine"){
    box.classList.add("you");
    box.appendChild(el("b",null, qa ? "You have this paper for QA on the chief editor's desk."
      : "You have this paper on the chief editor's desk."));
    if(qa) box.appendChild(el("span",null,"Edited by "+(S.paper.editor||"another editor")
      +". Check the editing, then pass or fail its QA with the buttons at the bottom."));
    else if(q.status==="failed") box.appendChild(el("span","bad-text","QA failed ("
      +(q.by||"an editor")+", "+when(q.at)+"): "+q.note+" Fix this, then finish the "
      +"paper again: it goes back for QA."));
    box.appendChild(el("span", s.error ? "bad-text" : null,
      s.error ? "Not sent yet: "+s.error
      : s.dirty ? "Your latest changes go to the chief editor's desk in a few seconds."
      : s.sent_at ? "Your work was sent to the chief editor's desk "+when(s.sent_at)+"."
      : "Your changes are sent to the chief editor's desk as you work."));
    const send = el("button","plain","Send now");
    send.onclick = () => claimAction("send");
    const give = el("button","plain", qa ? "Give up this QA" : "Give up this paper");
    give.onclick = () => {
      $("#giveUpTitle").textContent = "Give up "+(S.paper.paper_id||"this paper")+"?";
      $("#giveUpReason").value = "";
      $("#dlgGiveUp").showModal();
    };
    box.appendChild(send); box.appendChild(give);
  } else {
    box.classList.add("other");
    box.appendChild(el("b",null,"This copy is no longer yours on the chief editor's desk."));
    box.appendChild(el("span",null, s.error ||
      "You can read it. To change it, take the paper again: you get the chief's "
      +"latest version."));
    const take = el("button","plain","Take it again");
    take.onclick = () => claimAction("take");
    box.appendChild(take);
  }
  return box;
}

function showClaim(){
  const old = $("#claimBox");
  if(old) old.replaceWith(claimNotice(S.paper && S.paper.claim));
}

async function claimAction(action, extra){
  try{
    const data = await api("/api/claim",Object.assign({folder:S.folder, action}, extra||{}));
    if(data.pool_error){ toast(data.pool_error, true); }
    else if(action==="release" && S.pool){
      // Given up: back to the list, where it is free for the others now.
      toast("Given up — "+(data.paper_id||"the paper")+" is free for another editor");
      await loadWorklist(); backToList(); return;
    }
    S.paper = data;
    if(S.paper.screened) renderPaper(); else renderUnprepared();
    if(data.pool_error) return;
    toast(action==="send" ? "Sent to the chief editor's desk"
          : action==="release" ? "Let go — anyone can pick this paper up now"
          : "This paper is yours to edit now");
  }catch(err){ toast(err.message, true); }
}

$("#dlgGiveUp").addEventListener("close", () => {
  if($("#dlgGiveUp").returnValue !== "ok") return;
  claimAction("release", {reason: $("#giveUpReason").value.trim()});
});

/* ------------------------------------------------------------- worklist */
const FILTERS = [
  ["all","All papers"], ["todo","Still to do"], ["new","Not started"],
  ["in_review","In progress"], ["aside","Set aside"], ["done","Finished"],
];

/* Who holds each paper in Indico; shown only for a conference pulled from it. */
const WHOSE = [
  ["any","Everyone's"], ["you","Yours"], ["nobody","Not taken"],
  ["other","Taken by others"],
];

function matchesStatus(p, f=S.filter){
  if(f==="all") return true;
  // A paper set aside for the author is not "to do" until the wait is over.
  if(f==="todo") return p.status!=="done" && !(p.hold && !p.hold.over);
  if(f==="aside") return !!p.hold;
  return p.status===f;
}

function matchesWhose(p, w=S.whose){
  return w==="any" || (p.indico && p.indico.holder===w);
}

function matchesFilter(p){ return matchesStatus(p) && matchesWhose(p); }

const theirs = (p) => !!(p && p.indico && p.indico.holder==="other");

function when(iso){
  if(!iso) return "";
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString(undefined,{dateStyle:"medium",timeStyle:"short"});
}

/* The author/title verdict as a pill: a tick when the check is done. */
function verdictPill(ta, short){
  const passed = ta.status==="match" || ta.status==="done";
  const text = ta.status==="waiting" && ta.deadline && short
    ? "Waiting until "+when(ta.deadline) : ta.status_word;
  return el("span","pill ta-"+ta.status, (passed ? "✓ " : "")+text);
}

function heldNotice(ind){
  // An editor working from the chief's desk never deals with Indico: the
  // chief's desk keeps it in step.
  if(!ind || S.pool) return null;
  const box = el("div","held "+ind.holder);
  box.appendChild(el("b",null,
    ind.holder==="you" ? "This paper is yours in Indico."
    : ind.holder==="other" ? ind.editor+" has this paper in Indico."
    : "No editor has taken this paper in Indico yet."));
  if(S.pool && ind.holder!=="you"){
    // Joined to the chief's desk: taking the paper there reserved it among
    // the editors, but nothing is written to Indico.
    if(ind.holder==="nobody") box.firstChild.textContent =
      "Indico does not show an editor for this paper yet.";
    box.appendChild(el("span",null, ind.holder==="nobody"
      ? "Taking it here reserves it among the editors on the chief editor's desk; "
        +"the desk does not write to Indico. Assign yourself in Indico too (Open in "
        +"Indico ↗), or ask the chief editor to."
      : "The chief editor's desk gave it to you here. Check with the chief editor "
        +"which of you answers the author."));
  } else if(ind.holder==="other"){
    box.appendChild(el("span",null,"Your work here is not sent to Indico. Check "
      +"with them before you spend time on it."));
    if(!S.papers.some(x=>x.indico && x.indico.holder==="you"))
      box.appendChild(el("span",null,"If that is you, type your name at the top "
        +"exactly as Indico shows it."));
  } else if(ind.holder==="nobody"){
    box.appendChild(el("span",null,"Take it in Indico before you start, so nobody "
      +"else works on it too."));
  }
  box.appendChild(el("span","tiny muted",
    (ind.source==="indico" ? "Checked with Indico " : "As recorded when the papers were pulled, ")
    + when(ind.as_of)));
  if(ind.url){
    const a = el("a",null,"Open in Indico ↗");
    a.href = ind.url; a.target = "_blank"; a.rel = "noopener noreferrer";
    box.appendChild(a);
  }
  return box;
}

async function checkIndico(btn){
  btn.disabled = true; btn.textContent = "Checking Indico…";
  try{
    const res = await api("/api/indico-refresh", {});
    await loadWorklist();
    const n = (h) => S.papers.filter(p=>p.indico && p.indico.holder===h).length;
    toast("Checked Indico: "+n("you")+" yours, "+n("nobody")+" not taken yet"
      + (res.authors ? "; authors read for "+res.authors+" papers" : ""));
    if(res.authors_error) toast(res.authors_error, true);
  }catch(err){ toast(err.message, true); }
  renderWorklist();
}

/* ------------------------------------------------- the chief editor */
/* Only on a desk started with --manage: the conference as Indico lists it,
   what is already in the folder, and a button to download and prepare the
   rest. Indico is only read; the token never reaches this page. */
async function loadChiefPapers(){
  if(!S.chief || !S.chief.event || !S.chief.token) return;
  S.chiefLoading = true; S.chiefError = "";
  if(!S.folder) renderWorklist();
  try{ S.chiefPapers = await api("/api/chief/papers", {}); }
  catch(err){ S.chiefError = err.message; }
  S.chiefLoading = false;
  if(!S.folder) renderWorklist();
}

async function chooseEvent(value){
  try{
    S.chief = await api("/api/chief/event", {event:value});
    S.chiefPapers = null;
    await loadChiefPapers();
  }catch(err){ toast(err.message, true); }
}

async function downloadPapers(){
  try{
    const res = await api("/api/chief/download", {});
    S.job = res.job; renderWorklist(); pollJob();
  }catch(err){ toast(err.message, true); }
}

function chiefPanel(){
  const c = S.chief;
  const box = el("div","card pad"); box.style.marginBottom="18px";
  box.appendChild(el("h2",null,"The conference in Indico"));
  if(!c.event){
    box.appendChild(el("p","sub","Which Indico event is this conference? It is the "
      +"number in the event's address, e.g. 194 in "+c.url+"/event/194/."));
    const r = el("div","row");
    const input = el("input"); input.type="number"; input.min="1";
    input.placeholder="event number"; input.style.width="10em";
    const b = el("button","primary","Use this event");
    b.onclick = () => chooseEvent(input.value);
    input.addEventListener("keydown", e=>{ if(e.key==="Enter") chooseEvent(input.value); });
    r.appendChild(input); r.appendChild(b); box.appendChild(r);
    return box;
  }
  const where = el("p","sub");
  where.appendChild(document.createTextNode("Event "+c.event+" at "));
  const a = el("a",null,c.event_url); a.href=c.event_url; a.target="_blank"; a.rel="noopener";
  where.appendChild(a);
  where.appendChild(document.createTextNode("."));
  box.appendChild(where);
  box.appendChild(accountBox("The chief editor's desk reads the conference with your "
    +"Indico account and keeps Indico's editor assignments in step. Use a token with "
    +"the 'full:everything' scope (Indico → My profile → API tokens); "
    +"'read:everything' is enough to read only."));
  if(!c.token) return box;
  if(S.indicoSync) box.appendChild(syncBox());
  if(S.chiefLoading && !S.chiefPapers){
    const r = el("div","row"); r.appendChild(el("span","spin"));
    r.appendChild(el("span",null,"Reading the event's papers from Indico…"));
    box.appendChild(r); return box;
  }
  if(S.chiefError){
    box.appendChild(el("p","bad-text",S.chiefError));
    const retry = el("button",null,"Try again"); retry.onclick = loadChiefPapers;
    box.appendChild(retry); return box;
  }
  const info = S.chiefPapers;
  if(!info) return box;
  const sent = info.papers.filter(p=>p.submitted);
  const missing = sent.filter(p=>!p.here).length;
  box.appendChild(el("p",null, sent.length+" paper"+(sent.length===1?"":"s")
    +" submitted in Indico; "+info.here+" in this folder"
    +(missing ? ", "+missing+" not downloaded yet." : ".")
    +" Checked "+when(info.checked_at)+"."));
  const r = el("div","row");
  const busy = !!(S.job && !S.job.finished);
  const dl = el("button","primary", busy ? "Working — progress is shown above"
    : missing ? "Download and prepare "+missing+" new paper"+(missing===1?"":"s")
    : "Check Indico for new papers and prepare");
  dl.disabled = busy || !sent.length; dl.onclick = downloadPapers;
  const again = el("button",null,"Check Indico again");
  again.disabled = S.chiefLoading; again.onclick = loadChiefPapers;
  r.appendChild(dl); r.appendChild(again); box.appendChild(r);

  return box;
}

/* ---------------------------------------------- the Indico account */
/* Pasted once into the page; the desk checks it with Indico and keeps it on
   this computer. The page is only ever told whose account it is. */
function accountBox(why){
  const a = S.account || {};
  const box = el("div","held "+(a.connected ? "you" : "")); box.id = "accountBox";
  if(a.connected){
    box.appendChild(el("b",null,"Indico account: "+(a.name || "from the terminal")));
    box.appendChild(el("span","muted", a.source==="environment"
      ? "Using INDICO_TOKEN from the window that started the desk. Paste a token "
        +"here to keep it with the desk instead."
      : "Kept on this computer only."));
    if(a.source==="page"){
      const off = el("button","plain","Disconnect");
      off.onclick = async () => {
        if(!confirm("Disconnect the Indico account from this desk? The token is deleted "
          +"from this computer.")) return;
        try{ S.account = await api("/api/indico-account",{disconnect:true}); reboot(); }
        catch(err){ toast(err.message, true); }
      };
      box.appendChild(off);
    }
    if(a.source!=="environment") return box;
  } else {
    box.appendChild(el("b",null,"Connect your Indico account"));
  }
  box.appendChild(el("span",null,why));
  const r = el("div","row"); r.style.width="100%";
  const input = el("input"); input.type="password"; input.autocomplete="off";
  input.placeholder="paste your Indico API token"; input.style.flex="1 1 280px";
  const go = el("button","primary","Connect");
  const connect = async () => {
    go.disabled = true; go.textContent = "Checking with Indico…";
    try{
      S.account = await api("/api/indico-account",{token:input.value});
      input.value = "";
      toast("Connected as "+(S.account.name||"your Indico account"));
      reboot();
    }catch(err){ toast(err.message, true); go.disabled = false; go.textContent = "Connect"; }
  };
  go.onclick = connect;
  input.addEventListener("keydown", e=>{ if(e.key==="Enter") connect(); });
  r.appendChild(input); r.appendChild(go); box.appendChild(r);
  return box;
}

/* The chief's desk assigning editors in Indico as they take papers. */
function syncBox(){
  const y = S.indicoSync;
  const box = el("div","held "+(y.enabled ? "you" : "")); box.style.display="block";
  const lab = el("label"); lab.style.fontWeight="600";
  const cb = el("input"); cb.type="checkbox"; cb.checked = y.enabled;
  cb.onchange = async () => {
    if(cb.checked && !confirm("Let this desk assign and unassign editors in Indico for "
      +"event "+S.chief.event+"?\n\nWhen an editor takes a paper here they are "
      +"assigned to it in Indico; giving it back unfinished unassigns them. Papers "
      +"Indico gives to someone else are never changed. Papers already being edited "
      +"here are assigned now too. Indico sends no email for this; each change is "
      +"written to the event's log.")){ cb.checked = false; return; }
    try{ S.indicoSync = await api("/api/chief/indico-sync",{enabled:cb.checked}); }
    catch(err){ toast(err.message, true); }
    renderWorklist();
  };
  lab.appendChild(cb);
  lab.appendChild(document.createTextNode(" Keep Indico's editor assignments in step "
    +"with who is working on each paper"));
  box.appendChild(lab);
  const facts = [];
  facts.push(y.enabled ? "On: editors are assigned in Indico when they take a paper."
    : "Off: Indico is only read.");
  facts.push(y.last_read ? "Indico read "+when(y.last_read)+" (every 2 minutes)"
    : "Indico is read every 2 minutes");
  if(y.waiting.length) facts.push("waiting to send: "+y.waiting.join(", "));
  box.appendChild(el("div","muted",facts.join(" · ")));
  if(y.read_error) box.appendChild(el("div","bad-text","Could not read Indico: "+y.read_error));
  y.problems.forEach(pr=>box.appendChild(el("div","bad-text",pr.paper+": "+pr.message)));
  return box;
}

/* ------------------------------------- the chief's door for editors */
/* On the chief's desk: where editors' desks connect, who has connected, and
   who is editing which paper next to who has it in Indico. */
/* On the chief's page: papers editors gave up, until the chief dismisses them. */
function givenUpBox(){
  const list = (S.sharing && S.sharing.given_up) || [];
  const box = el("div","card pad"); box.style.marginBottom="18px";
  box.style.borderLeft = "3px solid var(--warn)";
  box.appendChild(el("h2",null, list.length===1 ? "An editor gave up a paper"
    : list.length+" papers given up by editors"));
  box.appendChild(el("p","sub","Each is free again: any editor can take it from "
    +"their desk. Their work so far is in it."));
  const ul = el("ul","people");
  list.forEach(n=>{
    const li = el("li");
    const row = S.papers.find(p=>p.paper_id===n.paper);
    li.appendChild(el("b",null,n.paper));
    li.appendChild(document.createTextNode(
      (row && row.title ? " — "+row.title : "")
      +(n.mode==="qa" ? " · its QA given up by " : " · given up by ")+(n.who||"an editor")
      +" "+when(n.at)));
    if(n.reason) li.appendChild(el("div","muted","“"+n.reason+"”"));
    const ok = el("button","plain","Dismiss");
    ok.style.marginLeft="8px";
    ok.onclick = () => dismissGivenUp(n.id);
    li.appendChild(ok);
    ul.appendChild(li);
  });
  box.appendChild(ul);
  if(list.length>1){
    const all = el("button","plain","Dismiss all");
    all.onclick = () => dismissGivenUp("all");
    box.appendChild(all);
  }
  return box;
}

async function dismissGivenUp(id){
  try{
    const d = await api("/api/chief/given-up",{dismiss:id});
    S.sharing.given_up = d.given_up;
    renderWorklist();
  }catch(err){ toast(err.message, true); }
}

/* A toast for each paper given up since the page last looked. */
function noteGivenUp(){
  const list = (S.sharing && S.sharing.given_up) || [];
  const fresh = list.filter(n=>!S.givenUpSeen.has(n.id));
  list.forEach(n=>S.givenUpSeen.add(n.id));
  if(S.givenUpPrimed && fresh.length){
    toast(fresh.map(n=>(n.who||"An editor")+" gave up "+(n.mode==="qa" ? "the QA of " : "")
      +n.paper).join(" · "), true);
  }
  S.givenUpPrimed = true;
}

function sharingPanel(){
  const sh = S.sharing;
  const box = el("div","card pad"); box.style.marginBottom="18px";
  box.appendChild(el("h2",null,"Editors on the network"));
  box.appendChild(el("p","sub","Each editor works on their own computer: their desk "
    +"takes a paper from this one, works on a copy, and sends the work back as they "
    +"go. They never open this folder."));
  const t = el("table","cmp");
  const fact = (k, v) => { const tr = el("tr"); tr.appendChild(el("th",null,k));
    tr.appendChild(el("td","mono",v)); t.appendChild(tr); };
  if(sh.local_only){
    box.appendChild(el("p","muted","This computer only: the desk was started with "
      +"--no-share, so only your own editing desk can take papers. Start it without "
      +"--no-share to let editors on the network join."));
  } else {
    fact("Address", sh.addresses.join("   or   "));
    fact("Join code", sh.code);
    const host = (sh.addresses[0]||"").replace(/^https?:\/\//,"");
    fact("Editors start", "uv run python main.py --join "+host+" --code "+sh.code);
    box.appendChild(t);
  }
  if(sh.editors.length){
    const ul = el("ul","people");
    sh.editors.forEach(e=>{
      const li = el("li",null,(e.name||"(no name yet)")
        +(e.machine ? " · on "+e.machine : "")+" · last seen "+when(e.last_seen));
      if(!e.indico_id) li.appendChild(el("span","tiny muted"," · no Indico account yet"));
      else if(e.editing_manager) li.appendChild(el("span","tiny muted",
        " · editing manager in Indico"));
      else if(e.paper_editor===false)
        li.appendChild(el("span","bad-text"," · neither a paper editor nor an editing "
          +"manager in Indico: add them to the paper editing team there, or they "
          +"cannot take papers"));
      ul.appendChild(li);
    });
    box.appendChild(el("b",null,"Desks that have connected"));
    box.appendChild(ul);
  } else {
    box.appendChild(el("p","muted","No editor's desk has connected yet."));
  }
  return box;
}

/* On an editor's desk joined to the chief's: the chief's papers, to take. */
async function loadPoolPapers(){
  try{
    const res = await api("/api/pool/papers",{});
    S.poolPapers = res.papers; S.poolYou = res.you || null; S.poolError = "";
  }
  catch(err){ S.poolError = err.message; }
  if(!S.folder) renderWorklist();
}

async function takePaper(paper, btn, mode){
  if(!(S.account && S.account.connected)){
    toast("Paste your Indico token first: the chief editor's desk knows you by "
      +"your Indico account", true);
    const token = document.querySelector("#accountBox input");
    if(token) token.focus();
    return;
  }
  btn.disabled = true; btn.textContent = "Taking…";
  try{
    const res = await api("/api/pool/take",{paper, mode: mode||"edit"});
    await loadWorklist();
    loadPoolPapers();
    toast(mode==="qa" ? paper+" is yours to QA: a copy is on this computer"
      : paper+" is yours: a copy is on this computer");
    openPaper(res.folder);
  }catch(err){
    toast(err.message, true); btn.disabled = false;
    btn.textContent = mode==="qa" ? "Take for QA" : "Take to edit";
    loadPoolPapers();
  }
}

const POOL_SHOW = [["edit","To edit"],["qa","To QA"],["yours","Assigned to you"],
                   ["all","All"]];

function poolPanel(){
  const box = el("div","card pad"); box.style.marginBottom="18px";
  box.appendChild(el("h2",null,"Papers on the chief editor's desk"));
  const where = S.pool.url + (S.pool.pool ? " · "+S.pool.pool : "")
    + (S.pool.event ? " · Indico event "+S.pool.event : "");
  box.appendChild(el("p","sub","Take a paper to work on it here. Your work is sent to "
    +"the chief editor's desk as you go; finishing a paper, or giving it back, frees "
    +"it for the others. ("+where+")"));
  if(!(S.account && S.account.connected))
    box.appendChild(accountBox("Paste your Indico token here once to take papers: the "
      +"chief editor's desk knows you by your Indico account, and assigns you the "
      +"papers you take there. Make one in Indico → My profile → API tokens, scope "
      +"'read:everything'. You never need to open Indico yourself."));
  else box.appendChild(accountBox(""));
  const notEditor = S.poolYou && S.poolYou.why ? S.poolYou.why : "";
  if(notEditor && S.account && S.account.connected){
    box.appendChild(el("p","bad-text",notEditor));
    if(S.poolYou.indico_said)
      box.appendChild(el("p","tiny muted","Asking Indico whether you are an editing "
        +"manager: "+S.poolYou.indico_said));
  } else if(S.poolYou && S.poolYou.role){
    box.appendChild(el("p","tiny muted","In Indico you are "
      +(S.poolYou.role==="editing manager" ? "an editing manager" : "a paper editor")
      +" of this conference."));
  }
  if(S.poolError){
    box.appendChild(el("p","bad-text",S.poolError));
    const retry = el("button",null,"Try again"); retry.onclick = loadPoolPapers;
    box.appendChild(retry);
    if(!S.poolPapers) return box;
  }
  if(!S.poolPapers){
    const r = el("div","row"); r.appendChild(el("span","spin"));
    r.appendChild(el("span",null,"Asking the chief editor's desk…"));
    box.appendChild(r); return box;
  }
  const rows = S.poolPapers;
  const keep = {
    edit: p=>!p.claim && p.take==="edit" && !p.blocked,
    qa: p=>!p.claim && p.take==="qa",
    yours: p=>p.indico && p.indico.yours,
    all: p=>true,
  };
  const filters = el("div","filters");
  POOL_SHOW.forEach(([key,label])=>{
    const n = rows.filter(keep[key]).length;
    const b = el("button",null,label+" ("+n+")");
    b.setAttribute("aria-pressed", S.poolShow===key ? "true":"false");
    b.onclick = () => { S.poolShow = key; renderWorklist(); };
    filters.appendChild(b);
  });
  box.appendChild(filters);
  const shown = rows.filter(keep[S.poolShow] || keep.all);
  if(!shown.length){
    box.appendChild(el("p","muted", S.poolShow==="edit" ? "No paper is waiting to be "
      +"edited right now." : S.poolShow==="qa" ? "No edited paper is waiting for its QA."
      : "No papers here.")); return box;
  }
  const t = el("table","wl"); const hr = el("tr");
  ["Paper","Title","Assigned to","Edited","QA","Being worked on by",""]
    .forEach(h=>hr.appendChild(el("th",null,h)));
  const th = el("thead"); th.appendChild(hr); t.appendChild(th);
  const tb = el("tbody");
  shown.forEach(p=>{
    const tr = el("tr");
    tr.appendChild(el("td","pid",p.paper_id));
    const tt = el("td"); const d = el("div","ttl",p.title||p.paper); d.title = p.title||"";
    tt.appendChild(d); tr.appendChild(tt);
    const ind = el("td");
    if(p.indico) ind.appendChild(el("span","pill who-"+(p.indico.yours ? "you"
      : p.indico.editor ? "other" : "nobody"),
      p.indico.yours ? "You" : p.indico.editor || "Nobody yet"));
    tr.appendChild(ind);
    tr.appendChild(stageCell(editedState(p)));
    tr.appendChild(stageCell(qaState(p)));
    tr.appendChild(el("td",null, !p.claim
      ? (p.blocked && p.indico ? p.indico.editor+" (in Indico)" : "—")
      : (p.claim.mine ? "You" : p.claim.who)+(p.claim.mode==="qa" ? " (QA)" : "")));
    const act = el("td"); act.style.textAlign="right"; act.style.whiteSpace="nowrap";
    if(p.claim && p.claim.mine && p.here){
      const b = el("button",null,"Open"); b.onclick = () => openPaper(p.folder);
      act.appendChild(b);
    } else if(!p.claim && p.take==="edit" && p.blocked){
      const s2 = el("span","tiny muted","taken in Indico");
      s2.title = p.blocked+" Ask the chief editor if it should be yours.";
      act.appendChild(s2);
    } else if(!p.claim && p.take && notEditor){
      act.appendChild(el("span","tiny muted","not an editor in Indico"));
    } else if(!p.claim && p.take){
      const b = el("button","primary", p.take==="qa" ? "Take for QA"
        : p.stage==="to_reedit" ? "Take to re-edit" : "Take to edit");
      b.onclick = () => takePaper(p.paper, b, p.take);
      act.appendChild(b);
    } else if(!p.prepared){
      act.appendChild(el("span","tiny muted","not prepared yet"));
    } else if(p.stage==="to_qa" && p.edited_by_you){
      act.appendChild(el("span","tiny muted","you edited it: another editor does its QA"));
    } else if(p.stage==="qa_passed"){
      act.appendChild(el("span","tiny muted","done"));
    }
    tr.appendChild(act);
    tb.appendChild(tr);
  });
  t.appendChild(tb); box.appendChild(t);
  return box;
}

/* --------------------------------------------- where a paper is in the work */
/* Shared by the editors' list and the managing page. Each returns
   [word, kind, detail] for stageCell; kind picks the pill's colour. */
function stageCell(state){
  const [word, kind, detail] = state;
  const td = el("td");
  td.appendChild(el("span","pill st-"+(kind||"none"), word));
  if(detail){ const d = el("span","cell-sub",detail); d.title = detail; td.appendChild(d); }
  return td;
}

function editedState(p){
  const by = p.editor ? "by "+p.editor : "";
  const claim = p.claim;
  if(p.stage==="unprepared" || p.prepared===false || p.screened===false)
    return ["—","none",""];
  if(claim && claim.mode!=="qa")
    return ["Editing","info",(claim.mine||claim.state==="mine") ? "you" : claim.who];
  if(p.stage==="to_reedit") return ["Re-edit needed","bad",by];
  if(p.stage==="waiting_author") return ["Sent back to author","warn",by];
  if(p.stage==="to_qa" || p.stage==="qa_passed") return ["Edited","good",by];
  if(p.status==="in_review") return ["Started, not finished","info",by];
  return ["Not yet","none",""];
}

function qaState(p){
  const qa = p.qa || {};
  const claim = p.claim;
  const by = (qa.by ? qa.by : "")+(qa.at ? (qa.by ? ", " : "")+when(qa.at) : "");
  if(claim && claim.mode==="qa")
    return ["In QA","info",(claim.mine||claim.state==="mine") ? "you" : claim.who];
  if(p.stage==="qa_passed") return ["Passed","good",by];
  if(p.stage==="to_reedit" || qa.status==="failed")
    return ["Failed","bad",(qa.by ? qa.by+": " : "")+(qa.note||"")];
  if(p.stage==="to_qa") return ["Not yet","warn", qa.rounds ? "after a re-edit" : ""];
  return ["—","none",""];
}

function duration(seconds){
  seconds = Math.max(0, seconds|0);
  const m = Math.floor(seconds/60), s = seconds%60;
  return m ? m+" min "+String(s).padStart(2,"0")+" s" : s+" s";
}

/* What a running job is doing, how far it has got, and how long it has taken:
   a grey button alone told the editor nothing. */
function jobBox(job){
  const box = el("div","card pad job"); box.style.marginBottom="18px";
  const r = el("div","row");
  r.appendChild(el("span","spin"));
  const line = el("b",null,(job.step ? job.step+" · " : "")+job.label
    + (job.total ? " — "+job.done+" of "+job.total : ""));
  r.appendChild(line);
  box.appendChild(r);
  if(job.total){
    const bar = el("div","bar"); const fill = el("span");
    fill.style.width = Math.round(job.done/job.total*100)+"%";
    bar.appendChild(fill); bar.style.margin="10px 0 6px"; box.appendChild(bar);
  }
  const facts = [];
  if(job.current) facts.push("now: "+job.current
    + (job.current_elapsed!=null ? " ("+duration(job.current_elapsed)+")" : ""));
  if(job.elapsed!=null) facts.push("running for "+duration(job.elapsed));
  if(facts.length) box.appendChild(el("div","muted",facts.join(" · ")));
  if(/^Preparing/.test(job.label)){
    box.appendChild(el("p","sub","Preparing reads each paper once: it checks the "
      +"formatting and looks every reference up online (Crossref, DataCite, arXiv), "
      +"which takes most of the time — a paper with many references can take a few "
      +"minutes. You can open papers that are already prepared meanwhile."));
  }
  if(job.errors && job.errors.length){
    const d = el("details"); d.style.marginTop="8px";
    d.appendChild(el("summary","bad-text",job.errors.length+" problem"
      +(job.errors.length===1?"":"s")+" so far"));
    job.errors.slice(0,20).forEach(e=>d.appendChild(el("div","muted",e)));
    box.appendChild(d);
  }
  return box;
}

function renderWorklist(){
  const host = $("#viewWorklist");
  host.innerHTML = "";
  $("#viewPaper").hidden = true; host.hidden = false;
  $("#footbar").hidden = true;

  const done  = S.papers.filter(p=>S.chief ? p.stage==="qa_passed" : p.status==="done").length;
  const total = S.papers.length;
  const unprepared = S.papers.filter(p=>!p.screened).length;

  const head = el("div","wl-head");
  const left = el("div"); left.style.flex="1 1 300px";
  left.appendChild(el("h1", null, S.chief ? "Managing the conference" : "Papers to review"));
  left.appendChild(el("p","sub",
    S.chief ? (total ? "Download and prepare the papers, and follow the editors' work. "
                       +"Papers are not edited here: Edit papers opens your own "
                       +"editing desk, which takes papers like any editor's."
                     : "Nothing downloaded yet: the papers come from Indico, below.")
    : S.pool ? (total ? "The papers you have taken, copied to this computer. Your work "
                      +"is sent to the chief editor's desk as you go."
                    : "You have not taken a paper yet: take one from the chief "
                      +"editor's list below.")
    : total ? "Open a paper to work through it. Your place is kept as you go."
          : S.chief ? "Nothing downloaded yet: the papers come from Indico, below."
          : "No submissions found in this folder."));
  head.appendChild(left);

  if(total){
    const prog = el("div","wl-progress");
    const lab = el("div","lab");
    lab.appendChild(el("span",null,done+" of "+total
      +(S.chief ? " done (edited and QA passed)" : " finished")));
    lab.appendChild(el("span","muted", Math.round(done/total*100)+"%"));
    prog.appendChild(lab);
    const bar = el("div","bar"); const fill = el("span");
    fill.style.width = (total? done/total*100 : 0)+"%"; bar.appendChild(fill);
    prog.appendChild(bar);
    head.appendChild(prog);
  }
  if(S.chief) head.appendChild(editingButton());
  host.appendChild(head);
  if(S.job && !S.job.finished) host.appendChild(jobBox(S.job));
  if(S.sharing && (S.sharing.given_up||[]).length) host.appendChild(givenUpBox());
  if(S.chief) host.appendChild(chiefPanel());
  if(S.sharing) host.appendChild(sharingPanel());
  if(S.pool) host.appendChild(poolPanel());

  if(unprepared && !S.pool){
    const box = el("div","card pad"); box.style.marginBottom="18px";
    box.appendChild(el("h2",null, unprepared+" paper"+(unprepared===1?"":"s")+" not prepared yet"));
    box.appendChild(el("p","sub",
      "The agent needs to read each paper once before "
      +(S.chief ? "an editor can take it" : "you can review it")+". This "
      +"takes a few seconds per paper and only happens once."));
    const b = el("button","primary","Prepare "+(unprepared===1?"it":"them")+" now");
    b.onclick = () => prepare({all:true});
    box.appendChild(b);
    host.appendChild(box);
  }
  if(!S.pool && total-unprepared>0 && !(S.job && !S.job.finished)) host.appendChild(reprepareBox());

  if(S.chief){ renderManaging(host); return; }
  if(!total) return;

  const filters = el("div","filters");
  FILTERS.forEach(([key,label])=>{
    const n = S.papers.filter(p=>matchesWhose(p) && matchesStatus(p,key)).length;
    const b = el("button",null,label+(n?" ("+n+")":""));
    b.setAttribute("aria-pressed", S.filter===key ? "true":"false");
    b.onclick = () => { S.filter=key; renderWorklist(); };
    filters.appendChild(b);
  });
  host.appendChild(filters);

  if(S.indico && !S.pool){
    const whose = el("div","filters");
    WHOSE.forEach(([key,label])=>{
      const n = S.papers.filter(p=>matchesStatus(p) && matchesWhose(p,key)).length;
      const b = el("button",null,label+(n?" ("+n+")":""));
      b.setAttribute("aria-pressed", S.whose===key ? "true":"false");
      b.onclick = () => { S.whose=key; renderWorklist(); };
      whose.appendChild(b);
    });
    host.appendChild(whose);

    const info = el("div","wl-indico");
    info.appendChild(el("span",null,"Who has each paper in Indico: "
      + (S.indico.source==="indico" ? "checked "+when(S.indico.as_of)
         : "as recorded when the papers were pulled, "+when(S.indico.as_of))));
    const chk = el("button",null,S.pool ? "Update from the chief's desk" : "Check Indico now");
    chk.onclick = () => checkIndico(chk);
    info.appendChild(chk);
    if(!S.editor){
      info.appendChild(el("span","muted", S.pool
        ? "Connect your Indico account above to see which papers are yours."
        : "Type your name at the top, as Indico shows it, to see which papers are yours."));
    } else if(!S.papers.some(p=>p.indico && p.indico.holder==="you")){
      info.appendChild(el("span","muted","No paper here is held by “"+S.editor
        +"” in Indico. If you have taken some, type your name exactly as Indico shows it."));
    }
    host.appendChild(info);
  }

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
  const numeric = ["To decide","Must fix","Your notes"];
  ["Paper","Title","Status"].concat(S.indico && !S.pool ? ["In Indico"] : [],
                                     S.indico ? ["Title & authors"] : [],
                                     numeric, [""])
    .forEach(h=>{ const th=el("th",null,h);
      if(numeric.includes(h)) th.style.textAlign="right"; htr.appendChild(th); });
  thead.appendChild(htr); table.appendChild(thead);

  const tbody = el("tbody");
  rows.forEach(p=>{
    const tr = el("tr", theirs(p) ? "theirs" : null);
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
    if(p.hold){
      const hp = el("span","pill "+(p.hold.over?"st-bad":"st-warn"),
        p.hold.over ? "Set aside: the wait is over"
          : "Set aside"+(p.hold.until ? " until "+when(p.hold.until) : ""));
      hp.title = p.hold.reason || "Waiting for the author";
      c3.appendChild(document.createTextNode(" ")); c3.appendChild(hp);
    }
    if(p.claim){
      const mine = p.claim.state==="mine";
      const cp = el("span","pill claim-"+(mine?"mine":"other"),
        mine ? "You're editing" : "Editing: "+p.claim.who);
      if(p.claim.since) cp.title = "Since "+when(p.claim.since)
        +(p.claim.machine ? " on "+p.claim.machine : "")
        +(p.received_at ? " · last sent here "+when(p.received_at) : "");
      if(!S.pool) c3.appendChild(cp);
    }
    if(p.sync){
      const s = p.sync;
      const sp = el("span","pill "+(!s.held ? "claim-other" : s.error ? "claim-other"
        : "claim-mine"),
        !s.held ? "Given back" : s.error ? "Not sent yet" : s.dirty ? "Sending…"
        : s.sent_at ? "Sent" : "Yours");
      sp.title = s.error || (s.sent_at ? "Sent to the chief editor's desk "+when(s.sent_at) : "");
      c3.appendChild(sp);
      if(s.mode==="qa" && s.held) c3.appendChild(el("span","pill st-info","QA"));
    }
    tr.appendChild(c3);

    if(S.indico && !S.pool){
      const c4 = el("td"); const ind = p.indico;
      if(ind){
        const pill = el("span","pill who-"+ind.holder,
          ind.holder==="you" ? "You" : ind.holder==="other" ? ind.editor : "Not taken");
        if(ind.state) pill.title = "Indico: "+ind.state.replace(/_/g," ");
        c4.appendChild(pill);
      }
      tr.appendChild(c4);
    }
    if(S.indico){
      const c5 = el("td"); const ta = p.title_authors;
      if(ta && p.screened) c5.appendChild(verdictPill(ta, true));
      tr.appendChild(c5);
    }

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

/* -------------------------------------------- the chief's managing page */
/* The chief's desk manages: Indico, the download, preparing papers, the
   editors' door. Papers are edited on an editor's desk; the chief's own is
   started from here and takes papers through the door like anyone's. */
function editingButton(){
  const wrap = el("div","row"); wrap.style.alignSelf="flex-start";
  const b = el("button","primary big","Edit papers");
  b.title = "Open your own editing desk: an editor's desk joined to this one";
  b.onclick = () => openEditingDesk(b);
  wrap.appendChild(b);
  if(S.editing && S.editing.url){
    const a = el("a",null,"Your editing desk ↗"); a.href = S.editing.url;
    a.target = "_blank"; a.rel = "noopener"; wrap.appendChild(a);
  }
  return wrap;
}

async function openEditingDesk(btn){
  // Open the tab now, while the click still counts, and send it on later:
  // a tab opened after waiting for the desk would be blocked as a pop-up.
  const tab = window.open("", "_blank");
  btn.disabled = true; btn.textContent = "Opening your editing desk…";
  try{
    const res = await api("/api/chief/editing-desk", {});
    S.editing = {open:true, url:res.url};
    if(tab){ tab.opener = null; tab.location = res.url; }
    else toast("Your editing desk is open at "+res.url);
  }catch(err){
    if(tab) tab.close();
    toast(err.message, true);
  }
  renderWorklist();
}

/* Every paper: those Indico has (from the conference box) and those in the
   folder, side by side. */
function managedRows(){
  const local = new Map(S.papers.map(p=>[p.name, p]));
  const indico = (S.chiefPapers && S.chiefPapers.papers) || [];
  const rows = indico.filter(ip=>ip.submitted || local.has(ip.name))
    .map(ip=>({name:ip.name, code:ip.code, ip, lp:local.get(ip.name) || null}));
  const seen = new Set(rows.map(r=>r.name));
  S.papers.forEach(lp=>{ if(!seen.has(lp.name))
    rows.push({name:lp.name, code:lp.paper_id, ip:null, lp}); });
  return rows;
}

const MANAGE_SHOW = [
  ["all","All"], ["to_edit","Free to edit"], ["working","Taken"],
  ["to_qa","To QA"], ["qa_failed","QA failed"], ["qa_passed","Done"],
  ["indico_newer","Newer in Indico"], ["not_here","Not downloaded"],
];
const MANAGE_KEEP = {
  all: r=>true,
  to_edit: r=>r.lp && !r.lp.claim && !(r.lp.holder && r.lp.holder.taken)
    && ["to_edit","waiting_author","to_reedit"].includes(r.lp.stage),
  working: r=>r.lp && (r.lp.claim || (r.lp.holder && r.lp.holder.taken)),
  to_qa: r=>r.lp && !r.lp.claim && r.lp.stage==="to_qa",
  qa_failed: r=>r.lp && r.lp.stage==="to_reedit",
  qa_passed: r=>r.lp && r.lp.stage==="qa_passed",
  indico_newer: r=>r.ip && (r.ip.newer==="indico" || r.ip.newer==="both"),
  not_here: r=>!r.lp,
};

function localState(r){
  if(!r.lp) return ["Not downloaded","none",""];
  const rev = r.ip && r.ip.local_revisions ? "revision "+r.ip.local_revisions : "";
  if(!r.lp.screened) return ["Not prepared","warn",rev];
  if(r.lp.outdated) return ["Downloaded","good",(rev ? rev+" · " : "")+"prepared by an older version"];
  return ["Downloaded","good",rev];
}

function newerState(r){
  const ip = r.ip;
  if(!r.lp) return ["—","none",""];
  if(!ip) return ["—","none", S.chiefPapers ? "not in Indico's list" : "Indico not read yet"];
  const counts = "revisions: "+ip.revisions+" in Indico, "+ip.local_revisions+" here";
  return {
    same: ["Same","good",""],
    local: ["Local","info","edited here; not in Indico"],
    indico: ["Indico","bad",counts],
    both: ["Both changed","bad",counts+"; edited here too"],
  }[ip.newer] || ["—","none",""];
}

function titleAuthorState(r){
  const ta = r.lp && r.lp.title_authors;
  if(!r.lp || !r.lp.screened || !ta) return ["—","none",""];
  const until = ta.deadline ? "until "+when(ta.deadline) : "";
  return {
    match: ["OK","good",""],
    differs: ["Email to send","warn","the paper and Indico differ"],
    waiting: ["Email sent","info",until],
    due: ["Email sent","warn","no reply: ready to apply"],
    replied: ["Email sent","info","the author replied"],
    changed: ["Email sent","warn","changed since the email"],
    applied: ["Fixed","info","Indico still to update"],
    done: ["Fixed","good",""],
    unknown: ["Not checked","none",""],
  }[ta.status] || [ta.status_word || "—","none",""];
}

/* Who holds a paper, for the chief: taken on this desk, taken in Indico, or
   both. Either way nobody else can take it to edit it until it is freed. */
function takenState(r){
  const h = r.lp && r.lp.holder;
  const state = (r.ip && r.ip.state) || (r.lp && r.lp.indico && r.lp.indico.state) || "";
  const st = state ? state.replace(/_/g," ") : "";
  const sep = (a, b) => [a, b].filter(Boolean).join(" · ");
  if(!h){
    const editor = (r.ip && r.ip.editor) || (r.lp && r.lp.indico && r.lp.indico.editor) || "";
    return editor ? [editor,"warn",sep("in Indico", st)] : ["Free","none",st];
  }
  const sync = S.indicoSync && S.indicoSync.enabled;
  const qa = h.here && h.here.mode==="qa";
  if(h.taken==="here") return [h.here.who+(qa ? " (QA)" : ""), "info",
    qa ? "QA, on this desk" : sep("on this desk", sync ? "assigning in Indico…"
      : "not in Indico: the sync is off")];
  if(h.taken==="both") return [h.here.who, "info", sep("on this desk and in Indico", st)];
  if(h.taken==="indico") return [h.indico, "warn", sep("took it in Indico, not on this desk", st)];
  if(h.taken==="conflict") return [h.here.who, "bad", "on this desk; Indico gives it to "+h.indico];
  if(h.freed) return ["Free", "warn", "freed here; Indico still shows "+h.freed+": unassign them there"];
  return ["Free", "none", st];
}

function renderManaging(host){
  const rows = managedRows();
  if(!rows.length) return;
  const inIndico = rows.filter(r=>r.lp && r.lp.holder && r.lp.holder.taken==="indico");
  const freed = rows.filter(r=>r.lp && r.lp.holder && r.lp.holder.freed);
  if(inIndico.length) host.appendChild(el("p","tiny muted", inIndico.length+" paper"
    +(inIndico.length===1 ? " was" : "s were")+" taken in Indico by an editor who is not "
    +"working on it here: nobody else can take "+(inIndico.length===1 ? "it" : "them")
    +" on the desk until you free "+(inIndico.length===1 ? "it" : "them")+"."));
  if(freed.length) host.appendChild(el("p","bad-text", freed.length+" paper"
    +(freed.length===1 ? " you freed is" : "s you freed are")+" still assigned in Indico ("
    +freed.map(r=>(r.lp.paper_id)+": "+r.lp.holder.freed).join(", ")+"). The desk lets other "
    +"editors take "+(freed.length===1 ? "it" : "them")+"; unassign "+(freed.length===1 ? "the editor" : "them")
    +" in Indico too."));
  const filters = el("div","filters");
  MANAGE_SHOW.forEach(([key,label])=>{
    const n = rows.filter(MANAGE_KEEP[key]).length;
    if(!n && key!=="all" && key!==S.manageShow) return;
    const b = el("button",null,label+" ("+n+")");
    b.setAttribute("aria-pressed", S.manageShow===key ? "true":"false");
    b.onclick = () => { S.manageShow=key; renderWorklist(); };
    filters.appendChild(b);
  });
  host.appendChild(filters);
  // Being edited here, and Indico shows nobody on it.
  const untold = rows.filter(r=>r.lp && r.lp.claim && r.lp.claim.mode!=="qa"
    && !((r.ip && r.ip.editor) || (r.lp.indico && r.lp.indico.editor)));
  if(untold.length && S.indicoSync && !S.indicoSync.enabled){
    host.appendChild(el("p","bad-text", untold.length+" paper"
      +(untold.length===1 ? " is" : "s are")+" being edited here, but Indico is not "
      +"told: switch on “Keep Indico's editor assignments in step” above to assign "
      +(untold.length===1 ? "its editor" : "their editors")+" in Indico."));
  }
  if(S.indico){
    const info = el("div","wl-indico");
    info.appendChild(el("span",null,"Who has each paper in Indico: "
      + (S.indico.source==="indico" ? "checked "+when(S.indico.as_of)
         : "as recorded when the papers were pulled, "+when(S.indico.as_of))));
    const chk = el("button",null,"Check Indico now");
    chk.onclick = () => checkIndico(chk);
    info.appendChild(chk);
    host.appendChild(info);
  }
  const shown = rows.filter(MANAGE_KEEP[S.manageShow] || MANAGE_KEEP.all);
  if(!shown.length){
    const e = el("div","empty");
    e.appendChild(el("b",null,"Nothing here"));
    e.appendChild(el("div",null,"No papers match this filter."));
    host.appendChild(e); return;
  }
  const table = el("table","wl manage");
  const htr = el("tr");
  ["Paper","Title","Local copy","Newer","Author/title","Edited","QA","Taken by",""]
    .forEach(h=>htr.appendChild(el("th",null,h)));
  const thead = el("thead"); thead.appendChild(htr); table.appendChild(thead);
  const tbody = el("tbody");
  shown.forEach(r=>{
    const lp = r.lp;
    const tr = el("tr");
    const c1 = el("td"); c1.appendChild(el("div","pid", (lp && lp.paper_id) || r.code));
    if(lp && lp.kind==="word") c1.appendChild(el("div","tiny muted","Word"));
    tr.appendChild(c1);
    const title = (lp && lp.title) || (r.ip && r.ip.title) || r.name;
    const c2 = el("td"); const t = el("div","ttl", title); t.title = title;
    c2.appendChild(t); tr.appendChild(c2);
    tr.appendChild(stageCell(localState(r)));
    tr.appendChild(stageCell(newerState(r)));
    tr.appendChild(stageCell(titleAuthorState(r)));
    tr.appendChild(stageCell(lp ? editedState(lp) : ["—","none",""]));
    tr.appendChild(stageCell(lp ? qaState(lp) : ["—","none",""]));
    tr.appendChild(stageCell(takenState(r)));
    const act = el("td"); act.style.textAlign="right"; act.style.whiteSpace="nowrap";
    if(lp && !lp.screened){
      const b = el("button",null,"Prepare"); b.onclick = () => prepare({folder:lp.folder});
      act.appendChild(b);
    }
    if(lp && (lp.holder ? lp.holder.can_free : lp.claim)){
      const b = el("button",null,"Free");
      b.title = "Free this paper so any editor can take it: whoever has it, here or in Indico";
      b.onclick = () => freePaper(lp, b);
      act.appendChild(b);
    }
    tr.appendChild(act);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  const wrap = el("div","manage-wrap"); wrap.appendChild(table);
  host.appendChild(wrap);
  const newer = rows.filter(MANAGE_KEEP.indico_newer).length;
  if(newer) host.appendChild(el("p","tiny bad-text", newer+" paper"+(newer===1?" has":"s have")
    +" a newer revision in Indico than the copy here. The desk does not download new "
    +"revisions of papers it already has yet: their copies here are the older ones."));
  host.appendChild(el("p","tiny muted",
    (S.chiefPapers ? "" : "Connect the Indico account above to see the papers not "
      +"downloaded yet and which copy is newer. ")
    +(S.indicoSync && S.indicoSync.enabled
      ? "Editors are assigned in Indico as they take papers to edit them."
      : "Indico is only read: switch on “Keep Indico's editor assignments in step” "
        +"above to assign editors there automatically.")));
}

async function freePaper(p, btn){
  const h = p.holder || {taken: p.claim ? "here" : "", here: p.claim, indico: ""};
  const sync = S.indicoSync && S.indicoSync.enabled;
  const finished = p.status==="done" || p.status==="needs_author";
  const lines = [];
  if(h.taken==="indico"){
    lines.push("Free "+p.paper_id+" from "+h.indico+", who took it in Indico?", "");
    lines.push(sync && !finished ? "They are unassigned in Indico, and any editor can then take it here."
      : "Any editor can then take it here. Indico still shows "+h.indico
        +(sync ? " (a finished paper stays assigned)" : " (the desk does not write to Indico while "
          +"the sync is off)")+": unassign them there too if they should not have it.");
  } else {
    const who = h.here && h.here.who ? h.here.who : "its editor";
    lines.push("Free "+p.paper_id+" from "+who+"?", "",
      "Any editor can then take it. Work their desk has not sent yet stays on their "
      +"computer, and their desk tells them the paper is no longer theirs.");
    if(h.indico) lines.push("", (h.taken==="conflict" ? "Indico gives it to "+h.indico+"; " : "")
      +(sync && !finished ? "they are unassigned in Indico too."
        : "Indico still shows "+h.indico+": unassign them there too."));
    else if(sync && !finished) lines.push("They are unassigned in Indico too.");
  }
  if(!confirm(lines.join("\n"))) return;
  btn.disabled = true;
  try{
    const res = await api("/api/chief/free", {folder:p.folder});
    const f = res.freed || {};
    toast(p.paper_id+" is free for any editor to take"
      +(f.indico==="still assigned" ? ": unassign "+f.indico_editor+" in Indico too"
        : f.indico==="unassigning" ? "; unassigning "+f.indico_editor+" in Indico" : ""),
      f.indico==="still assigned");
    await loadWorklist();
  }catch(err){ toast(err.message, true); }
  renderWorklist();
}

/* -------------------------------------------------------------- prepare */
/* After the way papers are prepared has improved: read every downloaded paper
   again. The editors' decisions follow their edits; papers an editor is working
   on, and finished ones, are left alone. */
function reprepareBox(){
  const prepared = S.papers.filter(p=>p.screened);
  const old = prepared.filter(p=>p.outdated).length;
  const box = el("div","card pad reprepare");
  const text = el("div","grow");
  text.appendChild(el("b",null, old
    ? old+" of "+prepared.length+" prepared paper"+(prepared.length===1?"":"s")
      +" "+(old===1?"was":"were")+" prepared by an older version of the agent"
    : "Every paper was prepared by the current version of the agent"));
  text.appendChild(el("div","tiny muted",
    "Preparing again reads each paper with the agent as it is now. Decisions, notes and "
    +"hand edits are kept; papers an editor is working on, and finished papers, are left alone."));
  box.appendChild(text);
  const b = el("button", old ? "primary" : null, "Prepare all again…");
  b.onclick = () => reprepareAll(b);
  box.appendChild(b);
  return box;
}

async function reprepareAll(btn){
  btn.disabled = true;
  try{
    const plan = await api("/api/prepare", {all:true, force:true, dry_run:true});
    btn.disabled = false;
    if(!plan.would_prepare){
      toast("Nothing to prepare again: "+[plan.held ? plan.held+" being edited" : "",
        plan.finished ? plan.finished+" finished" : ""].filter(Boolean).join(", ")
        +" — those are left alone", true);
      return;
    }
    const lines = [
      "Prepare "+plan.would_prepare+" paper"+(plan.would_prepare===1?"":"s")+" again with the "
        +"current version of the agent?"
        +(plan.outdated ? " ("+plan.outdated+" of them were prepared by an older version.)" : ""),
      "",
      "• Decisions, notes and hand edits are kept. A decision whose suggestion has changed "
        +"or gone is dropped, and that paper says which.",
    ];
    if(plan.held) lines.push("• Left alone: "+plan.held+" paper"+(plan.held===1?"":"s")
      +" an editor is working on.");
    if(plan.finished) lines.push("• Left alone: "+plan.finished+" finished paper"
      +(plan.finished===1?"":"s")+" (their reviewed files and letters are written).");
    lines.push("", "This takes a few seconds per paper"
      +(plan.would_prepare>20 ? " — several minutes in all" : "")+". You can keep working meanwhile.");
    if(!confirm(lines.join("\n"))) return;
    await prepare({all:true, force:true});
  }catch(err){ btn.disabled = false; toast(err.message, true); }
}

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
        toast(job.errors.length+" problem(s): "+job.errors[0], true);
      } else if(job.notes && job.notes.length){
        toast("Prepared. "+job.notes.length+" paper(s) to look at: "+job.notes[0]
          +(job.notes.length>1 ? " (and "+(job.notes.length-1)+" more)" : ""), true);
      } else { toast("Ready to review"); }
      await loadWorklist();
      if(S.chief) loadChiefPapers();
      if(S.folder) await openPaper(S.folder); else renderWorklist();
      return;
    }
    if(!S.folder) renderWorklist();
    setTimeout(pollJob, 900);
  }catch(err){ S.job=null; toast(err.message, true); }
}

/* ---------------------------------------------------------------- paper */
/* Four tabs, in the order an editor works: the title and authors against
   Indico (and the email if they differ), the reference list, the body of the
   paper, and the editor's own panel (tags, the letter, notes, files). */
const TABS = [
  ["names","Title & authors"],
  ["refs","References"],
  ["body","The paper"],
  ["panel","Editor's panel"],
];

async function openPaper(folder){
  try{
    const data = await api("/api/paper?folder="+encodeURIComponent(folder));
    if(S.folder!==folder){ S.tab = "names"; S.cursor = 0; S.refFilter = "all";
                           S.side = "review"; S.pdfName = ""; S.keepWorking = false; }
    S.folder = folder; S.paper = data;
    if(!data.screened){ renderUnprepared(); return; }
    renderPaper();
    window.scrollTo({top:0});
  }catch(err){ toast(err.message, true); }
}

function renderUnprepared(){
  const host = $("#viewPaper");
  $("#viewWorklist").hidden = true; host.hidden = false; $("#footbar").hidden = true;
  document.querySelector("main").classList.remove("wide");
  host.innerHTML = "";
  const back = el("button","crumb","← All papers"); back.onclick = backToList;
  host.appendChild(back);
  host.appendChild(el("h1",null,S.paper.paper_id));
  const held = heldNotice(S.paper.indico);
  if(held) host.appendChild(held);
  host.appendChild(claimNotice(S.paper.claim));
  const e = el("div","empty");
  e.appendChild(el("b",null,"Not prepared yet"));
  e.appendChild(el("div",null,S.paper.message||""));
  const b = el("button","primary big","Prepare this paper");
  b.style.marginTop="16px";
  b.onclick = () => prepare({folder:S.folder});
  e.appendChild(b);
  host.appendChild(e);
}

/* Which changes and findings belong to which tab (the server sorts them). */
const bodyDecisions  = () => S.paper.decisions.filter(d=>d.scope==="body");
const titleDecisions = () => S.paper.decisions.filter(d=>d.scope==="title");

function tabBadge(key){
  const p = S.paper, t = p.title_authors, R = p.references || {counts:{}};
  if(key==="names"){
    const n = titleDecisions().filter(d=>d.decision==="undecided").length;
    if(t && ["differs","due","changed"].includes(t.status)) return ["!", "attn"];
    return n ? [String(n), ""] : null;
  }
  if(key==="refs"){
    const c = R.counts || {};
    if(c.undecided) return [String(c.undecided), ""];
    return c.problem ? [String(c.problem), "attn"] : null;
  }
  if(key==="body"){
    const n = bodyDecisions().filter(d=>d.decision==="undecided").length;
    return n ? [String(n), ""] : null;
  }
  if(key==="panel"){
    const n = (p.tags && p.tags.chosen || []).length;
    return n ? [n+" tag"+(n===1?"":"s"), "soft"] : null;
  }
  return null;
}

function renderPaper(){
  const p = S.paper;
  const host = $("#viewPaper");
  $("#viewWorklist").hidden = true; host.hidden = false; $("#footbar").hidden = false;
  if(!TABS.some(([key])=>key===S.tab)) S.tab = "names";
  document.querySelector("main").classList.toggle("wide", S.tab==="body" || S.tab==="refs");
  host.innerHTML = "";

  const back = el("button","crumb","← All papers"); back.onclick = backToList;
  host.appendChild(back);

  const head = el("div","paper-head");
  const grow = el("div","grow");
  const h1 = el("h1"); h1.appendChild(el("span","pid",p.paper_id));
  grow.appendChild(h1);
  grow.appendChild(el("p","sub", p.title || p.name));
  head.appendChild(grow);
  const right = el("div","row");
  right.appendChild(el("span","pill "+p.status, p.status_word));
  if(p.title_authors) right.appendChild(verdictPill(p.title_authors, false));
  if(p.build) right.appendChild(el("span","pill count", p.build));
  head.appendChild(right);
  host.appendChild(head);
  const held = heldNotice(p.indico);
  if(held) host.appendChild(held);
  host.appendChild(claimNotice(p.claim));
  const hold = holdBanner(p);
  if(hold) host.appendChild(hold);
  const again = repreparedNotice(p);
  if(again) host.appendChild(again);
  const names = p.title_authors;
  if(names && names.status==="due" && S.tab!=="names"){
    const box = el("div","held other");
    box.appendChild(el("b",null,"No reply about the title and authors."));
    box.appendChild(el("span",null,"The author had until "+names.deadline_text+"."));
    const go = el("button","plain","Review and apply");
    go.onclick = () => { S.tab="names"; renderPaper(); };
    box.appendChild(go);
    host.appendChild(box);
  }

  const tabs = el("div","tabs");
  TABS.forEach(([key,label], i)=>{
    const b = el("button",null,(i+1)+". "+label);
    const badge = tabBadge(key);
    if(badge) b.appendChild(el("span","n "+badge[1], badge[0]));
    b.setAttribute("aria-selected", S.tab===key?"true":"false");
    b.onclick = () => { S.tab=key; S.cursor=0; renderPaper(); window.scrollTo({top:0}); };
    tabs.appendChild(b);
  });
  host.appendChild(tabs);

  const body = el("div");
  host.appendChild(body);
  ({names:tabNames, refs:tabRefs, body:tabBody, panel:tabPanel}[S.tab])(body);

  updateFoot();
  // Where you are, in the address: a reload comes back to this paper and tab.
  try{ history.replaceState(null, "", "#"+new URLSearchParams({paper:S.folder, tab:S.tab})); }
  catch(_){}
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
  const qa = !!(S.pool && p.sync && p.sync.mode==="qa");
  $("#btnFinish").hidden = qa;
  $("#btnQaPass").hidden = $("#btnQaFail").hidden = !(qa && p.sync.held);
}

function backToList(){
  S.folder=null; S.paper=null;
  try{ history.replaceState(null, "", location.pathname); }catch(_){}
  document.querySelector("main").classList.remove("wide");
  loadWorklist().then(renderWorklist);
}

/* Prepared again, some earlier decisions may have had no edit left to land on. */
function repreparedNotice(p){
  const r = p.reprepared;
  if(!r || !(r.dropped||[]).length || S.seenReprepared===p.folder+r.at) return null;
  const box = el("div","held other");
  box.appendChild(el("b",null,"Prepared again "+when(r.at)+"."));
  box.appendChild(el("span",null, r.dropped.length+" earlier decision"
    +(r.dropped.length===1?" no longer applies":"s no longer apply")
    +", because the suggestion changed or is gone"
    +(r.kept ? "; "+r.kept+" kept" : "")+". Look at the new suggestions where these were:"));
  const ul = el("ul","dropped");
  r.dropped.forEach(d=>{
    const li = el("li");
    li.appendChild(el("span","checkid",d.check_id||""));
    li.appendChild(document.createTextNode(" "+(d.decision ? d.decision+": " : "")
      +"“"+(d.before||"").slice(0,90)+"” → “"+(d.after||"").slice(0,90)+"”"
      +(d.note ? " — your note: "+d.note : "")));
    ul.appendChild(li);
  });
  box.appendChild(ul);
  const ok = el("button","plain","Got it");
  ok.onclick = () => { S.seenReprepared = p.folder+r.at; renderPaper(); };
  box.appendChild(ok);
  return box;
}

/* ------------------------------------------- setting a paper aside */
/* While the author has the email, the paper stays this editor's but leaves
   their list of papers to work on now. */
function holdBanner(p){
  const h = p.hold;
  if(!h) return null;
  const box = el("div","held "+(h.over?"other":"you"));
  box.appendChild(el("b",null, h.over ? "The wait is over." : "Set aside, waiting for the author."));
  box.appendChild(el("span",null,
    (h.until ? (h.over ? "The author had until " : "Until ")+when(h.until)+". " : "")
    + "Set aside "+when(h.since)+(h.reason ? " — "+h.reason : "")+"."));
  const b = el("button","plain","Take it up again");
  b.onclick = () => holdAction("clear");
  box.appendChild(b);
  return box;
}

async function holdAction(action, reason){
  try{
    S.paper = await api("/api/hold",{folder:S.folder, action, reason:reason||""});
    if(action==="set"){
      toast("Set aside until the author replies — it stays yours");
      backToList();
    } else { toast("Back in your work"); renderPaper(); }
  }catch(err){ toast(err.message, true); }
}

/* An email opened in the editor's own mail program: the desk sends nothing. */
function mailtoHref(text, subject){
  let body = text || "";
  const m = body.match(/^Subject:[ \t]*(.*)\r?\n(\r?\n)?/);
  if(m){ subject = m[1]; body = body.slice(m[0].length); }
  return "mailto:?subject="+encodeURIComponent(subject||"")+"&body="+encodeURIComponent(body);
}

function openMail(text, subject){
  const a = el("a"); a.href = mailtoHref(text, subject);
  a.rel = "noopener"; document.body.appendChild(a); a.click(); a.remove();
}

/* ------------------------------------------------------ shared cards */
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
  if(a.scope==="body") acts.appendChild(showInSource(a.id));
  const id = el("span","checkid"); id.textContent = a.check_id;
  id.title = (a.rule||"") + (a.detail? "\n\n"+a.detail : "");
  acts.appendChild(el("span",null," ")); acts.appendChild(id);
  item.appendChild(acts);

  if(a.note){
    const n = el("div","hasnote");
    n.appendChild(el("b",null,"Your note: "));
    n.appendChild(document.createTextNode(a.note));
    item.appendChild(n);
  }
  item.appendChild(noteEditor(a.note, a.id, "edit"));
  return item;
}

/* A suggestion: accept it, keep the author's text, or accept it in your own
   words ("Modify"). */
function decisionCard(d, index){
  const item = el("div","item "+(d.decision!=="undecided"?d.decision:"")
    + (index===S.cursor?" focus":""));
  item.dataset.index = index;
  item.dataset.id = d.id;

  const top = el("div","item-top");
  top.appendChild(el("h3",null,d.heading));
  if(d.line_label) top.appendChild(el("span","where",d.line_label));
  else if(d.kind==="reorder") top.appendChild(el("span","where","reference list"));
  item.appendChild(top);

  item.appendChild(el("p","why", d.why));

  const ba = el("div","ba");
  const was = el("div","was"); was.appendChild(el("span","lab","As submitted"));
  was.appendChild(document.createTextNode(d.before));
  const now = el("div","now");
  const mine = d.edited_text!=null;
  now.appendChild(el("span","lab", mine ? "Accepted in your words" : "Proposed"));
  now.appendChild(document.createTextNode((mine ? d.edited_text : d.after) || "(removed)"));
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
      d.decision==="accepted" ? (mine ? "✓ Accepted, your wording" : "✓ Accepted")
                              : "✗ Kept as submitted");
    acts.appendChild(badge);
    const undo = el("button","plain","change");
    undo.onclick = () => decide(d.id,"undecided");
    acts.appendChild(undo);
  }
  if(d.kind!=="reorder"){
    const mod = el("button",null,"Modify…");
    mod.onclick = () => openModify(item, d);
    acts.appendChild(mod);
  }
  if(d.scope==="body") acts.appendChild(showInSource(d.id));
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

function openModify(item, d){
  if(item.querySelector(".modbox")) return;
  const box = el("div","modbox");
  box.appendChild(el("label","tiny muted","Your wording for this change (it replaces “"
    + (d.before.length>60 ? d.before.slice(0,59)+"…" : d.before) + "”):"));
  const ta = el("textarea"); ta.value = d.edited_text!=null ? d.edited_text : d.after;
  ta.spellcheck = false; ta.className = "mono";
  box.appendChild(ta);
  const row = el("div","row"); row.style.marginTop="8px";
  const save = el("button","primary","Accept in my words");
  save.onclick = async () => {
    try{ S.paper = await api("/api/edit-text",{folder:S.folder,id:d.id,text:ta.value});
         toast("Accepted in your words"); renderPaper(); }
    catch(err){ toast(err.message,true); }
  };
  row.appendChild(save);
  if(d.edited_text!=null){
    const drop = el("button",null,"Back to the proposed text");
    drop.onclick = async () => {
      try{ S.paper = await api("/api/edit-text",{folder:S.folder,id:d.id,text:null});
           renderPaper(); }catch(err){ toast(err.message,true); }
    };
    row.appendChild(drop);
  }
  const cancel = el("button","plain","Cancel"); cancel.onclick = () => box.remove();
  row.appendChild(cancel);
  box.appendChild(row);
  item.querySelector(".acts").after(box);
  ta.focus();
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
    if(S.tab==="body" && decision!=="undecided" && decision!=="reverted"){
      const list = bodyDecisions();
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
    renderPaper();
    toast(ids.length+(decision==="accepted"?" accepted":" kept as submitted"));
  }catch(err){ toast(err.message, true); }
}

/* Scroll a node to the middle of the panel it scrolls in, not the page. */
function scrollWithin(node, smooth){
  if(!node) return;
  let box = node.parentElement;
  while(box && box!==document.body){
    const style = getComputedStyle(box);
    if(/(auto|scroll)/.test(style.overflowY) && box.scrollHeight>box.clientHeight) break;
    box = box.parentElement;
  }
  if(!box || box===document.body){ node.scrollIntoView({block:"center", behavior:smooth?"smooth":"auto"}); return; }
  const top = node.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
  box.scrollTo({top:Math.max(0, top - box.clientHeight/3), behavior:smooth?"smooth":"auto"});
}

function focusCursor(){
  const sel = S.tab==="refs" ? '.ref[data-index="'+S.cursor+'"]'
                             : '.item[data-index="'+S.cursor+'"]';
  scrollWithin(document.querySelector(sel), true);
}

const OWNER_GROUPS = [
  ["author","Only the author can fix these",
   "The agent will not touch these, because fixing them needs information it "
   +"does not have. They go into the letter unless you tick them off."],
  ["editor","For you to check",
   "Judgement calls and things the agent could not verify."],
  ["tool","For the record",
   "What the agent did, and which checks could not run. Nothing to do here."],
];

function findingCard(f){
  const item = el("div","item"+(f.handled?" handled":""));
  const top = el("div","item-top");
  top.appendChild(el("span","sevdot "+f.severity));
  top.appendChild(el("h3",null,f.heading));
  if(f.line){
    const where = el("span","where","line "+f.line);
    if(S.tab==="body" && S.paper.body && S.paper.body.editable){
      where.classList.add("link"); where.title = "Show it in the source";
      where.onclick = () => jumpToOrigLine(f.line);
    }
    top.appendChild(where);
  }
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

function findingGroups(host, items){
  OWNER_GROUPS.forEach(([owner,title,blurb])=>{
    const list = items.filter(f=>f.owner===owner);
    if(!list.length) return;
    const g = el("div","group");
    g.appendChild(el("h2",null,title+" ("+list.length+")"));
    g.appendChild(el("p",null,blurb));
    list.forEach(f=>g.appendChild(findingCard(f)));
    host.appendChild(g);
  });
}

/* --------------------------------------------- tab 1: title & authors */
function tabNames(host){
  const t = S.paper.title_authors;
  if(!t){ namesWithoutIndico(host); titleFormatting(host); return; }
  const c = t.comparison;
  const g = el("div","group");
  g.appendChild(el("h2",null,"Title and authors against Indico"));
  g.appendChild(el("p",null,"The proceedings' table of contents, author index and DOI "
    +"metadata come from Indico. Where Indico differs from the paper, the paper's title "
    +"is taken as right and the author list becomes the combined list, after the "
    +"author has had 48 hours to say otherwise."));

  const tone = {match:"you", done:"you", differs:"other", due:"other",
                changed:"other"}[t.status] || "";
  const state = el("div","held "+tone);
  state.appendChild(el("b",null,(tone==="you" ? "✓ " : "")+t.status_word+"."));
  const say = {
    match: "The paper's title and authors match Indico. Nothing to do.",
    done: "Corrected"+(t.reply==="agreed" ? " as the author agreed" : " after 48 hours without a reply")
      +", and every change in Indico is ticked off.",
    unknown: c && c.unreadable.length
      ? "The desk cannot compare this paper on its own: "+c.unreadable.join("; ")+"."
      : t.why_not,
    differs: "Check the email below, change anything you like, send it from your own mail "
      +"(or as a comment on the paper in Indico), then press “I’ve sent it”. If the author "
      +"does not reply within 48 hours, the changes it describes are made.",
    waiting: "Sent "+when(t.sent_at)+". The author has until "+t.deadline_text+".",
    due: "No reply by "+t.deadline_text+". The changes the email described are ready.",
    applied: "Applied "+when(t.applied_at)+(t.reply==="agreed" ? ", as the author agreed" : "")
      +". The reviewed files carry the paper's side; Indico's side is below for you to make.",
    replied: "The author replied, so the prepared changes are dropped. Follow their answer by hand.",
    changed: "The paper or its Indico record has changed since the email was sent; perhaps "
      +"the author has already fixed it. Compare again before changing anything.",
  }[t.status];
  if(say) state.appendChild(el("span",null,say));
  g.appendChild(state);

  const step = async (action, extra) => {
    try{
      S.paper = await api("/api/title-authors", Object.assign({folder:S.folder, action}, extra||{}));
      renderPaper();
    }catch(err){ toast(err.message, true); }
  };

  // Just sent: set the paper aside until the author answers, or keep going.
  if(t.status==="waiting" && !S.paper.hold && !S.keepWorking){
    const ask = el("div","card pad setaside");
    ask.appendChild(el("b",null,"Set this paper aside until the author replies?"));
    ask.appendChild(el("p","why","It stays yours, and leaves your list of papers to work "
      +"on now. It comes back when you take it up again, or when "+t.deadline_text
      +" has passed."));
    const row = el("div","row");
    const yes = el("button","primary","Set it aside until "+t.deadline_text);
    yes.onclick = () => holdAction("set", "waiting for the author's reply about the title and authors");
    const no = el("button",null,"Keep working on it");
    no.onclick = () => { S.keepWorking = true; renderPaper(); };
    row.appendChild(yes); row.appendChild(no);
    ask.appendChild(row);
    g.appendChild(ask);
  }

  const acts = el("div","row"); acts.style.margin = "0 0 16px";
  const button = (label, cls, action) => {
    const b = el("button", cls, label); b.onclick = () => step(action); acts.appendChild(b);
  };
  if(t.status==="due") button("Apply the changes","primary","apply");
  if(["waiting","due","changed"].includes(t.status)){
    button("The author agreed: apply now", null, "agreed");
    button("The author replied otherwise: drop the changes", null, "declined");
  }
  if(t.status==="applied" || t.status==="done") button("Undo the changes", null, "undo");
  if(["waiting","due","replied","changed","applied","done"].includes(t.status))
    button("Start again", "plain", "restart");
  if(t.status==="waiting" && !S.paper.hold && S.keepWorking){
    const b = el("button",null,"Set it aside until the author replies");
    b.onclick = () => holdAction("set", "waiting for the author's reply about the title and authors");
    acts.appendChild(b);
  }
  if(acts.childNodes.length) g.appendChild(acts);

  if(c && !t.roles_known){
    const warn = el("div","held other");
    warn.appendChild(el("b",null,"Indico's authors have not been read yet."));
    warn.appendChild(el("span",null,"This compares against the names the pull recorded, "
      +"which include speakers and carry no affiliation. Press “Check Indico now” on the "
      +"paper list before you send anything."));
    g.appendChild(warn);
  }

  const withAff = (x) => x.affiliation ? x.name+" ("+x.affiliation+")" : x.name;
  if(t.status==="applied" || t.status==="done"){
    if(t.plan.add_to_paper.length)
      g.appendChild(el("p",null,"Added to the paper's author list in the reviewed files: "
        + t.plan.add_to_paper.map(withAff).join(", ")+"."));
    if(t.indico_tasks.length){
      g.appendChild(el("h3",null,"For you to change in Indico"));
      const ul = el("ul","people");
      t.indico_tasks.forEach(task=>{
        const li = el("li"); const label = el("label");
        const box = el("input"); box.type = "checkbox"; box.checked = task.done;
        box.onchange = () => step("tick", {key:task.key, done:box.checked});
        label.appendChild(box); label.appendChild(document.createTextNode(" "+task.text));
        li.appendChild(label); ul.appendChild(li);
      });
      g.appendChild(ul);
      if(t.indico_url){
        const a = el("a",null,"Open the paper in Indico ↗");
        a.href = t.indico_url; a.target = "_blank"; a.rel = "noopener noreferrer";
        const line = el("p"); line.appendChild(a); g.appendChild(line);
      }
    }
  }

  if(c){
    const cols = el("div","names-cols");
    const left = el("div");
    left.appendChild(el("h3",null,"Title"));
    const table = el("table","cmp");
    const row = (k, v) => { const tr = el("tr"); tr.appendChild(el("th",null,k));
      tr.appendChild(el("td",null,v)); table.appendChild(tr); };
    row("In the paper", c.paper_title || "—");
    row("In Indico", c.indico_title || "—");
    if(c.title_differs)
      row("Indico becomes", c.proposed_indico_title
        + (c.check_capitals ? "  (check its capitals)" : ""));
    left.appendChild(table);
    cols.appendChild(left);

    const rightCol = el("div");
    rightCol.appendChild(el("h3",null,"Authors"));
    const ul = el("ul","people");
    const person = (name, detail, cls, tag) => {
      const li = el("li"); li.appendChild(el("span",null,name));
      li.appendChild(el("span","tag "+cls, tag));
      if(detail) li.appendChild(el("div","tiny muted", detail));
      ul.appendChild(li);
    };
    c.matched.forEach(([paper, indico]) =>
      person(paper, paper===indico ? "" : "In Indico as "+indico, "both", "in both"));
    c.paper_only.forEach(name =>
      person(name, "In the paper only", "to-indico", "will be added to Indico"));
    c.indico_only.forEach(x => person(x.jacow,
      ["In Indico only as "+x.name, x.affiliation,
       {primary:"primary author", coauthor:"co-author"}[x.role]].filter(Boolean).join(" · "),
      "to-paper", "will be added to the paper"));
    rightCol.appendChild(ul);
    if(c.not_names.length)
      rightCol.appendChild(el("p","tiny muted","Not read as names (address or footnote "
        +"fragments): "+c.not_names.join(", ")));
    if(c.unreadable.length && t.status!=="unknown")
      rightCol.appendChild(el("p","tiny muted","Not compared: "+c.unreadable.join("; ")+"."));
    cols.appendChild(rightCol);
    g.appendChild(cols);
  }

  if(t.email && ["differs","waiting","due","changed"].includes(t.status)){
    g.appendChild(el("h3",null,"Email to the author"));
    const box = el("div","card pad");
    box.appendChild(el("p","tiny muted","Edit it as you like: your wording is kept with the "
      +"paper. The changes it describes are applied no earlier than the time printed in it."));
    const text = el("textarea"); text.value = t.email; text.rows = 22; text.className = "mailtext";
    box.appendChild(text);
    const row2 = el("div","row"); row2.style.marginTop = "10px";
    const save = async () => { if(text.value !== t.email)
      await api("/api/title-authors",{folder:S.folder, action:"email", text:text.value}); };
    const mail = el("button", t.status==="differs" ? "primary" : null, "Open in my mail program");
    mail.title = "Opens a new message with this subject and text in your own mail program; "
      +"add the author's address and send it from there.";
    mail.onclick = async () => { try{ await save(); }catch(err){ toast(err.message,true); return; }
      openMail(text.value, ""); };
    row2.appendChild(mail);
    const copy = el("button",null,"Copy");
    copy.onclick = async () => {
      try{ await navigator.clipboard.writeText(text.value); toast("Copied"); }
      catch(_){ text.select(); toast("Press Ctrl-C / ⌘-C to copy"); }
    };
    row2.appendChild(copy);
    if(t.status==="differs"){
      const sent = el("button","yes","I’ve sent it");
      sent.onclick = async () => { try{ await save(); }catch(err){ toast(err.message,true); return; }
        S.keepWorking = false; step("send"); };
      row2.appendChild(sent);
    }
    const keep = el("button",null,"Save my wording");
    keep.onclick = async () => { try{ await save(); toast("Saved"); await refresh(); }
      catch(err){ toast(err.message,true); } };
    row2.appendChild(keep);
    if(t.email_edited){
      const reset = el("button","plain","Back to the drafted text");
      reset.onclick = () => step("email", {text:""});
      row2.appendChild(reset);
    }
    if(t.indico_url){
      const a = el("a",null,"Open the paper in Indico ↗");
      a.href = t.indico_url; a.target = "_blank"; a.rel = "noopener noreferrer";
      row2.appendChild(a);
    }
    box.appendChild(row2);
    g.appendChild(box);
    g.appendChild(el("p","tiny muted","The desk sends nothing itself: the message opens in "
      +"your mail program for you to send, or paste it into a comment on the paper in "
      +"Indico, which notifies the submitter."));
  }
  host.appendChild(g);
  titleFormatting(host);
}

function namesWithoutIndico(host){
  const p = S.paper;
  const g = el("div","group");
  g.appendChild(el("h2",null,"Title and authors"));
  g.appendChild(el("div","held",
    "This paper is not part of a conference pulled from Indico, so its title and authors "
    +"cannot be compared with Indico's. They are shown as the paper gives them."));
  const table = el("table","cmp");
  const row = (k, v) => { const tr = el("tr"); tr.appendChild(el("th",null,k));
    tr.appendChild(el("td",null,v)); table.appendChild(tr); };
  row("Title", p.title || "—");
  const names = (p.authors||[]).map(a => typeof a==="string" ? a
    : [a.name || [a.given, a.family].filter(Boolean).join(" "), a.affiliation ? "("+a.affiliation+")" : ""]
      .filter(Boolean).join(" ")).filter(Boolean);
  row("Authors", names.join(", ") || "—");
  g.appendChild(table);
  host.appendChild(g);
}

/* The title's and authors' own formatting in the paper (sentence case of the
   title, names written the JACoW way). */
function titleFormatting(host){
  const p = S.paper;
  const dec = titleDecisions(), app = p.applied.filter(a=>a.scope==="title"),
        fnd = p.findings.filter(f=>f.scope==="title");
  if(!dec.length && !app.length && !fnd.length) return;
  const g = el("div","group");
  g.appendChild(el("h2",null,"Title and author formatting in the paper"));
  g.appendChild(el("p",null,"How the title and the author names are written in the paper "
    +"itself, separately from whether they match Indico."));
  dec.forEach(d=>g.appendChild(decisionCard(d, -1)));
  app.forEach(a=>g.appendChild(appliedCard(a)));
  fnd.forEach(f=>g.appendChild(findingCard(f)));
  host.appendChild(g);
}

/* ------------------------------------------------- tab 2: references */
/* Each reference as written, beside what it becomes. Green: rewritten in
   Appendix B's layout with nothing missing. Red: something the desk cannot
   put right by itself. Grey: already right. */
const REF_FILTERS = [
  ["all","All"], ["undecided","To decide"], ["fixed","Fixed"],
  ["problem","Problems"], ["ok","Already right"],
];

function refMatches(r, f){
  if(f==="all") return true;
  if(f==="undecided") return (r.suggest_ids||[]).length>0 && r.decision==="undecided" && r.own==null;
  return r.status===f;
}
const visibleRefRows = () => ((S.paper.references||{}).rows||[])
  .filter(r=>refMatches(r, S.refFilter||"all"));

function tabRefs(host){
  const R = S.paper.references || {rows:[], counts:{}};
  const rows = R.rows || [];
  const g = el("div","group");
  g.appendChild(el("h2",null,"The reference list"));
  const intro = {
    bibitem: "Each \\bibitem as the author wrote it (left), beside the same reference in "
      +"Appendix B's layout, written as LaTeX (right). Accepting puts the right-hand text in "
      +"the reviewed source.",
    word: "Each reference as the author wrote it (left), beside the same reference in "
      +"Appendix B's layout (right). What you accept goes into the Word file as a tracked change.",
    bib: "Each .bib entry as the author wrote it (left), beside the entry with the fields the "
      +"JACoW bibliography style needs (right). “Prints as” is the reference as it will appear "
      +"in the paper. What you accept goes into the reviewed .bib.",
  }[R.origin] || "Each reference as the author wrote it, beside the same reference in "
      +"Appendix B's layout.";
  g.appendChild(el("p",null,intro));
  const legend = el("div","reflegend");
  [["fixed","Rewritten, nothing missing: accept it, edit it, or keep the author's"],
   ["problem","Something the desk cannot put right by itself (a missing part, an unknown "
     +"kind, a wrong DOI): edit it yourself, or leave it for the author"],
   ["ok","Already in the layout"]].forEach(([cls,text])=>{
    const s = el("span","lg "+cls); s.appendChild(el("i")); s.appendChild(document.createTextNode(text));
    legend.appendChild(s);
  });
  g.appendChild(legend);
  host.appendChild(g);

  if(!R.recorded && S.paper.screened){
    const box = el("div","held other");
    box.appendChild(el("b",null,"Prepared with an older version of the desk."));
    box.appendChild(el("span",null, S.pool
      ? "Its references were not recorded one by one. Ask the chief editor to prepare it again."
      : "Its references were not recorded one by one. Prepare it again to see them side by "
        +"side — your decisions and notes are kept."));
    if(!S.pool){
      const b = el("button","plain","Prepare it again");
      b.onclick = () => prepare({folder:S.folder});
      box.appendChild(b);
    }
    host.appendChild(box);
    // What there is: the reference changes as cards.
    S.paper.decisions.filter(d=>d.scope==="reference").forEach(d=>host.appendChild(decisionCard(d,-1)));
    return;
  }
  if(!rows.length){
    const e = el("div","empty"); e.appendChild(el("b",null,"No reference list found"));
    e.appendChild(el("div",null,"The desk found no \\bibitem, .bib entry or numbered reference in this paper."));
    host.appendChild(e);
  }

  if(R.reorder) host.appendChild(decisionCard(R.reorder, -1));

  if(rows.length){
    const bar = el("div","filters");
    REF_FILTERS.forEach(([key,label])=>{
      const n = rows.filter(r=>refMatches(r,key)).length;
      if(key!=="all" && !n) return;
      const b = el("button",null,label+" ("+n+")");
      b.setAttribute("aria-pressed", (S.refFilter||"all")===key ? "true" : "false");
      b.onclick = () => { S.refFilter = key; S.cursor = 0; renderPaper(); };
      bar.appendChild(b);
    });
    const greens = rows.filter(r=>r.status==="fixed" && refMatches(r,"undecided"));
    if(greens.length>1){
      const all = el("button","yes","Accept all "+greens.length+" green");
      all.title = "Accept every green rewrite still to decide. Each one can be changed afterwards.";
      all.onclick = () => decideMany(greens.flatMap(r=>r.suggest_ids), "accepted");
      bar.appendChild(all);
    }
    host.appendChild(bar);
    const hint = el("div","keyhint");
    hint.innerHTML = 'Keyboard: <kbd>a</kbd> accept · <kbd>r</kbd> keep as submitted '
      + '· <kbd>e</kbd> edit · <kbd>j</kbd>/<kbd>k</kbd> move';
    host.appendChild(hint);
  }

  const lists = R.list_findings || [];
  if(lists.length){
    const det = el("details","autobox");
    const sum = el("summary");
    sum.appendChild(el("b",null,"About the list as a whole ("+lists.length+")"));
    sum.appendChild(el("span","sub2","citation order, unresolved citations, the bibliography style"));
    det.appendChild(sum);
    const inner = el("div","inner");
    lists.forEach(f=>inner.appendChild(findingCard(f)));
    det.appendChild(inner);
    host.appendChild(det);
  }

  visibleRefRows().forEach((r,i)=>host.appendChild(refRow(r,i)));
}

const STATUS_WORDS_REF = {fixed:"Fixed", problem:"Problem", ok:"Already right"};

function refRow(r, index){
  const row = el("div","ref "+r.status
    + ((r.decision==="rejected"||r.decision==="reverted") && r.own==null ? " kept" : "")
    + (r.own!=null ? " own" : "") + (index===S.cursor ? " focus" : ""));
  row.dataset.index = index;
  row.dataset.ref = r.id;

  const top = el("div","ref-top");
  top.appendChild(el("span","num", r.origin==="word" ? "["+r.n+"]" : "["+r.n+"]"));
  if(r.origin!=="word") top.appendChild(el("span","where", r.key));
  if(r.kind) top.appendChild(el("span","kind", r.kind));
  top.appendChild(el("span","pill st-"+(r.own!=null ? "warn" : {fixed:"good",problem:"bad",ok:"none"}[r.status]),
    r.own!=null ? "Your version" : STATUS_WORDS_REF[r.status]));
  if(r.edit_id && r.own==null){
    if(r.auto) top.appendChild(el("span","decided "+r.decision,
      r.decision==="reverted" ? "↩ Put back as submitted" : "✓ Applied"));
    else if(r.decision!=="undecided") top.appendChild(el("span","decided "+r.decision,
      r.decision==="accepted" ? "✓ Accepted" : "✗ Kept as submitted"));
  }
  if(r.parsed_by==="model") top.appendChild(el("span","pill st-info","read by the local model"));
  row.appendChild(top);

  const grid = el("div","ref-grid");
  const left = el("div","src-col"); left.appendChild(el("div","lab","As written"));
  const right = el("div","res");
  let result = null, label = "";
  if(r.own!=null){ result = r.own; label = "Your version"; }
  else if(r.edit_id){ result = r.proposed;
    label = r.origin==="bib" ? "Entry for the JACoW style" : "Appendix B"; }
  if(result!=null){
    const d = tokenDiff(r.source, result);
    left.appendChild(diffNode(d.a, "del"));
    right.appendChild(el("div","lab",label));
    right.appendChild(diffNode(d.b, "ins"));
  } else {
    left.appendChild(diffNode([[r.source,false]], ""));
    right.appendChild(el("div","lab","Appendix B"));
    const t = el("div","reftext muted-box");
    if(r.status==="ok") t.textContent = "No change needed: already in Appendix B's layout.";
    else{
      t.textContent = "The desk could not rewrite this reference by itself.";
      if(r.text && r.text!==r.source){
        t.appendChild(el("div","nearest","Nearest it got: "+r.text));
      }
    }
    right.appendChild(t);
  }
  if(r.origin==="bib" && r.text && result!=null){
    const pr = el("div","prints"); pr.appendChild(el("b",null,"Prints as: "));
    pr.appendChild(document.createTextNode(r.text)); right.appendChild(pr);
  }
  grid.appendChild(left); grid.appendChild(right);
  row.appendChild(grid);

  const meta = el("div","refmeta");
  if(r.missing.length){
    const m = el("div","missing");
    m.textContent = "Missing: "+r.missing.map(x=>x.replace(/_/g," ")).join(", ")
      + " — no registry had "+(r.missing.length===1?"it":"them")+"; it is never invented.";
    meta.appendChild(m);
  }
  r.problems.forEach(pb=>{
    const line = el("div","prob "+(pb.severity||"warning"));
    line.appendChild(el("span","sevdot "+(pb.severity==="error"?"error":"warning")));
    line.appendChild(document.createTextNode(" "+pb.message));
    if(pb.key){
      const lab = el("label","inline");
      const cb = el("input"); cb.type="checkbox"; cb.checked=!!pb.handled;
      cb.onchange = async () => {
        try{ await api("/api/finding",{folder:S.folder,key:pb.key,handled:cb.checked}); await refresh(); }
        catch(err){ toast(err.message,true); cb.checked=!cb.checked; }
      };
      lab.appendChild(cb); lab.appendChild(document.createTextNode(" handled"));
      line.appendChild(lab);
    }
    meta.appendChild(line);
  });
  if(r.changes.length && r.own==null && r.edit_id)
    meta.appendChild(el("div","tiny muted","Changed: "+r.changes.join("; ")));
  if(r.sources.length) meta.appendChild(el("div","tiny muted","Values from "+r.sources.join(", ")+"."));
  if(meta.childNodes.length) row.appendChild(meta);

  const acts = el("div","acts");
  if(r.own==null && r.edit_id && !r.auto){
    if(r.decision==="undecided"){
      const yes = el("button","yes","Accept"); yes.onclick = () => refDecide(r,"accepted");
      const no = el("button","no","Keep as submitted"); no.onclick = () => refDecide(r,"rejected");
      acts.appendChild(yes); acts.appendChild(no);
    } else {
      const ch = el("button","plain","change"); ch.onclick = () => refDecide(r,"undecided");
      acts.appendChild(ch);
    }
  }
  if(r.own==null && r.edit_id && r.auto){
    const b = r.decision==="reverted" ? el("button","plain","apply it again")
                                      : el("button","no","Put back as submitted");
    b.onclick = () => refDecide(r, r.decision==="reverted" ? "undecided" : "reverted");
    acts.appendChild(b);
  }
  const edit = el("button",null, r.own!=null ? "Edit my version…" : "Edit…");
  edit.onclick = () => openRefEditor(row, r);
  acts.appendChild(edit);
  if(r.own!=null){
    const drop = el("button","plain","Drop my version");
    drop.onclick = () => saveRefText(r, null);
    acts.appendChild(drop);
  }
  row.appendChild(acts);
  row.onclick = (e) => {
    if(e.target.closest("button,textarea,input,label,a")) return;
    if(S.cursor!==index){ S.cursor = index;
      document.querySelectorAll(".ref.focus").forEach(n=>n.classList.remove("focus"));
      row.classList.add("focus"); }
  };
  return row;
}

/* A reference's changes are decided together: the whole rewrite, or the
   narrow fixes inside it when there is no rewrite. */
async function refDecide(r, decision){
  try{
    const calls = [];
    (r.suggest_ids||[]).forEach(id=>calls.push([id, decision==="reverted" ? "rejected" : decision]));
    (r.auto_ids||[]).forEach(id=>calls.push([id,
      (decision==="rejected" || decision==="reverted") ? "reverted" : "undecided"]));
    for(const [id, d] of calls){
      S.paper = await api("/api/decide",{folder:S.folder,id,decision:d});
    }
    if(decision==="accepted" || decision==="rejected"){
      const rows = visibleRefRows();
      const next = rows.findIndex((x,i)=> i>S.cursor && refMatches(x,"undecided"));
      if(next>=0) S.cursor = next;
      else S.cursor = Math.min(S.cursor, Math.max(0, rows.length-1));
    }
    renderPaper(); focusCursor();
  }catch(err){ toast(err.message, true); }
}

function openRefEditor(row, r){
  if(row.querySelector(".modbox")) { row.querySelector(".modbox textarea").focus(); return; }
  const box = el("div","modbox");
  box.appendChild(el("label","tiny muted", {
    bibitem:"The reference as LaTeX, without its \\bibitem{"+r.key+"} — it replaces the whole reference.",
    word:"The reference as it should read — it replaces the whole reference, as a tracked change.",
    bib:"The whole .bib entry, from @type{"+r.key+", to its closing brace.",
  }[r.origin] || "The reference as it should read."));
  const ta = el("textarea"); ta.className = "mono"; ta.spellcheck = false;
  ta.value = r.own!=null ? r.own : (r.edit_id && r.proposed ? r.proposed : r.source);
  ta.rows = Math.min(14, Math.max(3, Math.ceil(ta.value.length/90) + (ta.value.match(/\n/g)||[]).length));
  box.appendChild(ta);
  if(r.text && r.edit_id==="" && r.status==="problem"){
    const hint = el("div","tiny muted","Appendix B's layout for it, as far as the desk got: "+r.text);
    box.appendChild(hint);
  }
  const bar = el("div","row"); bar.style.marginTop="8px";
  const save = el("button","primary","Save my version");
  save.onclick = () => saveRefText(r, ta.value);
  const cancel = el("button","plain","Cancel"); cancel.onclick = () => box.remove();
  bar.appendChild(save); bar.appendChild(cancel);
  box.appendChild(bar);
  row.appendChild(box);
  ta.focus();
}

async function saveRefText(r, text){
  try{
    S.paper = await api("/api/ref-text",{folder:S.folder, ref:r.id, text});
    toast(text==null ? "Your version dropped" : "Saved: your version of ["+r.n+"]");
    renderPaper(); focusCursor();
  }catch(err){ toast(err.message, true); }
}

/* Word-level differences, so the eye goes to what changed. */
function tokenDiff(a, b){
  // A tie (~) is a space for the eye: "G.~J.~Portmann" is "G. J. Portmann".
  const split = (s) => (s||"").split(/([\s~]+)/).filter(x=>x!=="");
  const A = split(a), B = split(b);
  const key = (t) => /^[\s~]+$/.test(t) ? " " : t;
  const n = A.length, m = B.length;
  if(!n || !m || n*m > 400000) return {a:A.map(t=>[t,!!m]), b:B.map(t=>[t,!!n])};
  const L = Array.from({length:n+1}, ()=>new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--) for(let j=m-1;j>=0;j--)
    L[i][j] = key(A[i])===key(B[j]) ? L[i+1][j+1]+1 : Math.max(L[i+1][j], L[i][j+1]);
  const outA = [], outB = []; let i = 0, j = 0;
  while(i<n && j<m){
    if(key(A[i])===key(B[j])){ outA.push([A[i],false]); outB.push([B[j],false]); i++; j++; }
    else if(L[i+1][j]>=L[i][j+1]){ outA.push([A[i],true]); i++; }
    else { outB.push([B[j],true]); j++; }
  }
  while(i<n) outA.push([A[i++],true]);
  while(j<m) outB.push([B[j++],true]);
  return {a:outA, b:outB};
}

function diffNode(tokens, cls){
  const box = el("div","reftext");
  tokens.forEach(([t,changed])=>{
    if(changed && cls && /[^\s~]/.test(t)) box.appendChild(el("span",cls,t));
    else box.appendChild(document.createTextNode(t));
  });
  return box;
}

function gotoRef(id){
  S.tab = "refs"; S.refFilter = "all";
  const rows = visibleRefRows();
  const i = rows.findIndex(r=>r.id===id);
  S.cursor = i>=0 ? i : 0;
  renderPaper(); focusCursor();
}

/* ---------------------------------------------------- tab 3: the paper */
/* Laid out like an online LaTeX editor: the source on the left with every
   suggestion where it is, and on the right the list of changes to review or
   the PDF. Click a line to edit it; click a suggestion to decide it. */
function tabBody(host){
  const B = S.paper.body;
  if(!B || !B.editable){ wordBody(host); return; }

  const tools = el("div","srctools");
  (B.jumps||[]).forEach(j=>{
    const b = el("button",null,j.label);
    b.onclick = () => scrollToLine(j.line, true);
    tools.appendChild(b);
  });
  if((B.sections||[]).length){
    const sel = el("select","secsel");
    const first = el("option",null,"Go to a section…"); first.value=""; sel.appendChild(first);
    B.sections.forEach(s=>{ const o = el("option",null,s.label); o.value = s.line; sel.appendChild(o); });
    sel.onchange = () => { if(sel.value) scrollToLine(+sel.value, true); sel.value=""; };
    tools.appendChild(sel);
  }
  const onlyChanged = el("button",null,"Only changed lines");
  onlyChanged.setAttribute("aria-pressed", S.onlyChanged ? "true" : "false");
  onlyChanged.onclick = () => { S.onlyChanged = !S.onlyChanged; renderPaper(); };
  tools.appendChild(onlyChanged);
  const find = el("input"); find.type="text"; find.placeholder = "Find in the source…";
  find.value = S.find || "";
  find.oninput = () => { S.find = find.value; markFind(true); };
  tools.appendChild(find);
  host.appendChild(tools);

  const ol = el("div","ol");
  const left = el("div","ol-src");
  const box = el("div","src ol-box"); box.id = "srcbox";
  B.lines.forEach(line=>{
    const node = srcLine(line);
    if(S.onlyChanged && !node.classList.contains("changed") && !node.classList.contains("mine")
       && !node.classList.contains("pending")) node.hidden = true;
    box.appendChild(node);
  });
  box.onscroll = () => { S.srcScroll = box.scrollTop; };
  left.appendChild(box);
  const legend = el("p","tiny muted legend");
  legend.innerHTML = '<span class="lgx und"><del>red</del><ins>green</ins></span> a suggestion '
    + 'to decide · <span class="lgx ok">green</span> corrected · <span class="lgx own">orange</span> '
    + 'yours · click a suggestion to decide it, any other text to edit its line';
  left.appendChild(legend);
  ol.appendChild(left);

  const side = el("div","ol-side");
  const st = el("div","side-tabs");
  const und = bodyDecisions().filter(d=>d.decision==="undecided").length;
  [["review","Review"+(und?" ("+und+")":"")],["pdf","PDF"]].forEach(([key,label])=>{
    const b = el("button",null,label);
    b.setAttribute("aria-selected", (S.side||"review")===key ? "true" : "false");
    b.onclick = () => { S.side = key; renderPaper(); };
    st.appendChild(b);
  });
  side.appendChild(st);
  const sb = el("div","side-body"+((S.side||"review")==="pdf" ? " pdf" : ""));
  side.appendChild(sb);
  ol.appendChild(side);
  host.appendChild(ol);
  if((S.side||"review")==="pdf") pdfPane(sb); else reviewPane(sb);

  requestAnimationFrame(()=>{
    fitPanes();
    if(S.find) markFind(false);
    if(S.srcScroll!=null && S.srcFolder===S.folder){ box.scrollTop = S.srcScroll; }
    else {
      S.srcFolder = S.folder;
      const first = B.lines.find(l=>l.segs.some(s=>s.state==="undecided" && s.scope==="body"))
        || B.lines.find(l=>l.segs.some(s=>s.id));
      if(first) scrollToLine(first.n, false);
    }
  });
}

/* The source and the side panel fill the window down to the footer bar. */
function fitPanes(){
  const foot = $("#footbar");
  const bottom = (foot && !foot.hidden ? foot.offsetHeight : 0) + 14;
  const legend = document.querySelector(".ol-src .legend");
  const below = legend ? legend.offsetHeight + 10 : 0;
  document.querySelectorAll(".ol-box, .ol-side").forEach(node=>{
    const top = node.getBoundingClientRect().top;
    node.style.height = Math.max(380, window.innerHeight - top - bottom - below) + "px";
  });
}
window.addEventListener("resize", () => { if(S.paper && S.tab==="body") fitPanes(); });

function srcLine(line){
  const changed = line.segs.some(s=>s.id && (s.state==="applied"||s.state==="accepted"));
  const pending = line.segs.some(s=>s.state==="undecided");
  const row = el("div","srcline"+(line.mine?" mine":"")+(changed?" changed":"")
    +(pending?" pending":""));
  row.dataset.n = line.n;
  const ln = el("div","ln", String(line.n));
  if(line.findings){ ln.classList.add("flag");
    ln.title = line.findings.length+" problem(s) on this line: see Review"; }
  if(line.mine) ln.title = "You changed this line (was: "+(line.was||"")+")";
  row.appendChild(ln);
  const tx = el("div","tx");
  if(!line.segs.length || line.segs.every(s=>s.t==="" && !s.id)) tx.textContent = " ";
  line.segs.forEach(seg => tx.appendChild(segNode(seg)));
  tx.onclick = (e) => { if(e.target.closest(".sg")) return; openLineEditor(row, line); };
  row.appendChild(tx);
  return row;
}

function segNode(seg){
  if(!seg.id && seg.state!=="own") return document.createTextNode(seg.t);
  const span = el("span","sg "+seg.state+(seg.scope==="reference"?" ref":""));
  if(seg.id) span.dataset.id = seg.id;
  if(seg.state==="undecided"){
    if(seg.t) span.appendChild(el("del",null,seg.t));
    if(seg.last && seg.proposed) span.appendChild(el("ins",null,seg.proposed));
    if(!seg.t && !seg.proposed) span.appendChild(el("ins",null,"∅"));
    span.title = seg.scope==="reference" ? "A reference suggestion: decide it on the References tab"
                                         : "A suggestion: click to decide it";
  } else {
    span.textContent = seg.t;
    if(seg.last && seg.was!=null) span.title = "Was: "+seg.was;
    else if(seg.last && seg.proposed!=null) span.title = "You kept the author's text. Suggested: "+seg.proposed;
  }
  span.onclick = (e) => {
    e.stopPropagation();
    if(seg.scope==="reference"){ if(seg.ref) gotoRef(seg.ref); else { S.tab="refs"; renderPaper(); } return; }
    if(seg.id) focusSuggestion(seg.id);
  };
  return span;
}

function scrollToLine(n, flash){
  const box = $("#srcbox"); if(!box) return;
  const node = box.querySelector('.srcline[data-n="'+n+'"]');
  if(!node) return;
  if(node.hidden){ S.onlyChanged = false; renderPaper(); return scrollToLine(n, flash); }
  const top = node.offsetTop - box.clientHeight/3;
  box.scrollTo({top:Math.max(0, top), behavior: flash ? "smooth" : "auto"});
  if(flash){ node.classList.remove("flash"); void node.offsetWidth; node.classList.add("flash"); }
}

function lineOfEdit(id){
  const B = S.paper.body; if(!B || !B.lines) return null;
  const line = B.lines.find(l=>l.segs.some(s=>s.id===id));
  return line ? line.n : null;
}

function jumpToOrigLine(orig){
  const B = S.paper.body; if(!B || !B.lines) return;
  const line = B.lines.find(l=>l.orig>=orig) || B.lines[B.lines.length-1];
  if(line) scrollToLine(line.n, true);
}

function showInSource(id){
  const b = el("button","plain","show in source");
  b.onclick = () => {
    const n = lineOfEdit(id);
    if(S.tab!=="body"){ S.tab = "body"; renderPaper(); }
    if(n) requestAnimationFrame(()=>scrollToLine(n, true));
  };
  return b;
}

function focusSuggestion(id){
  const list = bodyDecisions();
  const i = list.findIndex(d=>d.id===id);
  if(i>=0){ S.cursor = i; S.side = "review"; S.showDecided = S.showDecided || list[i].decision!=="undecided"; }
  else { S.side = "review"; S.showApplied = true; }
  renderPaper();
  requestAnimationFrame(()=>{
    const node = document.querySelector('.side-body .item[data-id="'+id+'"]');
    scrollWithin(node, true);
    document.querySelectorAll('.sg[data-id="'+id+'"]').forEach(n=>n.classList.add("focus"));
  });
}

function markFind(scroll){
  const box = $("#srcbox"); if(!box) return;
  const q = (S.find||"").trim().toLowerCase();
  let first = null;
  box.querySelectorAll(".srcline").forEach(node=>{
    const hit = q && node.querySelector(".tx").textContent.toLowerCase().includes(q);
    node.classList.toggle("hit", !!hit);
    if(hit && !first) first = node;
  });
  if(first && scroll) scrollToLine(first.dataset.n, false);
}

function openLineEditor(row, line){
  if(row.nextSibling && row.nextSibling.classList
     && row.nextSibling.classList.contains("srcedit")) return;
  const box = el("div","srcedit");
  const ta = el("textarea"); ta.value = line.text;
  ta.spellcheck = false;
  box.appendChild(ta);
  if(line.segs.some(s=>s.state==="undecided")){
    box.appendChild(el("p","tiny muted","This line has a suggestion still to decide. You are "
      +"editing it as the author wrote it; decide the suggestion first if you want to build on it."));
  }
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
  if(line.mine){
    const undo = el("button","plain","Undo my change to this line");
    undo.onclick = async () => {
      try{ S.paper = await api("/api/my-edit/delete",{folder:S.folder,id:line.mine});
           toast("Undone"); renderPaper(); }catch(err){ toast(err.message,true); }
    };
    acts.appendChild(undo);
  }
  box.appendChild(acts);
  ta.addEventListener("keydown", (e)=>{
    if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); save.click(); }
    if(e.key==="Escape"){ e.preventDefault(); box.remove(); }
  });
  row.after(box);
  ta.focus();
}

/* The review panel: suggestions to decide, then what is decided, what was
   corrected automatically, the problems, and your own changes. */
function reviewPane(host){
  const p = S.paper;
  const list = bodyDecisions();
  const undecided = list.filter(d=>d.decision==="undecided");

  if(list.length){
    const hint = el("div","keyhint");
    hint.innerHTML = '<kbd>a</kbd> accept · <kbd>r</kbd> keep as submitted '
      + '· <kbd>j</kbd>/<kbd>k</kbd> move · <kbd>n</kbd> note';
    host.appendChild(hint);
  }
  const kinds = new Map();
  undecided.forEach(d=>{
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

  const g = el("div","group");
  g.appendChild(el("h2",null, undecided.length ? "To decide ("+undecided.length+")" : "Nothing left to decide"));
  if(!undecided.length) g.appendChild(el("p",null, list.length
    ? "Every suggestion in the body is decided. You can change any of them below."
    : "The agent has no suggestion for the body of this paper. Corrections it made on its "
      +"own are below, and you can edit any line of the source."));
  list.forEach((d,i)=>{ if(d.decision==="undecided") g.appendChild(decisionCard(d,i)); });
  host.appendChild(g);

  const decided = list.filter(d=>d.decision!=="undecided");
  if(decided.length){
    const det = el("details","autobox");
    det.open = !!S.showDecided;
    det.ontoggle = () => { S.showDecided = det.open; };
    const sum = el("summary"); sum.appendChild(el("b",null,"Decided ("+decided.length+")"));
    det.appendChild(sum);
    const inner = el("div","inner");
    list.forEach((d,i)=>{ if(d.decision!=="undecided") inner.appendChild(decisionCard(d,i)); });
    det.appendChild(inner);
    host.appendChild(det);
  }

  const applied = p.applied.filter(a=>a.scope==="body");
  if(applied.length){
    const back = applied.filter(a=>a.decision==="reverted").length;
    const det = el("details","autobox");
    det.open = !!S.showApplied || back>0;
    det.ontoggle = () => { S.showApplied = det.open; };
    const sum = el("summary");
    sum.appendChild(el("b",null,(applied.length-back)+" corrected automatically"));
    sum.appendChild(el("span","sub2", back ? back+" put back" : "open to check or undo"));
    det.appendChild(sum);
    const inner = el("div","inner");
    applied.forEach(a=>inner.appendChild(appliedCard(a)));
    det.appendChild(inner);
    host.appendChild(det);
  }

  const problems = p.findings.filter(f=>f.scope==="body");
  if(problems.length) findingGroups(host, problems);

  if(p.my_edits.length){
    const g3 = el("div","group");
    g3.appendChild(el("h2",null,"Lines you changed ("+p.my_edits.length+")"));
    p.my_edits.forEach(m=>{
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
      const acts = el("div","acts");
      const del = el("button","plain","undo this change");
      del.onclick = async () => {
        try{ S.paper = await api("/api/my-edit/delete",{folder:S.folder,id:m.id});
          toast("Undone"); renderPaper(); }catch(err){ toast(err.message,true); }
      };
      acts.appendChild(del);
      const show = el("button","plain","show in source");
      show.onclick = () => scrollToLine(m.line, true);
      acts.appendChild(show);
      item.appendChild(acts);
      g3.appendChild(item);
    });
    host.appendChild(g3);
  }
}

/* The PDF beside the source, and a button to compile the paper as it stands. */
function pdfPane(host){
  const P = S.paper.pdf || {choices:[]};
  const bar = el("div","pdfbar");
  if(P.choices.length){
    const sel = el("select");
    P.choices.forEach(c=>{
      const o = el("option",null,c.label+(c.at ? " · "+when(c.at) : ""));
      o.value = c.name; sel.appendChild(o);
    });
    if(!P.choices.some(c=>c.name===S.pdfName)) S.pdfName = P.choices[0].name;
    sel.value = S.pdfName;
    sel.onchange = () => { S.pdfName = sel.value; renderPaper(); };
    bar.appendChild(sel);
  }
  if(P.can_compile){
    const b = el("button","primary", S.compiling ? "Compiling…" : "Recompile");
    b.disabled = !!S.compiling;
    b.title = "Compile the paper as it stands now: your decisions, your wording, your lines.";
    b.onclick = recompile;
    bar.appendChild(b);
    if(S.compiling) bar.appendChild(el("span","spin"));
  }
  host.appendChild(bar);
  if(S.compileError){
    const e = el("div","held other"); e.style.margin="8px";
    e.appendChild(el("b",null,"Not compiled."));
    e.appendChild(el("span",null,S.compileError));
    host.appendChild(e);
  }
  const choice = P.choices.find(c=>c.name===S.pdfName);
  if(!choice){
    const e = el("div","empty"); e.style.margin="12px";
    e.appendChild(el("b",null,"No PDF yet"));
    e.appendChild(el("div",null, P.can_compile ? "Press Recompile to see the paper as it stands."
      : "There is no PDF for this paper."));
    host.appendChild(e);
    return;
  }
  const frame = el("iframe","pdfframe");
  frame.title = choice.label;
  frame.src = "/file?folder="+encodeURIComponent(S.folder)+"&name="+encodeURIComponent(choice.name)
    + "&t="+encodeURIComponent(choice.at||"");
  host.appendChild(frame);
}

async function recompile(){
  try{
    S.compiling = true; S.compileError = ""; renderPaper();
    const res = await api("/api/compile",{folder:S.folder});
    const id = res.job.id, folder = S.folder;
    const wait = async () => {
      let job;
      try{ job = await api("/api/job?id="+encodeURIComponent(id)); }
      catch(err){ S.compiling = false; toast(err.message,true); return; }
      if(!job.finished){ setTimeout(wait, 1500); return; }
      if(S.folder!==folder){ S.compiling = false; return; }
      S.compiling = false;
      S.compileError = (job.errors||[])[0] || "";
      S.paper = await api("/api/paper?folder="+encodeURIComponent(folder));
      if(!S.compileError){ S.pdfName = (S.paper.pdf.choices[0]||{}).name || ""; toast("Compiled"); }
      renderPaper();
    };
    setTimeout(wait, 1500);
  }catch(err){ S.compiling = false; toast(err.message, true); renderPaper(); }
}

/* A Word paper's text is edited in Word: the changes are listed beside the
   author's PDF. */
function wordBody(host){
  const note = el("p","sub"); note.textContent = (S.paper.source||{}).note || "";
  host.appendChild(note);
  const ol = el("div","ol");
  const left = el("div","ol-side solo"); const lb = el("div","side-body"); left.appendChild(lb);
  reviewPane(lb);
  const right = el("div","ol-side"); const rb = el("div","side-body pdf"); right.appendChild(rb);
  pdfPane(rb);
  ol.appendChild(left); ol.appendChild(right);
  host.appendChild(ol);
  requestAnimationFrame(fitPanes);
}

/* --------------------------------------------- tab 4: editor's panel */
function tabPanel(host){
  tagsSection(host);
  letterSection(host);
  notesSection(host);
  filesSection(host);
}

const TAG_COLOURS = ["red","orange","yellow","violet","pink","green","brown"];

function tagsSection(host){
  const T = S.paper.tags;
  if(!T) return;
  const g = el("div","group");
  g.appendChild(el("h2",null,"JACoW tags"));
  g.appendChild(el("p",null,"The editorial tags for this paper, proposed from what was "
    +"corrected and what the author must fix. Tick or untick any of them. The desk does not "
    +"write to Indico: copy the codes into the paper's revision there."));
  const card = el("div","card pad");
  const chosenRow = el("div","row tagrow");
  if(T.chosen.length){
    T.chosen.forEach(code=>{
      const t = T.vocabulary.find(v=>v.code===code) || {colour:""};
      const chip = el("span","tagc "+(TAG_COLOURS.includes(t.colour)?t.colour:""), code);
      chip.title = t.title || "";
      chosenRow.appendChild(chip);
    });
    const copy = el("button",null,"Copy the codes");
    copy.onclick = async () => {
      const text = T.chosen.join(", ");
      try{ await navigator.clipboard.writeText(text); toast("Copied: "+text); }
      catch(_){ toast(text); }
    };
    chosenRow.appendChild(copy);
  } else chosenRow.appendChild(el("span","muted","No tag chosen yet."));
  if(Object.keys(T.explicit || {}).length){
    const reset = el("button","plain","Back to the proposed tags");
    reset.onclick = async () => {
      try{ S.paper = await api("/api/tags",{folder:S.folder, reset:true}); renderPaper(); }
      catch(err){ toast(err.message,true); }
    };
    chosenRow.appendChild(reset);
  }
  card.appendChild(chosenRow);

  const fams = el("div","tagfams");
  Object.entries(T.families).forEach(([fam, title])=>{
    const codes = T.vocabulary.filter(v=>v.family===fam);
    if(!codes.length) return;
    const det = el("details","tagfam");
    det.open = codes.some(v=>T.chosen.includes(v.code) || T.proposed[v.code]);
    const sum = el("summary"); sum.appendChild(el("b",null,fam)); sum.appendChild(document.createTextNode(" · "+title));
    det.appendChild(sum);
    codes.forEach(v=>{
      const lab = el("label","opt tagopt");
      const cb = el("input"); cb.type = "checkbox"; cb.checked = T.chosen.includes(v.code);
      cb.onchange = async () => {
        try{ S.paper = await api("/api/tags",{folder:S.folder, code:v.code, on:cb.checked});
             const y = window.scrollY; renderPaper(); window.scrollTo({top:y}); }
        catch(err){ toast(err.message,true); cb.checked = !cb.checked; }
      };
      lab.appendChild(cb);
      const sp = el("span");
      sp.appendChild(el("span","tagc small "+(TAG_COLOURS.includes(v.colour)?v.colour:""), v.code));
      sp.appendChild(document.createTextNode(" "+v.title));
      if(T.proposed[v.code]) sp.appendChild(el("small",null,"Proposed: "+T.proposed[v.code].join("; ")));
      lab.appendChild(sp);
      det.appendChild(lab);
    });
    fams.appendChild(det);
  });
  card.appendChild(fams);
  g.appendChild(card);
  host.appendChild(g);
}

function letterSection(host){
  const g = el("div","group letter");
  g.appendChild(el("h2",null,"Letter to the author"));
  g.appendChild(el("p",null,
    "Drafted for you from your decisions, the problems only the author can fix, and your "
    +"notes. Edit it however you like — it is saved with the paper and written to a file "
    +"when you finish."));

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
  const mail = el("button",null,"Open in my mail program");
  mail.onclick = () => openMail(ta.value, S.paper.paper_id+": your paper for the proceedings");
  const reset = el("button",null,"Start again from the automatic version");
  reset.onclick = async () => {
    try{ const r = await api("/api/letter",{folder:S.folder,reset:true});
      ta.value = r.letter; toast("Reset"); await refresh(); }
    catch(err){ toast(err.message,true); }
  };
  const copy = el("button",null,"Copy");
  copy.onclick = async () => {
    try{ await navigator.clipboard.writeText(ta.value); toast("Copied"); }
    catch(_){ ta.select(); toast("Press Ctrl-C / ⌘-C to copy"); }
  };
  acts.appendChild(save); acts.appendChild(mail); acts.appendChild(copy); acts.appendChild(reset);
  if(S.paper.letter_override) acts.appendChild(el("span","tiny muted","Your wording is kept: "
    +"later decisions do not change it until you start again."));
  box.appendChild(acts);
  g.appendChild(box);
  host.appendChild(g);
}

function notesSection(host){
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
      item.appendChild(el("p","why", n.for_author
        ? "This will appear in the letter to the author."
        : "Kept for the record only — not sent to the author."));
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

function filesSection(host){
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
    const det = el("details","autobox");
    const sum = el("summary"); sum.appendChild(el("b",null,"Which checks could run"));
    sum.appendChild(el("span","sub2","online services the agent asked"));
    det.appendChild(sum);
    const inner = el("div","inner");
    S.paper.lookups.forEach(s=>{
      const row = el("div","filerow");
      const grow = el("div","grow");
      grow.appendChild(el("div",null,s.service));
      grow.appendChild(el("div","nm", s.reachable ? "answered"
        : (s.attempted ? "could not be reached" : "not needed")));
      row.appendChild(grow);
      row.appendChild(el("span","pill "+(s.reachable?"done":(s.attempted?"needs_author":"new")),
        s.reachable?"ok":(s.attempted?"offline":"—")));
      inner.appendChild(row);
    });
    det.appendChild(inner);
    host.appendChild(det);
  }
}

/* ------------------------------------------------------------------ QA */
/* A paper taken for QA: the editor checks the editing, then passes it, or
   fails it back to the editors with a note for whoever re-edits it. */
$("#btnQaPass").onclick = () => {
  if(!confirm("Pass the QA of "+(S.paper.paper_id||"this paper")+"?\n\nIt is then done: "
    +"nothing further is needed from the editors.")) return;
  qaVerdict("passed", "");
};
$("#btnQaFail").onclick = () => {
  $("#qaFailTitle").textContent = "Fail the QA of "+(S.paper.paper_id||"this paper")+"?";
  $("#qaFailNote").value = "";
  $("#dlgQaFail").showModal();
};
$("#dlgQaFail").addEventListener("close", () => {
  if($("#dlgQaFail").returnValue !== "ok") return;
  qaVerdict("failed", $("#qaFailNote").value.trim());
});

async function qaVerdict(verdict, note){
  const id = S.paper.paper_id || "The paper";
  try{
    const res = await api("/api/qa", {folder:S.folder, verdict, note});
    if(res.pool_error) toast(res.pool_error, true);
    else toast(verdict==="passed" ? "QA passed: "+id+" is done"
      : "QA failed: "+id+" is back with the editors to re-edit");
    await loadWorklist(); backToList(); loadPoolPapers();
  }catch(err){ toast(err.message, true); }
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
  if(theirs(S.paper)){
    box.appendChild(el("p","held other", S.paper.indico.editor+" has this paper in "
      +"Indico. Agree with them who answers the author before anything is sent."));
  }
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
    if(S.pool){
      body.appendChild(el("p", res.pool_error ? "bad-text" : "tiny muted",
        res.pool_error || "Sent to the chief editor's desk and given back, so "
          +"another editor can pick it up. You can read your copy here until "
          +"the desk is next started."));
    } else {
      body.appendChild(el("p","tiny muted",
        "You can reopen this paper at any time. It is no longer marked as "
        +"yours, so another editor can pick it up."));
    }
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
    const open = (x) => x.status!=="done" && !theirs(x) && !(x.hold && !x.hold.over);
    for(let k=i+1;k<S.papers.length;k++){
      if(open(S.papers[k])){ openPaper(S.papers[k].folder); return; }
    }
    for(let k=0;k<i;k++){
      if(open(S.papers[k])){ openPaper(S.papers[k].folder); return; }
    }
    toast(S.indico ? "Every paper not held by another editor is finished"
                   : "Every paper is finished");
    backToList(); return;
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
  if(!S.paper || !S.paper.screened) return;
  if(["1","2","3","4"].includes(e.key)){
    e.preventDefault(); S.tab = TABS[+e.key-1][0]; S.cursor = 0; renderPaper(); return;
  }
  const move = (list, delta) => {
    S.cursor = Math.max(0, Math.min(S.cursor+delta, list.length-1));
    renderPaper(); focusCursor();
  };
  if(S.tab==="body"){
    const list = bodyDecisions();
    if(!list.length) return;
    const cur = list[S.cursor];
    if(e.key==="a" && cur){ e.preventDefault(); decide(cur.id,"accepted"); }
    else if(e.key==="r" && cur){ e.preventDefault(); decide(cur.id,"rejected"); }
    else if(e.key==="j"){ e.preventDefault(); move(list, 1); }
    else if(e.key==="k"){ e.preventDefault(); move(list, -1); }
    else if(e.key==="n"){
      const node = document.querySelector('.item[data-index="'+S.cursor+'"] .notebox');
      if(node){ e.preventDefault(); node.open=true; node.querySelector("textarea").focus(); }
    }
  } else if(S.tab==="refs"){
    const rows = visibleRefRows();
    if(!rows.length) return;
    const cur = rows[S.cursor];
    const decidable = cur && cur.edit_id && !cur.auto && cur.own==null;
    if(e.key==="a" && decidable){ e.preventDefault(); refDecide(cur,"accepted"); }
    else if(e.key==="r" && decidable){ e.preventDefault(); refDecide(cur,"rejected"); }
    else if(e.key==="e" && cur){
      const node = document.querySelector('.ref[data-index="'+S.cursor+'"]');
      if(node){ e.preventDefault(); openRefEditor(node, cur); }
    }
    else if(e.key==="j"){ e.preventDefault(); move(rows, 1); }
    else if(e.key==="k"){ e.preventDefault(); move(rows, -1); }
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
  S.indico = data.indico || null;
  if(data.sharing){ S.sharing = data.sharing; noteGivenUp(); }
  if(data.indico_sync) S.indicoSync = data.indico_sync;
  const names = [...new Set(S.papers.map(p=>p.indico && p.indico.editor)
    .filter(Boolean))].sort();
  const list = $("#indicoEditors"); list.innerHTML = "";
  names.forEach(n=>{ const o=document.createElement("option"); o.value=n; list.appendChild(o); });
}

/* The chief's page shows who is taking which paper, and an editor's shows
   what is still free, so both look again every few seconds while the list is
   open (not while a paper is open or someone is typing). */
async function keepUpToDate(){
  if(document.hidden) return;
  if(S.folder){
    // Reading a paper: the chief still hears at once when one is given up.
    if(S.sharing){
      try{ S.sharing.given_up = (await api("/api/chief/given-up",{})).given_up;
           noteGivenUp(); }catch(_){}
    }
    return;
  }
  const a = document.activeElement;
  if(a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) return;
  try{ await loadWorklist(); }catch(_){ return; }
  if(S.pool){ await loadPoolPapers(); return; }
  if(!S.folder) renderWorklist();
}

const nameInput = $("#editorName");
let nameTimer = null;
nameInput.addEventListener("input", ()=>{
  clearTimeout(nameTimer);
  nameTimer = setTimeout(async ()=>{
    S.editor = nameInput.value.trim();
    try{ await api("/api/editor",{editor:S.editor}); }catch(_){}
    if(!S.indico) return;
    try{ await loadWorklist(); }catch(_){ return; }
    if(!S.folder){ renderWorklist(); return; }
    const row = S.papers.find(x=>x.folder===S.folder);
    if(row && S.paper){ S.paper.indico = row.indico;
      if(S.paper.screened) renderPaper(); else renderUnprepared(); }
  }, 500);
});

/* Who is at this desk. Joined to the chief's desk, an editor is known by
   their Indico account, so there is no name to type. */
function showWho(){
  const joined = !!S.pool, managing = !!S.chief;
  $("#whoName").hidden = joined || managing;
  const who = $("#whoIndico"); who.hidden = !(joined || managing);
  if(managing){ who.textContent = "Chief editor · managing page"; return; }
  if(!joined) return;
  const a = S.account || {};
  who.textContent = a.connected ? "Indico: "+(a.name || "connected")
    : "Not connected to Indico";
}

/* After the Indico account changes, start again from the server's view. */
async function reboot(){
  try{
    const setup = await api("/api/setup");
    S.chief = setup.chief || null; S.account = setup.account || null;
    S.indicoSync = setup.indico_sync || null; S.pool = setup.pool || null;
    S.editor = setup.editor || (S.pool ? "" : S.editor); nameInput.value = S.editor;
    showWho();
    await loadWorklist();
    if(S.chief){ S.chiefPapers = null; loadChiefPapers(); }
    if(S.pool) loadPoolPapers();
    if(!S.folder) renderWorklist();
  }catch(err){ toast(err.message, true); }
}

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
    S.chief = setup.chief || null;
    S.sharing = setup.sharing || null;
    S.account = setup.account || null;
    S.indicoSync = setup.indico_sync || null;
    S.pool = setup.pool || null;
    S.editing = setup.editing || null;
    if(S.pool) $("#rootName").textContent = "copies of papers from "+S.pool.url;
    showWho();
    if((setup.jobs||[]).length){ S.job = setup.jobs[0]; pollJob(); }
    await loadWorklist();
    renderWorklist();
    if(S.chief) loadChiefPapers();
    if(S.pool) loadPoolPapers();
    if(!S.editor && !S.pool && !S.chief) nameInput.focus();
    if(S.chief || S.pool) setInterval(keepUpToDate, 10000);
    const wanted = new URLSearchParams(location.hash.slice(1));
    if(wanted.get("paper") && !S.chief){
      await openPaper(wanted.get("paper"));
      const tab = wanted.get("tab");
      if(wanted.get("side")==="pdf") S.side = "pdf";
      if(S.paper && S.paper.screened && TABS.some(([key])=>key===tab)){ S.tab = tab; renderPaper(); }
    }
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
