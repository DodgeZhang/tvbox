# coding=utf-8
# 儿童口才 TVBox Python 爬虫 (基于 base.spider 标准)
# 站点: https://www.bilibili.com/
# 数据: B站官方搜索/视频接口, 分类全部以口才类学习相关关键词抓取,
#       一次获取所有分类数据返回影片列表.
# 播放: 直接调用 B站 playurl 接口获取真实可播放的 MP4 视频地址,
#       无需任何解析器, 返回直链交由 TVBox 直接播放.
#       未登录默认360p, 在源"extend"中填入 B 站 SESSDATA 可解锁更高清晰度.
# 关注微信公众号“源力软件汇”，更多优质资源尽在源力。
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
PLAY_HEADER = {'User-Agent': UA, 'Referer': WEB + '/', 'Origin': WEB}

PROMO = '\n\n关注微信公众号“源力软件汇”，更多优质资源尽在源力。'

# 分类 = 关键词, 一次获取全部口才分类数据
CATES = [
    {'type_id': '儿童口才', 'type_name': '儿童口才'},
    {'type_id': '少儿口才', 'type_name': '少儿口才'},
    {'type_id': '口才训练', 'type_name': '口才训练'},
    {'type_id': '演讲口才', 'type_name': '演讲口才'},
    {'type_id': '少儿主持', 'type_name': '少儿主持'},
    {'type_id': '播音主持', 'type_name': '播音主持'},
    {'type_id': '少儿朗诵', 'type_name': '少儿朗诵'},
    {'type_id': '朗诵技巧', 'type_name': '朗诵技巧'},
    {'type_id': '语言表演', 'type_name': '语言表演'},
    {'type_id': '即兴表达', 'type_name': '即兴表达'},
    {'type_id': '绕口令', 'type_name': '绕口令'},
    {'type_id': '口才' + '课堂', 'type_name': '口才课堂'},
]
# 每个分类下再补一组备选关键词以获得更丰富的“全部分类数据”
EXTRA_KEYWORDS = {
    '儿童口才': ['儿童口才 训练', '儿童口才 课'],
    '少儿口才': ['少儿口才 训练营', '少儿口才 公开课'],
    '口才训练': ['少儿 口才 训练', '小学生 口才'],
    '演讲口才': ['少儿演讲', '幼儿 演讲'],
    '少儿主持': ['少儿主持 训练', '小主持人'],
    '播音主持': ['儿童 播音', '少儿播音主持 教学'],
    '少儿朗诵': ['儿童朗诵 比赛', '幼儿朗诵'],
    '朗诵技巧': ['诗歌朗诵 技巧', '古诗词 朗诵 儿童'],
    '语言表演': ['少儿语言表演', '语言艺术 儿童'],
    '即兴表达': ['少儿 即兴表达', '孩子 表达力'],
    '绕口令': ['儿童绕口令', '绕口令 口才'],
    '口才' + '课堂': ['少儿口才 课程', '口才 快板'],
}

