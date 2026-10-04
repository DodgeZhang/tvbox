# coding=utf-8
# =============================================================================
# AV大平台（porndav.com）四壳 Python Spider
# -----------------------------------------------------------------------------
# 站点形态：Laravel + Livewire 定制站（非苹果CMS / 非苹果系 JSON 接口）
# 入口域名：https://porndav.com   （语言前缀 /tw/，可用 /cn/ /en/ 同构切换）
#
# 取流路线（已实测）：
#   · 列表 / 详情 / 搜索 / 分类  —— 全部免登录，服务端直出 HTML，正则解析即可
#   · 播放                      —— 详情页脚本内联注入 loadFilm('{HOST}/trailer/{id}')
#                                 该地址直接吐出标准 HLS（media playlist），
#                                 分片走 5a439.sh06.co，AES-128 加密，key 地址
#                                 https://skey.sh06.co/key/en.key，全程无需登录
#   · 免费馆（/tw/live/free）   —— 页面内联 loadLiveFilm('...flv?token=..&ip=..')
#                                 该 token 与请求方 IP 绑定，换设备即失效，故只做解析保留
#
# 说明：详情页 og:video:duration 给的是正片时长，而 /trailer/{id} 固定为 90s 试看；
#      正片流由服务端在「已登录 + 已购」会话下另行下发，未登录态拿不到，本源统一走
#      /trailer/{id} 免登录取流（详见交付说明）。
#
# 分类体系：一级分类 10 个（快速选片 / 类型 / 限时免费 / 免费馆）
#           + 子分类 320 个标签（filters，全量从 /tw/tag 抓取）
#           + 演员筛选器（filters，主页运行时从 /tw/actors 动态拉热门演员）
#
# 铁律17：广告预检 has_ads=False —— 实测 /trailer/{id} 返回的 m3u8 为纯试看切片，
#        无贴片广告段；仍保留完整 m3u8 清洗链路（localProxy + _clean_m3u8 +
#        _is_ad_segment），以应对 CDN 侧策略变化。
# =============================================================================

import base64
import gzip
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urljoin, urlsplit

try:
    import requests
except Exception:
    requests = None

try:
    from base.spider import Spider as _BaseSpider
    _HAS_BASE = True
except Exception:
    try:
        from base.spider import BaseSpider as _BaseSpider
        _HAS_BASE = True
    except Exception:
        _HAS_BASE = False

        class _BaseSpider:
            pass


# ============================== 站点常量 ==============================
HOST = 'https://porndav.com'
LANG = 'tw'
HOME = HOST + '/' + LANG

UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36')

PAGE_SIZE = 24

# 一级分类： (type_id, 显示名, 路径)  —— 顺序与站点导航一致
CLASSES = [
    ('new', '最新上架', '/tw/video/all'),
    ('rank', '排行榜', '/tw/rank'),
    ('shorts', '短影片', '/tw/shorts'),
    ('exclusive', '大平台独家', '/tw/video/exclusive'),
    ('jav', '中文', '/tw/video/type/jav'),
    ('nopix', '无码', '/tw/video/type/not-pixelated'),
    ('euam', '欧美', '/tw/video/type/europe-america'),
    ('china', '国产', '/tw/video/type/china'),
    ('free', '限时免费', '/tw/free'),
    ('live', '免费馆', '/tw/live/free'),
]

# 单页、无翻页的分类
NO_PAGING = ('live',)   # 免费馆页忽略页码参数，固定单页

