# -*- coding: utf-8 -*-
"""
Jable.TV —— TVBox / WebHTV / FongMi 四壳通用 Python 源   (v2 重写版)
=====================================================================
站点架构: KVS (Kernel Video Sharing) + Cloudflare

通道策略(这是上一版跑不起来的主因,已改):
  主通道 = 纯标准库 urllib  —— 壳里没装 curl_cffi / requests 也能活
  备用   = curl_cffi(Chrome 指纹) -> requests -> 回 urllib
  每个通道独立重试退避, 单次调用有总时间预算, 不会把壳卡死;
  识别到 Cloudflare 挑战页(Just a moment...)当失败处理并换通道,
  绝不再把挑战页当正文返回(那样只会得到空列表 = 壳里显示"暂无视频数据")。

接口契约(四壳): init / homeContent / homeVideoContent / categoryContent
                detailContent / searchContent / playerContent
返回格式: dict。分页字段统一输出【字符串】(两种解析习惯的壳都能吃下);
          任何异常都在内部消化, 不往外抛(抛出去壳里就是"取页失败")。

分类体系(2026-09 现网实测, 逐项校验过):
  最近更新  /latest-updates/N/          共 1630 页
  熱門      /hot/N/
  主題分類  /categories/<slug>/N/       12 个(全量)
  標籤      /tags/<slug>/N/             115 个(全量)
  女優      /models/<slug>/N/           索引 200 页·每页 20, 内置 120 位热门
  搜索      /search/<kw>/N/
播放:        详情页 var hlsUrl = 'xxxx.m3u8' 直出, 播放需带 Referer

自测:  python3 jable.py --selftest      (四接口 + 播放源全链路)
       python3 jable.py --engine        (看当前走哪条通道)
"""
import sys
import re
import json
import time
import gzip
import urllib.parse
import urllib.request
import urllib.error

sys.path.append('..')
try:
    from base.spider import Spider as _Base
except Exception:
    _Base = object

HOST = "https://jable.tv"

# ============================================================ 常量(现网实测)
# 主题分类 12 个
CATS = [
    ("roleplay", "角色劇情"), ("chinese-subtitle", "中文字幕"), ("uniform", "制服誘惑"),
    ("pantyhose", "絲襪美腿"), ("groupsex", "多P群交"), ("insult", "凌辱快感"),
    ("bdsm", "主奴調教"), ("sex-only", "直接開啪"), ("private-cam", "盜攝偷拍"),
    ("uncensored", "無碼解放"), ("pov", "男友視角"), ("lesbian", "女同歡愉"),
]

# 标签 115 个
TAGS = [
    ("3p", "3P"), ("more-than-4-hours", "4小時以上"), ("Cosplay", "Cosplay"), ("ntr", "NTR"),
    ("ol", "OL"), ("10-times-a-day", "一日十回"), ("rainy-day", "下雨天"), ("creampie", "中出"),
    ("female-anchor", "主播"), ("tit-wank", "乳交"), ("wife", "人妻"), ("store", "便利店"),
    ("gym-room", "健身房"), ("idol", "偶像"), ("private-cam", "偷拍"), ("hypnosis", "催眠"),
    ("bunny-girl", "兔女郎"), ("insult", "凌辱"), ("affair", "出軌"), ("grip", "刑具"),
    ("blowjob", "口交"), ("cum-in-mouth", "口爆"), ("stockings", "吊帶襪"), ("kimono", "和服"),
    ("library", "圖書館"), ("groupsex", "多P"), ("sex-beside-husband", "夫目前犯"), ("maid", "女僕"),
    ("for-women", "女性觀眾"), ("wedding-dress", "婚紗"), ("love-potion", "媚藥"), ("dainty", "嬌小"),
    ("school", "學校"), ("private-teacher", "家庭教師"), ("housewife", "家政婦"), ("girl", "少女"),
    ("big-tits", "巨乳"), ("giant", "巨漢"), ("age-difference", "年齡差"), ("shoplifting", "店鋪盜竊"),
    ("toilet", "廁所"), ("avenge", "復仇"), ("couple", "情侶"), ("thanksgiving", "感謝祭"),
    ("massage", "按摩"), ("kiss", "接吻"), ("detective", "搜查官"), ("piss", "放尿"),
    ("cheongsam", "旗袍"), ("time-stop", "時間停止"), ("widow", "未亡人"), ("school-uniform", "校服"),
    ("breast-milk", "母乳"), ("swimsuit", "水着"), ("car", "汽車"), ("soapland", "泡姬"),
    ("crapulence", "泥醉"), ("swimming-pool", "泳池"), ("bathing-place", "洗浴場"), ("deep-throat", "深喉"),
    ("hot-spring", "溫泉"), ("fishnets", "漁網"), ("squirting", "潮吹"), ("mature-woman", "熟女"),
    ("kemonomimi", "獸耳"), ("team-manager", "球隊經理"), ("masochism-guy", "男M"), ("spasms", "痙攣"),
    ("chizyo", "痴女"), ("chikan", "痴漢"), ("hairless-pussy", "白虎"), ("prison", "監獄"),
    ("glasses", "眼鏡娘"), ("quickie", "瞬間插入"), ("short-hair", "短髮"), ("flight-attendant", "空姐"),
    ("virginity", "童貞"), ("festival", "節日主題"), ("tattoo", "紋身"), ("pantyhose", "絲襪"),
    ("bondage", "綑綁"), ("variety-show", "綜藝"), ("beautiful-butt", "美尻"), ("beautiful-leg", "美腿"),
    ("teacher", "老師"), ("flesh-toned-pantyhose", "肉絲"), ("anal-sex", "肛交"), ("footjob", "腳交"),
    ("first-night", "處女"), ("debut-retires", "處女作/引退作"), ("kinship", "親屬"), ("temptation", "誘惑"),
    ("tune", "調教"), ("nurse", "護士"), ("small-tits", "貧乳"), ("flexible-body", "軟體"),
    ("fugitive", "逃犯"), ("intrusion", "進犯"), ("sportswear", "運動裝"), ("knee-socks", "過膝襪"),
    ("ugly-man", "醜男"), ("doctor", "醫生"), ("video-recording", "錄像"), ("missed-last-train", "錯過末班車"),
    ("tall", "長身"), ("gang-intrusion", "集團進犯"), ("tram", "電車"), ("outdoor", "露出"),
    ("childhood", "青梅竹馬"), ("facial", "顏射"), ("club-hostess-and-sex-worker", "風俗娘"),
    ("magic-mirror", "魔鏡號"), ("black", "黑人"), ("black-pantyhose", "黑絲"), ("suntan", "黑肉"),
]

