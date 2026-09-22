# coding=utf-8
# 儿童思维 TVBox Python 爬虫 (基于 base.spider 标准)
# 站点: https://www.bilibili.com/
# 数据: B站官方搜索/视频接口, 分类全部以儿童思维学习相关关键词抓取
# 播放: 直接调用 B站 playurl 接口获取真实可播放的 MP4 地址,
#       无需任何解析器, 返回直链交由 TVBox 直接播放.
#       未登录默认360p, 在源"extend"中填入 B 站 SESSDATA 可解锁更高清晰度.
# 关注微信公众号“源力软件汇”, 更多优质资源尽在源力。
import json
import re
import time

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        def __init__(self):
            self.extend = ''


try:
    import requests
except Exception:
    requests = None


API = 'https://api.bilibili.com'
WEB = 'https://www.bilibili.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
HEADERS = {
    'User-Agent': UA,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': WEB + '/',
}
PLAY_HEADER = {'User-Agent': UA, 'Referer': WEB + '/'}

PROMO = '\n\n关注微信公众号“源力软件汇”，更多优质资源尽在源力。'

# 分类 = 关键词, “获取所有分类数据”
CATES = [
    {'type_id': '儿童思维训练', 'type_name': '儿童思维训练'},
    {'type_id': '逻辑思维', 'type_name': '逻辑思维'},
    {'type_id': '思维启蒙', 'type_name': '思维启蒙'},
    {'type_id': '专注力训练', 'type_name': '专注力训练'},
    {'type_id': '记忆力训练', 'type_name': '记忆力训练'},
    {'type_id': '全脑开发', 'type_name': '全脑开发'},
    {'type_id': '数学思维', 'type_name': '数学思维'},
    {'type_id': '益智游戏', 'type_name': '益智游戏'},
    {'type_id': '观察力训练', 'type_name': '观察力训练'},
    {'type_id': '判断推理', 'type_name': '判断推理'},
    {'type_id': '左右脑开发', 'type_name': '左右脑开发'},
    {'type_id': '思维导图', 'type_name': '思维导图'},
]
# 每个分类下再补一组备选关键词以获得更丰富的结果
EXTRA_KEYWORDS = {
    '儿童思维训练': ['儿童思维 训练 视频', '思维训练 幼儿'],
    '逻辑思维': ['逻辑思维 训练 儿童', '儿童 逻辑思维'],
    '思维启蒙': ['思维启蒙 幼儿', '儿童 思维启蒙'],
    '专注力训练': ['专注力 训练 小孩', '儿童 专注力'],
    '记忆力训练': ['记忆力 训练 儿童', '儿童 记忆训练'],
    '全脑开发': ['全脑开发 儿童', '幼儿 全脑开发'],
    '数学思维': ['数学思维 儿童', '幼儿 数学思维训练'],
    '益智游戏': ['益智游戏 儿童', '幼儿 益智 视频'],
    '观察力训练': ['观察力 训练 幼儿', '儿童 观察力'],
    '判断推理': ['判断 推理 训练 儿童', '儿童 推理能力'],
    '左右脑开发': ['左右脑 开发 儿童', '右脑开发 幼儿'],
    '思维导图': ['思维导图 儿童', '儿童 思维导图 学习'],
}

QUALITY_GUEST = 16   # 未登录 360p
QUALITY_LOGIN = 127  # 登录后尝试 1080p


def _strip_tags(s):
    if not s:
        return ''
    return re.sub(r'<[^>]+>', '', str(s))


def _pic(u):
    u = u or ''
    if u.startswith('//'):
        return 'https:' + u
    return u


def _fmt(n):
    try:
        n = int(n)
        if n >= 100000000:
            return '%.1f亿' % (n / 100000000.0)
        if n >= 10000:
            return '%.1f万' % (n / 10000.0)
        return str(n)
    except Exception:
        return str(n)