# 子分类（标签）：全量 320 条，抓自 https://porndav.com/tw/tag
TAGS = [
    ("monomer-works", "單體作品"), ("cumshot", "中出內射"), ("big-boobs", "巨乳"), ("wife", "人妻"),
    ("ntr", "NTR"), ("milf", "熟女"), ("slim", "苗條"), ("slut", "痴女"),
    ("plot", "劇情版"), ("blowjob", "口交"), ("amateurs", "素人"), ("beautiful-teen", "美少女"),
    ("live-selfie", "直播自拍"), ("insult", "凌辱"), ("over-4-hours", "4小時以上作品"), ("candid", "偷拍"),
    ("beautiful-legs", "美腳"), ("two-girls", "女女蕾絲"), ("debut", "出道作"), ("incest", "亂倫"),
    ("3p4p", "3P・4P"), ("field-exposure", "野外露出"), ("assistance-communication", "援交"), ("very-lewd", "大亂搞"),
    ("beautiful-tits", "美乳"), ("shame", "羞恥"), ("ghostism", "鬼畜"), ("dirty-talk", "淫語"),
    ("big-butt", "大屁股"), ("adultery", "不倫"), ("flat-chested", "貧乳"), ("beautiful-butt", "美臀"),
    ("delusion", "妄想"), ("sweat-sex", "汗流浹背"), ("couple-exchange", "伴侶交換"), ("petite", "嬌小"),
    ("tall", "高挑"), ("cross-dresser", "偽娘"), ("beautiful-thighs", "美腿"), ("baby-face", "童顔"),
    ("huge-cock", "巨屌"), ("first-shot", "初攝"), ("mousozoku", "妄想族"), ("transsexual", "變性"),
    ("legs-fetish", "戀腳癖"), ("massage", "按摩"), ("promiscuous", "粗暴"), ("ass-fetish", "戀臀癖"),
    ("harem", "後宮"), ("date", "約會"), ("extreme-orgasm", "極致高潮"), ("funny", "惡作劇"),
    ("condom-off", "無套"), ("s-female", "S女"), ("torture", "拷問"), ("pure", "清純"),
    ("love", "戀愛"), ("premature-ejaculation", "早洩"), ("f-cup", "F罩杯"), ("soft-body", "柔軟身體"),
    ("yoga", "瑜珈"), ("e-cup", "E罩杯"), ("sexy", "性感"), ("transgender", "跨性別"),
    ("d-cup", "D罩杯"), ("50-years", "五十歲"), ("g-cup", "G罩杯"), ("adapted-from-the-comic-book", "漫畫改編"),
    ("short-video", "短視頻"), ("pronunciation", "特殊發音"), ("complaint", "説教"), ("smooth-and-white-skin", "皮膚白皙"),
    ("group-sex", "多P"), ("sex-education", "性教育"), ("tundele", "傲嬌"), ("muscle", "肌肉"),
    ("black-skin", "皮膚黝黑"), ("H-cup", "H罩杯"), ("obscene-drama", "淫穢劇"), ("comedy", "搞笑/喜劇"),
    ("experience-confession", "告白"), ("defecation", "糞便"), ("SF", "科幻"), ("anime", "日本動畫"),
    ("anime-characters", "動漫人物"), ("gangster", "黑幫"), ("Japanese-clothes", "和服・喪服"), ("shota", "正太控"),
    ("virgin-male", "處男"), ("prostitute", "妓女"), ("sex-slave", "性奴"), ("fat-woman", "豐腴"),
    ("taking-turns", "輪流抽插"), ("foot-job", "腳炮"), ("deep-throat", "深喉嚨"), ("urine", "放尿"),
    ("force", "強插"), ("cum-explosion-in-mouth", "口爆"), ("squirt", "潮吹"), ("slave-training", "調教"),
    ("titty-fuck", "乳交"), ("anal-sex", "肛交"), ("facial-cumshot", "顏射"), ("69-sex", "69式"),
    ("shaved", "剃毛"), ("tied-up-and-fucked", "束縛"), ("riding", "騎乘位"), ("masturbation", "自慰"),
    ("jerk-off", "打手槍"), ("pussy-licking", "舔陰"), ("face-riding", "面騎"), ("breast-milk", "母乳"),
    ("immediate", "當場做愛"), ("orgasm", "高潮"), ("sm", "SM"), ("enema", "浣腸"),
    ("pussy-fingering", "指交"), ("promiscuity", "濫交"), ("mangle-return", "打樁機"), ("man-squirting", "男人潮吹"),
    ("kiss", "接吻"), ("expose", "走光"), ("doggy-style", "後背位"), ("lesbian-kiss", "女同之吻"),
    ("drinking-urine", "喝尿"), ("dancing", "跳舞"), ("absentminded", "翻白眼"), ("spanking", "打屁股"),
    ("vomit", "嘔吐"), ("fist-fuck", "拳交"), ("rape", "強姦"), ("coprophagy", "食糞"),
    ("Women-on-top", "女上位"), ("peeking", "偷窥"), ("gang-rape", "輪姦"), ("sexual-harassment", "性騷擾"),
    ("hunting", "獵豔"), ("anal-creampie", "肛内中出"), ("swallowing-cum", "吞精"), ("cosplay", "角色扮演"),
    ("japanese-chikan", "痴漢"), ("fashion-beauty", "時尚美女"), ("teacher", "女教師"), ("mourish", "喪服"),
    ("hot", "辣妹"), ("idolentertainer", "偶像/藝人"), ("leather", "皮革緊身"), ("widow", "寡婦"),
    ("maternal-family", "母系家族"), ("maid", "女僕"), ("racing-girl", "賽車女郎"), ("cheongsam", "旗袍"),
    ("mixed-girl", "混血兒"), ("virgin-sex", "處女"), ("hotel-public-relations", "酒店公關"), ("office-lady", "OL"),
    ("mom-in-law", "岳母"), ("sailor", "水手服"), ("celebrity", "名媛"), ("model", "模特兒"),
    ("swimsuit", "泳裝"), ("shemale", "人妖"), ("secretary", "秘書"), ("female-anchor", "女主播"),
    ("school-uniform", "學生服"), ("african-american", "黑人男優"), ("bath-girl", "風俗孃"), ("mini-skirt", "迷你裙"),
    ("virginity", "童貞"), ("teen", "蘿莉"), ("nurse", "護士"), ("kimono", "和服"),
    ("foreigner", "洋妞"), ("stewardess", "空姐"), ("taiwanese-amateur", "台灣素人"), ("female-university-student", "女大生"),
    ("uniform", "制服"), ("various-occupations", "各種職業"), ("m-male", "M男"), ("schoolgirl", "女學生"),
    ("female-boss", "女上司"), ("mother", "母親"), ("pregnant-woman", "孕婦"), ("bride", "新娘"),
    ("female-doctor", "女醫生"), ("female-investigator", "女調查員"), ("sexy-lingerie", "性感內衣"), ("sportswear", "運動服"),
    ("leotard", "緊身衣"), ("sister", "姊姊"), ("m-female", "M女"), ("aunt", "阿姨"),
    ("bathrobe", "浴衣"), ("young-wife", "幼妻"), ("30-years", "三十歲"), ("manager", "經理"),
    ("employeecolleague", "下屬/同事"), ("short-hair", "短髮"), ("40-years", "四十歲"), ("bunny", "兔女郎"),
    ("tutor", "家庭教師"), ("couple", "情侶"), ("young-ladydaughter", "小姐/女兒"), ("business-attire", "職業裝"),
    ("hostess", "女主人"), ("childhood-sweetheart", "青梅竹馬"), ("nude-apron", "裸體圍裙"), ("adopted-daughter", "女兒、養女"),
    ("wearing-erotic", "穿著色情"), ("no-panties", "沒穿內褲"), ("receptionist", "接待員"), ("no-bra", "沒穿內衣"),
    ("fighter", "格闘家"), ("female-ninja", "女忍者"), ("waitress", "女服務員"), ("show-girl", "展場接待員"),
    ("bus-guide", "巴士乘務員"), ("porn-star", "AV女優"), ("gay", "同性戀"), ("ancient-costume", "古裝劇情"),
    ("campaign-girl", "競選女郎"), ("housewife", "家政婦"), ("friend-with-benefit", "炮友"), ("athlete", "運動員"),
    ("look-alike", "相似者"), ("grandpa", "爺爺"), ("celebrities", "名人"), ("female-warrior", "女戰士"),
    ("longuehea", "長髮"), ("lecturer", "講師"), ("nerd", "宅男"), ("queen", "女王"),
    ("magical-girl", "魔法少女"), ("cheerleader", "啦啦隊長"), ("princess", "公主"), ("black-hair", "黑髮"),
    ("blonde-hair", "金髪"), ("witch", "巫女"), ("mommy-friends", "媽咪朋友"), ("futanari", "雙性人"),
    ("grandma", "奶奶"), ("waist", "小蠻腰"), ("brown-hair", "茶髪"), ("Taiwanese-model", "台灣模特兒"),
    ("witch-costume", "魔女"), ("bunny-girl", "兔女郎"), ("drug", "春藥"), ("apron", "圍裙"),
    ("stockings", "絲襪"), ("glasses", "眼鏡"), ("vibradores", "電動按摩棒"), ("panty-and-stocking-with-garterbelt", "吊帶襪"),
    ("dildo", "情趣玩具"), ("lotion-oil", "乳液"), ("drugs", "藥物和壯陽藥"), ("soap", "肥皂"),
    ("doll", "人形娃娃"), ("candle", "蠟燭"), ("animals", "貓耳朵/動物"), ("masks", "面具"),
    ("bubble-socks", "泡泡襪"), ("pantyhose", "連褲襪"), ("hook-nose", "鼻勾"), ("tentacle", "觸手"),
    ("speculum", "窺器"), ("cervix", "子宮頸"), ("love-egg", "跳蛋"), ("spa", "溫泉"),
    ("hospital", "醫院"), ("campus", "校園"), ("public-toilet", "公廁"), ("tram", "電車"),
    ("sports", "運動"), ("car", "汽車"), ("office", "辦公室"), ("school-swimsuit", "死庫水"),
    ("train-chikan", "電車痴漢"), ("drinking-party", "酒會/聯歡會"), ("bath", "風呂"), ("open-air-bath", "露天風呂"),
    ("travel", "旅行"), ("beauty-salon", "美容院"), ("sofa", "沙發"), ("thin-mosaic", "數位薄碼"),
    ("nude", "全裸"), ("av-planning", "AV企劃"), ("collaboration", "女優合輯"), ("street-accosted", "搭訕"),
    ("av-topic", "AV話題"), ("for-women", "女性向"), ("asia", "華人國產"), ("fetish", "戀物癖"),
    ("best-collection", "合集"), ("original-cooperation", "原創合作"), ("album", "寫真視頻"), ("poult", "倒追"),
    ("pov", "男優視角"), ("document", "紀錄片"), ("interview", "面試"), ("time-stop", "時間停止"),
    ("insertion", "異物插入"), ("imprison", "監禁"), ("drunk", "泥醉"), ("foot-affair", "戀足癖"),
    ("actionfighting", "格鬥動作"), ("over-16-hours", "16時間以上作品"), ("special-effects", "特殊攝影"), ("detail-shot", "局部特寫"),
    ("emmanuelle", "艾曼紐"), ("post", "投稿"), ("game-live-action", "遊戲實景"), ("pov-sex", "第一視角"),
    ("vip", "VIP會員點播"), ("ai-decoding-version", "AI解碼版"), ("VR", "VR"), ("AI-generated", "AI生成作品"),
    ("romantic-comedy", "浪漫喜劇"), ("hypnosis", "催眠"), ("Sunburn", "曬斑"), ("tickling", "搔癢"),
]

