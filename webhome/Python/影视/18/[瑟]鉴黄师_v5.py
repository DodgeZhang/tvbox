# -*- coding: utf-8 -*-
# Javrate (www.javrate.com) TVBox 源 — v5
# 站点全站 Cloudflare Managed Challenge(必须跑 JS, 纯 HTTP 复刻不了)。
# v5 的过盾思路: 不再依赖壳内 WebView 桥接, 改用「服务端渲染代理」通道 ——
#   把请求交给 r.jina.ai, 由对方在真实浏览器里完成 CF 验证后回传原始 HTML, 解析层一行不用改。
#   直连作为快路径(在部分网络下可通), 被挡就自动切渲染通道并静默 15 分钟。
# 播放层: 站点 player 页把签名密钥下发到客户端, 本地可 HMAC 自签后直连 /api/token/generate
#   换 token(该接口不在盾后面), 30 秒有效期由代理层自动续签, 长片不断流。
# 开关(extend 里传 JSON): {"direct": false} 强制走渲染通道;
#   {"relay": "https://自己的反代前缀/"} 换掉默认渲染通道; {"jina_gap": 0.5} 调节流;
#   {"cache_ttl": 300} 调页面缓存秒数。
import sys, os, re, json, time, ssl, hmac, hashlib, html as H, base64, threading, http.client, http.cookiejar
import urllib.request as ur
from urllib.parse import quote, unquote, urljoin, parse_qs
sys.path.append('..')
try:
    from base.spider import Spider as _Base
except ImportError:
    class _Base(object):
        def fetch(self, url, headers=None, timeout=10):
            return ''
try:
    from java import jclass, dynamic_proxy
except ImportError:
    jclass = None
    dynamic_proxy = None
try:
    import requests
    from requests.adapters import HTTPAdapter
    HAS_REQ = True
except Exception:
    HAS_REQ = False
try:
    from urllib3.util.ssl_ import create_urllib3_context
    HAS_U3 = True
except Exception:
    HAS_U3 = False

def lower_all(t):
    return t[:6000].lower()


CIP = 'DEFAULT:!aNULL:!eNULL:!MD5:!3DES:!DES:!RC4:!IDEA:!SEED:!aDSS:!SRP:!PSK'

# WebView 内取正文 / 看渲染状态
GRAB_JS = "(function(){try{return document.documentElement.outerHTML}catch(e){return ''}})()"
READY_JS = "(function(){try{return document.readyState}catch(e){return ''}})()"

# ---------- 过盾 Cookie 缓存目录(按域名存一份) ----------
COOKIE_DIRS = ['/storage/emulated/0/tmp/123',
               '/storage/emulated/0/Android/data/tmp/123',
               os.path.join(os.path.expanduser('~'), '.javrate')]


class CFAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        if HAS_U3:
            try:
                ctx = create_urllib3_context(ciphers=CIP)
                try:
                    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                except Exception:
                    pass
                try:
                    ctx.set_alpn_protocols(['http/1.1'])
                except Exception:
                    pass
                for curve in ('X25519', 'prime256v1'):
                    try:
                        ctx.set_ecdh_curve(curve)
                        break
                    except Exception:
                        continue
                kw['ssl_context'] = ctx
            except Exception:
                pass
        super(CFAdapter, self).init_poolmanager(*a, **kw)


SITE = 'https://www.javrate.com'
HOSTS = [SITE]
REFERER = SITE + '/'
MAX_PAGE = 2000
UA_D = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
UA_M = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'
UA_A = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'

# ---------- 主分类 ----------
CATS = [
    ['/movie/new', '最新更新'],
    ['/menu/uncensored', '无码A片'],
    ['/menu/censored', '日本A片'],
    ['/menu/chinese', '国产AV'],
    ['/movie/subtitle', '中文字幕'],
    ['/best', '最多人看'],
    ['__tags', '标签找片'],
    ['/actor/list/1-0-1.html', 'AV女优'],
    ['/moviesets', '专辑系列'],
    ['/issuer', '片商厂牌'],
    ['__tools', '过盾工具'],
]

# ---------- 女优轴 ----------
ACTOR_CATS = [['1', '知名女优'], ['2', '无码女优'], ['3', '日本女优'], ['4', '国产女优'], ['5', '素人女优']]
ACTOR_SORTS = [['2', '按新片发行'], ['3', '最多人看'], ['4', '最多收藏'], ['5', '按知名度'], ['6', '最近更新']]
# ---------- 排序轴(实测抓下来的真实取值) ----------
MENU_SORTS = [['5', '最新更新'], ['1', '按新片发行'], ['2', '按观看次数'], ['3', '大家都喜欢'], ['4', '做多点赞']]
NEW_SORTS = [['2', '最新更新'], ['1', '本日优选']]
SUB_SORTS = [['1', '最新更新'], ['2', '最多人看'], ['3', '最高评分'], ['4', '上市新片']]
ISSUER_SORTS = [['3', '按发行数量'], ['1', '按厂商名气'], ['2', '按厂商名称']]