# 女优 120 位(取 /models/ 热度榜前 6 页, 2026-09 实测)
MODELS = [
    ("bfaca44240620be2f3092c294fb22fbe", "仲間あずみ"), ("d52d439054a2d095151691b11a99b802", "大橋未久"), ("f5fcda107aadc340592ec5b60671c1b8", "上原亜衣"),
    ("a9a8dea24d88a7d6dea79cfdd749f97c", "立花瑠莉"), ("yua-mikami", "三上悠亜"), ("tiny", "Tiny"),
    ("dbfe587363e5f187594b961b03d953eb", "尾上若葉"), ("kirara-asuka", "明日花キララ"), ("9a9e7e432a8bf1817d155a4b6e4cabce", "北島玲"),
    ("arina-hashimoto", "橋本ありな"), ("8c495da1c617938f9e32a00d221f7a22", "倖田李梨"), ("c72999e3ad1f7c36e8018f84a283103e", "桜井美里"),
    ("7342f30fc0b4acffccc8083f1529b157", "望月涼子"), ("7bc503e42b004a64371957472b765add", "高垣怜"), ("a295a49a530517f2b2e4ea725a4672d8", "渡辺茜"),
    ("76deee4a66140394afb9b342222318c9", "あまつか亜夢"), ("saika-kawakita", "河北彩花"), ("20d0c4a34eda32e442cc3ff532f568fd", "小宵こなん"),
    ("2b1eac8f3806062163c2bf6b70e090bc", "天音りせ"), ("kaede-karen", "楓カレン"), ("momonogi-kana", "桃乃木かな"),
    ("24257d5c6006ca3cd34b2448dee156de", "倉科もえ"), ("cb1fb7b070858e3a0cb086ddcd96d22d", "児玉るみ"), ("768bf94ab8061a01981cd5dcbb856abf", "悠月アイシャ"),
    ("faa49facc6d78f42683db853817fd8e0", "伊東紅蘭"), ("db312094fa3efa6d9c62e281fbc3986d", "南なつき"), ("851cf1602f37c2611917b675f2d432c7", "田中レモン"),
    ("5c4980ee9b087170c6b11e1fba146ef1", "みほの"), ("52a33aabdfd0440202e57950dafe079f", "安齋らら"), ("382635fc5873b217ff01bdd14f5058a7", "山手梨愛"),
    ("f4255b11381c3ee006e9427804986189", "篠田あゆみ"), ("12050cf0c6145a5269401fa63ae27009", "百多えみり"), ("090c3c847f8bd334b34ad5882462c56a", "尾野真知子"),
    ("91fca8d824e07075d09de0282f6e9076", "凪ひかる"), ("ef9b1ab9a21b58d6ee4d7d97ab883288", "神木麗"), ("50901b0fe0f78eecfbe730d9b2eb6e22", "佐藤悠美"),
    ("e2d6d3396730920dd30202223e266d89", "西川七瀬"), ("432452635da3d62dbd6d28270e162e48", "みづなれい"), ("cf83191c7504cd0d2a0ccb33ea07e12a", "高坂麗子"),
    ("2dac6a51a3dbec07b432cc265c3a13ae", "板谷友美"), ("7cdb926baab256cc26da8146f4980a10", "めぐり"), ("207eab0581b09e3e0230498770e8ced4", "與田知佳"),
    ("aizawa-minami", "相沢みなみ"), ("09c2c4b1e2193f7f1399af09e0104c62", "中井綾香"), ("f88e49c4c1adb0fd1bae71ac122d6b82", "楓ふうあ"),
    ("ayami-syunka", "あやみ旬果"), ("cfec639ac8663bf921c59d15029c6758", "都盛星空"), ("9248571e579fb08fec5a19b9132fb274", "成瀬まゆり"),
    ("cbb37daf8c697c0ff169e974bf40630f", "天音まひな"), ("1c9660a46c0bacf960fc3fb98329fdc8", "伊織しずく"), ("matsushita-saeko", "松下紗栄子"),
    ("bb2c39a1ddc2df680cf28886d63e6395", "杏樹紗奈"), ("67591c96271cece8694e2321b1d6f7a9", "古瀬玲"), ("875461f0e45bc89f14d2219794ddb4cd", "森崎りか"),
    ("e7e38de905d722e4853d69a4c37493e5", "近藤郁美"), ("e763382dc86aa703456d964ca25d0e8b", "新ありな"), ("bd4eea19d6e092fb05751b91eeea4381", "吉川あいみ"),
    ("7cadf3e484f607dc7d0f1c0e7a83b007", "涼森れむ"), ("sakura-momo", "桜空もも"), ("adbd3cadad664d54507df801eb823673", "柳田やよい"),
    ("c1e2860bac5dd4266def313cb4820872", "澁谷果歩"), ("54be1913d5e82a9797208636fe3779b3", "長澤あずさ"), ("erina-hk", "絵麗奈 (素海霖)"),
    ("2193fac085b10b777c898fae90c7522d", "あかね葵"), ("75100fb77398ccfc652d72fbb64a8b99", "風間リナ"), ("e1bafa5fa5f0a84810e5952baa8f4505", "上原結衣"),
    ("546174c3d14f575cd0f470493aa843cf", "市橋えりな"), ("b83dcecffa102bade708281379f103af", "沖田杏梨"), ("b37faa29fa030819408346f883fff384", "後藤里香"),
    ("4a26391ab1f22bf5d99d8bbe6d7b6c0e", "希咲あや"), ("ce2c0769c38d88799a286eb41e436b06", "夢咲ひなみ"), ("saika-kawakita2", "河北彩伽"),
    ("db460d545c6a3e723cd4baeab316097a", "桃菜あこ"), ("b9065ad74e4c6c374c31b243bde551a8", "廿楽まり"), ("1029afd768657f02b4918846d68b565d", "望月あみ"),
    ("679c69a5488daa35a5544749b75556c6", "藍芽みずき"), ("f1d2df75a04e97af74b9960a10042680", "宮野ゆかな"), ("ef395f3231a58db2657c6838297dc578", "すみれ美香"),
    ("1a71be5a068c6f9e00fac285b31019f9", "瀬戸環奈"), ("2314fe643ced2a0476c019353bb7dcca", "星あんず"), ("mayuki-ito", "伊藤舞雪"),
    ("2958338aa4f78c0afb071e2b8a6b5f1b", "小野夕子"), ("4ff66c0139a67951da3c92a5dd389813", "佐藤遥希"), ("5be8df19ac81451ed12f23891e2c5205", "平野蒼"),
    ("17351b212ec557d72e6a6521748e8c5a", "雨宮琴音"), ("yamagishi-aika", "山岸逢花"), ("32ce073d2ad8b94c70864344db21184d", "星乃美桜"),
    ("6fcfa03b92ef42dd71e0e7c0cf77bfd0", "涼南佳奈"), ("4c378181073271498110acb911e63d19", "有坂唯"), ("aoi-tsukasa", "葵つかさ"),
    ("b80c68cb0d59577515d34609024cc16c", "松本メイ"), ("koharu-suzuki", "鈴木心春"), ("2b5b59320c901fb2ad29583b6c3d4267", "向理来"),
    ("1a266219a69a34cc4a5be730e8646d2e", "佐々木優奈"), ("0cd27e0b88a0c50a8f6a7bc2a41437a0", "瑞稀そら"), ("moe-amatsuka", "天使もえ"),
    ("ab0f987c11a51c7436c7fc2f75b53229", "東雲みれい"), ("dbd86ef3bcb8d4194b527d8acec79796", "桃谷エリカ"), ("shoko-takasaki", "高橋しょう子"),
    ("5f2a56509aafbdabfac138e3f09b9e34", "櫻ゆの"), ("tsumugi-akari", "明里つむぎ"), ("b435825a4941964079157dd2fc0a8e5a", "宮下玲奈"),
    ("miura-sakura", "水卜さくら"), ("6d3c1a1396b01c0e375f5357142c126f", "篠めぐみ"), ("b8f9dcbcf39f739e81939ca768ed4061", "深田ナナ"),
    ("73c6496cde07448d601a19b5c958cb9f", "泉ののか"), ("07d2664576e70e433bfbca794ea6c7bb", "成宮祐希"), ("aoi", "葵"),
    ("hongo-ai", "本郷愛"), ("yumeno-aika", "夢乃あいか"), ("97381438b416f07d828041a29a4654a1", "双葉みお"),
    ("9bb767fca083e74af996ba9c328fcb13", "石原莉奈"), ("da40331930649a37323b7eae0acd36ae", "大城かえで"), ("a19df8acacafc834711d98d10fc23727", "遥めぐみ"),
    ("dcb26add212a5a1bcc3d888b18908895", "美月"), ("0c48a2e15ec61689bb88a7e31592eda3", "星まりあ"), ("b3adaef761e84cf5a6114dd9cae3006f", "はやのうた"),
    ("miru", "Miru"), ("231f37f5861f33b0bc330784588d2cda", "涼風うい"), ("e1e3b4d737bcdea394c55a84a5bf677f", "小西悠"),
]