# 免费馆直播频道（免登录可看，其余频道需登录，故只保留 free）
LIVE_CHANNELS = [
    ('free', '免费馆'),
]


# ============================== 铁律11：敏感词古典映射表 ==============================
# 说明：本表按技能规范保留（供需要时开启），但按本次交付要求**不启用实际替换**，
#      desensitize() 原样透传，站点原始标题/标签不做任何改写。
CLASSICAL_MAP = {
    "成人": "风月", "色情": "风月", "情色": "春宫", "淫": "风月", "黄色": "春宫", "淫秽": "猥亵",
    "AV": "光影", "av": "光影", "三级": "风月",
    "激情": "云雨", "做爱": "云雨", "性交": "交欢", "欲": "情思", "高潮": "云端",
    "偷拍": "窥帘", "偷窥": "窥帘", "乱伦": "禁脔", "强奸": "强占", "轮奸": "群辱",
    "迷奸": "迷占", "无码": "素纱", "有码": "遮面", "熟女": "徐娘",
    "萝莉": "豆蔻", "幼女": "玉蕊", "少女": "碧玉", "学生": "书生",
    "人妻": "罗敷", "少妇": "艳妇", "御姐": "玉人", "护士": "药女",
    "教师": "先生", "医生": "郎中", "警察": "捕快", "军人": "军爷",
    "秘书": "掌印", "老板": "东家", "丈夫": "夫君", "妻子": "拙荆",
    "情人": "相好", "小三": "外遇", "二奶": "外室", "出轨": "翻墙",
    "偷情": "私会", "通奸": "私通", "嫖娼": "寻花", "卖淫": "卖身",
    "妓女": "花娘", "性骚扰": "轻薄", "猥亵": "猥亵", "露阴": "曝玉",
    "咸猪手": "禄山爪", "丝袜": "丝履", "网袜": "网履", "内衣": "亵衣",
    "内裤": "亵裤", "情趣": "风月", "春药": "催情", "巨乳": "丰盈",
    "爆乳": "丰盈", "胸": "酥胸", "乳": "玉兔", "美乳": "玉兔",
    "臀": "玉臀", "屁股": "玉臀", "脚": "莲步", "玉足": "莲步",
    "腿": "玉腿", "裸体": "玉体", "全裸": "玉体", "半裸": "半褪",
    "走光": "泄春", "露点": "泄玉", "自慰": "弄玉", "口交": "含朱",
    "口活": "含朱", "肛交": "后庭", "屁眼": "后庭", "肛门": "后庭",
    "群交": "合卺", "乳交": "玉兔", "足交": "莲步", "车震": "车行",
    "野战": "郊合", "精液": "元阳", "精子": "元阳", "阴道": "幽处",
    "阴户": "幽处", "阴茎": "玉茎", "阳具": "玉茎", "SM": "调教",
    "制服": "官衣", "OL": "衙内", "空姐": "行云", "继母": "继室",
    "姐妹": "同根", "同学": "同窗", "邻居": "东邻", "处女": "处子",
    "初夜": "破瓜", "暴力": "杀伐", "血腥": "殷红", "恐怖": "幽冥",
    "赌博": "孤注", "毒品": "药石", "枪支": "火器", "刀具": "利刃",
}

# 铁律13：未成年内容关键词（命中即整条目剔除，最高优先级）
# 说明：只保留明确指向未成年的词。校园 / 学生 / 制服 / 美少女 / 少女 等属于成人题材标签，
# 不作为未成年判定依据，不剔除（避免批量误杀正常条目）。
_MINOR_KEYWORDS = (
    '未成年', '稚子', '幼童', '儿童', '兒童', '幼女', '萝莉', '小學生', '小学生',
    '中學生', '中学生', '國中', '国中',
    'loli', 'lolita', 'teen', 'schoolgirl', 'child', 'underage', 'shota',
)

# 铁律15：默认反代配置（CF 站）
_PROXY_CONFIG_PATHS = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'proxy_config.json'),
    os.path.expanduser('~/.deepseek/skills/zaka-video-site-build/assets/proxy_config.json'),
    os.path.expanduser('~/.super_doubao/super-doubao-runtime/workspace/.user_skills/tvbox-dev/assets/proxy_config.json'),
)
_DEFAULT_PROXY_FALLBACK = 'https://xsz-shared-proxy.97471201.workers.dev'

_pic_proxy_port = None
_proxy_lock = threading.Lock()
_pic_cache = {}


def _load_default_proxy():
    for path in _PROXY_CONFIG_PATHS:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                proxy = (data.get('default_proxy') or '').strip()
                if proxy:
                    return proxy
        except Exception:
            continue
    return _DEFAULT_PROXY_FALLBACK


