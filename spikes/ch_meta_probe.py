#!/usr/bin/env python3
"""ch_meta_probe: 不用金鑰，探測 Meta 平台（Threads / Facebook / Instagram）的官方端點。

驗證三件事：
1. 哪些端點不帶 token 就能用（oEmbed），哪些一定要 token（keyword_search 等）。
2. oEmbed 回傳的 html 裡有沒有貼文文字或連結（能不能拿來給模型讀）。
3. 各站 robots.txt 對自動化收集的聲明。

執行：python3 spikes/ch_meta_probe.py
只用標準函式庫；不含任何金鑰。
"""
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

UA = "pickfit-spike/0.1 (+research; contact via repo)"

# 官方文件裡的範例貼文（Threads oEmbed 文件、Instagram oEmbed 文件、Facebook 舊範例）
THREADS_POST = "https://www.threads.com/@meta/post/DDzbnVKx57R"
IG_POST = "https://www.instagram.com/p/fA9uwTtkSN/"
FB_POST = "https://www.facebook.com/facebook/posts/10153231379946729"


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def visible_text(embed_html):
    """把 embed html 去掉 svg / 標籤，只留看得到的文字。"""
    h = re.sub(r"<svg.*?</svg>", "", embed_html, flags=re.S)
    h = re.sub(r"<script.*?</script>", "", h, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", h)
    return html.unescape(re.sub(r"\s+", " ", t)).strip()


def summarize(status, body):
    try:
        d = json.loads(body)
    except ValueError:
        return f"HTTP {status} | 非 JSON（{len(body)} bytes）"
    if "error" in d:
        e = d["error"]
        return f"HTTP {status} | error code={e.get('code')} msg={e.get('message')!r}"
    if "html" in d:
        h = d["html"]
        links = sorted(set(re.findall(r'href=\\?"([^"\\]+)', h)))
        return (
            f"HTTP {status} | keys={sorted(d)} | html={len(h)} bytes | "
            f"可見文字={visible_text(h)[:60]!r} | 連結={links[:3]}"
        )
    return f"HTTP {status} | keys={sorted(d)}"


def q(base, **params):
    return base + "?" + urllib.parse.urlencode(params)


PROBES = [
    # (說明, URL)
    ("Threads oEmbed（無 token）", q("https://graph.threads.com/v1.0/oembed", url=THREADS_POST)),
    ("Threads oEmbed 不存在的貼文", q("https://graph.threads.com/v1.0/oembed", url="https://www.threads.com/t/AAAAAAAAAAA")),
    ("Threads keyword_search（無 token）", q("https://graph.threads.com/v1.0/keyword_search", q="buildinpublic")),
    ("Threads profile_lookup（無 token）", q("https://graph.threads.com/v1.0/profile_lookup", username="meta")),
    ("Threads profile_posts（無 token）", q("https://graph.threads.com/v1.0/profile_posts", username="meta")),
    ("Threads /me（無 token）", "https://graph.threads.com/v1.0/me?fields=id"),
    ("Instagram oEmbed（無 token）", q("https://graph.facebook.com/instagram_oembed", url=IG_POST)),
    ("Facebook oembed_post（無 token）", q("https://graph.facebook.com/oembed_post", url=FB_POST)),
    ("Facebook Page feed（無 token）", "https://graph.facebook.com/facebook/feed"),
    ("Facebook pages/search（無 token）", q("https://graph.facebook.com/pages/search", q="opensource")),
    ("Instagram ig_hashtag_search（無 token）", q("https://graph.facebook.com/ig_hashtag_search", q="buildinpublic")),
]

ROBOTS = ["https://www.threads.com/robots.txt", "https://www.instagram.com/robots.txt", "https://www.facebook.com/robots.txt"]


def main():
    print("## 端點探測（不帶任何 token）\n")
    print("| 端點 | 結果 |\n|---|---|")
    for label, url in PROBES:
        status, body = get(url)
        print(f"| {label} | {summarize(status, body).replace('|', '/')} |")

    print("\n## robots.txt 開頭的聲明\n")
    for url in ROBOTS:
        status, body = get(url)
        notice = [ln.lstrip("# ").strip() for ln in body.splitlines()[:12] if ln.startswith("#")]
        print(f"- {url}（HTTP {status}）：{' '.join(notice)[:300] or '（無註解）'}")


if __name__ == "__main__":
    main()