# Cloudflare 挑战页特征(命中即判定为"没拿到正文")
_CHALLENGE = ("just a moment", "cf_chl_opt", "cf-browser-verification", "attention required",
              "enable javascript and cookies", "checking your browser", "cf-mitigated")


# ============================================================ HTTP 自适应层
class Http(object):
    """纯标准库 urllib 优先; 逐级降级 curl_cffi -> requests -> 回 urllib。全程重试。"""

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

    def __init__(self, proxy="", timeout=12):
        self.proxy = (proxy or "").strip()
        self.timeout = timeout
        self.engine = ""          # 首次成功后锁定, 后续优先用它
        self.last_error = ""
        self._curl = None
        self._req = None

    # ---- 请求头 ----
    def headers(self, referer=""):
        return {
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer or (HOST + "/"),
            "Upgrade-Insecure-Requests": "1",
            "Connection": "close",
        }

    # ---- 三个通道 ----
    def _by_urllib(self, url, referer):
        req = urllib.request.Request(url, headers=self.headers(referer))
        if self.proxy:
            op = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))
        else:
            op = urllib.request.build_opener()
        resp = op.open(req, timeout=self.timeout)
        raw = resp.read()
        enc = (resp.headers.get("Content-Encoding") or "").lower()
        if "gzip" in enc:
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        code = getattr(resp, "status", 200) or 200
        if code != 200:
            raise RuntimeError("HTTP %s" % code)
        return raw.decode("utf-8", "ignore")

    def _by_curl(self, url, referer):
        if self._curl is None:
            from curl_cffi import requests as _c
            self._curl = _c
        kw = {"impersonate": "chrome", "timeout": self.timeout}
        if self.proxy:
            kw["proxies"] = {"http": self.proxy, "https": self.proxy}
        r = self._curl.get(url, headers=self.headers(referer), **kw)
        if r.status_code != 200:
            raise RuntimeError("HTTP %s" % r.status_code)
        return r.text

    def _by_requests(self, url, referer):
        if self._req is None:
            import requests as _r
            self._req = _r
        kw = {"timeout": self.timeout}
        if self.proxy:
            kw["proxies"] = {"http": self.proxy, "https": self.proxy}
        r = self._req.get(url, headers=self.headers(referer), **kw)
        if r.status_code != 200:
            raise RuntimeError("HTTP %s" % r.status_code)
        return r.text

    def _fetch(self, engine, url, referer):
        if engine == "curl_cffi":
            return self._by_curl(url, referer)
        if engine == "requests":
            return self._by_requests(url, referer)
        return self._by_urllib(url, referer)

    # ---- 正文有效性 ----
    @staticmethod
    def looks_ok(txt):
        if not txt or len(txt) < 400:
            return False
        low = txt[:4000].lower()
        for k in _CHALLENGE:
            if k in low:
                return False
        return True

    # ---- 统一入口 ----
    def get(self, url, referer="", tries=2, budget=30):
        order = []
        if self.engine:
            order.append(self.engine)
        for e in ("urllib", "curl_cffi", "requests"):
            if e not in order:
                order.append(e)
        t0 = time.time()
        for eng in order:
            for i in range(tries):
                try:
                    txt = self._fetch(eng, url, referer)
                    if self.looks_ok(txt):
                        self.engine = eng
                        return txt
                    self.last_error = "%s: challenge/empty" % eng
                except Exception as e:
                    self.last_error = "%s: %s" % (eng, type(e).__name__)
                if time.time() - t0 > budget:
                    break
                time.sleep(0.4 * (i + 1))
            if time.time() - t0 > budget:
                break
        raise RuntimeError("fetch failed: %s (%s)" % (url, self.last_error))