# ============================== 脱敏 / 过滤 ==============================
def desensitize(text):
    """按交付要求关闭实际替换：原样透传（不做任何敏感词改写）。"""
    if text is None:
        return ''
    return str(text)


def _is_minor_content(text):
    """铁律13：未成年内容识别（命中即剔除，不改写）"""
    if not text:
        return False
    low = str(text).lower()
    for kw in _MINOR_KEYWORDS:
        if kw.lower() in low:
            return True
    return False


def _sanitize_classes(classes):
    out = []
    for c in classes or []:
        name = desensitize(c.get('type_name') or '')
        if not name or _is_minor_content(name):
            continue
        out.append({'type_id': str(c.get('type_id')), 'type_name': name})
    return out


def _sanitize_list(items):
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = desensitize(it.get('vod_name') or '')
        if not name or _is_minor_content(name):
            continue
        it = dict(it)
        it['vod_name'] = name
        out.append(it)
    return out


def _sanitize_vod(vod):
    if not isinstance(vod, dict):
        return None
    name = desensitize(vod.get('vod_name') or '')
    if not name or _is_minor_content(name):
        return None
    vod = dict(vod)
    vod['vod_name'] = name
    for k in ('vod_content', 'vod_actor', 'vod_director', 'vod_area'):
        if k in vod:
            vod[k] = desensitize(vod.get(k) or '')
    return vod


def _b64e(text):
    try:
        return base64.urlsafe_b64encode(str(text).encode('utf-8')).decode('ascii')
    except Exception:
        return ''


def _b64d(text):
    try:
        pad = '=' * (-len(text) % 4)
        return base64.urlsafe_b64decode(str(text) + pad).decode('utf-8', 'ignore')
    except Exception:
        return ''


def _mime(data):
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:2] == b'\xff\xd8':
        return 'image/jpeg'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF':
        return 'image/webp'
    return 'application/octet-stream'


# ============================== 图片本地代理 ==============================
class _PicHandler(BaseHTTPRequestHandler):
    spider = None

    def log_message(self, *a):
        pass

    def do_GET(self):
        q = self.path.split('url=', 1)[-1]
        data = self.spider._fetch_pic(unquote(q))
        if not data:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', _mime(data))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(data)


