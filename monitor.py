#!/usr/bin/env python3
"""
MEXC Launchpad 认购监控（GitHub Actions 版本）
每天 9/16/20 北京时间记录认购数据，生成趋势图发到 Lark Webhook。

架构：GitHub Actions cron → curl_cffi → MEXC API → matplotlib → 提交回仓库 → Lark webhook
图表通过 raw.githubusercontent.com 公开访问，无需单独上传。
"""

import json
import os
import urllib.request
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 配置 ────────────────────────────────────────────────
PROJECT_ID   = "70"
PROJECT_NAME = "SpaceX xStocks (SPCXX)"

LARK_WEBHOOK = os.environ["LARK_WEBHOOK"]

GITHUB_REPO  = "AndyJ-2026/mexc-charts"
CHART_REMOTE = "chart.png"

SCRIPT_DIR = Path(__file__).parent
DATA_FILE  = SCRIPT_DIR / "data.json"
CHART_FILE = SCRIPT_DIR / "chart.png"

CST = timezone(timedelta(hours=8))
# ─────────────────────────────────────────────────────────


def fetch_pool_data() -> dict:
    from curl_cffi import requests
    url = f"https://www.mexc.com/api/financialactivity/launchpad/detail/{PROJECT_ID}"
    delays = [5, 15, 30, 45, 60, 60, 60]
    last_exc = None
    for attempt, delay in enumerate([0] + delays):
        if delay:
            print(f"[retry {attempt}/{len(delays)}] 等待 {delay}s 后重试...", file=sys.stderr)
            time.sleep(delay)
        try:
            r = requests.get(url, impersonate="chrome", timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_exc = e
            print(f"[fetch 失败 attempt={attempt}] {type(e).__name__}: {e}", file=sys.stderr)
    raise last_exc


def parse_snapshot(data: dict) -> dict:
    coins = data["data"]["launchpadTakingCoins"]
    pools = []
    for c in coins:
        if c["onlyForNewUser"]:
            name = "新用户专属池"
        elif c["investCurrency"] == "USD1":
            name = "USD1池"
        else:
            name = "老用户池"
        cap = float(c["supply"]) * float(c["takingPrice"])
        amt = float(c["takingAmount"])
        pools.append({
            "name": name,
            "amount": round(amt),
            "cap": round(cap),
            "pct": round(amt / cap * 100, 2) if cap else 0,
            "currency": c["investCurrency"],
        })
    return {
        "ts": datetime.now(CST).strftime("%m/%d %H:%M"),
        "pools": pools,
        "join_num": data["data"]["joinNum"],
        "status": data["data"]["activityStatus"],
    }


def load_history() -> list:
    if DATA_FILE.exists():
        with open(DATA_FILE) as f:
            return json.load(f)
    return []


def save_history(h: list):
    with open(DATA_FILE, "w") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def generate_chart(history: list, out: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    import matplotlib.gridspec as gridspec
    import matplotlib.patches as mpatches
    import numpy as np

    plt.rcParams["font.family"] = [
        "Noto Sans CJK SC", "Noto Sans CJK JP",
        "PingFang HK", "Heiti TC", "Arial Unicode MS", "DejaVu Sans",
    ]

    pool_names  = ["新用户专属池", "老用户池", "USD1池"]
    short_names = ["新用户池",    "老用户池",  "USD1池"]
    bar_colors  = ["#5b8dd9",    "#f5a623",   "#50e3c2"]
    line_colors = ["#7eb3ff",    "#ffc86b",   "#7dfff0"]
    pct_colors  = ["#7eb3ff",    "#ffc86b",   "#7dfff0"]

    labels  = [h["ts"] for h in history]
    amounts = {n: [] for n in pool_names}
    pcts    = {n: [] for n in pool_names}

    for snap in history:
        pm = {p["name"]: p for p in snap["pools"]}
        for n in pool_names:
            p = pm.get(n)
            amounts[n].append(p["amount"] if p else 0)
            pcts[n].append(p["pct"]    if p else 0)

    x = np.arange(len(labels))
    w = 0.25
    n_data = len(history)

    fig_w = max(12, n_data * 1.6)
    chart_h = 6.5
    row_h   = 0.38
    table_h = max(2.0, n_data * row_h + 1.0)
    fig_h   = chart_h + table_h

    fig = plt.figure(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor("#0f1117")

    gs = gridspec.GridSpec(
        2, 1,
        height_ratios=[chart_h, table_h],
        hspace=0.06,
        top=0.96, bottom=0.01, left=0.07, right=0.93,
    )

    ax1 = fig.add_subplot(gs[0])
    ax1.set_facecolor("#1a1d26")

    for i, n in enumerate(pool_names):
        ax1.bar(x + (i-1)*w, amounts[n], width=w,
                facecolor="none", edgecolor=bar_colors[i], linewidth=1.5,
                label=f"{short_names[i]} 认购量", zorder=2)

    ax1.set_ylabel("认购量 (USDT)", color="#666", fontsize=9)
    ax1.tick_params(axis="y", labelcolor="#777", labelsize=8)
    ax1.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _:
            f"{v/1e6:.2f}M" if v >= 1e6
            else f"{v/1e3:.0f}K" if v >= 1e3
            else str(int(v)))
    )
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels, rotation=18, ha="right", color="#888", fontsize=8)
    ax1.tick_params(axis="x", colors="#777")
    for spine in ax1.spines.values():
        spine.set_color("#2a2d3a")
    ax1.grid(axis="y", color="#252830", zorder=0, linewidth=0.6)

    ax2 = ax1.twinx()
    ax2.set_facecolor("none")
    for i, n in enumerate(pool_names):
        vals = pcts[n]
        ax2.plot(x, vals, color=line_colors[i], linewidth=2,
                 linestyle="--", marker="o", markersize=4,
                 label=f"{short_names[i]} 比例", zorder=3)
        for j, v in enumerate(vals):
            if v >= 100:
                ax2.plot(x[j], v, "o", color="#ff4444", markersize=7, zorder=4)

    latest_pools = {p["name"]: p for p in history[-1]["pools"]}
    for i, n in enumerate(pool_names):
        p = latest_pools.get(n)
        if p and p["cap"]:
            ax1.axhline(p["cap"], color=bar_colors[i], linewidth=1.0,
                        linestyle="--", alpha=0.55, zorder=1)
            ax1.text(len(labels) - 0.5, p["cap"], f" {short_names[i]} 满额线",
                     color=bar_colors[i], fontsize=7, alpha=0.85,
                     va="bottom", ha="right", zorder=1)

    max_pct = max((max(pcts[n]) for n in pool_names if pcts[n]), default=100)
    ax2.set_ylim(0, max(max_pct * 1.1, 120))
    ax2.set_ylabel("认购比例 (%)", color="#666", fontsize=9)
    ax2.tick_params(axis="y", labelcolor="#777", labelsize=8)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    for spine in ax2.spines.values():
        spine.set_color("#2a2d3a")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1+h2, l1+l2, loc="upper left", fontsize=7, ncol=3,
               facecolor="#1a1d26", edgecolor="#2a2d3a", labelcolor="#aaa")

    ax1.set_title(
        f"Launchpad 认购数据\n"
        "柱形图 = 认购量 · 折线图 = 认购比例（认购量 / 池子上限）· 同色虚线 = 各池满额线（柱子高出虚线 = 超募）",
        color="#ddd", fontsize=11, pad=8
    )

    ax_t = fig.add_subplot(gs[1])
    ax_t.set_facecolor("#131620")
    ax_t.set_xlim(0, 1)
    ax_t.set_ylim(0, 1)
    ax_t.axis("off")

    cols = [
        (0.06, "left",  "时间点",       None),
        (0.22, "right", "新用户池 认购量", None),
        (0.35, "right", "新用户池 比例",  pct_colors[0]),
        (0.50, "right", "老用户池 认购量", None),
        (0.63, "right", "老用户池 比例",  pct_colors[1]),
        (0.79, "right", "USD1池 认购量",  None),
        (0.93, "right", "USD1池 比例",    pct_colors[2]),
    ]

    total_slots = n_data + 1
    slot_h = 1.0 / (total_slots + 0.6)
    header_y = 1.0 - slot_h * 0.65

    for cx, ca, hdr, _ in cols:
        ax_t.text(cx, header_y, hdr,
                  ha=ca, va="center", fontsize=7.5,
                  color="#cccccc", transform=ax_t.transAxes)

    sep_y = 1.0 - slot_h * 1.15
    ax_t.plot([0.02, 0.98], [sep_y, sep_y],
              color="#2a2d3a", linewidth=0.8, transform=ax_t.transAxes)

    for ri, snap in enumerate(history):
        pm     = {p["name"]: p for p in snap["pools"]}
        latest = (ri == n_data - 1)
        ry     = 1.0 - slot_h * (ri + 1.7)

        row = [snap["ts"]]
        for n in pool_names:
            p = pm.get(n)
            row.append(f"{p['amount']:,}" if p else "—")
            row.append(f"{p['pct']:.2f}%" if p else "—")

        if latest:
            rect = mpatches.FancyBboxPatch(
                (0.02, ry - slot_h * 0.48), 0.96, slot_h * 0.90,
                boxstyle="round,pad=0.005",
                facecolor="#1b2040", edgecolor="#3a4070",
                linewidth=1.2, transform=ax_t.transAxes, zorder=0,
            )
            ax_t.add_patch(rect)

        for ci, (cx, ca, _, pct_col) in enumerate(cols):
            is_pct  = pct_col is not None
            if is_pct:
                color = pct_col
            elif latest:
                color = "#ffffff"
            else:
                color = "#999999"
            fw = "bold" if latest else "normal"
            ax_t.text(cx, ry, row[ci],
                      ha=ca, va="center", fontsize=7.5,
                      color=color, fontweight=fw,
                      transform=ax_t.transAxes)

        if not latest:
            line_y = ry - slot_h * 0.52
            ax_t.plot([0.02, 0.98], [line_y, line_y],
                      color="#1c1f2c", linewidth=0.5, transform=ax_t.transAxes)

    plt.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#0f1117")
    plt.close()
    print(f"图表生成: {out}")