# ============================================================ 解析工具
_ENT = (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'),
        ("&#39;", "'"), ("&apos;", "'"), ("&nbsp;", " "), ("&#8211;", "-"),
        ("&#8217;", "'"), ("&#8220;", '"'), ("&#8221;", '"'), ("&hellip;", "..."))


def clean(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", "", s)
    for a, b in _ENT:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def abs_url(u):
    if not u:
        return ""
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return HOST + u
    return u


def to_int(v, d=1):
    try:
        return int(str(v).strip())
    except Exception:
        return d


# ------------------------------------------------------------ 列表卡片
def parse_cards(html):
    """列表页 / 分类页 / 标签页 / 女优页 / 搜索页 —— 通用卡片解析"""
    out = []
    if not html:
        return out
    seen = set()
    for seg in html.split('<div class="video-img-box')[1:]:
        seg = seg[:3000]
        m = re.search(r'href="([^"]*?/videos/([^"/]+)/)"', seg)
        if not m:
            continue
        vid = m.group(2)
        if vid in seen:
            continue
        seen.add(vid)
        t = re.search(r'<h6 class="title">\s*<a[^>]*>(.*?)</a>', seg, re.S)
        name = clean(t.group(1)) if t else vid
        img = re.search(r'data-src="([^"]+)"', seg)
        if not img:
            img = re.search(r'<img[^>]+src="(https?://[^"]+)"', seg)
        pic = abs_url(img.group(1)) if img else ""
        du = re.search(r'<span class="label">([^<]*)</span>', seg)
        dur = clean(du.group(1)) if du else ""
        views = likes = ""
        st = re.search(r'<p class="sub-title">(.*?)</p>', seg, re.S)
        if st:
            nums = [clean(x) for x in re.sub(r'<svg.*?</svg>', '|', st.group(1), flags=re.S).split('|')]
            nums = [x for x in nums if x]
            if nums:
                views = nums[0]
            if len(nums) > 1:
                likes = nums[1]
        remark = " · ".join([x for x in (dur,
                                         ("👁 " + views) if views else "",
                                         ("♥ " + likes) if likes else "") if x])
        out.append({"vod_id": vid, "vod_name": name, "vod_pic": pic, "vod_remarks": remark})
    return out


def parse_pager(html):
    """取分页最大页码(兼容 class 在 href 前后两种写法)"""
    mx = 0
    for pat in (r'class="page-link"[^>]*href="([^"]+)"', r'href="([^"]+)"[^>]*class="page-link"'):
        for m in re.finditer(pat, html or ""):
            seg = m.group(1).rstrip("/").split("/")[-1].split("?")[0]
            if seg.isdigit():
                mx = max(mx, int(seg))
    return mx


# ------------------------------------------------------------ 详情页
def parse_detail(html, vid="", url=""):
    if not html:
        return None

    name = ""
    m = re.search(r'<div class="header-left">\s*<h4>(.*?)</h4>', html, re.S)
    if m:
        name = clean(m.group(1))
    if not name:
        m = re.search(r'<meta property="og:title" content="([^"]*)"', html)
        if m:
            name = clean(m.group(1))
    if not name:
        m = re.search(r'<title>(.*?)</title>', html, re.S)
        name = clean(m.group(1)) if m else vid
    name = re.sub(r'\s*-\s*Jable\.TV.*$', '', name).strip() or vid

    pic = ""
    m = re.search(r'<meta property="og:image" content="([^"]*)"', html)
    if m:
        pic = abs_url(m.group(1))
    if not pic:
        m = re.search(r'<video[^>]+poster="([^"]*)"', html)
        if m:
            pic = abs_url(m.group(1))

    play = ""
    for pat in (r"var\s+hlsUrl\s*=\s*'([^']+)'", r'var\s+hlsUrl\s*=\s*"([^"]+)"',
                r'"hlsUrl"\s*:\s*"([^"]+)"', r"(https?://[^\"'\s<>]+\.m3u8[^\"'\s<>]*)"):
        m = re.search(pat, html)
        if m:
            play = m.group(1).replace("\\/", "/").replace("&amp;", "&")
            break

    # 信息区只取 video-info 段, 避免被下方"相关影片"卡片的数字污染
    vi = ""
    k = html.find('section class="video-info')
    if k >= 0:
        vi = html[k:k + 5000]

    actors = []
    mb = re.search(r'<div class="models">(.*?)</div>', vi or html, re.S)
    if mb:
        for t in re.finditer(r'title="([^"]+)"', mb.group(1)):
            nm = clean(t.group(1))
            if nm and nm not in actors:
                actors.append(nm)
        if not actors:
            for a in re.finditer(r'<a\b[^>]*>(.*?)</a>', mb.group(1), re.S):
                nm = clean(a.group(1))
                if nm and nm not in actors:
                    actors.append(nm)

    cats, tags = [], []
    tb = re.search(r'<h5 class="tags[^"]*">(.*?)</h5>', vi or html, re.S)
    if tb:
        for a in re.finditer(r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>', tb.group(1), re.S):
            href, txt = a.group(1), clean(a.group(2))
            if not txt:
                continue
            if "/categories/" in href:
                if txt not in cats:
                    cats.append(txt)
            elif "/tags/" in href:
                if txt not in tags:
                    tags.append(txt)

    badge = ""
    bb = re.search(r'<div class="header-right[^"]*">(.*?)</div>', vi or html, re.S)
    if bb:
        badge = clean(re.sub(r'<span[^>]*>.*?</span>', ' ', bb.group(1), flags=re.S))
    date = ""
    m = re.search(r'上市於\s*([\d\-]+)', vi or html)
    if m:
        date = m.group(1)
    posted = ""
    m = re.search(r'#icon-clock"></use></svg>\s*<span[^>]*>(.*?)</span>', vi or html, re.S)
    if m:
        posted = clean(m.group(1))
    views = ""
    m = re.search(r'#icon-eye"></use></svg>\s*<span[^>]*>([\d\s,]+)</span>', vi or html, re.S)
    if m:
        views = clean(m.group(1))
    likes = ""
    m = re.search(r'class="count">([\d\s,]+)</span>', vi or html)
    if m:
        likes = clean(m.group(1))

    desc = ""
    m = re.search(r'<meta property="og:description" content="([^"]*)"', html)
    if m:
        desc = clean(m.group(1))

    parts = []
    if desc:
        parts.append(desc)
    if cats:
        parts.append("主題: " + " / ".join(cats))
    if tags:
        parts.append("標籤: " + " / ".join(tags))
    if actors:
        parts.append("女優: " + " / ".join(actors))
    meta = " | ".join([x for x in (date, badge, ("觀看 " + views) if views else "",
                                   ("收藏 " + likes) if likes else "") if x])
    if meta:
        parts.append(meta)
    content = "\n".join(parts) or name

    remark = " · ".join([x for x in (badge, ("👁 " + views) if views else "",
                                     ("♥ " + likes) if likes else "") if x])

    return {
        "vod_id": vid,
        "vod_name": name,
        "vod_pic": pic,
        "type_name": " / ".join(cats) if cats else "Jable",
        "vod_year": (date[:4] if date else ""),
        "vod_area": "日本",
        "vod_remarks": remark or posted,
        "vod_actor": ", ".join(actors),
        "vod_director": "",
        "vod_content": content,
        "vod_play_from": "jable",
        "vod_play_url": ("播放$" + play) if play else ("播放$" + (url or "")),
        "_play": play,
    }


# ============================================================ 主类
class Spider(_Base):

    host = HOST
    PAGE_SIZE = 24

    def __init__(self):
        self._h = None
        self._cache = {}
        self.last_error = ""

    # -------------------------------------------------- 基础
    def getName(self):
        return "Jable"

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4)(\?|$)", url or ""))

    def manualVideoCheck(self):
        return False

    def destroy(self):
        self._cache = {}

    def init(self, extend=""):
        cfg = {}
        if isinstance(extend, dict):
            cfg = extend
        elif extend:
            try:
                cfg = json.loads(str(extend))
            except Exception:
                cfg = {}
        if not isinstance(cfg, dict):
            cfg = {}
        if cfg.get("host"):
            self.host = str(cfg["host"]).rstrip("/")
        self._h = Http(cfg.get("proxy", ""), to_int(cfg.get("timeout", 12), 12))
        return None

    def http(self):
        if self._h is None:
            self.init("")
        return self._h

    def get(self, url, referer=""):
        now = time.time()
        hit = self._cache.get(url)
        if hit and now - hit[0] < 300:
            return hit[1]
        try:
            txt = self.http().get(url, referer=referer)
        except Exception as e:
            self.last_error = "%s @ %s" % (e, url)
            return ""
        if len(self._cache) > 40:
            self._cache = {}
        self._cache[url] = (now, txt)
        return txt

    # -------------------------------------------------- 首页
    def homeContent(self, filter):
        classes = [
            {"type_id": "latest", "type_name": "最近更新"},
            {"type_id": "hot", "type_name": "熱門影片"},
            {"type_id": "cat", "type_name": "主題分類"},
        ]
        for slug, nm in CATS:
            classes.append({"type_id": "c:" + slug, "type_name": nm})
        classes.append({"type_id": "tag", "type_name": "標籤"})
        classes.append({"type_id": "model", "type_name": "女優"})

        filters = {}
        if filter:
            filters["cat"] = [{"key": "cat", "name": "主題分類",
                               "value": [{"n": n, "v": s} for s, n in CATS]}]
            filters["tag"] = [{"key": "tag", "name": "標籤(%d)" % len(TAGS),
                               "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": s} for s, n in TAGS]}]
            filters["model"] = [{"key": "model", "name": "女優(%d)" % len(MODELS),
                                 "value": [{"n": "全部", "v": ""}] + [{"n": n, "v": s} for s, n in MODELS]}]

        html = self.get(self.host + "/latest-updates/")
        return {"class": classes, "filters": filters, "list": parse_cards(html)}

    def homeVideoContent(self):
        html = self.get(self.host + "/latest-updates/")
        return {"list": parse_cards(html)}

    # -------------------------------------------------- 列表地址
    def _list_url(self, tid, pg, extend):
        ext = extend if isinstance(extend, dict) else {}
        suffix = "" if pg <= 1 else "%d/" % pg
        if tid == "hot":
            return "%s/hot/%s" % (self.host, suffix)
        if tid == "tag" or tid.startswith("t:"):
            slug = str(ext.get("tag") or (tid[2:] if tid.startswith("t:") else "")).strip()
            if slug:
                return "%s/tags/%s/%s" % (self.host, slug, suffix)
            return "%s/latest-updates/%s" % (self.host, suffix)
        if tid == "model" or tid.startswith("m:"):
            slug = str(ext.get("model") or (tid[2:] if tid.startswith("m:") else "")).strip()
            if slug:
                return "%s/models/%s/%s" % (self.host, slug, suffix)
            return "%s/latest-updates/%s" % (self.host, suffix)
        if tid == "cat" or tid.startswith("c:"):
            slug = str(ext.get("cat") or (tid[2:] if tid.startswith("c:") else "")).strip()
            if not slug:
                slug = "chinese-subtitle"
            return "%s/categories/%s/%s" % (self.host, slug, suffix)
        return "%s/latest-updates/%s" % (self.host, suffix)

    # -------------------------------------------------- 分类
    def categoryContent(self, tid, pg, filter, extend):
        pg = max(to_int(pg, 1), 1)
        try:
            url = self._list_url(str(tid or "latest"), pg, extend)
            html = self.get(url)
            vlist = parse_cards(html)
            pc = parse_pager(html)
            if pc < pg:
                pc = pg
            return {"list": vlist, "page": str(pg), "pagecount": str(pc),
                    "limit": str(self.PAGE_SIZE), "total": str(pc * self.PAGE_SIZE)}
        except Exception as e:
            self.last_error = str(e)
            return {"list": [], "page": str(pg), "pagecount": str(pg),
                    "limit": str(self.PAGE_SIZE), "total": "0"}

    # -------------------------------------------------- 详情
    def detailContent(self, ids):
        try:
            vid = ids
            if isinstance(ids, (list, tuple)):
                vid = ids[0] if ids else ""
            vid = str(vid).strip()
            if vid.startswith("["):
                try:
                    arr = json.loads(vid)
                    if isinstance(arr, list) and arr:
                        vid = str(arr[0]).strip()
                except Exception:
                    pass
            if not vid:
                return {"list": []}
            if vid.startswith("http"):
                url = vid
                vid = url.rstrip("/").split("/")[-1]
            else:
                url = "%s/videos/%s/" % (self.host, vid)
            vod = parse_detail(self.get(url), vid, url)
            if not vod:
                return {"list": []}
            vod.pop("_play", None)
            return {"list": [vod]}
        except Exception as e:
            self.last_error = str(e)
            return {"list": []}

    # -------------------------------------------------- 搜索
    def searchContent(self, key, quick, pg="1"):
        pg = max(to_int(pg, 1), 1)
        try:
            kw = urllib.parse.quote(str(key).strip())
            suffix = "" if pg <= 1 else "%d/" % pg
            url = "%s/search/%s/%s" % (self.host, kw, suffix)
            html = self.get(url, referer=self.host + "/")
            vlist = parse_cards(html)
            pc = parse_pager(html)
            if pc < pg:
                pc = pg
            return {"list": vlist, "page": str(pg), "pagecount": str(pc),
                    "limit": str(self.PAGE_SIZE), "total": "0"}
        except Exception as e:
            self.last_error = str(e)
            return {"list": [], "page": str(pg), "pagecount": str(pg),
                    "limit": str(self.PAGE_SIZE), "total": "0"}

    # -------------------------------------------------- 播放
    def playerContent(self, flag, id, vipFlags):
        vid = str(id or "").strip()
        url = vid
        try:
            if not vid.startswith("http"):
                url = "%s/videos/%s/" % (self.host, vid.strip("/"))
            if ".m3u8" not in url:
                vod = parse_detail(self.get(url), vid, url)
                if vod and vod.get("_play"):
                    url = vod["_play"]
        except Exception as e:
            self.last_error = str(e)
        return {
            "parse": 0,
            "playUrl": "",
            "url": url,
            "header": json.dumps({
                "User-Agent": self.http().UA,
                "Referer": self.host + "/",
                "Origin": self.host,
            }, ensure_ascii=False),
        }

    def localProxy(self, param):
        return None