# ---------- 子分类: 标签 12 组(实站抓取) ----------
TAGS = {
        "類型": [
            "劇情",
            "形象俱樂部",
            "美少女電影",
            "單體作品",
            "企畫",
            "真實拍攝",
            "鬼畜片",
            "4K",
            "官能",
            "真人秀",
            "純慾系",
            "妄想奇特",
            "魔鬼系",
            "素人作品",
            "主觀視角",
            "重口味",
            "紀念作",
            "出道作品",
            "4小時以上作品",
            "國產",
            "故事集",
            "紀錄片",
            "局部特寫",
            "精選輯・合集",
            "二次元",
            "精選綜合",
            "暗黑系",
            "殘忍畫面",
            "自拍性愛",
            "業餘",
            "偷拍・盜撮",
            "綜藝",
            "惡搞",
            "後宮系",
            "解禁作",
            "無做愛場面",
            "原作改編",
            "共演作品",
            "漫畫改編",
            "店長珍藏",
            "驚悚片",
            "ASMR顱內高潮",
            "無碼流出",
            "特效",
            "昭和系",
            "實寫化",
            "魔鏡號",
            "性愛教學",
            "搞笑・模仿",
            "引退作品",
            "女性向",
            "無碼破解",
            "中日合作",
            "禁欲解除",
            "JOI",
            "不露臉",
            "奇幻",
            "移籍作",
            "節日限定",
            "唯美寫真",
            "8小時以上作品",
            "熱點改編",
            "AI 重製版",
            "聯動作品",
            "復活作",
            "民國",
            "科幻",
            "古風",
            "中文字幕",
            "AI生成作品",
            "臺日合作"
        ],
        "劇情": [
            "NTR",
            "不倫",
            "勾引・誘惑",
            "出軌",
            "豔遇",
            "寢取",
            "強姦",
            "背德",
            "女優訪談",
            "輪姦",
            "按摩・回春",
            "脅迫",
            "媚藥・迷藥",
            "職場",
            "亂倫",
            "校園生活",
            "約炮",
            "獵豔",
            "迷姦・睡姦",
            "純愛・戀愛",
            "旅行",
            "禁斷",
            "綁架・監禁",
            "奉仕",
            "外送茶・援交",
            "復仇",
            "搭訕",
            "出差",
            "看病・住院",
            "枕營業",
            "欠債肉償",
            "偷窺",
            "泡泡浴",
            "加班",
            "聚會・PARTY",
            "相部屋",
            "攝影會",
            "感謝祭",
            "約會",
            "買春",
            "尾行",
            "立場逆轉",
            "上門福利",
            "運動",
            "回鄉",
            "瑜珈·健身",
            "挑戰",
            "懲罰",
            "逆推",
            "謝罪",
            "接待",
            "黑幫",
            "街頭福利",
            "女性SPA",
            "潛入",
            "合宿",
            "換妻",
            "同學會",
            "護理",
            "入室侵犯",
            "Cosplay",
            "直播",
            "面試",
            "時間停止",
            "跳舞",
            "電子菸",
            "上門家訪",
            "喪夫",
            "牛頭人",
            "上門輔導",
            "女優面試",
            "上門推銷",
            "金主包養",
            "走光",
            "高利貸",
            "新聞播報",
            "繪畫",
            "看房",
            "撿屍",
            "男女互換",
            "全裸勤務",
            "格鬥",
            "露營",
            "女體盛",
            "學園祭",
            "仙人跳",
            "相親",
            "賭博",
            "麻将",
            "電競",
            "疫情",
            "異世界"
        ],
        "職業": [
            "女優",
            "女學生",
            "OL",
            "家庭主婦",
            "風俗娘",
            "按摩小姐",
            "女教師",
            "Coser",
            "寫真偶像",
            "護士",
            "偶像",
            "外送妹",
            "女僕",
            "網紅主播",
            "店員",
            "藝人",
            "模特",
            "泡姫",
            "女秘書",
            "女主持",
            "服務生",
            "家庭教師",
            "女公關",
            "搜索官",
            "家政婦",
            "空姐",
            "老闆娘",
            "私人教練",
            "其他職業",
            "女業務",
            "女醫",
            "AI女優",
            "幼稚園老師",
            "看護",
            "各種職業",
            "黑人男優",
            "精靈・妖怪",
            "房屋仲介",
            "櫃台小姐",
            "白人女優",
            "賽車女郎",
            "台灣女優",
            "舞娘",
            "罪犯・逃犯",
            "格鬥家",
            "遊泳教練",
            "舞蹈老師",
            "社團助理",
            "DJ",
            "運動員",
            "巫女",
            "女賊",
            "拉拉隊",
            "性愛娃娃",
            "國產女優",
            "實習生",
            "看板娘",
            "清掃員",
            "女工",
            "社工",
            "AI女友",
            "記者",
            "荷官",
            "靈媒師・魔女",
            "公主",
            "啦啦隊女孩",
            "忍者",
            "遊覽車導遊",
            "韓國女優",
            "香港女優",
            "殺手",
            "泰國女優",
            "ShowGirl",
            "政客",
            "白人男優",
            "美少女戰士"
        ],
        "關係": [
            "女同事",
            "女友・妻子",
            "姐姐・妹妹",
            "鄰居",
            "女上司",
            "同學",
            "公公・媳婦",
            "老師・學生",
            "青梅竹馬",
            "粉絲",
            "母子",
            "嫂嫂",
            "小三・情人",
            "繼母・繼子",
            "岳母",
            "繼父・繼女",
            "朋友女友・妻子",
            "叔叔・姪女",
            "下屬女友・妻子",
            "女友姐姐",
            "學姐・學妹",
            "上司女友・妻子",
            "小姨子",
            "表姐・表妹",
            "父女",
            "前女友",
            "朋友母親",
            "女友閨蜜",
            "阿姨・侄子",
            "同事女友・妻子",
            "母女",
            "繼姐繼妹",
            "嬸嬸",
            "父親",
            "母親的朋友",
            "養女",
            "室友",
            "小姨・姑姑",
            "女租客",
            "女房東",
            "女友妹妹",
            "弟媳",
            "孫女・爺爺"
        ],
        "衣作": [
            "情趣內衣",
            "黑絲",
            "JK校服",
            "內衣",
            "猥褻穿著",
            "制服",
            "網襪",
            "丁字褲",
            "過膝襪・小腿襪",
            "肉絲",
            "眼鏡",
            "COSPLAY服飾",
            "白絲",
            "和服・浴衣・喪服",
            "女僕制服",
            "泳裝",
            "高跟鞋",
            "比基尼",
            "短裙・迷你裙",
            "運動服裝",
            "OL套裝",
            "緊身衣",
            "護士制服",
            "蒙面・面罩",
            "兔女郎",
            "完全着衣",
            "性感睡衣",
            "牛仔褲",
            "包臀裙・緊身裙",
            "靴子",
            "貓耳裝飾",
            "口罩",
            "中國服裝",
            "熱褲・超短褲",
            "裸體圍裙",
            "真空",
            "睡衣",
            "空姐制服",
            "體操服",
            "醫生製服",
            "公關禮服",
            "皮衣",
            "警察制服",
            "婚紗",
            "緊身褲",
            "作業服",
            "古裝",
            "女王裝",
            "女扮男裝",
            "泡泡襪",
            "聖誕裝"
        ],
        "特徵": [
            "美人",
            "美少女",
            "癡女",
            "人妻",
            "少女",
            "極品美人",
            "熟女",
            "蕩婦",
            "美人妻",
            "清楚系",
            "M男・M女",
            "蠻橫嬌羞",
            "御姐系",
            "辣妹-GAL系",
            "坂道系",
            "三十路",
            "溫柔",
            "素人",
            "可愛",
            "變態",
            "正統派",
            "輕熟女",
            "蘿莉",
            "校花",
            "羞澀",
            "老頭子",
            "清純系",
            "野性",
            "超騷",
            "痴漢",
            "人氣女優",
            "港區女子",
            "傲嬌",
            "若妻",
            "拜金女",
            "綺麗御姐",
            "女神",
            "J系",
            "綠茶婊",
            "大姐姐",
            "地味",
            "治愈系",
            "肉食系",
            "四十路",
            "單純娘",
            "S女",
            "叛逆少女",
            "順從",
            "小惡魔",
            "處男",
            "小動物系",
            "女王",
            "體育系",
            "心機婊",
            "內向",
            "地雷系",
            "名媛・貴婦",
            "文藝女",
            "宅男・宅女",
            "知性",
            "豪放女",
            "元氣系",
            "女同性戀",
            "老太婆",
            "五十路",
            "文系",
            "超辣",
            "大小姐",
            "公車癡漢",
            "中性",
            "未亡人・寡婦",
            "新娘",
            "新婚妻子・幼妻",
            "田舍娘",
            "神待娘",
            "正太",
            "處女",
            "喪女",
            "單親母親",
            "陰角系",
            "草食系",
            "男娘",
            "孕婦",
            "團地妻",
            "雙胞胎姐妹"
        ],
        "主題": [
            "淫亂",
            "亂交 • 群P",
            "3P・4P",
            "兩男一女",
            "凌辱",
            "按摩棒",
            "多P",
            "淫蕩・硬核",
            "乳液・精油",
            "調教",
            "拘束・拷問",
            "淫語",
            "緊縛",
            "SM",
            "跳蛋",
            "兩女一男",
            "雙飛",
            "反差",
            "肉便器",
            "性騷擾",
            "成人玩具",
            "放尿",
            "色誘",
            "誘騙女性",
            "猥褻",
            "一男多女",
            "大亂交",
            "露出",
            "在丈夫面前被操",
            "即時插入",
            "口球",
            "兩男兩女",
            "車震",
            "洗澡",
            "一泊兩日",
            "蠟燭",
            "催眠",
            "刑具",
            "野戰",
            "喝尿",
            "灌腸",
            "身體塗鴉",
            "一日戀人",
            "鞭打",
            "辱罵",
            "瘙癢",
            "剃毛",
            "2泊3日",
            "脱糞"
        ],
        "角色狀態": [
            "絕頂高潮",
            "羞恥",
            "慾求不滿",
            "濕身",
            "流汗",
            "白眼失神",
            "絕叫高潮",
            "大潮噴",
            "粘滑・溼滑",
            "早漏",
            "醉酒",
            "嗑嗨"
        ],
        "做愛玩法": [
            "口交",
            "女上位",
            "中出",
            "騎乗位",
            "後入",
            "手指插入",
            "舔陰",
            "乳交",
            "潮吹",
            "接吻",
            "口爆",
            "顏射",
            "深喉",
            "吞精",
            "舔腳",
            "自慰",
            "打手槍",
            "插入異物",
            "集體顏射",
            "足交",
            "69",
            "舔舐",
            "顏面騎乘",
            "肛交",
            "打屁股",
            "寸止",
            "素股",
            "二穴同入",
            "即尺",
            "拳交",
            "扶他"
        ],
        "習慣癖好": [
            "胸控・戀乳癖",
            "足控・戀足癖",
            "臀控",
            "顏控",
            "蘿莉控",
            "性虐癖",
            "御姐控",
            "戀物癖",
            "制服控",
            "女王控",
            "正太控"
        ],
        "顔值身材": [
            "美乳",
            "美腳",
            "性感",
            "巨乳",
            "高顏值",
            "美臀",
            "苗條",
            "色白",
            "清純",
            "巨尻",
            "無毛",
            "小隻馬",
            "肉感",
            "明星臉",
            "短髮",
            "大奶頭",
            "超爆乳",
            "長身",
            "超高顏值",
            "貧乳",
            "金髮",
            "童顏",
            "大乳暈",
            "剛毛",
            "大雞巴",
            "雙馬尾",
            "膚黑",
            "美穴",
            "胖女人",
            "肌肉",
            "混血",
            "刺青紋身",
            "9頭身",
            "乳釘、穿孔、乳環",
            "假乳",
            "穿孔"
        ],
        "場景地點": [
            "自宅",
            "飯店",
            "OFFICE",
            "學校",
            "美容院・按摩店",
            "公共場所",
            "浴室",
            "溫泉",
            "AV拍攝現場",
            "醫院・診所",
            "野外露天",
            "更衣室",
            "教室",
            "泡泡浴店",
            "倉庫",
            "厠所",
            "田舍",
            "風俗店",
            "電車",
            "廚房",
            "泳池",
            "健身房",
            "KTV夜總會",
            "酒吧",
            "圖書館",
            "便利商店",
            "體育館",
            "監獄",
            "商店",
            "咖啡店",
            "保健室",
            "餐廳",
            "帳篷",
            "垃圾屋",
            "海灘",
            "廢墟",
            "公園",
            "巴士",
            "居酒屋",
            "畫室",
            "計程車",
            "角色扮演風俗店",
            "建築工地",
            "工廠",
            "賭場",
            "電梯",
            "浴場",
            "電影院",
            "飛機上"
        ]
    }

