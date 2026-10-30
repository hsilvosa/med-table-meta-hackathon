"""The planner's CSS: large text and buttons, cards, the step bar."""

from planner.common import embedded


def css(scale: float) -> str:
    return f"""
<style>
html {{ font-size: {int(18 * scale)}px; }}
.block-container {{ padding-top: {1 if embedded() else 3.5}rem; max-width: 820px; }}
h1, h2, h3 {{ letter-spacing: 0; }}
.stButton > button, .stDownloadButton > button {{ min-height: 3.1rem; font-size: 1.05rem; font-weight: 650; border-radius: 12px; }}
.stButton button p, .stDownloadButton button p {{ font-size: 1.15rem !important; font-weight: 700 !important; }}
[data-testid="stButtonGroup"] button p {{ font-size: 1.15rem !important; font-weight: 700 !important; }}
[data-testid="stBaseButton-tertiary"] {{ min-height: 2.6rem; padding: .3rem 1.1rem; color: #a02020; border: 1px solid #ecc3c3; background: #fff; }}
[data-testid="stBaseButton-tertiary"] p {{ font-size: 1rem !important; font-weight: 650 !important; color: #a02020 !important; }}
[data-testid="stBaseButton-tertiary"]:hover {{ background: #fdeeee; border-color: #d98a8a; }}
[data-testid="stBaseButton-primary"] {{ background: #1b5e8a; border-color: #1b5e8a; }}
[data-testid="stBaseButton-primary"]:disabled {{ background: #c9d3dd; border-color: #c9d3dd; color: #fff; }}
[data-testid="stButtonGroup"] button {{ min-height: 2.9rem; font-size: 1.1rem; font-weight: 650; }}
[data-testid="stWidgetLabel"] p {{ font-size: 1.05rem; font-weight: 650; color: #1f2933; }}
[data-testid="stCheckbox"] label p {{ font-size: 1.1rem; font-weight: 600; }}
[data-testid="stCheckbox"] label > div:nth-of-type(1) {{ width: 1.9rem; height: 1.9rem; min-width: 1.9rem; border-width: 3px; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] {{ background: #1b5e8a !important; border-color: #1b5e8a !important; }}
[data-testid="stButtonGroup"] button[aria-checked="true"] p {{ color: #fff !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] {{ background: #1b5e8a !important; border-color: #1b5e8a !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] p, [data-testid="stButtonGroup"] button[data-variant="pills"][aria-pressed="true"] span {{ color: #fff !important; }}
[data-testid="stButtonGroup"] button[data-variant="pills"] {{ min-height: 2.9rem; min-width: 3.4rem; }}
[data-testid="stTabs"] button p {{ font-size: 1.05rem; font-weight: 650; }}
.mt-title {{ font-size: 1.75rem !important; font-weight: 800 !important; margin: .2rem 0 .1rem !important; line-height: 1.2 !important; color: #14202b; }}
.mt-lead {{ font-size: 1.12rem !important; color: #33404d; margin: 0 0 .8rem !important; line-height: 1.5 !important; }}
.mt-steps {{ display: flex; gap: 6px; margin: .2rem 0 1rem; }}
.mt-s {{ flex: 1; text-align: center; font-size: .9rem; color: #5d6875; border-top: 6px solid #d3dae3; padding-top: 6px; line-height: 1.2; }}
.mt-s b {{ display: block; font-size: .95rem; color: #5d6875; }}
.mt-s.done {{ border-color: #1f8a5b; }} .mt-s.done b {{ color: #1f8a5b; }}
.mt-s.cur {{ border-color: #1b5e8a; color: #1b5e8a; font-weight: 700; }} .mt-s.cur b {{ color: #1b5e8a; }}
.mt-box {{ border-radius: 12px; padding: 12px 16px; margin: 10px 0; line-height: 1.45; font-size: 1.02rem; }}
.mt-box.tip {{ background: #eef5fb; border: 1px solid #c4dcf0; }}
.mt-box.warn {{ background: #fff6e0; border: 1px solid #f0c777; }}
.mt-box.bad {{ background: #fdeeee; border: 1px solid #eba5a5; }}
.mt-box.ok {{ background: #eaf7f0; border: 1px solid #8fd0ad; }}
.mt-box b.t {{ display: block; font-size: 1.08rem; margin-bottom: 2px; }}
.mt-chip {{ display: inline-block; padding: 2px 11px; border-radius: 999px; font-size: .85rem; font-weight: 700; margin: 0 5px 5px 0; }}
.mt-chip.ok {{ background: #d6f0e2; color: #0f5a35; }} .mt-chip.warn {{ background: #ffecc2; color: #6f4800; }}
.mt-chip.bad {{ background: #fbd7d7; color: #8f1818; }} .mt-chip.grey {{ background: #e4e9ef; color: #323d49; }}
.mt-card {{ display: flex; gap: 14px; align-items: center; border: 1px solid #d7dde4; border-radius: 14px; padding: 12px 14px; margin: 0 0 10px; background: #fff; }}
.mt-card.plain {{ border: none; padding: 0; margin: 0 0 6px; }}
.mt-pic {{ flex: none; width: 112px; height: 84px; object-fit: contain; background: #f4f6f8; border-radius: 8px; }}
.mt-name {{ font-weight: 750; line-height: 1.25; font-size: 1.1rem; margin: 2px 0 6px; }}
.mt-meta {{ color: #55606e; font-size: .88rem; }}
.mt-agenda {{ width: 100%; border-collapse: collapse; }}
.mt-agenda td {{ padding: 14px 12px; border-bottom: 2px solid #e3e7ec; vertical-align: top; font-size: 1.12rem; }}
.mt-agenda tr:last-child td {{ border-bottom: none; }}
.mt-slot {{ width: 8.5rem; font-weight: 800; }} .mt-time {{ display: block; color: #55606e; font-weight: 500; font-size: .9rem; }}
.mt-dose {{ font-weight: 800; }} .mt-empty {{ color: #7d8793; }}
.mt-quote {{ color: #323d49; font-style: italic; margin-top: 6px; }}
.mt-brand {{ font-size: .95rem !important; font-weight: 800 !important; color: #1b5e8a; margin: 0 0 .3rem !important; letter-spacing: .02em; }}
.mt-pic.none {{ display: flex; align-items: center; justify-content: center; color: #7d8793; font-size: .8rem; text-align: center; }}
.mt-sum {{ font-size: 1.05rem; line-height: 1.5; margin: 4px 0 0; }}
.mt-sum b {{ font-weight: 800; }}
[data-testid="stProgress"] p {{ font-size: 1.05rem !important; font-weight: 700 !important; }}
.mt-heads {{ color: #6f4800; font-weight: 650; margin-top: 4px; line-height: 1.4; }}
.mt-alert {{ color: #8f1818; font-weight: 700; margin-top: 4px; }}
.mt-hint {{ color: #55606e; font-size: .95rem !important; margin: -4px 0 6px !important; }}
@media (max-width: 560px) {{ .mt-card {{ gap: 10px; align-items: flex-start; }} .mt-pic {{ width: 76px; height: 60px; }} .mt-agenda td {{ padding: 10px 6px; }} .mt-slot {{ width: 6rem; }} }}
</style>"""