# ============================================================ 自测
def _selftest():
    s = Spider()
    s.init("")
    ok = []

    def chk(name, good, extra=""):
        ok.append(bool(good))
        print("  [%s] %-22s %s" % ("PASS" if good else "FAIL", name, extra))

    print("=" * 72)
    hc = s.homeContent(True)
    chk("homeContent", len(hc["class"]) >= 15 and len(hc["list"]) > 0,
        "classes=%d filters=%s list=%d" % (len(hc["class"]), list(hc["filters"].keys()), len(hc["list"])))
    print("      engine = %s" % (s.http().engine or "?"))
    for v in hc["list"][:3]:
        print("       · %s | %s | %s" % (v["vod_id"], v["vod_name"][:46], v["vod_remarks"]))

    tests = [
        ("categoryContent latest", s.categoryContent("latest", "1", True, {})),
        ("categoryContent hot", s.categoryContent("hot", "1", True, {})),
        ("categoryContent cat(中文字幕)", s.categoryContent("cat", "1", True, {"cat": "chinese-subtitle"})),
        ("categoryContent c:roleplay", s.categoryContent("c:roleplay", "1", True, {})),
        ("categoryContent tag:ntr", s.categoryContent("tag", "1", True, {"tag": "ntr"})),
        ("categoryContent model:三上悠亜", s.categoryContent("model", "1", True, {"model": "yua-mikami"})),
        ("categoryContent latest p2", s.categoryContent("latest", "2", True, {})),
    ]
    for nm, r in tests:
        chk(nm, len(r["list"]) > 0, "list=%d page=%s/%s" % (len(r["list"]), r["page"], r["pagecount"]))

    first = hc["list"][0]["vod_id"] if hc["list"] else ""
    d = s.detailContent([first]) if first else {"list": []}
    if d["list"]:
        v = d["list"][0]
        chk("detailContent", bool(v.get("vod_name")), "%s | 女優=%s | %s" % (v["vod_name"][:36], v["vod_actor"][:24], v["vod_remarks"]))
        print("      片源: %s" % ((v.get("vod_play_url") or "无")[:110]))
    else:
        chk("detailContent", False, first)

    sr = s.searchContent("三上悠亜", True, "1")
    chk("searchContent", len(sr["list"]) > 0, "list=%d" % len(sr["list"]))

    pr = s.playerContent("", first, None)
    chk("playerContent", ".m3u8" in (pr.get("url") or ""), (pr.get("url") or "")[:110])
    if ".m3u8" in (pr.get("url") or ""):
        try:
            body = s.http().get(pr["url"], referer="%s/videos/%s/" % (s.host, first))
            chk("playlist fetch", body.startswith("#EXTM3U"), "bytes=%d" % len(body))
        except Exception as e:
            chk("playlist fetch", False, str(e)[:60])

    print("=" * 72)
    print("结果: %d/%d 通过" % (sum(ok), len(ok)))
    return all(ok)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--engine", action="store_true")
    ap.add_argument("--cat", action="store_true")
    ap.add_argument("--list", nargs=2, metavar=("TID", "PG"))
    ap.add_argument("--detail")
    ap.add_argument("--search")
    ap.add_argument("--play")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if _selftest() else 1)
    s = Spider()
    s.init("")
    if a.engine:
        try:
            s.get(s.host + "/latest-updates/")
        except Exception:
            pass
        print("HTTP engine:", s.http().engine or ("FAILED (%s)" % s.http().last_error))
    if a.cat:
        hc = s.homeContent(True)
        for c in hc["class"]:
            print("  ", c["type_id"], c["type_name"])
        print("filters:", dict((k, len(v[0]["value"])) for k, v in hc["filters"].items()))
    if a.list:
        tid, pg = a.list
        ext = {"cat": "chinese-subtitle", "tag": "ntr", "model": "yua-mikami"}
        r = s.categoryContent(tid, pg, True, ext)
        print("page=%s pagecount=%s list=%d" % (r["page"], r["pagecount"], len(r["list"])))
        for v in r["list"][:8]:
            print("   ", v["vod_id"], "|", v["vod_name"][:56], "|", v["vod_remarks"])
    if a.detail:
        r = s.detailContent([a.detail])
        for v in r["list"]:
            print("name:", v["vod_name"])
            print("pic :", v["vod_pic"])
            print("actor:", v["vod_actor"])
            print("type:", v["type_name"])
            print("meta:", v["vod_remarks"])
            print("play:", v["vod_play_url"][:160])
    if a.search:
        r = s.searchContent(a.search, True, "1")
        print("hits:", len(r["list"]))
        for v in r["list"][:8]:
            print("   ", v["vod_id"], "|", v["vod_name"][:56])
    if a.play:
        r = s.playerContent("", a.play, None)
        print("url:", r["url"][:200])