class Spider(_BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.name = '儿童思维'
        self.session = None
        self._cookie_ok = False
        self._sessdata = ''

    # ---------- 基础 ----------
    def getName(self):
        return self.name

    def init(self, extend=''):
        self.extend = extend or ''
        if not self.session and requests:
            self.session = requests.Session()
            self.session.headers.update(HEADERS)
            try:
                from requests.adapters import HTTPAdapter
                ad = HTTPAdapter(max_retries=2, pool_connections=10, pool_maxsize=10)
                self.session.mount('http://', ad)
                self.session.mount('https://', ad)
            except Exception:
                pass
        extend = str(self.extend or '').strip()
        if extend.startswith('{'):
            try:
                ext = json.loads(extend)
                extend = (ext.get('SESSDATA') or ext.get('sessdata') or '')
            except Exception:
                extend = ''
        else:
            m = re.search(r'SESSDATA=([^;\"\']+)', extend)
            extend = m.group(1) if m else ''
        self._sessdata = (extend or '').strip()
        if self._sessdata:
            self._set_cookie('SESSDATA', self._sessdata)
        return None

    def destroy(self):
        try:
            if self.session:
                self.session.close()
        except Exception:
            pass

    def _set_cookie(self, k, v):
        try:
            self.session.cookies.set(k, v, domain='.bilibili.com')
        except Exception:
            pass

    def _ensure_cookies(self):
        if self._cookie_ok or not self.session:
            return
        try:
            self.session.get(WEB + '/', timeout=10)
        except Exception:
            pass
        try:
            d = self.session.get(API + '/x/frontend/finger/spi', timeout=10).json() or {}
            d = d.get('data') or {}
            if d.get('b_3'):
                self._set_cookie('buvid3', d['b_3'])
            if d.get('b_4'):
                self._set_cookie('buvid4', d['b_4'])
        except Exception:
            pass
        self._cookie_ok = True

    def _get_json(self, path, params=None):
        self._ensure_cookies()
        try:
            r = self.session.get(API + path, params=params, timeout=15)
            return r.json()
        except Exception:
            pass
        try:
            import ssl
            import urllib.request
            q = '&'.join('%s=%s' % (k, v) for k, v in (params or {}).items())
            req = urllib.request.Request(API + path + ('?' + q if q else ''), headers=dict(HEADERS))
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return json.loads(resp.read().decode('utf-8', 'ignore'))
        except Exception:
            return {}

    # ---------- 搜索视频 ----------
    def _search(self, keyword, page, page_size=24):
        try:
            d = self._get_json('/x/web-interface/search/type', {
                'search_type': 'video', 'keyword': keyword,
                'page': page, 'page_size': page_size})
            return ((d.get('data') or {}).get('result')) or []
        except Exception:
            return []

    def _to_vod(self, it, prefix=''):
        bvid = it.get('bvid') or it.get('id')
        if not bvid:
            return None
        title = _strip_tags(it.get('title') or '无标题').strip()
        title = title.replace('<em class="keyword">', '').replace('</em>', '')
        play = it.get('play')
        if isinstance(play, str) and not play.isdigit():
            remark = play
        else:
            remark = _fmt(play) + '播放' if play is not None else ''
        up = _strip_tags(it.get('author') or '')
        if up:
            remark = (remark + ' · ' if remark else '') + up
        return {
            'vod_id': prefix + str(bvid),
            'vod_name': title[:80],
            'vod_pic': _pic(it.get('pic')),
            'vod_remarks': remark[:40],
        }

    # ---------- TVBox 标准方法 ----------
    def homeContent(self, filter):
        return {'class': CATES, 'filters': {}}

    def homeVideoContent(self):
        videos, seen = [], set()
        # 抓取各分类首页内容以获得“所有分类”数据
        for cate in CATES:
            kw = cate['type_id']
            try:
                for it in self._search(kw, 1, 12)[:6]:
                    vod = self._to_vod(it)
                    if not vod or vod['vod_id'] in seen:
                        continue
                    seen.add(vod['vod_id'])
                    videos.append(vod)
            except Exception:
                continue
        return {'list': videos[:60]}

    def categoryContent(self, cid, pg, filter, ext):
        result = {}
        pg = int(pg) if str(pg).isdigit() and int(pg) > 0 else 1
        videos, seen = [], set()
        kws = [cid]
        kws += EXTRA_KEYWORDS.get(cid, [])
        for it in self._search(kws[0], pg, 24):
            vod = self._to_vod(it)
            if vod and vod['vod_id'] not in seen:
                seen.add(vod['vod_id'])
                videos.append(vod)
        # 第一页补充备选关键词结果
        if pg == 1:
            for ekw in kws[1:]:
                for it in self._search(ekw, 1, 12):
                    vod = self._to_vod(it)
                    if vod and vod['vod_id'] not in seen:
                        seen.add(vod['vod_id'])
                        videos.append(vod)
                if len(videos) >= 40:
                    break
        pagecount = len(videos) // 24 + 3 if videos else pg + 1
        result.update({'list': videos, 'page': pg, 'pagecount': pagecount,
                       'limit': len(videos), 'total': 999999})
        return result

    def detailContent(self, ids):
        result = {}
        did = ids[0]
        try:
            bvid = did
            d = self._get_json('/x/web-interface/view', {'bvid': bvid})
            data = d.get('data') or {}
            pages = data.get('pages') or []
            if not pages:
                pages = [{'cid': data.get('cid'), 'part': '正片'}]

            name = _strip_tags(data.get('title') or '未知标题')
            pic = _pic(data.get('pic'))
            owner = (data.get('owner') or {}).get('name', '')
            pubdate = data.get('pubdate')
            pub_time = time.strftime('%Y-%m-%d', time.localtime(pubdate)) if pubdate else ''
            stat = data.get('stat') or {}
            desc = _strip_tags(data.get('desc') or '')

            info = []
            if pub_time:
                info.append('发布时间：' + pub_time)
            if stat.get('view'):
                info.append('播放：' + _fmt(stat.get('view')))
            if stat.get('danmaku'):
                info.append('弹幕：' + _fmt(stat.get('danmaku')))
            if stat.get('like'):
                info.append('点赞：' + _fmt(stat.get('like')))
            content = (('　'.join(info) + '\n') if info else '')
            if desc:
                content += '简介：' + desc[:500] + '\n'
            content += PROMO

            play_from = '直接播放[源力软件汇]'
            play_url = '#'.join(
                '%s$%s|%s' % (_strip_tags(p.get('part') or ('第%d集' % (i + 1)))
                              .replace('$', '').replace('#', '')
                              .replace('|', ' '),
                              bvid, p.get('cid'))
                for i, p in enumerate(pages))

            result['list'] = [{
                'vod_id': did,
                'vod_name': name,
                'vod_pic': pic,
                'vod_actor': owner,
                'vod_director': owner,
                'vod_area': _strip_tags(data.get('tname') or ''),
                'vod_year': pub_time[:4] if pub_time else '',
                'vod_remarks': (str(stat.get('view') and _fmt(stat.get('view')) + '播放') or ''),
                'vod_content': content,
                'vod_play_from': play_from,
                'vod_play_url': play_url,
            }]
        except Exception:
            result['list'] = [{
                'vod_id': did, 'vod_name': '', 'vod_pic': '',
                'vod_content': '获取失败，请重试。' + PROMO.strip(),
                'vod_play_from': '直接播放[源力软件汇]', 'vod_play_url': '',
            }]
        return result

    def _direct_mp4(self, bvid, cid):
        # 直接获取真实可播放的 MP4 直链 (无需解析)
        try:
            qn = QUALITY_LOGIN if self._sessdata else QUALITY_GUEST
            d = self._get_json('/x/player/playurl', {
                'bvid': bvid, 'cid': cid, 'qn': qn,
                'fnver': 0, 'fnval': 0, 'fourk': 1})
            data = d.get('data') or {}
            durl = data.get('durl') or []
            if durl and durl[0].get('url'):
                return durl[0]['url']
            # 兜底: DASH 返回时直接给无重定向地址并交由直链
            dash = data.get('dash') or {}
            if dash.get('video'):
                return (dash.get('video') or [{}])[0].get('baseUrl')
        except Exception:
            return ''
        return ''

    def playerContent(self, flag, id, vipFlags):
        id = str(id)
        bvid, _, cid = id.partition('|')
        url = self._direct_mp4(bvid, cid) if cid else ''
        if not url:
            return {'jx': 1, 'parse': 1, 'url': '%s/video/%s' % (WEB, bvid),
                    'header': PLAY_HEADER}
        return {
            'jx': 0,
            'parse': 0,
            'playUrl': '',
            'url': url,
            'header': dict(PLAY_HEADER),
        }

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    # ---------- 搜索 ----------
    def searchContentPage(self, key, quick, page):
        result = {}
        page = int(page) if str(page).isdigit() and int(page) > 0 else 1
        videos = [v for v in (self._to_vod(it) for it in self._search(key, page, 24)) if v]
        result.update({'list': videos, 'page': page,
                       'pagecount': page + 1 if videos else page,
                       'limit': len(videos), 'total': 999999 if videos else 0})
        return result

    def searchContent(self, key, quick, pg='1'):
        return self.searchContentPage(key, quick, pg)


if __name__ == '__main__':
    sp = Spider()
    sp.init('')
