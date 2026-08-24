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
</head>
<body>
<div class="page">
{body}
</div>
</body>
</html>
"""
