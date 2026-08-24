"""Page shell + CSS. Design tokens follow the product mockup (navy palette,
RTL, confidence colors) so the document and the app read as one system."""

from __future__ import annotations

CSS = """
:root{
  --navy-900:#0a1535; --navy-700:#1a3a8f; --navy-600:#0d4e8a;
  --blue-500:#4285f4; --blue-600:#1565c0;
  --bg:#eef0f4; --ink:#1a1a2e; --muted:#5a627a; --line:#e0e4f0;
  --surface:#ffffff; --soft:#f8f9ff;
  --c-high-bg:#e8f5e9; --c-high-fg:#2e7d32; --c-high-bd:#a5d6a7;
  --c-mod-bg:#e3f2fd;  --c-mod-fg:#1565c0;  --c-mod-bd:#90caf9;
  --c-lim-bg:#fff3e0;  --c-lim-fg:#e65100;  --c-lim-bd:#ffcc80;
  --c-emg-bg:#ffebee;  --c-emg-fg:#c62828;  --c-emg-bd:#ef9a9a;
}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI','Arial',sans-serif;background:var(--bg);
  color:var(--ink);font-size:15.5px;line-height:1.85;direction:rtl}
.page{max-width:900px;margin:0 auto;background:var(--surface);
  box-shadow:0 1px 3px rgba(10,21,53,.08),0 6px 22px rgba(10,21,53,.06)}
.cover{background:linear-gradient(135deg,#0a1535 0%,#1a3a8f 55%,#0d4e8a 100%);
  color:#fff;padding:64px 48px;text-align:center}
.cover .kicker{font-size:13px;letter-spacing:.14em;opacity:.8;text-transform:uppercase}
.cover h1{margin:14px 0 8px;font-size:2.1rem;line-height:1.3}
.cover .sub{opacity:.88;font-size:15px;margin-bottom:26px}
.cover .metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;
  max-width:640px;margin:0 auto}
.cover .metric{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.16);
  border-radius:12px;padding:12px 8px}
.cover .metric .n{font-size:1.5rem;font-weight:800}
.cover .metric .l{font-size:12px;opacity:.85;margin-top:2px}
.body{padding:40px 48px 64px}
h2.chapter{color:var(--navy-900);font-size:1.5rem;border-bottom:3px solid var(--navy-700);
  padding-bottom:10px;margin:44px 0 8px;display:flex;align-items:center;gap:12px;
  justify-content:space-between}
h3{color:var(--navy-700);font-size:1.13rem;margin:26px 0 6px}
p{margin:0 0 14px}
cite{color:var(--navy-700);font-weight:600;font-style:normal;background:#e8f0fe;
  border-radius:5px;padding:0 5px;white-space:nowrap}
cite.wcite{background:#fff3e0;color:#e65100;border-bottom:2px dotted #e65100}
.badge{display:inline-flex;align-items:center;border-radius:12px;padding:2px 12px;
  font-size:12.5px;font-weight:700;border:1px solid transparent;vertical-align:middle}
.badge.HIGH{background:var(--c-high-bg);color:var(--c-high-fg);border-color:var(--c-high-bd)}
.badge.MODERATE{background:var(--c-mod-bg);color:var(--c-mod-fg);border-color:var(--c-mod-bd)}
.badge.LIMITED{background:var(--c-lim-bg);color:var(--c-lim-fg);border-color:var(--c-lim-bd)}
.badge.EMERGING{background:var(--c-emg-bg);color:var(--c-emg-fg);border-color:var(--c-emg-bd)}
.callout{border-radius:10px;padding:14px 18px;margin:18px 0;border-right:5px solid;
  background:var(--soft);font-size:14.5px}
.callout.blue{background:#e8f0fe;border-color:var(--blue-500)}
.callout.green{background:var(--c-high-bg);border-color:var(--c-high-fg)}
.callout.red{background:var(--c-emg-bg);border-color:var(--c-emg-fg)}
.callout.orange{background:var(--c-lim-bg);border-color:var(--c-lim-fg)}
.callout.purple{background:#f3e8ff;border-color:#7b1fa2}
.notice{background:#fff8e1;border-right:5px solid #f9a825;border-radius:10px;
  padding:14px 18px;margin:26px 0;font-size:14px;color:#5d4037}
.toc-box{background:var(--soft);border:1px solid var(--line);border-radius:12px;
  padding:20px 26px;margin:30px 0;column-count:2;column-gap:36px}
.toc-box h3{margin-top:0;column-span:all}
.toc-box ol{margin:0;padding-inline-start:20px}
.toc-box li{margin-bottom:6px;break-inside:avoid}
.toc-box .secs{color:var(--muted);font-size:12.5px}
.bib{padding-inline-start:0;list-style:none;counter-reset:bib}
.bib li{margin-bottom:12px;padding-right:44px;position:relative;font-size:14px}
.bib li::before{counter-increment:bib;content:"[" counter(bib) "]";
  position:absolute;right:0;top:0;font-weight:700;color:var(--navy-700)}
.bib .vlabel{font-size:12px;font-weight:700;border-radius:8px;padding:1px 8px;margin-inline-start:8px}
.vlabel.ok{background:var(--c-high-bg);color:var(--c-high-fg)}
.vlabel.na{background:#f3f4f8;color:#5a627a}
.vlabel.warn{background:var(--c-lim-bg);color:var(--c-lim-fg)}
.vlabel.bad{background:var(--c-emg-bg);color:var(--c-emg-fg)}
.transparency{background:var(--soft);border:1px solid var(--line);border-radius:12px;
  padding:22px 26px;margin:34px 0}
.transparency table{border-collapse:collapse;width:100%;font-size:13.5px}
.transparency td,.transparency th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:right}
details{margin-top:14px}
details summary{cursor:pointer;font-weight:700;color:var(--navy-700)}
.audit{font-family:'SF Mono','Courier New',monospace;font-size:12px;direction:ltr;
  text-align:left;background:#0b1020;color:#c7d0e8;border-radius:10px;
  padding:14px 16px;max-height:340px;overflow:auto;line-height:1.7}
.prisma-flow{display:flex;flex-direction:column;align-items:center;gap:4px;margin:14px 0}
.prisma-flow .step{background:#fff;border:1.5px solid var(--navy-700);border-radius:10px;
  padding:8px 22px;font-size:13.5px;font-weight:600;color:var(--navy-900)}
.prisma-flow .arrow{color:var(--navy-700);font-size:18px;line-height:1}
.formula{background:var(--soft);border:1px solid var(--line);border-radius:10px;
  padding:12px 18px;margin:16px 0;direction:ltr;text-align:center;overflow-x:auto}
.trl{background:#ede7f6;color:#5e35b1;border:1px solid #d1c4e9;border-radius:9px;
  padding:1px 9px;font-size:12px;font-weight:700;white-space:nowrap}
.case-card{border:1px solid var(--line);border-radius:12px;margin:18px 0;overflow:hidden}
.case-card .case-head{background:var(--soft);border-bottom:1px solid var(--line);
  padding:10px 16px;font-weight:700;color:var(--navy-900);font-size:14px}
.case-card>div:last-child{padding:12px 16px;font-size:14.5px}
.case-card .tag{background:#e8f0fe;color:var(--navy-700);border-radius:8px;
  padding:1px 8px;font-size:11.5px;margin-inline-start:6px;font-weight:600}
.example-card{border:1px solid var(--line);border-inline-start:4px solid #2f855a;
  border-radius:12px;margin:18px 0;overflow:hidden;background:#f6fbf8}
.example-card .ex-head{background:#e7f4ec;padding:10px 16px;font-weight:700;
  color:#22543d;font-size:14px}
.example-card .ex-row{padding:8px 16px;font-size:14px;border-top:1px solid #e2efe7}
.example-card .ex-lbl{font-weight:700;color:#2f855a}
.example-card .ex-result{font-weight:700}
table.tbl{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}
table.tbl th{background:var(--navy-900);color:#fff;padding:9px 12px;text-align:right;
  font-weight:600;font-size:13px}
table.tbl td{padding:8px 12px;border-bottom:1px solid var(--line)}
table.tbl tr:nth-child(even) td{background:var(--soft)}
table.tbl td.best{background:var(--c-high-bg);color:var(--c-high-fg);font-weight:700}
table.tbl td.bad{background:var(--c-emg-bg);color:var(--c-emg-fg);font-weight:700}
.exec{background:var(--soft);border:1px solid var(--line);border-radius:14px;
  padding:24px 28px;margin:30px 0}
.exec h3{margin-top:0}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
  gap:12px;margin:18px 0}
.kpi-box{background:linear-gradient(135deg,#e8f0fe,#f3e8ff);border-radius:10px;
  padding:14px;border-right:4px solid var(--navy-700)}
.kpi-box .num{font-size:1.6rem;font-weight:800;color:var(--navy-700);line-height:1.1}
.kpi-box .label{font-size:12.5px;font-weight:700;margin-top:4px}
.kpi-box .desc{font-size:11.5px;color:var(--muted);margin-top:2px}
.conclusions{margin:14px 0;padding:0;list-style:none}
.conclusions li{padding:6px 0;display:flex;gap:8px;font-size:14.5px}
.conclusions li::before{content:"✓";color:var(--c-high-fg);font-weight:800;flex-shrink:0}
.roi{background:linear-gradient(135deg,#e8f5e9,#e3f2fd);border-right:5px solid
  var(--c-high-fg);border-radius:10px;padding:14px 18px;margin:14px 0;font-weight:600}
.scorecard{background:var(--surface);border:2px solid var(--navy-700);border-radius:14px;
  padding:22px 26px;margin:30px 0}
.scorecard .score-line{display:flex;align-items:baseline;gap:14px;margin-bottom:16px}
.scorecard .score-num{font-size:2.6rem;font-weight:800;color:var(--navy-700)}
.scorecard .metric-row{display:grid;grid-template-columns:170px 1fr 40px;gap:10px;
  align-items:center;margin-bottom:7px;font-size:13px}
.scorecard .bar{height:8px;border-radius:6px;background:#e7eaf3;overflow:hidden}
.scorecard .bar>span{display:block;height:100%;border-radius:6px;
  background:linear-gradient(90deg,#1a3a8f,#4285f4)}
.score-warn{background:var(--c-emg-bg);border:1px solid var(--c-emg-bd);
  color:var(--c-emg-fg);border-radius:10px;padding:12px 16px;margin-top:12px;font-weight:700}
.ideation{border:2px dashed #b39ddb;border-radius:14px;padding:22px 26px;margin:30px 0;
  background:#faf5ff}
.gen-badge{background:#ede7f6;color:#5e35b1;border:1px solid #d1c4e9;border-radius:9px;
  padding:1px 9px;font-size:11px;font-weight:700;margin-inline-start:8px}
.ideation h4{margin:16px 0 6px;color:#5e35b1}
.ideation ul{margin:0;padding-inline-start:20px;font-size:14px}
.charts{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:24px 0}
.charts figure{margin:0;border:1px solid var(--line);border-radius:12px;padding:10px;
  background:#fff;break-inside:avoid}
@media(max-width:760px){.charts{grid-template-columns:1fr}}
.wsrc{padding-inline-start:0;list-style:none}
.wsrc li{margin-bottom:10px;padding-right:52px;position:relative;font-size:13.5px}
.wsrc li .wnum{position:absolute;right:0;top:0;font-weight:700;color:#e65100}
.wsrc .quote{color:var(--muted);font-size:12.5px;font-style:italic}
.wsrc .primary{font-size:12.5px;margin-top:3px}
.wsrc .primary a{color:#1d6b2f;font-weight:600}
details.signals{margin-top:6px;font-size:12.5px}
details.signals summary{cursor:pointer;color:#5a627a;font-weight:600}
details.signals .sig-tbl{margin-top:5px;border-collapse:collapse;width:100%}
details.signals .sig-tbl td{border-top:1px solid #eceef4;padding:3px 6px;vertical-align:top}
details.signals .sig-tbl td:first-child{width:18px;text-align:center}
details.signals .sig-tbl td:nth-child(2){white-space:nowrap;color:#3b4252;font-weight:600}
@media print{
  @page{size:A4;margin:18mm 16mm}
  body{background:#fff}
  .page{box-shadow:none;max-width:none}
  h2.chapter{page-break-before:always;break-before:page}
  .callout,.notice,.transparency{break-inside:avoid}
}
"""


def page(title: str, body: str, lang: str = "he") -> str:
    direction = "rtl" if lang in ("he", "ar") else "ltr"
    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{direction}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{CSS}</style>
<script>
window.MathJax = {{tex: {{displayMath: [['\\\\[','\\\\]']], inlineMath: [['\\\\(','\\\\)']]}}}};
</script>
<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
</head>
<body>
<div class="page">
{body}
</div>
</body>
</html>
"""