ORDERS = [
    {'n': '最多播放', 'v': 'click'},
    {'n': '最新发布', 'v': 'pubdate'},
    {'n': '最多弹幕', 'v': 'dm'},
    {'n': '最多点赞', 'v': 'scores'},
]

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
        self.name = '儿童口才'
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
        # 获取 buvid3/buvid4 风控Cookie, 保证搜索与直播放接口可用
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
    def _search(self, keyword, page, page_size=24, order='click'):
        try:
            d = self._get_json('/x/web-interface/search/type', {
                'search_type': 'video', 'keyword': keyword,
                'page': page, 'page_size': page_size, 'order': order})
            return ((d.get('data') or {}).get('result')) or []
        except Exception:
            return []

    @staticmethod
    def _to_vod(it):
        bvid = it.get('bvid') or it.get('id')
        if not bvid:
            return None
        title = _strip_tags(it.get('title') or '无标题').strip()
        title = title.replace('<em class="keyword">', '').replace('</em>', '').strip()
        play = it.get('play')
        if isinstance(play, str) and not play.isdigit():
            remark = play
        else:
            remark = _fmt(play) + '播放' if play is not None else ''
        duration = it.get('duration')
        if duration:
            try:
                m, s = divmod(int(duration), 60)
                h, m = divmod(m, 60)
                remark = (('%02d:%02d:%02d' % (h, m, s)) if h else ('%02d:%02d' % (m, s))) + ' · ' + remark
            except Exception:
                pass
        up = _strip_tags(it.get('author') or '')
        if up:
            remark = (remark + ' · ' if remark else '') + up
        return {
            'vod_id': str(bvid),
            'vod_name': title[:80],
            'vod_pic': _pic(it.get('pic')),
            'vod_remarks': (remark or '')[:40],
        }

    # ---------- TVBox 标准方法 ----------
    def homeContent(self, filter):
        filters = {}
        for c in CATES:
            filters[c['type_id']] = [{'key': 'order', 'name': '排序', 'value': ORDERS}]
        return {'class': CATES, 'filters': filters}

    def homeVideoContent(self):
        videos, seen = [], set()
        # 抓取全部分类首页内容以获得“全部分类”数据
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
        order = 'click'
        if isinstance(ext, dict) and ext.get('order'):
            order = ext['order']
        elif isinstance(ext, str) and ext:
            try:
                order = json.loads(ext).get('order') or order
            except Exception:
                pass
        videos, seen = [], set()
        kws = [cid] + EXTRA_KEYWORDS.get(cid, [])
        for it in self._search(kws[0], pg, 24, order):
            vod = self._to_vod(it)
            if vod and vod['vod_id'] not in seen:
                seen.add(vod['vod_id'])
                videos.append(vod)
        # 第一页补充备选关键词结果, 让全部分类数据更丰富
        if pg == 1:
            for ekw in kws[1:]:
                for it in self._search(ekw, 1, 12, order):
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
        did = str((ids or [''])[0])
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
            if owner:
                info.append('UP主：' + owner)
            if pub_time:
                info.append('发布：' + pub_time)
            if stat.get('view'):
                info.append('播放：' + _fmt(stat.get('view')))
            if stat.get('danmaku'):
                info.append('弹幕：' + _fmt(stat.get('danmaku')))
            if stat.get('like'):
                info.append('点赞：' + _fmt(stat.get('like')))
            if stat.get('favorite'):
                info.append('收藏：' + _fmt(stat.get('favorite')))
            content = (('　'.join(info) + '\n') if info else '')
            if desc:
                content += '简介：' + desc[:500] + '\n'
            content += PROMO

            play_url = '#'.join(
                '%s$%s|%s' % (_strip_tags(p.get('part') or ('第%d集' % (i + 1)))
                              .replace('$', '').replace('#', '').replace('|', ' '),
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
                'vod_remarks': (_fmt(stat.get('view')) + '播放') if stat.get('view') else '',
                'vod_content': content,
                'vod_play_from': '直接播放[源力软件汇]',
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
        # 直接获取真实可播放的 MP4 视频地址 (无需任何解析)
        qn = QUALITY_LOGIN if self._sessdata else QUALITY_GUEST
        # 方式1: 常规 playurl 返回 durl MP4
        try:
            d = self._get_json('/x/player/playurl', {
                'bvid': bvid, 'cid': cid, 'qn': qn,
                'fnver': 0, 'fnval': 0, 'fourk': 1})
            data = d.get('data') or {}
            durl = data.get('durl') or []
            if durl and durl[0].get('url'):
                return durl[0]['url']
        except Exception:
            pass
        # 方式2: html5 模式拿 MP4
        try:
            d = self._get_json('/x/player/playurl', {
                'bvid': bvid, 'cid': cid, 'qn': qn, 'platform': 'html5',
                'high_quality': 1, 'otype': 'json'})
            data = d.get('data') or {}
            durl = data.get('durl') or []
            if durl and durl[0].get('url'):
                return durl[0]['url']
        except Exception:
            pass
        # 方式3: DASH 兜底视频流
        try:
            d = self._get_json('/x/player/playurl', {
                'bvid': bvid, 'cid': cid, 'qn': qn, 'fnval': 16, 'fourk': 1})
            data = d.get('data') or {}
            dash = data.get('dash') or {}
            videos = dash.get('video') or []
            if videos:
                return videos[0].get('baseUrl') or videos[0].get('base_url', '')
        except Exception:
            pass
        return ''

    def playerContent(self, flag, id, vipFlags):
        id = str(id)
        bvid, _, cid = id.partition('|')
        url = self._direct_mp4(bvid, cid) if cid else ''
        if not url:
            return {'jx': 1, 'parse': 1, 'url': '%s/video/%s' % (WEB, bvid),
                    'header': dict(PLAY_HEADER)}
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