TOOLS = [
    ['cf::diag', '通道自检', '检查取页/播放/token续签每一环, 出问题先点这个'],
    ['cf::verify', '重置通道', '清掉页面缓存, 重新探测最快通道'],
    ['cf::log', '查看运行日志', '看最近 200 条抓取日志'],
    ['cf::clear', '清除缓存', '清掉页面缓存和 token 缓存'],
]


# ================= 自包含弹窗(过盾用, 无 java 桥时自动降级) =================
_DLG_CLS = {}
_WV_KEEP = {}


def _proxy_cls(name, parent):
    """按接口类型生成 Java 代理类并缓存。
    注意: 每个接口必须实现它自己的抽象方法 —— Runnable 要 run(),
    OnClickListener 要 onClick(), ValueCallback 必须实现 onReceiveValue(),
    少一个方法 WebView 的取页回调就永远不回来(踩过, 整条原生通道等于废的)。"""
    if name in _DLG_CLS:
        return _DLG_CLS[name]
    if jclass is None or dynamic_proxy is None:
        return None
    try:
        P = jclass(parent)
    except Exception:
        return None

    if 'ValueCallback' in parent:
        class _VC(dynamic_proxy(P)):
            def onReceiveValue(self, value):
                fn = getattr(self, '_fn', None)
                if fn:
                    try:
                        fn(value)
                    except Exception:
                        pass
        cls = _VC
    elif 'OnClickListener' in parent:
        class _CL(dynamic_proxy(P)):
            def onClick(self, dialog, which):
                fn = getattr(self, '_fn', None)
                if fn:
                    try:
                        fn(dialog, which)
                    except Exception:
                        pass
        cls = _CL
    else:
        class _RN(dynamic_proxy(P)):
            def run(self):
                fn = getattr(self, '_fn', None)
                if fn:
                    try:
                        fn()
                    except Exception:
                        pass
        cls = _RN

    _DLG_CLS[name] = cls
    return cls


class MiniDialog(object):
    def __init__(self, spider=None):
        self.spider = spider
        self._refs = []
        self._act = None

    def available(self):
        return not (jclass is None or dynamic_proxy is None)

    def _keep(self, *o):
        self._refs.extend([x for x in o if x is not None])
        if len(self._refs) > 80:
            self._refs = self._refs[-80:]

    def _activity(self):
        if self._act is not None:
            return self._act
        # 路子一: ActivityThread.mActivities 里挑未暂停的 Activity
        try:
            AT = jclass('java.lang.Class').forName('android.app.ActivityThread')
            cur = AT.getMethod('currentActivityThread').invoke(None)
            f = AT.getDeclaredField('mActivities')
            f.setAccessible(True)
            m = f.get(cur)
            vals = m.values().toArray() if hasattr(m, 'values') else m.toArray()
            for r in vals:
                rc = r.getClass()
                pf = rc.getDeclaredField('paused')
                pf.setAccessible(True)
                if not pf.getBoolean(r):
                    af = rc.getDeclaredField('activity')
                    af.setAccessible(True)
                    a = af.get(r)
                    if a:
                        self._act = a
                        return a
        except Exception:
            pass
        # 路子二: 直接取 Application(拿不到 Activity 时的兜底, 建 WebView 够用)
        try:
            AT2 = jclass('android.app.ActivityThread')
            app = AT2.currentApplication()
            if app is not None:
                self._act = app
                return app
        except Exception:
            pass
        return None

    def run_on_ui(self, ui_fn):
        if not self.available():
            return False
        act = self._activity()
        if not act:
            return False
        R = _proxy_cls('run', 'java.lang.Runnable')
        if R is None:
            return False
        try:
            r = R()
            r._fn = lambda: ui_fn(act)
            self._keep(r)
        except Exception:
            return False
        try:
            act.runOnUiThread(r)
            return True
        except Exception:
            pass
        # 兜底: 用主线程 Handler 投递
        try:
            H = jclass('android.os.Handler')
            L = jclass('android.os.Looper')
            h = H(L.getMainLooper())
            self._keep(h)
            h.post(r)
            return True
        except Exception:
            pass
        # 最后兜底: 直接执行(部分壳允许)
        try:
            ui_fn(act)
            return True
        except Exception:
            return False

    def _click(self, fn):
        C = _proxy_cls('click', 'android.content.DialogInterface$OnClickListener')
        if C is None:
            return None
        c = C()
        c._fn = fn
        self._keep(c)
        return c

    def toast(self, msg):
        try:
            def ui(act):
                T = jclass('android.widget.Toast')
                T.makeText(act, str(msg), 0).show()
            self.run_on_ui(ui)
        except Exception:
            pass

    def show_log(self, title, lines=None, height_ratio=0.6):
        lines = lines or ['(暂无日志)']
        def ui(act):
            Builder = jclass('android.app.AlertDialog$Builder')
            b = Builder(act)
            b.setTitle(str(title))
            b.setMessage('\n'.join([str(x) for x in lines[-200:]]))
            b.setPositiveButton('知道了', None)
            d = b.create()
            self._keep(d)
            d.show()
        self.run_on_ui(ui)