def chart_raw_url() -> str:
    return (
        f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{CHART_REMOTE}"
        f"?t={int(time.time())}"
    )


def send_card(img_url: str, snapshot: dict):
    pools = snapshot["pools"]
    total_u = sum(p["amount"] for p in pools)

    lines = [f"💰 **总认购**　{total_u:,} U"]
    for p in pools:
        icon = "🔴" if p["pct"] >= 300 else "🟠" if p["pct"] >= 100 else "🟡" if p["pct"] >= 50 else "🟢"
        lines.append(
            f"{icon} **{p['name']}**　{p['amount']:,} {p['currency']}　**{p['pct']:.1f}%**"
        )
    body_md = "\n".join(lines)

    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 {PROJECT_NAME} · {snapshot['ts']}  参与 {snapshot['join_num']:,} 人",
                },
                "template": "blue",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body_md}},
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📈 查看趋势图"},
                            "type": "primary",
                            "url": img_url,
                        }
                    ],
                },
            ],
        },
    }

    payload = json.dumps(card).encode()
    req = urllib.request.Request(
        LARK_WEBHOOK, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def main():
    print(f"[{datetime.now(CST).isoformat()}] 开始采集...")

    raw      = fetch_pool_data()
    snapshot = parse_snapshot(raw)
    print(f"数据: {snapshot['ts']} | " + " | ".join(f"{p['name']} {p['pct']}%" for p in snapshot["pools"]))

    history = load_history()
    history.append(snapshot)
    save_history(history)

    generate_chart(history, CHART_FILE)

    img_url = chart_raw_url()
    print(f"图片 URL: {img_url}")

    result = send_card(img_url, snapshot)
    print(f"发送完成: {result}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print(f"[ERROR] {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