class Spider(_BaseSpider):
    """铁律8：双协议兼容继承 base.spider，13 个标准接口齐全"""

    def __init__(self):
        self.session = requests.Session() if requests is not None else None
        if self.session is not None:
            self.session.headers.update({'User-Agent': UA})
        self._cache = {}
        self._actor_cache = None
        # 铁律15：反代相关属性初始化
        self.rawSite = HOST
        self.siteUrl = HOST
        self.HOST = HOST
        self._use_proxy = True
        self._default_proxy = _load_default_proxy()

    def getName(self):
        return 'AV大平台'

    def init(self, extend=''):
        config = {}
        if isinstance(extend, dict):
            config = extend
        elif extend:
            try:
                config = json.loads(extend)
            except Exception:
                try:
                    import ast
                    config = ast.literal_eval(extend)
                except Exception:
                    config = {}

        # 铁律15：原始站点（防盗链 Referer / Origin 用 rawSite）
        raw = config.get('host') or config.get('rawSite') or HOST
        if not str(raw).startswith('http'):
            raw = 'https://' + str(raw)
        self.rawSite = str(raw).rstrip('/')

        direct = str(config.get('direct', '')).lower() in ('1', 'true', 'yes', 'on')
        ext_proxy = str(config.get('proxy') or config.get('siteUrl') or '').strip()
        if direct:
            self._use_proxy = False
            self.siteUrl = self.rawSite
        elif ext_proxy:
            self._use_proxy = True
            self.siteUrl = ext_proxy.rstrip('/')
        else:
            # CF 站：默认走反代，避免机房 IP 被 Cloudflare 拦
            self._use_proxy = True
            self.siteUrl = self._default_proxy
        self.HOST = self.siteUrl

    # ==================== HTTP 自适应层（requests → urllib） ====================
    def _headers(self, referer=None):
        h = {
            'User-Agent': UA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        }
        if referer:
            h['Referer'] = referer
        return h

    def _http(self, url, referer=None, timeout=15, raw=False, headers=None, body=None, method='GET'):
        hd = self._headers(referer)
        payload = body.encode('utf-8') if isinstance(body, str) else body
        if payload is not None:
            # 分页参数放请求体：站点对 URL 携带 page= 的请求配置了 WAF 规则，
            # 放 body 后由 Laravel 的 $request->input('page') 正常读取
            hd['Content-Type'] = 'application/json'
            hd['X-Requested-With'] = 'XMLHttpRequest'
        if headers:
            hd.update(headers)
        if self.session is not None:
            try:
                r = self.session.request(method, url, headers=hd, data=payload,
                                         timeout=timeout, verify=False)
                if not raw:
                    r.encoding = 'utf-8'
                return r.content if raw else r.text
            except Exception:
                return b'' if raw else ''
        try:
            req = urllib.request.Request(url, data=payload, headers=hd, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
            return data if raw else data.decode('utf-8', 'ignore')
        except Exception:
            return b'' if raw else ''

    def _get(self, url, referer=None, timeout=15):
        now = time.time()
        hit = self._cache.get(url)
        if hit and now - hit[0] < 180:
            return hit[1]
        txt = self._http(url, referer=referer or (HOME + '/'), timeout=timeout)
        if txt:
            self._cache[url] = (now, txt)
        return txt

    def _is_blocked(self, txt):
        return (not txt) or ('Just a moment' in txt[:3000]) or ('cf_chl_opt' in txt[:6000])

    def _get_page(self, base, page=1, referer=None, timeout=20):
        """分页取页：页码只放请求体（不拼进 URL），并做直连→反代双通道降级"""
        p = int(page) if page else 1
        ref = referer or (HOME + '/')
        key = '%s#p%d' % (base, p)
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - hit[0] < 180:
            return hit[1]
        body = json.dumps({'page': p}) if p > 1 else None
        txt = self._http(self.rawSite + base, referer=ref, timeout=timeout, body=body, method='GET')
        if self._is_blocked(txt) and self._default_proxy:
            txt2 = self._http(self._default_proxy + base, referer=ref, timeout=timeout, body=body, method='GET')
            if not self._is_blocked(txt2):
                txt = txt2
        if txt:
            self._cache[key] = (now, txt)
        return txt

    def _fetch_pic(self, url):
        if not url:
            return b''
        now = time.time()
        hit = _pic_cache.get(url)
        if hit and now - hit[0] < 600:
            return hit[1]
        data = self._http(url, referer=self.rawSite + '/', timeout=12, raw=True)
        if data:
            _pic_cache[url] = (now, data)
        return data or b''

    def _start_pic_proxy(self):
        global _pic_proxy_port
        with _proxy_lock:
            if _pic_proxy_port:
                return _pic_proxy_port
            _PicHandler.spider = self
            httpd = ThreadingHTTPServer(('127.0.0.1', 0), _PicHandler)
            _pic_proxy_port = httpd.server_address[1]
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            return _pic_proxy_port

    def _pic_url(self, url):
        if not url:
            return ''
        try:
            return 'http://127.0.0.1:{}/pic?url={}'.format(self._start_pic_proxy(), quote(url, safe=''))
        except Exception:
            return url

    # ==================== 站内页解析 ====================
    _TITLE_TAIL = re.compile(r'\s*[-|]\s*AV\s*大平台.*$', re.S)

    def _clean_title(self, title):
        t = re.sub(r'\s+', ' ', (title or '')).strip()
        t = self._TITLE_TAIL.sub('', t)
        return t.strip(' -|')

    def _cards(self, html):
        """列表页卡片解析：影片卡片 /tw/video/detail/{id}，短影片卡片 /tw/shorts/{id}"""
        out = []
        if not html:
            return out
        parts = re.split(r'<a\b(?=[^>]*?href="[^"]*?(?:/video/detail/\d+|/tw/shorts/\d+)")', html)
        seen = set()
        for seg in parts[1:]:
            m = re.match(
                r'[^>]*?href="(?:https?://[^"]*?)?(?:/video/detail/(\d+)|/tw/shorts/(\d+))"[^>]*?title="([^"]*)"',
                seg, re.S)
            if not m:
                continue
            vnum, snum, raw_title = m.group(1), m.group(2), m.group(3)
            vid = ('s' + snum) if snum else vnum
            if not vid or vid in seen:
                continue
            title = self._clean_title(raw_title)
            if not title:
                continue
            seen.add(vid)
            pm = re.search(r'<img[^>]*?src="([^"]+)"', seg)
            pic = pm.group(1) if pm else ''
            if pic.startswith('//'):
                pic = 'https:' + pic
            dm = re.search(r'(\d{4}/\d{2}/\d{2})', seg)
            remark = dm.group(1) if dm else ''
            out.append({
                'vod_id': vid,
                'vod_name': title,
                'vod_pic': self._pic_url(pic) if pic else '',
                'vod_remarks': remark,
            })
        return out

    def _pagecount(self, html, per_page=PAGE_SIZE, got=0):
        """分页页数：从页码输入框 max 属性取实测值；无该控件按单页处理"""
        if not html:
            return 0
        m = re.search(r'id="page"[^>]*?max="?(\d+)', html)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return 0
        return 0   # 无分页控件 → 页数未知，交由上层按单页/未知处理

    def _dt_dd(self, html, label):
        m = re.search(r'<dt[^>]*>\s*' + re.escape(label) + r'\s*</dt>\s*<dd[^>]*>(.*?)</dd>', html or '', re.S)
        return m.group(1) if m else ''

    def _links_of(self, block, pattern):
        out = []
        for m in re.finditer(pattern, block or '', re.S):
            name = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', m.group(2))).strip()
            if name and name not in out:
                out.append(name)
        return out

    def _hot_actors(self, limit=40):
        """从 /tw/actors 抓热门演员（用于子分类筛选器），进程内缓存"""
        if self._actor_cache is not None:
            return self._actor_cache
        html = self._get_page('/tw/actors', 1)
        out = []
        seen = set()
        for m in re.finditer(r'<a\b[^>]*?href="(?:https?://[^"]*?)?/tw/actors/(\d+)"[^>]*?title="([^"]*)"', html or '', re.S):
            aid, name = m.group(1), self._clean_title(m.group(2))
            if not aid or aid in seen or not name or _is_minor_content(name):
                continue
            seen.add(aid)
            out.append((aid, name))
            if len(out) >= limit:
                break
        self._actor_cache = out
        return out

    def _filters(self):
        """子分类：320 个标签 + 热门演员（运行时动态）"""
        tag_values = [{'n': '全部', 'v': ''}]
        for slug, name in TAGS:
            if _is_minor_content(name):
                continue
            tag_values.append({'n': name, 'v': slug})
        base = [{'key': 'tag', 'name': '标签', 'value': tag_values}]
        actors = self._hot_actors()
        if actors:
            av = [{'n': '全部', 'v': ''}]
            for aid, aname in actors:
                av.append({'n': aname, 'v': aid})
            base.append({'key': 'actor', 'name': '演员', 'value': av})
        return base

    def _build_url(self, base, page):
        url = self.siteUrl + base
        if page and int(page) > 1:
            url += ('&' if '?' in url else '?') + 'page=%d' % int(page)
        return url

    def _resolve_base(self, tid, ext):
        """决定分类请求路径：演员 > 标签 > 一级分类"""
        actor = str(ext.get('actor') or '').strip() if isinstance(ext, dict) else ''
        tag = str(ext.get('tag') or '').strip() if isinstance(ext, dict) else ''
        if actor:
            return '/tw/actors/' + actor
        if tag:
            return '/tw/video/' + tag
        for cid, _name, path in CLASSES:
            if cid == str(tid):
                return path
        return '/tw/video/all'

    # ==================== 13 接口 ====================
    def homeContent(self, filter):
        classes = [{'type_id': cid, 'type_name': name} for cid, name, _p in CLASSES]
        classes = _sanitize_classes(classes)
        filters = {}
        try:
            f = self._filters()
            for c in classes:
                filters[c['type_id']] = f
        except Exception:
            filters = {}
        return {'class': classes, 'filters': filters}

    def homeVideoContent(self):
        html = self._get_page('/tw/video/all', 1)
        return {'list': _sanitize_list(self._cards(html))}

    def categoryContent(self, tid, pg=1, filter=False, extend=''):
        p = int(pg) if pg else 1
        ext = extend if isinstance(extend, dict) else {}
        base = self._resolve_base(tid, ext)
        html = self._get_page(base, p)
        items = self._cards(html)
        pagecount = self._pagecount(html, got=len(items))
        if str(tid) in NO_PAGING and not ext.get('tag') and not ext.get('actor'):
            pagecount = 1
        return {
            'page': p,
            'pagecount': pagecount,
            'limit': PAGE_SIZE,
            'total': len(items),
            'list': _sanitize_list(items),
        }

    def detailContent(self, ids):
        # 铁律8：ids 是 list/tuple 必须遍历
        id_list = list(ids) if isinstance(ids, (list, tuple)) else [ids]
        result_list = []
        for source_id in id_list:
            vid = str(source_id)
            if not re.match(r'^s?\d+$', vid):
                vid = _b64d(vid)
            if not re.match(r'^s?\d+$', vid or ''):
                continue
            if vid.startswith('s'):
                vod = self._short_detail(vid[1:])
            else:
                vod = self._detail(vid)
            cleaned = _sanitize_vod(vod) if vod else None
            if cleaned is not None:
                result_list.append(cleaned)
        return {'list': result_list}

    def _short_detail(self, vid):
        """短影片详情：页面内 <source src> 直接给完整 MP4（免登录）"""
        html = self._get_page('/tw/shorts/' + str(vid), 1)
        if not html:
            return None
        hm = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        title = ''
        if hm:
            title = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', hm.group(1))).strip()
            title = re.sub(r'^[^|]*\|\s*短影片\s*\|\s*', '', title)
        title = self._clean_title(title) or ('短影片 ' + str(vid))

        pm = re.search(r'<source[^>]*?src="([^"]+)"', html)
        play_url = pm.group(1) if pm else ''
        if not play_url:
            lm = re.search(r'streaming_url\\?"?\s*:\s*\\?"(https[^"\\]+)', html)
            if lm:
                play_url = lm.group(1).replace('\\/', '/')

        pic = ''
        im = re.search(r'<video[^>]*?poster="([^"]+)"', html)
        if im:
            pic = im.group(1)

        dm = re.search(r'(\d{4}/\d{2}/\d{2})', html)
        date = dm.group(1) if dm else ''

        kids = []
        for m in re.finditer(r'<a\b[^>]*?href="[^"]*?/tw/video/[a-zA-Z0-9\-_]+"[^>]*?>([^<]{1,20})</a>', html, re.S):
            n = self._clean_title(re.sub(r'<[^>]+>', '', m.group(1)))
            if n and n not in kids and len(kids) < 12:
                kids.append(n)

        return {
            'vod_id': 's' + str(vid),
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': date or '短影片',
            'vod_year': (date[:4] if date else ''),
            'vod_content': ('标签：' + '、'.join(kids)) if kids else '',
            'vod_play_from': 'AV大平台',
            'vod_play_url': '正片$' + play_url,
        }

    def _detail(self, vid):
        html = self._get_page('/tw/video/detail/' + str(vid), 1)
        if not html:
            return None

        tm = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', html)
        title = self._clean_title(tm.group(1)) if tm else ''
        if not title:
            hm = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            title = self._clean_title(re.sub(r'<[^>]+>', '', hm.group(1))) if hm else ('影片 ' + str(vid))
        title = re.sub(r'^.*?\|', '', title).strip() if '|' in title and len(title) > 90 else title
        if not title:
            title = '影片 ' + str(vid)

        pm = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]*)"', html)
        pic = pm.group(1) if pm else ''

        dm = re.search(r'<meta[^>]*property="og:video:duration"[^>]*content="([^"]*)"', html)
        duration = dm.group(1) if dm else ''

        ym = re.search(r'<meta[^>]*property="og:video:release_date"[^>]*content="([^"]*)"', html)
        if not ym:
            ym = re.search(r'<dt[^>]*>\s*上架日\s*</dt>\s*<dd[^>]*>\s*([0-9/.\-]+)', html)
        date = ym.group(1) if ym else ''

        actors = self._links_of(self._dt_dd(html, '演員'), r'<a\b[^>]*?href="([^"]*?/tw/actors/\d+)"[^>]*?>(.*?)</a>')
        tag_names = []
        for m in re.finditer(r'<a\b[^>]*?href="(?:https?://[^"]*?)?/tw/video/[a-zA-Z0-9\-_]+"[^>]*?>([^<]{1,40})</a>', self._dt_dd(html, '標籤'), re.S):
            n = self._clean_title(re.sub(r'<[^>]+>', '', m.group(1)))
            if n and n not in tag_names:
                tag_names.append(n)

        maker = re.sub(r'<[^>]+>', '', self._dt_dd(html, '製作商'))
        maker = re.sub(r'\s+', ' ', maker).strip()

        lm = re.search(r"loadFilm\('([^']+)'\)", html)
        if lm:
            play_url = lm.group(1).replace('\\/', '/')
            # 详情页注入的取流地址可能是相对/绝对，统一用原始站点域名补全
            if play_url.startswith('/'):
                play_url = self.rawSite + play_url
        else:
            play_url = '{}/trailer/{}'.format(self.rawSite, vid)

        content_parts = []
        if tag_names:
            content_parts.append('标签：' + '、'.join(tag_names))
        if maker:
            content_parts.append('制作商：' + maker)
        if duration:
            content_parts.append('片长：' + duration)
        if date:
            content_parts.append('上架：' + date)

        vod = {
            'vod_id': str(vid),
            'vod_name': title,
            'vod_pic': pic,
            'vod_remarks': duration or date,
            'vod_year': (date[:4] if date else ''),
            'vod_actor': '、'.join(actors),
            'vod_director': maker,
            'vod_content': '\n'.join(content_parts),
            'vod_play_from': 'AV大平台',
            'vod_play_url': '正片$' + play_url,
        }
        return vod

    def searchContent(self, key, quick=False, pg=1):
        p = int(pg) if pg else 1
        base = '/tw/search?query=' + quote(str(key))
        html = self._get_page(base, p)
        items = self._cards(html)
        return {
            'list': _sanitize_list(items),
            'page': p,
            'pagecount': self._pagecount(html, got=len(items)),
            'limit': 12,
            'total': len(items),
        }

    def playerContent(self, flag, id, vipFlags=None):
        raw = str(id)
        if not raw.startswith('http'):
            raw = _b64d(raw)
        raw = unquote(raw)
        # 铁律·广告拦截：m3u8 走本地代理清洗；非 m3u8 直连
        if '.m3u8' in raw or '/trailer/' in raw:
            url = self._proxy_m3u8_url(raw, self.rawSite + '/')
        else:
            url = raw
        # 铁律15：防盗链双 Header，Referer/Origin 用原始站点 rawSite
        return {
            'parse': 0,
            'url': url,
            'header': {
                'User-Agent': UA,
                'Referer': self.rawSite + '/',
                'Origin': self.rawSite,
            },
        }

    def liveContent(self, url=''):
        """免费馆直播（/tw/live/free 页面内联 loadLiveFilm 的 FLV 直链）"""
        try:
            html = self._get_page('/tw/live/free', 1)
            m = re.search(r"loadLiveFilm\('([^']+)'", html or '')
            if not m:
                return ''
            play = m.group(1).replace('\\/', '/')
            return '#EXTM3U\n#EXTINF:-1 tvg-name="免费馆" group-title="AV大平台",免费馆\n%s\n' % play
        except Exception:
            return ''

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|flv|ts)(\?|$)', url or '', re.I))

    def manualVideoCheck(self):
        return False

    def getDependence(self):
        return ''

    def action(self, action):
        return ''

    def destroy(self):
        try:
            if self.session is not None:
                self.session.close()
        except Exception:
            pass
        return ''

    # ==================== m3u8 广告清洗 + 本地代理（铁律·广告拦截） ====================
    def _sanitize_m3u8_url(self, url):
        """清洗m3u8 URL中的广告参数（cover/poster/thumb/pic等）"""
        if not url:
            return url
        url = unquote(url)
        url = re.sub(r'&[Cc]over=.*', '', url)
        url = re.sub(r'&[Pp]oster=.*', '', url)
        url = re.sub(r'&[Tt]humb=.*', '', url)
        url = re.sub(r'&[Pp]ic=.*', '', url)
        url = url.rstrip('&?')
        return url

    def _proxy_m3u8_url(self, url, referer=''):
        """生成m3u8代理地址：优先用壳的getProxyUrl()，否则返回原地址"""
        try:
            if hasattr(self, 'getProxyUrl'):
                return self.getProxyUrl() + '&type=m3u8&url=' + quote(url, safe='') + '&referer=' + quote(referer or self.rawSite, safe='')
        except Exception:
            pass
        return url

    def _get_m3u8_content(self, url, referer):
        """带防盗链header下载m3u8文件"""
        try:
            headers = {
                'User-Agent': UA,
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': referer,
                'Origin': self.rawSite,
                'Connection': 'keep-alive',
            }
            resp = self.session.get(url, headers=headers, timeout=10, allow_redirects=True, verify=False)
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception:
            return None

    def _is_ad_segment(self, uri, dur=0, prev_tags=None):
        """广告片段识别：关键词匹配 + 短时长判定"""
        u = (uri or '').strip().lower()
        if not u:
            return False
        ad_words = [
            # 英文明确广告词
            'advertisement', 'advertise', 'advert', 'commercial', 'sponsor', 'sponsorship',
            'preroll', 'pre-roll', 'pre_roll', 'midroll', 'mid-roll', 'postroll', 'post-roll',
            'banner', 'banners', 'popup', 'pop-up', 'interstitial', 'overlay', 'splash',
            'bumper', 'stinger', 'vast', 'vpaid', 'vmap',
            'doubleclick', 'googleads', 'googlesyndication', 'googletag', 'adsense', 'admob',
            'adx', 'adnetwork', 'adserving', 'ad-serving', 'adserver', 'ad-server',
            'inmobi', 'unityads', 'applovin', 'ironsource', 'vungle', 'chartboost', 'tapjoy',
            'mintegral', 'pangle', 'bytedance', 'tiktokads', 'kuaishou', 'ks-ad',
            'tracking', 'tracker', 'beacon', 'pixel', 'analytics', 'statistic',
            'leaderboard', 'skyscraper', 'rectangle', 'filler',
            # 中文广告词
            '广告', '片头', '片尾', '贴片', '赞助商', '赞助', '推广', '硬广',
            '前贴', '中插', '后贴', '角标', '广告位', '广告片', '广告段', '广告视频',
            '广告素材', '弹窗', '悬浮', '开屏', '插屏', '激励视频', '激励广告',
            # 拼音/缩写
            'guanggao', 'ggao', 'ggvideo', 'ggmedia',
            # 路径特征（精确匹配）
            '/ad/', '/ads/', '/adv/', '/adver/', '/gg/', '/gga/', '/ggb/', '/ggc/', '/ggd/',
            '_ad.', '.ad/', '_ads.', '_adv.', '_gg.', 'gg_', '_gg', '/gg', 'gg.',
            '/ad_', '/ads_', '/adv_', '/sponsor/', '/banner/', '/promo/', '/commercial/',
            '/preroll/', '/midroll/', '/postroll/', '/popup/', '/interstitial/', '/overlay/',
            '/splash/', '/bumper/', '/vast/', '/vpaid/', '/adnetwork/', '/adserving/',
            '/doubleclick/', '/googleads/', '/googlesyndication/', '/adsense/', '/admob/',
            '/tracking/', '/tracker/', '/beacon/', '/pixel/', '/analytics/',
        ]
        if any(w in u for w in ad_words):
            return True
        try:
            if 0 < float(dur) <= 1.2:
                return True
        except Exception:
            pass
        return False

    def _parse_m3u8_segments(self, text):
        """m3u8解析器：拆出header/segments/tail"""
        from urllib.parse import urlsplit
        lines = [x.strip() for x in (text or '').replace('\r', '').split('\n') if x.strip()]
        header, segments, tail = [], [], []
        pending_tags = []
        media_sequence = 0
        target_duration = 0
        started = False
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('#EXT-X-MEDIA-SEQUENCE'):
                try:
                    media_sequence = int(line.split(':', 1)[1])
                except Exception:
                    pass
                if not started:
                    header.append(line)
                else:
                    pending_tags.append(line)
            elif line.startswith('#EXT-X-TARGETDURATION'):
                try:
                    target_duration = float(line.split(':', 1)[1])
                except Exception:
                    pass
                if not started:
                    header.append(line)
                else:
                    pending_tags.append(line)
            elif line.startswith('#EXTINF'):
                started = True
                dur = target_duration or 3.0
                m = re.search(r'#EXTINF:\s*([\d.]+)', line)
                if m:
                    try:
                        dur = float(m.group(1))
                    except Exception:
                        pass
                tags = pending_tags + [line]
                pending_tags = []
                uri = ''
                j = i + 1
                while j < len(lines):
                    if lines[j].startswith('#'):
                        tags.append(lines[j])
                        j += 1
                        continue
                    uri = lines[j]
                    break
                if uri:
                    segments.append({'tags': tags, 'uri': uri, 'dur': dur})
                    i = j
                else:
                    tail.extend(tags)
            elif line.startswith('#EXT-X-ENDLIST'):
                tail.append(line)
            elif line.startswith('#'):
                if started:
                    pending_tags.append(line)
                else:
                    header.append(line)
            else:
                started = True
                dur = target_duration or 3.0
                segments.append({'tags': pending_tags, 'uri': line, 'dur': dur})
                pending_tags = []
            i += 1
        return header, segments, tail, media_sequence, target_duration

    def _segment_host_key(self, uri, base_url):
        """提取片段的主机+路径前缀，用于统计主CDN"""
        from urllib.parse import urlsplit
        try:
            full = urljoin(base_url, uri)
            p = urlsplit(full)
            path = re.sub(r'/[^/]*$', '/', p.path or '/')
            return (p.netloc.lower(), path.lower())
        except Exception:
            return ('', '')

    def _main_path_marker(self, m3u8_url):
        """从m3u8 URL提取主路径标记"""
        from urllib.parse import urlsplit
        try:
            p = urlsplit(m3u8_url).path
            m = re.search(r'(/\d{8}/[^/]+/\d+kb/hls/)', p)
            if m:
                return m.group(1).lower()
            m = re.search(r'(/\d{8}/[^/]+/)', p)
            if m:
                return m.group(1).lower()
        except Exception:
            pass
        return ''

    def _clean_m3u8(self, m3u8_text, m3u8_url='', referer='', skip_seconds=25):
        """核心m3u8广告清洗：五重广告识别 + 主CDN统计 + 前置贴片切除 + 多码率递归代理"""
        from urllib.parse import urlsplit
        text = (m3u8_text or '').replace('\r', '')
        # 多码率m3u8：递归代理子m3u8
        if '#EXT-X-STREAM-INF' in text:
            out = []
            last_stream = False
            for raw in text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line.startswith('#'):
                    out.append(line)
                    last_stream = line.startswith('#EXT-X-STREAM-INF')
                else:
                    abs_url = urljoin(m3u8_url, line)
                    if last_stream or '.m3u8' in line.lower():
                        out.append(self._proxy_m3u8_url(abs_url, referer or self.rawSite))
                    else:
                        out.append(abs_url)
                    last_stream = False
            return '\n'.join(out) + '\n'

        header, segments, tail, media_sequence, target_duration = self._parse_m3u8_segments(text)
        if not segments:
            return text

        marker = self._main_path_marker(m3u8_url)

        # 统计各主机路径的总时长，找出主CDN
        stat = {}
        for seg in segments:
            key = self._segment_host_key(seg['uri'], m3u8_url)
            stat[key] = stat.get(key, 0.0) + float(seg.get('dur') or 0)
        main_key = max(stat.items(), key=lambda x: x[1])[0] if stat else ('', '')
        total_dur = sum(stat.values()) or 0
        main_dur = stat.get(main_key, 0)

        # 五重广告识别
        cleaned = []
        removed = 0
        for idx, seg in enumerate(segments):
            key = self._segment_host_key(seg['uri'], m3u8_url)
            is_front = idx < 12
            abs_uri = urljoin(m3u8_url, seg.get('uri', ''))
            is_ad = self._is_ad_segment(seg['uri'], seg.get('dur'), seg.get('tags'))
            if marker and marker not in urlsplit(abs_uri).path.lower():
                is_ad = True
            tags_text = '\n'.join(seg.get('tags') or []).upper()
            if is_front and 'METHOD=NONE' in tags_text and marker and marker not in urlsplit(abs_uri).path.lower():
                is_ad = True
            if (not is_ad) and is_front and total_dur > 0 and main_dur >= total_dur * 0.6:
                if key != main_key and stat.get(key, 0) <= 90:
                    is_ad = True
            if is_ad:
                removed += 1
                continue
            seg['_idx'] = idx
            cleaned.append(seg)

        # 兜底策略：前置贴片切除
        if removed == 0 and len(segments) > 4:
            acc = 0.0
            cut = 0
            for idx, seg in enumerate(segments[:12]):
                key = self._segment_host_key(seg['uri'], m3u8_url)
                if key == main_key and acc >= 3:
                    break
                acc += float(seg.get('dur') or target_duration or 3)
                cut = idx + 1
                if acc >= skip_seconds:
                    break
            if cut > 0 and cut < len(segments):
                first_key = self._segment_host_key(segments[0]['uri'], m3u8_url)
                if first_key != main_key:
                    cleaned = segments[cut:]
                    removed = cut

        if not cleaned:
            cleaned = segments
            removed = 0

        # 重新生成干净的m3u8
        new_lines = []
        has_m3u = False
        for line in header:
            if line.startswith('#EXTM3U'):
                has_m3u = True
            if line.startswith('#EXT-X-MEDIA-SEQUENCE') or line.startswith('#EXT-X-START'):
                continue
            if line.startswith('#EXT-X-KEY') and 'METHOD=NONE' in line.upper() and removed > 0:
                continue
            new_lines.append(line)
        if not has_m3u:
            new_lines.insert(0, '#EXTM3U')
        first_idx = cleaned[0].get('_idx', removed) if cleaned else removed
        new_lines.append('#EXT-X-MEDIA-SEQUENCE:%d' % (media_sequence + first_idx))

        for seg in cleaned:
            for tag in seg.get('tags') or []:
                if tag.startswith('#EXT-X-KEY') or tag.startswith('#EXT-X-MAP'):
                    def _fix_uri(m):
                        return 'URI="' + urljoin(m3u8_url, m.group(1)) + '"'
                    tag = re.sub(r'URI="([^"]+)"', _fix_uri, tag)
                new_lines.append(tag)
            new_lines.append(urljoin(m3u8_url, seg.get('uri', '')))
        if tail:
            for line in tail:
                if line.startswith('#EXT-X-ENDLIST'):
                    new_lines.append(line)
        elif '#EXT-X-ENDLIST' in text:
            new_lines.append('#EXT-X-ENDLIST')
        return '\n'.join(new_lines) + '\n'

    def localProxy(self, param):
        """本地代理：m3u8广告清洗 + 图片分片代理（原有功能保留）"""
        if not isinstance(param, dict):
            param = {}
        do = param.get('type') or param.get('action') or param.get('do')
        url = param.get('url', '') or param.get('path', '')
        # m3u8广告清洗分支
        if do == 'm3u8' or (isinstance(url, str) and url.endswith('.m3u8')):
            try:
                referer = param.get('referer', '') or self.rawSite
                if isinstance(url, list):
                    url = url[0]
                if isinstance(referer, list):
                    referer = referer[0]
                url = unquote(url)
                referer = unquote(referer)
                text = self._get_m3u8_content(url, referer)
                if not text:
                    return [502, "text/plain", "m3u8 download failed"]
                # 优先使用独立m3u8_cleaner模块（最新六重+CUE广告检测），失败回退内嵌版
                try:
                    from m3u8_cleaner import M3U8Cleaner
                    _cleaner = M3U8Cleaner(raw_site=referer or self.rawSite)
                    cleaned = _cleaner.clean(text, url, referer)
                except Exception:
                    cleaned = self._clean_m3u8(text, url, referer)
                return [200, "application/vnd.apple.mpegurl", cleaned]
            except Exception as e:
                import traceback
                return [500, "text/plain", "proxy error: %s\n%s" % (e, traceback.format_exc())]
        # 图片本地代理（列表封面走 127.0.0.1 转发，规避图片域 Referer 校验）
        data = self._fetch_pic(url)
        if data:
            return [200, _mime(data), data]
        return [404, 'text/plain', b'']
