"""The planner's CSS: the shared design tokens (web/tokens.css), large text and buttons, cards, the step bar."""

from pathlib import Path

from planner.common import embedded

TOKENS = (Path(__file__).resolve().parent.parent / "web" / "tokens.css").read_text(encoding="utf-8").replace('url("fonts/', 'url("app/static/fonts/')


def css(scale: float) -> str:
    return f"""
<style>
{TOKENS}
html {{ font-size: {int(18 * scale)}px; }}
html, body, .stApp, .stMarkdown, button, input, textarea, select {{ font-family: var(--mt-font) !important; }}
.material-symbols-rounded, [data-testid="stIconMaterial"] {{ font-family: "Material Symbols Rounded" !important; }}
.block-container {{ padding-top: {.8 if embedded() else 2.2}rem; padding-bottom: 3rem; max-width: 860px; }}
h1, h2, h3 {{ letter-spacing: 0; }}
[data-testid="stHeader"] {{ background: transparent; }}

/* buttons */
.stButton > button, .stDownloadButton > button, [data-testid="stPopover"] button {{ min-height: 3rem; border-radius: 10px; border-color: var(--mt-line-strong); }}
.stButton button p, .stDownloadButton button p {{ font-size: 1.05rem !important; font-weight: 700 !important; }}
[data-testid="stBaseButton-primary"] {{ background: var(--mt-accent); border-color: var(--mt-accent); }}
[data-testid="stBaseButton-primary"]:hover {{ background: var(--mt-accent-hover); border-color: var(--mt-accent-hover); }}
[data-testid="stBaseButton-primary"]:disabled {{ background: #c9d3dd; border-color: #c9d3dd; color: #fff; }}
[data-testid="stBaseButton-tertiary"] {{ min-height: 2.5rem; padding: .25rem .8rem; color: var(--mt-muted); border: 1px solid transparent; background: transparent; border-radius: 10px; }}
[data-testid="stBaseButton-tertiary"] p {{ font-size: .95rem !important; font-weight: 700 !important; color: var(--mt-muted) !important; }}
[data-testid="stBaseButton-tertiary"]:hover {{ background: var(--mt-bad-soft); border-color: #f0c4c0; }}
[data-testid="stBaseButton-tertiary"]:hover p, [data-testid="stBaseButton-tertiary"]:hover span {{ color: var(--mt-bad) !important; }}

/* inputs */
[data-testid="stWidgetLabel"] p {{ font-size: 1rem; font-weight: 700; color: var(--mt-ink); }}
[data-testid="stCheckbox"] label p {{ font-size: 1.05rem; font-weight: 700; }}
[data-testid="stCheckbox"] label > div:nth-of-type(1) {{ width: 1.8rem; height: 1.8rem; min-width: 1.8rem; border-width: 2px; }}
[data-testid="stButtonGroup"] button {{ min-height: 2.8rem; }}
[data-testid="stButtonGroup"] button p {{ font-size: 1.05rem !important; font-weight: 700 !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"], [data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] {{ background: var(--mt-accent) !important; border-color: var(--mt-accent) !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p, [data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] p,
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] span {{ color: #fff !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] {{ min-height: 2.8rem; min-width: 3.4rem; }}
[data-testid="stSelectbox"] [role="group"] {{ min-height: 3rem; border-radius: 10px; }}
[data-testid="stSelectbox"] input {{ font-size: 1.1rem !important; font-weight: 700 !important; cursor: pointer; }}
[data-testid="stTabs"] button p {{ font-size: 1rem; font-weight: 700; }}
[data-testid="stExpander"] details {{ border-radius: var(--mt-radius); border-color: var(--mt-line); }}
[data-testid="stExpander"] summary p {{ font-weight: 700; }}
[data-testid="stProgress"] p {{ font-size: 1rem !important; font-weight: 700 !important; }}
[data-testid="stProgress"] [role="progressbar"] > div > div {{ background: var(--mt-subtle); }}

/* bordered containers are the cards of the planner */
[data-testid="stVerticalBlock"][class*="BorderWrapper"], div[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: var(--mt-line) !important; border-radius: var(--mt-radius-lg) !important; box-shadow: var(--mt-shadow); background: var(--mt-surface); }}

/* top bar: brand or steps on the left, settings on the right, on one line at every width */
.st-key-mt_top [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; align-items: center; gap: .6rem; }}
.st-key-mt_top [data-testid="stColumn"] {{ min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }}
.st-key-mt_top [data-testid="stColumn"]:last-child {{ flex: 0 0 auto !important; }}
.st-key-mt_top [data-testid="stPopover"] button {{ min-height: 2.6rem; border-color: var(--mt-line); }}
.mt-brandbar {{ display: flex; align-items: center; gap: .6rem; }}
.mt-brandbar img {{ width: 34px; height: 34px; flex: none; }}
.mt-brandbar b {{ display: block; font-size: 1.05rem; line-height: 1.15; }}
.mt-brandbar span span {{ display: block; color: var(--mt-muted); font-size: .9rem; line-height: 1.2; }}

/* steps */
.mt-steps {{ display: flex; gap: .4rem; margin: .1rem 0 1rem !important; padding: 0 !important; list-style: none; }}
.mt-steps li {{ margin: 0 !important; padding-left: .5rem; }}
.mt-s {{ flex: 1; display: flex; align-items: center; gap: .45rem; min-width: 0; font-size: .9rem; color: var(--mt-muted); line-height: 1.15; padding: .45rem .5rem; border-radius: 10px; background: var(--mt-subtle); }}
.mt-s b {{ flex: none; width: 1.55rem; height: 1.55rem; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: .82rem;
          background: var(--mt-surface); border: 1.5px solid var(--mt-line-strong); color: var(--mt-muted); }}
.mt-s span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.mt-s.done {{ color: var(--mt-ok); background: var(--mt-ok-soft); }} .mt-s.done b {{ background: var(--mt-ok); border-color: var(--mt-ok); color: #fff; }}
.mt-s.cur {{ color: var(--mt-accent); background: var(--mt-accent-soft); font-weight: 700; box-shadow: inset 0 0 0 1.5px var(--mt-accent); }}
.mt-s.cur b {{ background: var(--mt-accent); border-color: var(--mt-accent); color: #fff; }}
.st-key-mt_top .mt-steps {{ margin: 0; }}
.st-key-mt_top .mt-s {{ flex: 0 0 auto; }} .st-key-mt_top .mt-s span {{ display: none; }}
.st-key-mt_top .mt-s.cur {{ flex: 1 1 auto; }} .st-key-mt_top .mt-s.cur span {{ display: inline; }}

/* the one-line notice (public demo, not medical advice), with the details folded */
.mt-note {{ margin: 0 0 1.1rem; font-size: .9rem; color: var(--mt-muted); border-radius: 10px; background: var(--mt-subtle); }}
.mt-note summary {{ cursor: pointer; padding: .5rem .8rem; list-style: none; display: flex; gap: .6rem; align-items: baseline; }}
.mt-note summary::-webkit-details-marker {{ display: none; }}
.mt-note summary b {{ color: var(--mt-warn); }}
.mt-note .mt-more {{ margin-left: auto; flex: none; color: var(--mt-accent); font-weight: 700; text-decoration: underline; text-underline-offset: 2px; }}
.mt-note[open] .mt-more {{ visibility: hidden; }}
.mt-note p {{ margin: 0 !important; padding: 0 .8rem .7rem; line-height: 1.5; font-size: .9rem !important; }}

/* titles */
.mt-title {{ font-size: var(--mt-fs-title) !important; font-weight: 700 !important; margin: .1rem 0 .2rem !important; line-height: 1.2 !important; color: var(--mt-ink); }}
.mt-title.sub {{ font-size: var(--mt-fs-lg) !important; margin-top: 1.4rem !important; }}
.mt-lead {{ font-size: 1.08rem !important; color: #3a4652; margin: 0 0 1rem !important; line-height: 1.5 !important; }}

/* message boxes */
.mt-box {{ border-radius: var(--mt-radius); padding: .75rem 1rem; margin: .6rem 0; line-height: 1.45; font-size: 1rem; border: 1px solid; }}
.mt-box.tip {{ background: var(--mt-accent-soft); border-color: #c7dcec; }}
.mt-box.warn {{ background: var(--mt-warn-soft); border-color: var(--mt-warn-line); }}
.mt-box.bad {{ background: var(--mt-bad-soft); border-color: #efb3ad; }}
.mt-box.ok {{ background: var(--mt-ok-soft); border-color: #9fd3b7; }}
.mt-box b.t {{ display: block; font-size: 1.05rem; margin-bottom: 2px; }}

/* chips: state only */
.mt-chip {{ display: inline-flex; align-items: center; gap: .3rem; padding: 1px 10px; border-radius: 999px; font-size: .82rem; font-weight: 700; margin: 0 5px 5px 0; line-height: 1.6; }}
.mt-chip::before {{ content: ""; width: .45rem; height: .45rem; border-radius: 50%; background: currentColor; opacity: .85; }}
.mt-chip.ok {{ background: var(--mt-ok-soft); color: #0f5a35; }} .mt-chip.warn {{ background: var(--mt-warn-soft); color: #6f4800; }}
.mt-chip.bad {{ background: var(--mt-bad-soft); color: #8f1818; }} .mt-chip.grey {{ background: var(--mt-subtle); color: #3a4652; }} .mt-chip.grey::before {{ display: none; }}

/* medicine cards */
.mt-card {{ display: flex; gap: 16px; align-items: flex-start; padding-bottom: .5rem; }}
.mt-card > div:not(.mt-pic) {{ min-width: 0; flex: 1; }}
.mt-pic {{ flex: none; width: 104px; height: 78px; object-fit: contain; background: var(--mt-bg); border-radius: 10px; border: 1px solid var(--mt-line); }}
.mt-pic.none {{ display: flex; align-items: center; justify-content: center; color: #8a96a3; }}
.mt-pic.none svg {{ width: 34px; height: 34px; }}
.mt-name {{ font-weight: 700; line-height: 1.25; font-size: 1.1rem; margin: 0 0 6px; overflow-wrap: anywhere; }}
.mt-meta {{ color: var(--mt-muted); font-size: .9rem; line-height: 1.45; }}
.mt-sum {{ font-size: 1.02rem; line-height: 1.5; margin: 4px 0 0; }}
.mt-sum b {{ font-weight: 700; }}
.mt-heads {{ color: #6f4800; font-weight: 700; margin-top: 4px; line-height: 1.4; font-size: .95rem; }}
.mt-alert {{ color: #8f1818; font-weight: 700; margin-top: 4px; font-size: .95rem; }}
.mt-hint {{ color: var(--mt-muted); font-size: .92rem !important; margin: -2px 0 6px !important; }}
.st-key-mt_cardrow [data-testid="stHorizontalBlock"], [class*="st-key-mtrow_"] [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: .4rem; }}
[class*="st-key-mtrow_"] [data-testid="stColumn"] {{ min-width: 0 !important; width: auto !important; flex: 1 1 auto !important; }}
[class*="st-key-mtrow_"] [data-testid="stColumn"]:last-child {{ flex: 0 0 auto !important; }}

/* doses: a grid of four times of day */
.mt-qhead {{ font-weight: 700; margin: .6rem 0 .2rem; font-size: 1rem; }}
[class*="st-key-mtgrid_"] [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: .6rem; }}
[class*="st-key-mtgrid_"] [data-testid="stColumn"] {{ flex: 1 1 6.5rem !important; min-width: 6.5rem !important; width: auto !important; }}
[class*="st-key-mtgrid_"] [data-testid="stWidgetLabel"] {{ min-height: 2.7em; display: flex; align-items: flex-end; }}
[class*="st-key-mtgrid_"] [data-testid="stWidgetLabel"] p {{ font-size: .95rem; line-height: 1.3; }}

/* the plan */
.mt-agenda {{ width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid var(--mt-line); border-radius: var(--mt-radius); overflow: hidden; }}
.mt-agenda th {{ text-align: left; background: var(--mt-accent); color: #fff; font-size: .9rem; padding: 10px 14px; font-weight: 700; letter-spacing: .02em; }}
.mt-agenda td {{ padding: 14px; border-top: 1px solid var(--mt-line); vertical-align: top; font-size: 1.08rem; }}
.mt-agenda tr:nth-child(even) td {{ background: #fafbfc; }}
.mt-slot {{ width: 9rem; font-weight: 700; }} .mt-time {{ display: block; color: var(--mt-muted); font-weight: 400; font-size: .9rem; }}
.mt-dose {{ font-weight: 700; }} .mt-empty {{ color: #7d8793; }}
.mt-group {{ display: flex; align-items: center; gap: .5rem; font-weight: 700; font-size: 1.05rem; margin: 1rem 0 .3rem; }}
.mt-group span {{ font-size: .82rem; background: var(--mt-warn-soft); color: #6f4800; border-radius: 999px; padding: 0 9px; }}
.mt-finding {{ border: 1px solid var(--mt-line); border-radius: var(--mt-radius); padding: .7rem .9rem; margin: 0 0 .5rem; background: var(--mt-surface); line-height: 1.45; }}
.mt-finding details {{ margin-top: .4rem; }}
.mt-finding summary {{ cursor: pointer; color: var(--mt-accent); font-weight: 700; font-size: .92rem; }}
.mt-quote {{ color: #323d49; font-style: italic; margin-top: 6px; font-size: .95rem; border-left: 3px solid var(--mt-line); padding-left: .7rem; }}

/* downloads */
.mt-dl {{ display: flex; gap: 14px; align-items: center; margin-bottom: .6rem; }}
.mt-dl img, .mt-dl .mt-ico {{ flex: none; width: 76px; height: 96px; object-fit: cover; object-position: top; border: 1px solid var(--mt-line); border-radius: 8px; background: var(--mt-bg); }}
.mt-dl .mt-ico {{ height: 76px; display: flex; align-items: center; justify-content: center; color: var(--mt-accent); }}
.mt-dl .mt-ico svg {{ width: 34px; height: 34px; }}
.mt-dl b {{ display: block; font-size: 1.08rem; margin-bottom: 2px; }}
.mt-dl {{ min-height: 6.6rem; align-items: flex-start; }}
[data-testid="stElementContainer"][height="1px"] {{ position: absolute; opacity: 0; pointer-events: none; }}      /* the scroll-to-top helper */
.mt-dl span {{ color: var(--mt-muted); font-size: .92rem; line-height: 1.4; display: block; }}

@media (max-width: 560px) {{
  .mt-card {{ gap: 10px; }} .mt-pic {{ width: 72px; height: 56px; }}
  .mt-agenda td {{ padding: 10px 8px; }} .mt-slot {{ width: 6rem; }}
  .mt-s span {{ display: none; }} .mt-s.cur span {{ display: inline; }} .mt-s {{ flex: 0 0 auto; padding: .35rem !important; }} .mt-s.cur {{ flex: 1; padding-right: .7rem !important; }}
  .mt-title {{ font-size: 1.5rem !important; }}
}}
</style>"""