class Spider(_Base):
    # ================= 初始化 =================
    def init(self, extend=''):
        self.cfg = {}
        try:
            if extend:
                e = json.loads(extend) if isinstance(extend, str) else extend
                if isinstance(e, dict):
                    self.cfg.update(e)
        except Exception:
            pass
        self.dlg = MiniDialog(self)
        self._jar = http.cookiejar.CookieJar()
        self._opener = ur.build_opener(ur.HTTPCookieProcessor(self._jar))
        self._tpl = {}
        self._ctx = None
        self._sess = None
        self._dc = {}
        self._ttl = int(self.cfg.get('cache_ttl') or 300)
        self._wv_ua = ''
        self._view = None
        self._view_err = ''
        self._wv_err = ''
        self._warmed = False
        self._ck = None
        self._http_dead = 0.0
        self._log_buf = []
        # v5: 渲染通道 + token 续签
        self._jina_dead = 0.0
        self._jina_last = 0.0
        self._jina_gap = float(self.cfg.get('jina_gap') or 0.25)
        self._direct_on = self.cfg.get('direct', True) is not False
        self._tok = {}
        return ''

    # ================= 日志 =================
    def _log(self, msg):
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
        self._log_buf.append(line)
        if len(self._log_buf) > 200:
            self._log_buf = self._log_buf[-200:]
        try:
            print(line)
        except Exception:
            pass

    # ================= 盾判定 =================
    def _is_cf(self, text):
        if not text:
            return True
        head = text[:4000]
        low = head.lower()
        if '<title>just a moment' in low or '<title>请稍候' in head:
            return True
        for m in ('cf-mitigated', 'challenge-platform', '_cf_chl_opt', 'cf_chl_',
                  'enable javascript and cookies to continue', 'attention required! | cloudflare'):
            if m in lower_all(text):
                return True
        return False

    # ================= Cookie 缓存 =================
    def _ck_path(self, domain):
        for d in COOKIE_DIRS:
            try:
                os.makedirs(d, exist_ok=True)
                return os.path.join(d, domain + '.json')
            except Exception:
                continue
        return os.path.join('/tmp', domain + '.json')

    def _ck_load(self, domain='www.javrate.com'):
        p = self._ck_path(domain)
        try:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self._log('读 cookie 缓存失败: ' + str(e))
        return None

    def _ck_save(self, domain, cookies, ua):
        try:
            p = self._ck_path(domain)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'cookies': cookies, 'ua': ua, 'ts': int(time.time())}, f, ensure_ascii=False)
            self._ck = {'cookies': cookies, 'ua': ua, 'ts': int(time.time())}
            self._log('已缓存过盾 cookie -> ' + p)
        except Exception as e:
            self._log('存 cookie 失败: ' + str(e))

    def _ck(self_get):
        pass

    def _ck_now(self):
        if self._ck is None:
            d = self._ck_load()
            self._ck = d if (d and d.get('cookies')) else {}
        return self._ck

    def _ck_restore(self):
        d = self._ck_now()
        if not (d and d.get('cookies')) or jclass is None:
            return
        try:
            cm = jclass('android.webkit.CookieManager').getInstance()
            cm.setAcceptCookie(True)
            try:
                cm.setAcceptThirdPartyCookies(None, True)
            except Exception:
                pass
            for k, v in d['cookies'].items():
                cm.setCookie(SITE, '%s=%s' % (k, v))
            cm.flush()
            self._log('[恢复] cookie 已写回 WebView')
        except Exception as e:
            self._log('[恢复] 写 cookie 失败: ' + str(e))

    # ================= WebView 原生取页(过盾主通道) =================
    def _wv_ready(self):
        return not (jclass is None or dynamic_proxy is None)

    def _ensure_view(self):
        """常驻 WebView: 只建一次, 之后复用它取页。
        挑战过一次后同域请求都秒过, 比每次新建再销毁快很多也稳很多。"""
        if self._view is not None:
            return self._view
        if not self._wv_ready():
            self._wv_err = 'no-java-bridge'
            return None
        holder = {}

        def ui(act):
            try:
                WV = jclass('android.webkit.WebView')
                WVC = jclass('android.webkit.WebViewClient')
                wv = WV(act)
                st = wv.getSettings()
                st.setJavaScriptEnabled(True)
                st.setDomStorageEnabled(True)
                try:
                    st.setDatabaseEnabled(True)
                except Exception:
                    pass
                try:
                    # 挑战页要靠资源渲染完才放行, 屏蔽图片会一直卡在"验证中"
                    st.setLoadsImagesAutomatically(True)
                    st.setBlockNetworkImage(False)
                except Exception:
                    pass
                try:
                    st.setJavaScriptCanOpenWindowsAutomatically(True)
                    st.setSupportMultipleWindows(False)
                except Exception:
                    pass
                # 默认用浏览器自带 UA: 硬塞外部 UA 会和浏览器内部特征对不上, 挑战反而反复不过
                if self.cfg.get('force_ua') and (self.cfg.get('ua') or self._ck_now().get('ua')):
                    try:
                        st.setUserAgentString(str(self.cfg.get('ua') or self._ck_now().get('ua')))
                    except Exception:
                        pass
                try:
                    wv.setWebViewClient(WVC())
                except Exception:
                    pass
                try:
                    wv.setVisibility(8)   # View.INVISIBLE: 只取页, 不干扰界面
                except Exception:
                    pass
                try:
                    self._wv_ua = str(st.getUserAgentString() or '')
                except Exception:
                    pass
                holder['v'] = wv
                self.dlg._keep(wv)
            except Exception as e:
                holder['e'] = str(e)

        if not self.dlg.run_on_ui(ui):
            self._wv_err = 'no-context'
            self._log('WebView 通道拿不到界面上下文')
            return None
        for _ in range(40):
            if holder.get('v') is not None or holder.get('e'):
                break
            time.sleep(0.1)
        if holder.get('v') is None:
            self._wv_err = str(holder.get('e') or 'no-context')
            self._log('WebView 创建失败: ' + self._wv_err[:80])
            return None
        self._view = holder['v']
        self._log('WebView 已就绪')
        return self._view

    def _eval_js(self, script, timeout=3.0):
        """在 WebView 里执行 JS 取回结果(evaluateJavascript 必须在 UI 线程调用)。"""
        v = self._view
        if v is None:
            return ''
        VC = _proxy_cls('vc', 'android.webkit.ValueCallback')
        if VC is None:
            return ''
        box = {}

        def ui(act):
            try:
                cb = VC()
                cb._fn = lambda value: box.setdefault('v', value)
                self.dlg._keep(cb)
                v.evaluateJavascript(script, cb)
            except Exception as e:
                box['e'] = str(e)

        self.dlg.run_on_ui(ui)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if 'v' in box or 'e' in box:
                break
            time.sleep(0.05)
        if box.get('e'):
            self._log('JS 执行失败: ' + str(box['e'])[:60])
            return ''
        raw = box.get('v') or ''
        if not raw or raw == 'null':
            return ''
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def _load(self, url, ref=None):
        v = self._view
        if v is None:
            return False
        ok = {}

        def ui(act):
            try:
                if ref:
                    try:
                        HM = jclass('java.util.HashMap')
                        hm = HM()
                        hm.put('Referer', str(ref))
                        v.loadUrl(url, hm)
                    except Exception:
                        v.loadUrl(url)
                else:
                    v.loadUrl(url)
                ok['y'] = 1
            except Exception as e:
                ok['e'] = str(e)

        self.dlg.run_on_ui(ui)
        time.sleep(0.08)
        if ok.get('e'):
            self._log('打开页面失败: ' + str(ok['e'])[:60])
            return False
        return bool(ok.get('y'))

    def _warm(self):
        """首次取页前先在首页把挑战走完, 后面分类页就快。"""
        if self._warmed or not self._wv_ready():
            return
        self._warmed = True
        try:
            h = self._wv_fetch(SITE + '/', timeout=35)
            self._log('预热首页: %s' % ('%d 字节' % len(h) if h else '未通过'))
        except Exception as e:
            self._log('预热异常: ' + str(e)[:60])

    def _wv_fetch(self, url, timeout=30, ref=None, settle=1.2):
        """加载 url 并把渲染后的 HTML 取回。挑战页一般 5~15 秒才放行,
        一轮等不到会自动重载一次, 避免偶发卡住的挑战页直接判死。"""
        if not self._wv_ready():
            return ''
        v = self._ensure_view()
        if v is None:
            return ''
        budget = max(int(timeout), 12)
        deadline = time.time() + budget
        best = ''
        rounds = 0
        while rounds < 2 and time.time() < deadline:
            rounds += 1
            if not self._load(url, ref=ref):
                return ''
            time.sleep(max(float(settle), 0.4))
            round_end = min(deadline, time.time() + max(budget / 2.0, 9.0))
            while time.time() < round_end:
                h = self._eval_js(GRAB_JS)
                if h and len(h) > len(best):
                    best = h
                if h and len(h) > 1500 and not self._is_cf(h):
                    rdy = self._eval_js(READY_JS) or ''
                    if (not rdy) or ('complete' in str(rdy).lower()):
                        self._grab_cookie(url)
                        return h
                time.sleep(0.6)
            if rounds == 1:
                self._log('还在挑战中, 重载一次: ' + url[:60])
                try:
                    v.stopLoading()
                except Exception:
                    pass
        if best and len(best) > 1500 and not self._is_cf(best):
            self._grab_cookie(url)
            return best
        self._log('取页被挡: %s (拿到 %d 字节)' % (url[:60], len(best)))
        return ''

    def _diag(self):
        """通道自检: 直连 -> 渲染通道 -> 取页 -> 播放续签, 逐层报卡在哪一环。"""
        out = ['时间: ' + time.strftime('%Y-%m-%d %H:%M:%S'),
               '配置: ' + json.dumps(self.cfg, ensure_ascii=False),
               '直连: ' + ('开启' if self._direct_on else '已关闭(强制走渲染通道)')]
        t0 = time.time()
        b = self._http_try(SITE + '/')
        out.append('  直连测试: ' + ('%d 字节 %.1fs' % (len(b), time.time() - t0) if b else '被盾挡(正常, 会自动走渲染通道)'))
        t0 = time.time()
        j = self._jina(SITE + '/')
        out.append('渲染通道: ' + ('%d 字节 %.1fs' % (len(j), time.time() - t0) if j else '失败'))
        if j:
            out.append('  首页解析: %d 个卡片' % len(self._cards(j)))
            h2 = self._jina(SITE + '/menu/chinese')
            out.append('  分类取页: ' + ('%d 字节, %d 卡片' % (len(h2), len(self._cards(h2))) if h2 else '失败'))
            u = self._jina(SITE + '/movie/new', no_cache=True)
            m = re.search(r'href="/movie/detail/([a-f0-9\-]+)\.html"', u or '')
            if not m:
                out.append('  详情入口: 没抓到片号, 跳过播放检测')
            else:
                s = self._resolve_play(SITE + '/movie/detail/%s.html' % m.group(1))
                out.append('  播放会话: ' + ('拿到 guid=' + str(s.get('guid'))[:8] + '...' if s else '失败'))
                if s:
                    tok = self._gen_token(s)
                    out.append('  token续签: ' + ('成功, %d 秒有效' % int(tok['expires'] - time.time())
                                                  if tok and tok.get('token') else '失败'))
                    bb = self._bin(self._mkurl(s, 'playlist.m3u8'))
                    out.append('  正片清单: ' + ('%d 字节' % len(bb) if bb else '失败'))
        else:
            out.append('结论: 渲染通道不通, 检查网络能否访问 r.jina.ai')
        out.append('--- 最近日志 ---')
        out.extend(self._log_buf[-15:])
        self.dlg.show_log('通道自检', out)

    def _grab_cookie(self, url):
        try:
            cm = jclass('android.webkit.CookieManager').getInstance()
            raw = cm.getCookie(url) or ''
            out = {}
            for p in raw.split(';'):
                p = p.strip()
                if '=' in p:
                    k, v = p.split('=', 1)
                    out[k.strip()] = v
            if out:
                self._ck_save(url.split('/')[2] if '://' in url else 'www.javrate.com', out, self._wv_ua or UA_A)
        except Exception:
            pass

    # ================= HTTP 通道 =================
    def _session(self):
        if self._sess is None and HAS_REQ:
            s = requests.Session()
            s.headers.clear()
            s.mount('https://', CFAdapter())
            self._sess = s
        return self._sess

    def _hdrs(self, ref=None, ua=None):
        d = self._ck_now()
        hd = {'User-Agent': ua or (d.get('ua') or self._wv_ua or UA_D),
              'Referer': ref or REFERER,
              'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
              'Accept-Language': 'zh-CN,zh;q=0.9',
              'Accept-Encoding': 'identity',
              'Connection': 'close',
              'Upgrade-Insecure-Requests': '1'}
        if d and d.get('cookies'):
            hd['Cookie'] = '; '.join('%s=%s' % (k, v) for k, v in d['cookies'].items())
        return hd

    def _build_ctx(self):
        if self._ctx:
            return self._ctx
        ctx = ssl.create_default_context()
        try:
            ctx.set_ciphers(CIP)
        except Exception:
            pass
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            pass
        try:
            ctx.set_alpn_protocols(['http/1.1'])
        except Exception:
            pass
        for curve in ('X25519', 'prime256v1'):
            try:
                ctx.set_ecdh_curve(curve)
                break
            except Exception:
                continue
        self._ctx = ctx
        return ctx

    def _httpclient(self, url, hd):
        try:
            p = url.split('://', 1)[1]
            host, path = p.split('/', 1)
            c = http.client.HTTPSConnection(host, timeout=15, context=self._build_ctx())
            c.request('GET', '/' + path, headers=hd)
            r = c.getresponse()
            b = r.read()
            c.close()
            return b
        except Exception:
            return b''

    def _urllib(self, url, hd):
        try:
            req = ur.Request(url, headers=hd)
            return self._opener.open(req, timeout=15).read()
        except Exception:
            return b''

# ===== v5 新增: 取页通道 =====
    JINA = 'https://r.jina.ai/'

    def _plain(self, url, hd, timeout=30, data=None):
        """纯净 HTTP 请求(不带 cookie / 不做 TLS 伪装), 用于渲染通道和 token 接口。"""
        try:
            req = ur.Request(url, data=data.encode() if isinstance(data, str) else data, headers=hd)
            return ur.urlopen(req, timeout=timeout).read()
        except Exception:
            return b''

    def _jina(self, url, no_cache=False, timeout=45):
        """渲染通道: 由对方在真实浏览器环境里完成 CF 验证, 回传原始 HTML。"""
        if time.time() < self._jina_dead:
            return ''
        gap = time.time() - self._jina_last
        if gap < self._jina_gap:
            time.sleep(self._jina_gap - gap)
        self._jina_last = time.time()
        hd = {'X-Return-Format': 'html'}
        if no_cache:
            hd['X-No-Cache'] = 'true'
        b = self._plain(str(self.cfg.get('relay') or self.JINA) + url, hd, timeout)
        if not b:
            return ''
        t = b.decode('utf-8', 'replace')
        if self._is_cf(t) or 'Just a moment' in t:
            return ''
        if len(t) < 500:
            low = t.lower()
            if 'rate limit' in low or 'too many requests' in low or '429' in low:
                self._jina_dead = time.time() + 45
                self._log('渲染通道限流, 暂停 45s')
                return ''
        return t

    def _http_try(self, url, ref=None):
        """直连快路径: 一次不带 cookie 的普通请求。被盾挡就返回空, 交给渲染通道。"""
        ref = ref or REFERER
        hd = {'User-Agent': UA_D, 'Referer': ref, 'Accept-Encoding': 'identity',
              'Upgrade-Insecure-Requests': '1',
              'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
              'Accept-Language': 'zh-CN,zh;q=0.9'}
        b = self._plain(url, hd, 10)
        if b and not self._is_cf(b.decode('utf-8', 'replace')):
            return b
        return b''

    def fetch(self, url, headers=None, timeout=15, no_cache=False):
        """统一取页: 直连快路径 -> 渲染通道 -> WebView 兜底。"""
        if not no_cache:
            t = self._dc.get(url)
            if t and time.time() - t[0] < self._ttl:
                return t[1]
        ref = (headers or {}).get('Referer') or REFERER
        txt = ''
        if self._direct_on and time.time() > self._http_dead:
            b = self._http_try(url, ref=ref)
            if b:
                txt = b.decode('utf-8', 'replace')
            else:
                self._http_dead = time.time() + 900
                self._log('直连被盾挡, 切渲染通道')
        if not txt:
            txt = self._jina(url, no_cache=no_cache)
        if not txt and self._wv_ready():
            self._warm()
            txt = self._wv_fetch(url, ref=ref) or ''
        if txt and not self._is_cf(txt):
            if not no_cache:
                self._dc[url] = (time.time(), txt)
            return txt
        return ''

    def _html(self, url, ref=None, no_cache=False):
        return self.fetch(url, headers={'Referer': ref or REFERER} if ref else None, no_cache=no_cache)

    # ===== v5 新增: 播放 token 续签 =====
    def _gen_token(self, s):
        """本地 HMAC 签名 + 直连换 token。该接口不在盾后面, 不需要过盾通道。
        返回 {token, expires, tp} 或 None。"""
        ck = s.get('mid', '') + '|' + s.get('sid', '')
        now = time.time()
        c = self._tok.get(ck)
        if c and c.get('expires', 0) - now > 8:
            return c
        if not (s.get('mid') and s.get('sid') and s.get('sec')):
            return c
        ts = int(now)
        try:
            sig = base64.b64encode(hmac.new(s.get('sec', '').encode(),
                                            ('%s|%d|%s' % (s.get('mid', ''), ts, s.get('sid', ''))).encode(),
                                            hashlib.sha256).digest()).decode()
        except Exception:
            return c
        body = json.dumps({'sessionId': s.get('sid', ''), 'movieId': s.get('mid', ''),
                           'guidId': s.get('guid', ''), 'timestamp': ts,
                           'url': SITE + '/player/v2', 'signature': sig})
        hd = {'Content-Type': 'application/json', 'Origin': SITE, 'Referer': SITE + '/', 'User-Agent': UA_D}
        b = self._plain(SITE + '/api/token/generate', hd, 20, data=body)
        if not b:
            return c
        try:
            d = json.loads(b.decode('utf-8', 'replace'))
        except Exception:
            return c
        d = d.get('data') if isinstance(d, dict) else None
        if not d or not d.get('token'):
            self._tok[ck] = {}
            return None
        r = {'token': d.get('token', ''), 'expires': int(d.get('expires') or 0),
             'tp': d.get('tokenPath') or s.get('tp') or ''}
        self._tok[ck] = r
        return r

    def _sign_url(self, base_url, tok):
        u = base_url.split('?', 1)[0]
        q = '?token=%s&expires=%s' % (quote(tok.get('token', ''), safe=''), tok.get('expires', 0))
        if tok.get('tp'):
            q += '&token_path=' + str(tok['tp'])
        return u + q

    def _resolve_play(self, detail_url):
        """解析播放会话: guid/movieId/sessionId/apiSecret/tokenPath + 初始签名 URL。"""
        h = self._html(detail_url)
        if not h:
            return None
        cands = []
        for pat in (r'id="v2-player"[^>]*src="([^"]+)"', r'<iframe[^>]+src="(/[Pp]layer[^"]*)"',
                    r'"embedUrl":\s*"([^"]+)"'):
            m = re.search(pat, h)
            if m:
                cands.append(H.unescape(m.group(1)).replace('\\/', '/'))
        for c in cands:
            p = self._html(urljoin(SITE, c), ref=detail_url, no_cache=True)
            if not p:
                continue
            s = {}
            for k, kk in (('sessionId', 'sid'), ('movieId', 'mid'), ('guidId', 'guid'),
                          ('apiSecret', 'sec'), ('initialTokenPath', 'tp')):
                m = re.search(k + r"\s*[:=]\s*'([^']+)'", p) or re.search(k + r'\s*[:=]\s*"([^"]+)"', p)
                if m:
                    s[kk] = m.group(1)
            m = (re.search(r"initialSignedUrl:\s*'([^']+)'", p) or re.search(r"signedUrl:\s*'([^']+)'", p)
                 or re.search(r'(https?://videocdn[^\s"\']+m3u8[^\s"\']*)', p))
            if m:
                s['url'] = H.unescape(m.group(1)).replace('\\/', '/')
            if s.get('guid') and not s.get('tp'):
                s['tp'] = quote('/%s/' % s['guid'], safe='')
            if s.get('mid') and s.get('sec') and s.get('sid') and s.get('url'):
                return s
            u = self._extract_m3u8(p)
            if u:
                return {'url': u}
        return None

    def playerContent(self, flag, id, vipFlags=None):
        detail_url = id if str(id).startswith('http') else SITE + '/movie/detail/' + str(id) + '.html'
        s = self._resolve_play(detail_url)
        if not s:
            return {'parse': 1, 'url': detail_url,
                    'header': {'User-Agent': UA_D, 'Referer': SITE + '/'},
                    'msg': '未解析到播放地址, 交给播放器嗅探'}
        key = base64.urlsafe_b64encode(json.dumps(s).encode()).decode().rstrip('=')
        return {'parse': 0, 'url': self._proxy_url(key),
                'header': {'User-Agent': UA_D, 'Referer': SITE + '/'}}

    # ===== v5 新增: 播放代理(带 token 自动续签) =====
    def _mkurl(self, s, path):
        """用 fresh token 拼出目标 URL。path 可含 guid 也可不含, 统一归一化。"""
        tok = self._gen_token(s)
        base = s.get('url') or ''
        host = 'https://videocdn.avking.xyz'
        if base and '//' in base:
            host = base.split('//', 1)[0] + '//' + base.split('//', 1)[1].split('/', 1)[0]
        g = str(s.get('guid') or '')
        p = path.lstrip('/')
        if g and not p.startswith(g + '/') and p != g:
            p = g + '/' + p
        return self._sign_url(host + '/' + p, tok) if tok and tok.get('token') else (base or host + '/' + p)

    # ================= 过盾工具入口 =================
    def action(self, action_str):
        if action_str == 'cf::diag':
            threading.Thread(target=self._diag, daemon=True).start()
        elif action_str == 'cf::verify':
            self._do_verify()
        elif action_str == 'cf::log':
            self.dlg.show_log('最近运行日志', lines=self._log_buf or ['(暂无日志)'])
        elif action_str == 'cf::clear':
            try:
                p = self._ck_path('www.javrate.com')
                if os.path.exists(p):
                    os.remove(p)
                self._ck = {}
                self._dc.clear()
                self._http_dead = 0.0
                self._warmed = False
                if jclass is not None:
                    try:
                        cm = jclass('android.webkit.CookieManager').getInstance()
                        cm.removeAllCookies(None)
                        cm.flush()
                    except Exception:
                        pass
                self._log('已清除过盾缓存 + 页面缓存 + 浏览器 Cookie')
                self.dlg.toast('已清空, 重新打开分类会重新过一次验证')
            except Exception as e:
                self._log('清缓存失败: ' + str(e))
        return {}

    def _do_verify(self):
        url = SITE + '/'
        self._log('打开过盾页: ' + url)

        def ui(act):
            try:
                WV = jclass('android.webkit.WebView')
                WVC = jclass('android.webkit.WebViewClient')
                LL = jclass('android.widget.LinearLayout')
                TV = jclass('android.widget.TextView')
                Builder = jclass('android.app.AlertDialog$Builder')
                CM = jclass('android.webkit.CookieManager')
                TV2 = jclass('android.util.TypedValue')
                pad = int(TV2.applyDimension(TV2.COMPLEX_UNIT_DIP, 8.0, act.getResources().getDisplayMetrics()))
                box = LL(act)
                box.setOrientation(LL.VERTICAL)
                tip = TV(act)
                tip.setText('等页面正常显示后点「完成」, Cookie 会自动缓存')
                tip.setPadding(pad, pad, pad, pad)
                wv = WV(act)
                st = wv.getSettings()
                st.setJavaScriptEnabled(True)
                st.setDomStorageEnabled(True)
                try:
                    st.setLoadsImagesAutomatically(True)
                    st.setBlockNetworkImage(False)
                except Exception:
                    pass
                # 不覆盖 UA: 和浏览器自带特征保持一致, 挑战才给过
                wv.setWebViewClient(WVC())
                wv.loadUrl(url)
                box.addView(tip)
                box.addView(wv)
                self.dlg._keep(wv, box, tip)

                res = {'ck': {}}

                def collect():
                    raw = CM.getInstance().getCookie(url) or ''
                    for p in raw.split(';'):
                        p = p.strip()
                        if '=' in p:
                            k, v = p.split('=', 1)
                            res['ck'][k.strip()] = v

                def finish(d, w):
                    collect()
                    try:
                        d.dismiss()
                    except Exception:
                        pass
                    if res['ck']:
                        self._ck_save('www.javrate.com', res['ck'], self._wv_ua or UA_A)
                        self._dc.clear()
                        self._http_dead = 0.0
                        self._warmed = True
                        self.dlg.toast('过盾成功, Cookie 已缓存')
                    else:
                        self.dlg.toast('没抓到 Cookie, 稍后再试')

                def cancel(d, w):
                    try:
                        d.dismiss()
                    except Exception:
                        pass

                b = Builder(act)
                b.setTitle('手动过盾')
                b.setView(box)
                b.setPositiveButton('完成', self.dlg._click(finish))
                b.setNegativeButton('取消', self.dlg._click(cancel))
                dlg = b.create()
                self.dlg._keep(dlg)
                dlg.show()
            except Exception as e:
                self._log('过盾窗口失败: ' + str(e))

        self.dlg.run_on_ui(ui)

    # ================= 解析: 影片卡 =================
    def _cards(self, html):
        out = []
        if not html:
            return out
        for m in re.finditer(r'<div class="mgn-item"', html):
            s = m.start()
            e = html.find('<div class="mgn-item"', s + 10)
            b = html[s:e if e > 0 else s + 6000]
            a = re.search(r'<a href="(/movie/detail/([a-f0-9\-]+)\.html)"[^>]*title="([^"]*)"', b)
            if not a:
                a = re.search(r'<a href="(/movie/detail/([a-f0-9\-]+)\.html)"[^>]*>(.*?)</a>', b, re.S)
                if not a:
                    continue
                nm = H.unescape(re.sub(r'<[^>]+>', '', a.group(3))).strip()
            else:
                nm = H.unescape(a.group(3)).strip()
            img = re.search(r'<img[^>]+src="([^"]+)"', b)
            pic = img.group(1) if img else ''
            if pic.startswith('//'):
                pic = 'https:' + pic
            rk = []
            y = re.search(r'mgn-badge-year[^>]*>([^<]+)', b)
            if y:
                rk.append(H.unescape(y.group(1)).strip())
            ty = re.search(r'mgn-badge-type[^>]*>([^<]+)', b)
            if ty:
                rk.append(H.unescape(ty.group(1)).strip())
            sb = re.search(r'mgn-badge-subtitle[^>]*>([^<]+)', b)
            if sb:
                rk.append(H.unescape(sb.group(1)).strip())
            act = [H.unescape(x).strip() for x in re.findall(r'mgn-actress[^>]*>\s*<a[^>]*>([^<]+)', b)][:8]
            act = [x for x in act if x]
            out.append({'vod_id': a.group(2), 'vod_name': nm, 'vod_pic': pic,
                        'vod_actor': ','.join(act), 'vod_remarks': ' '.join([x for x in rk if x])})
        return out

    # ================= 解析: 女优卡 =================
    def _actor_cards(self, html):
        out = []
        if not html:
            return out
        for m in re.finditer(r'<div class="actor-card', html):
            s = m.start()
            e = html.find('<div class="actor-card', s + 10)
            if e < 0:
                e = html.find('<div class="ads-box', s + 10)
            if e < 0:
                e = s + 8000
            b = html[s:e]
            a = re.search(r'<a href="(/actor/detail/([a-f0-9\-]+)\.html)"[^>]*title="([^"]*)"', b)
            if not a:
                continue
            img = re.search(r'<img[^>]+src="([^"]+)"', b)
            pic = img.group(1) if img else ''
            if pic.startswith('//'):
                pic = 'https:' + pic
            rk = re.search(r'<div class="right">\s*([^<]+)', b)
            out.append({'vod_id': SITE + a.group(1), 'vod_name': H.unescape(a.group(3)).strip(),
                        'vod_pic': pic, 'vod_actor': '', 'vod_remarks': (H.unescape(rk.group(1)).strip() if rk else '')})
        return out

    # ================= 解析: 专辑 / 片商卡 =================
    def _set_cards(self, html):
        out = []
        for m in re.finditer(r'<a href="(/moviesets/([^"]+))"[^>]*data-movieset-name="([^"]*)"[^>]*data-movie-count="(\d+)"', html or ''):
            pic = ''
            img = re.search(r"--bg-image:\s*url\('([^']+)'\)", html[max(0, m.start() - 300):m.start() + 300])
            if img:
                pic = img.group(1)
            out.append({'vod_id': SITE + m.group(1), 'vod_name': H.unescape(m.group(3)).strip(),
                        'vod_pic': pic, 'vod_remarks': '收录 %s 部' % m.group(4)})
        return out

    def _issuer_cards(self, html):
        out = []
        for m in re.finditer(r'<a href="(/Issuer/([^"]+))"[^>]*data-issuer-name="([^"]*)"[^>]*data-movie-count="(\d+)"', html or ''):
            pic = ''
            img = re.search(r"--bg-image:\s*url\('([^']+)'\)", html[max(0, m.start() - 300):m.start() + 300])
            if img:
                pic = img.group(1)
            out.append({'vod_id': SITE + m.group(1), 'vod_name': H.unescape(m.group(3)).strip(),
                        'vod_pic': pic, 'vod_remarks': '收录 %s 部' % m.group(4)})
        return out

    def _pageinfo(self, html):
        """data-page-info="第 X 頁 / 共 Y 頁" -> (当前页, 总页数)"""
        cur = tot = 0
        m = re.search(r'data-page-info="([^"]*)"', html or '')
        if m:
            t = H.unescape(m.group(1))
            a = re.search(r'第\s*(\d+)\s*頁', t)
            b = re.search(r'共\s*(\d+)\s*頁', t)
            if a:
                cur = int(a.group(1))
            if b:
                tot = int(b.group(1))
        return cur, tot

    # ================= 分类 =================
    def _filters(self):
        f = {}
        for tid, _ in CATS:
            if tid in ('/menu/uncensored', '/menu/censored', '/menu/chinese'):
                f[tid] = [{'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for v, n in MENU_SORTS]}]
            elif tid == '/movie/new':
                f[tid] = [{'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for v, n in NEW_SORTS]}]
            elif tid == '/movie/subtitle':
                f[tid] = [{'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for v, n in SUB_SORTS]}]
            elif tid == '/issuer':
                f[tid] = [{'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for v, n in ISSUER_SORTS]}]
            elif tid == '/actor/list/1-0-1.html':
                f[tid] = [
                    {'key': 'asort', 'name': '排序', 'value': [{'n': n, 'v': v} for v, n in ACTOR_SORTS]},
                    {'key': 'acat', 'name': '分类', 'value': [{'n': '全部女优', 'v': '0'}] +
                     [{'n': n, 'v': v} for v, n in ACTOR_CATS]},
                ]
            elif tid == '__tags':
                grp = []
                for g, tags in TAGS.items():
                    grp.append({'key': 'tag', 'name': g,
                                'value': [{'n': t, 'v': '/keywords/movie/' + t} for t in tags]})
                grp.append({'key': 'tsort', 'name': '排序',
                            'value': [{'n': '最新更新', 'v': '5'}, {'n': '最多人看', 'v': '2'}]})
                f[tid] = grp
        return f

    def homeContent(self, filter=False):
        return {'class': [{'type_id': c[0], 'type_name': c[1]} for c in CATS],
                'filters': self._filters(),
                'list': self._cards(self._html(SITE + '/'))[:30]}

    def homeVideoContent(self):
        return self.homeContent(False)

    def _shield_tip(self, url=''):
        rmk = '取页失败(%s), 到「过盾工具」点「通道自检」看卡在哪' % (url[:36])
        return {'vod_id': 'cf::diag', 'vod_name': '这一页没取到 — 点这里跑通道自检',
                'vod_pic': '', 'vod_remarks': rmk,
                'action': 'cf::diag', 'style': {'type': 'list'}}

    def _tool_list(self):
        return [{'vod_id': t[0], 'vod_name': t[1], 'vod_pic': '', 'vod_remarks': t[2],
                 'action': t[0], 'style': {'type': 'list'}} for t in TOOLS]

    def _tag_list(self, tag_path, page):
        url = SITE + quote(tag_path, safe='/:') + '?page=%d' % page
        h = self._html(url)
        return self._cards(h), h, url

    def categoryContent(self, tid, pg, filter=False, extend=''):
        try:
            p = max(1, int(pg or 1))
        except Exception:
            p = 1
        tid = str(tid or '').strip()
        ext = extend if isinstance(extend, dict) else {}
        if isinstance(extend, str) and extend.strip().startswith('{'):
            try:
                ext = json.loads(extend)
            except Exception:
                ext = {}
        sort = str(ext.get('sort') or ext.get('asort') or '').strip()
        acat = str(ext.get('acat') or '').strip()
        tag = str(ext.get('tag') or '').strip()
        tsort = str(ext.get('tsort') or '').strip()

        if tid == '__tools':
            ls = self._tool_list()
            return {'list': ls, 'page': 1, 'pagecount': 1, 'limit': len(ls), 'total': len(ls)}

        # ---- 标签(子分类) ----
        if tid == '__tags':
            path = tag if tag.startswith('/keywords/') else '/keywords/movie/' + (tag or '中出')
            url = SITE + quote(path, safe='/:') + '?page=%d' % p
            if tsort:
                url += '&moviesort=' + tsort
            h = self._html(url)
            ls = self._cards(h)
            _, tot = self._pageinfo(h)
            return {'list': ls, 'page': p, 'pagecount': min(tot or (p + 1 if len(ls) >= 15 else p), MAX_PAGE),
                    'limit': len(ls), 'total': tot * 20 if tot else len(ls)}

        # ---- 女优列表 ----
        if tid.startswith('/actor/list'):
            asort = sort or '2'
            cat = acat if acat != '' else '0'
            if p == 1 and not sort and not acat:
                url = SITE + '/actor/list/1-0-1.html'
            else:
                url = SITE + '/actor/list/%s-%s-%d.html' % (asort, cat, p)
            h = self._html(url)
            ls = self._actor_cards(h)
            _, tot = self._pageinfo(h)
            return {'list': ls, 'page': p, 'pagecount': min(tot or (p + 1 if len(ls) >= 25 else p), MAX_PAGE),
                    'limit': len(ls), 'total': tot * 30 if tot else len(ls)}

        # ---- 专辑系列(单页全量) ----
        if tid == '/moviesets':
            h = self._html(SITE + '/moviesets')
            ls = self._set_cards(h)
            return {'list': ls, 'page': 1, 'pagecount': 1, 'limit': len(ls), 'total': len(ls)}

        # ---- 片商厂牌 ----
        if tid == '/issuer':
            url = SITE + '/issuer?page=%d&sort=%s' % (p, sort or '3')
            h = self._html(url)
            ls = self._issuer_cards(h)
            _, tot = self._pageinfo(h)
            return {'list': ls, 'page': p, 'pagecount': min(tot or 1, MAX_PAGE), 'limit': len(ls),
                    'total': tot * 24 if tot else len(ls)}

        # ---- 最多人看 ----
        if tid == '/best':
            url = SITE + '/best' if p == 1 else SITE + '/best/thisweek?page=%d' % p
            h = self._html(url)
            ls = self._cards(h)
            _, tot = self._pageinfo(h)
            return {'list': ls, 'page': p, 'pagecount': min(tot or (p + 1 if len(ls) >= 40 else p), MAX_PAGE),
                    'limit': len(ls), 'total': tot * 60 if tot else len(ls)}

        # ---- 三大主轴: 最新更新 / 字幕 / menu 分类 ----
        if tid == '/movie/new':
            s = sort or '2'
            url = SITE + '/movie/new' if (p == 1 and not sort) else SITE + '/movie/new/%s-2-%d' % (s, p)
        elif tid == '/movie/subtitle':
            s = sort or '1'
            url = SITE + '/movie/subtitle' if (p == 1 and not sort) else SITE + '/movie/subtitle/%s-2-%d' % (s, p)
        elif tid.startswith('/menu/'):
            s = sort or '5'
            url = SITE + tid if (p == 1 and not sort) else SITE + tid + '/%s-2-%d/' % (s, p)
        else:
            url = SITE + tid if p == 1 else SITE + tid.rstrip('/') + '/%d-2-1/' % p

        h = self._html(url)
        ls = self._cards(h)
        if not h:
            ls = [self._shield_tip(url)]
        _, tot = self._pageinfo(h)
        return {'list': ls, 'page': p, 'pagecount': min(tot or (p + 1 if len(ls) >= 15 else p), MAX_PAGE),
                'limit': len(ls), 'total': tot * 20 if tot else len(ls)}

    # ================= 详情 =================
    def _dh(self, vid, path='/movie/detail/%s.html'):
        url = SITE + path % str(vid)
        t = self._dc.get(url)
        if t and time.time() - t[0] < 600:
            return t[1]
        h = self._html(url)
        if h:
            self._dc[url] = (time.time(), h)
        return h

    def _meta(self, h, vid, name_path=True):
        t = re.search(r'<title>([^<]+)</title>', h or '')
        name = H.unescape(t.group(1)).split('|')[0].strip() if t else str(vid)
        pic = ''
        m = re.search(r'property="og:image"[^>]+content="([^"]+)"', h or '')
        if not m:
            m = re.search(r'content="([^"]+)"[^>]+property="og:image"', h or '')
        if m:
            pic = m.group(1)
        if pic.startswith('//'):
            pic = 'https:' + pic
        desc = ''
        dm = re.search(r'name="description"[^>]+content="([^"]+)"', h or '')
        if dm:
            desc = H.unescape(dm.group(1)).strip()
        act = [H.unescape(x).strip() for x in re.findall(r'(?:actor-name|actress-link)[^>]*>\s*<a[^>]*>([^<]+)', h or '')][:12]
        return name, pic, desc, [x for x in act if x]

    def detailContent(self, ids, quick='1'):
        vid = ids[0] if isinstance(ids, (list, tuple)) and ids else ids
        vid = str(vid or '').strip()
        if not vid:
            return {'list': []}

        # 女优详情: 起影片列表页 /actor/movie/1-0-2-<页>/<id>.html 当剧集(最多翻 3 页)
        if '/actor/detail/' in vid or '/actor/movie/' in vid:
            url = vid if vid.startswith('http') else SITE + vid
            h = self._html(url)
            if not h:
                return {'list': [{'vod_id': vid, 'vod_name': '女优', 'vod_pic': '',
                                  'vod_content': '取页失败: 站点盾判定较严, 请到「过盾工具」过一次验证后重试',
                                  'vod_play_from': 'Javrate', 'vod_play_url': '暂无影片$' + url}]}
            name, pic, desc, act = self._meta(h, vid)
            uid = re.search(r'([a-f0-9\-]{20,})', url)
            uid = uid.group(1) if uid else ''
            ls = []
            if uid:
                for pg in (1, 2, 3):
                    lu = SITE + '/actor/movie/1-0-2-%d/%s.html' % (pg, uid)
                    lh = self._html(lu, ref=url)
                    got = self._cards(lh)
                    if not got:
                        break
                    ls.extend(got)
                    _, tot = self._pageinfo(lh)
                    if tot and pg >= tot:
                        break
            if not ls:
                ls = self._cards(h)
            uniq, seen = [], set()
            for v in ls:
                if v['vod_id'] in seen:
                    continue
                seen.add(v['vod_id'])
                uniq.append(v)
            pl = [v['vod_name'] + '$' + v['vod_id'] for v in uniq[:300]]
            return {'list': [{'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_actor': ','.join(act),
                              'vod_content': desc, 'vod_remarks': '共 %d 部' % len(uniq),
                              'vod_play_from': 'Javrate', 'vod_play_url': '#'.join(pl) if pl else '暂无影片$' + url}]}

        # 专辑详情: /moviesets/<名>?page=N (实测)
        if '/moviesets/' in vid:
            url = vid if vid.startswith('http') else SITE + vid
            base = url.split('?')[0]
            h = self._html(url)
            name, pic, desc, act = self._meta(h, vid)
            ls = []
            for pg in (1, 2, 3):
                ph = h if pg == 1 else self._html(base + '?page=%d&sort=5' % pg, ref=url)
                got = self._cards(ph)
                if not got:
                    break
                ls.extend(got)
                _, tot = self._pageinfo(ph)
                if tot and pg >= tot:
                    break
            pl = [v['vod_name'] + '$' + v['vod_id'] for v in ls[:500]]
            return {'list': [{'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_actor': ','.join(act),
                              'vod_content': desc, 'vod_remarks': '收录 %d 部' % len(ls),
                              'vod_play_from': 'Javrate', 'vod_play_url': '#'.join(pl) if pl else '暂无影片$' + url}]}

        # 片商详情: /issuer/<名>?page=N&sort=5 (实测)
        if '/Issuer/' in vid or '/issuer/' in vid:
            url = vid if vid.startswith('http') else SITE + vid
            base = url.split('?')[0]
            h = self._html(url)
            name, pic, desc, act = self._meta(h, vid)
            ls = []
            for pg in (1, 2, 3):
                ph = h if pg == 1 else self._html(base + '?page=%d&sort=5' % pg, ref=url)
                got = self._cards(ph)
                if not got:
                    break
                ls.extend(got)
                _, tot = self._pageinfo(ph)
                if tot and pg >= tot:
                    break
            pl = [v['vod_name'] + '$' + v['vod_id'] for v in ls[:500]]
            return {'list': [{'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_actor': ','.join(act),
                              'vod_content': desc, 'vod_remarks': '收录 %d 部' % len(ls),
                              'vod_play_from': 'Javrate', 'vod_play_url': '#'.join(pl) if pl else '暂无影片$' + url}]}

        # 影片详情
        url = vid if vid.startswith('http') else SITE + '/movie/detail/' + vid + '.html'
        h = self._html(url) if vid.startswith('http') else self._dh(vid)
        if not h:
            return {'list': [{'vod_id': vid, 'vod_name': str(vid), 'vod_pic': '',
                              'vod_content': '详情取页失败: 站点盾判定较严, 请到「过盾工具」过一次验证后重试',
                              'vod_play_from': 'Javrate', 'vod_play_url': '正片$' + url}]}
        name, pic, desc, act = self._meta(h, vid)
        rk = []
        du = re.search(r'duration["\']?\s*[:=]\s*["\']?(\d{1,2}:\d{2}(?::\d{2})?)', h)
        if du:
            rk.append(du.group(1))
        return {'list': [{'vod_id': vid, 'vod_name': name, 'vod_pic': pic, 'vod_actor': ','.join(act),
                          'vod_content': desc, 'vod_remarks': ' '.join([x for x in rk if x]),
                          'vod_play_from': 'Javrate', 'vod_play_url': '正片$' + url}]}

    def searchContent(self, key, quick=False, pg='1'):
        if not key:
            return {'list': []}
        try:
            p = max(1, int(pg or 1))
        except Exception:
            p = 1
        k = quote(str(key))
        urls = [SITE + '/search/' + k + ('?page=%d' % p if p > 1 else ''),
                SITE + '/search?keyword=' + k]
        for u in urls:
            h = self._html(u)
            ls = self._cards(h)
            if ls:
                _, tot = self._pageinfo(h)
                return {'list': ls[:60], 'page': p,
                        'pagecount': min(tot or (p + 1 if len(ls) >= 30 else p), MAX_PAGE),
                        'limit': len(ls)}
        return {'list': []}

    def searchContentPage(self, key, quick, pg='1'):
        return self.searchContent(key, quick, pg)

    # ================= 播放 =================
    def _extract_m3u8(self, txt):
        if not txt:
            return ''
        for pat in (r'var\s+source\s*=\s*["\']([^"\']+)', r'var\s+(?:now|url|videoUrl|src|playUrl)\s*=\s*["\']([^"\']+)',
                    r'["\'](https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*)', r'(https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*)'):
            m = re.search(pat, txt)
            if m:
                u = H.unescape(m.group(1))
                if u.startswith('//'):
                    u = 'https:' + u
                if '/Player?' in u or '/player/' in u:
                    continue
                return u
        return ''

    # ================= 分片代理 =================
    def _proxy_url(self, key, extra=''):
        return 'http://127.0.0.1:9978/proxy?do=py&key=' + key + extra

    def _g(self, p, n):
        v = p.get(n) or ''
        return v[0] if isinstance(v, list) else v

    def localProxy(self, param):
        """播放代理: m3u8 与分片统一走这里, 每次都用 fresh token 重签, 长片不会中途断。"""
        try:
            if isinstance(param, dict):
                p = param
            else:
                q = param.split('?', 1)[-1]
                p = parse_qs(q) if '=' in q else {'key': [param]}
            key = unquote(self._g(p, 'key'))
            if not key:
                return [404, 'text/plain', '']
            try:
                s = json.loads(base64.urlsafe_b64decode(key.encode() + b'=' * (-len(key) % 4)).decode())
            except Exception:
                return [404, 'text/plain', '']
            seg = unquote(self._g(p, 'seg'))
            vpath = unquote(self._g(p, 'vpath'))
            if seg:
                u = self._mkurl(s, seg)
                b = self._bin(u)
                return [200, 'video/mp2t', b] if b else [404, 'text/plain', '']
            if vpath:
                u = self._mkurl(s, vpath)
                b = self._bin(u)
                if not b or b'#EXTM3U' not in b[:200]:
                    return [404, 'text/plain', '']
                root = u.split('?', 1)[0].rsplit('/', 1)[0]
                out = []
                for line in b.decode('utf-8', 'replace').splitlines():
                    t = line.strip()
                    if t and not t.startswith('#'):
                        full = t if t.startswith('http') else root + '/' + t.lstrip('/')
                        rel = full.split('//', 1)[1].split('/', 1)[1] if '//' in full else t
                        out.append(self._proxy_url(key, '&seg=' + quote(rel, safe='')))
                    else:
                        out.append(line)
                return [200, 'application/vnd.apple.mpegurl', '\n'.join(out).encode()]
            # 主清单
            b = self._bin(self._mkurl(s, 'playlist.m3u8'))
            if not b or b'#EXTM3U' not in b[:200]:
                return [404, 'text/plain', '']
            out = []
            for line in b.decode('utf-8', 'replace').splitlines():
                t = line.strip()
                if t and not t.startswith('#'):
                    if t.startswith('http'):
                        rel = t.split('//', 1)[1].split('/', 1)[1]
                    else:
                        rel = t
                    out.append(self._proxy_url(key, '&vpath=' + quote(rel, safe='')))
                else:
                    out.append(line)
            return [200, 'application/vnd.apple.mpegurl', '\n'.join(out).encode()]
        except Exception:
            return [404, 'text/plain', '']

    def _bin(self, url, ref=None):
        """取二进制(分片/m3u8)。分片走本机 HTTP, 不做过盾。"""
        hd = {'User-Agent': UA_D, 'Referer': SITE + '/', 'Accept': '*/*'}
        if ref:
            try:
                hd['Referer'] = ref
            except Exception:
                pass
        b = b''
        try:
            req = ur.Request(url, headers=hd)
            b = self._opener.open(req, timeout=15).read()
        except Exception:
            b = b''
        if not b and HAS_REQ:
            try:
                b = self._session().get(url, headers=hd, timeout=15).content
            except Exception:
                b = b''
        # 别把 CDN 的 403/错误页当成片源
        if b[:200].lstrip().lower().startswith(b'<html') or b'403 Forbidden' in b[:400]:
            return b''
        return b
