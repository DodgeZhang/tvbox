# coding=utf-8
# 高中课堂 TVBox Python 爬虫
# 站点: https://www.bilibili.com/
# 功能: 获取B站教育类视频分类，直接返回真实视频播放地址
# 分类: 高中各科目课程
# 说明: 直接获取B站视频真实播放地址，无需解析
# 关注微信公众号"源力软件汇"，更多优质资源尽在源力。
import json
import re

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

PROMO = '\n\n关注微信公众号"源力软件汇"，更多优质资源尽在源力。'

# 高中教育相关分类
CATES = [
    {'type_id': 'math', 'type_name': '高中数学'},
    {'type_id': 'chinese', 'type_name': '高中语文'},
    {'type_id': 'english', 'type_name': '高中英语'},
    {'type_id': 'physics', 'type_name': '高中物理'},
    {'type_id': 'chemistry', 'type_name': '高中化学'},
    {'type_id': 'biology', 'type_name': '高中生物'},
    {'type_id': 'history', 'type_name': '高中历史'},
    {'type_id': 'geography', 'type_name': '高中地理'},
    {'type_id': 'politics', 'type_name': '高中政治'},
    {'type_id': 'gaokao', 'type_name': '高考真题'},
    {'type_id': 'method', 'type_name': '高效学习方法'},
    {'type_id': 'notes', 'type_name': '学霸笔记'},
]

# 搜索关键词映射
KEYWORD_MAP = {
    'math': '高中数学',
    'chinese': '高中语文',
    'english': '高中英语',
    'physics': '高中物理',
    'chemistry': '高中化学',
    'biology': '高中生物',
    'history': '高中历史',
    'geography': '高中地理',
    'politics': '高中政治',
    'gaokao': '高考真题',
    'method': '高效学习方法',
    'notes': '学霸笔记',
}


def _strip_tags(s):
    if not s:
        return ''
    return re.sub(r'<[^>]+>', '', str(s)).replace('&amp;', '&').replace('&quot;', '"')


def _pic(u):
    u = u or ''
    if u.startswith('//'):
        return 'https:' + u
    return u


class Spider(_BaseSpider):
    def __init__(self):
        super(Spider, self).__init__()
        self.name = '高中课堂'
        self.session = None
        self._cookie_ok = False

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
        return None

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
                self.session.cookies.set('buvid3', d['b_3'], domain='.bilibili.com')
            if d.get('b_4'):
                self.session.cookies.set('buvid4', d['b_4'], domain='.bilibili.com')
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
            import urllib.request
            q = '&'.join('%s=%s' % (k, v) for k, v in (params or {}).items())
            req = urllib.request.Request(API + path + ('?' + q if q else ''), headers=dict(HEADERS))
            ctx_ok = True
            try:
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            except Exception:
                ctx_ok = False
            with urllib.request.urlopen(req, timeout=15, context=ctx if ctx_ok else None) as resp:
                return json.loads(resp.read().decode('utf-8', 'ignore'))
        except Exception:
            return {}

    def _get_play_url(self, bvid, cid):
        """获取视频真实播放地址"""
        try:
            # 请求视频流地址 fnval=0 表示返回mp4格式
            d = self._get_json('/x/player/playurl', {
                'bvid': bvid,
                'cid': cid,
                'qn': 80,  # 清晰度 80=1080p 64=720p 32=480p
                'fnval': 0,  # 0=返回mp4格式
                'fourk': 1,
            })
            data = d.get('data') or {}
            durl = data.get('durl') or []
            if durl and isinstance(durl, list):
                url = durl[0].get('url', '')
                if url:
                    return url
        except Exception:
            pass
        return ''

    def homeContent(self, filter):
        return {'class': CATES, 'filters': {}}

    def homeVideoContent(self):
        videos, seen = [], set()
        for cid, kw in KEYWORD_MAP.items():
            try:
                d = self._get_json('/x/web-interface/search/type', {
                    'search_type': 'video',
                    'keyword': kw + ' 教学',
                    'page': 1,
                    'order': 'totalrank',
                })
                data = d.get('data') if isinstance(d.get('data'), dict) else {}
                for it in (data.get('result') or [])[:3]:
                    bvid = it.get('bvid')
                    if not bvid or bvid in seen:
                        continue
                    seen.add(bvid)
                    videos.append({
                        'vod_id': 'bv' + bvid,
                        'vod_name': _strip_tags(it.get('title')),
                        'vod_pic': _pic(it.get('pic')),
                        'vod_remarks': kw,
                    })
            except Exception:
                pass
        return {'list': videos}

    def categoryContent(self, cid, pg, filter, ext):
        pg = int(pg) if pg else 1
        kw = KEYWORD_MAP.get(cid, '高中')
        videos = []
        try:
            d = self._get_json('/x/web-interface/search/type', {
                'search_type': 'video',
                'keyword': kw,
                'page': pg,
                'order': 'totalrank',
            })
            data = d.get('data') if isinstance(d.get('data'), dict) else {}
            for it in (data.get('result') or []):
                bvid = it.get('bvid')
                if not bvid:
                    continue
                videos.append({
                    'vod_id': 'bv' + bvid,
                    'vod_name': _strip_tags(it.get('title')),
                    'vod_pic': _pic(it.get('pic')),
                    'vod_remarks': _strip_tags(it.get('author', '')),
                })
        except Exception:
            pass
        total = 50
        pagecount = max(1, (total + 19) // 20)
        return {'list': videos, 'page': pg, 'pagecount': pagecount,
                'limit': len(videos), 'total': total}

    def detailContent(self, ids):
        did = str(ids[0])
        bvid = did[2:] if did.startswith('bv') else did
        result = {}
        try:
            d = self._get_json('/x/web-interface/view', {'bvid': bvid})
            data = d.get('data') or {}
            pages = data.get('pages') or [{'cid': data.get('cid'), 'part': data.get('title')}]
            title = data.get('title', '')
            desc = _strip_tags(data.get('desc') or '')
            owner = (data.get('owner') or {}).get('name', '')

            play_urls = []
            for p in pages:
                cid = p.get('cid')
                part = _strip_tags(p.get('part') or p.get('title') or '正片')
                # 直接获取真实播放地址
                real_url = self._get_play_url(bvid, cid)
                if real_url:
                    # 使用真实地址格式: 标题$url
                    play_urls.append('%s$%s' % (part, real_url))
                else:
                    # 兜底使用cid
                    play_urls.append('%s$%s_%s' % (part, bvid, str(cid)))

            detail = '简介：' + desc + PROMO

            result['list'] = [{
                'vod_id': did,
                'vod_name': title,
                'vod_pic': _pic(data.get('pic')),
                'vod_year': str(data.get('pubdate', '')),
                'vod_area': '中国',
                'vod_remarks': data.get('tname', ''),
                'vod_actor': owner,
                'vod_director': owner,
                'vod_content': detail,
                'vod_play_from': 'B站直链[源力软件汇]',
                'vod_play_url': '#'.join(play_urls),
            }]
        except Exception as e:
            result['list'] = [{
                'vod_id': did, 'vod_name': '', 'vod_pic': '',
                'vod_content': '获取失败，请重试。' + PROMO.strip(),
                'vod_play_from': 'B站直链[源力软件汇]', 'vod_play_url': '',
            }]
        return result

    def playerContent(self, flag, id, vipFlags):
        id = str(id)
        header = dict(PLAY_HEADER)
        # 如果是真实URL，直接返回
        if id.startswith('http'):
            return {'header': header, 'url': id}
        # 如果是bvid_cid格式
        if '_' in id:
            parts = id.split('_')
            if len(parts) == 2:
                bvid, cid = parts
                real_url = self._get_play_url(bvid, cid)
                if real_url:
                    return {'header': header, 'url': real_url}
        # 兜底返回B站页面
        return {'jx': 1, 'parse': 1, 'playUrl': '', 'url': WEB + '/video/' + id, 'header': header}

    def isVideoFormat(self, url):
        return '.mp4' in url or 'bilivideo.com' in url or 'playurl' in url

    def manualVideoCheck(self):
        return False

    def searchContent(self, key, quick, pg='1'):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick, page):
        result = {'list': [], 'page': int(page or 1)}
        page = int(page or 1)
        videos = []
        try:
            d = self._get_json('/x/web-interface/search/type', {
                'search_type': 'video',
                'keyword': key,
                'page': page,
            })
            data = d.get('data') if isinstance(d.get('data'), dict) else {}
            for it in (data.get('result') or []):
                bvid = it.get('bvid')
                if not bvid:
                    continue
                videos.append({
                    'vod_id': 'bv' + bvid,
                    'vod_name': _strip_tags(it.get('title')),
                    'vod_pic': _pic(it.get('pic')),
                    'vod_remarks': _strip_tags(it.get('author', '')),
                })
        except Exception:
            pass
        result['list'] = videos
        result['page'] = page
        result['pagecount'] = page + 1 if videos else page
        result['limit'] = len(videos)
        result['total'] = 999999 if videos else 0
        return result


if __name__ == '__main__':
    sp = Spider()
    sp.init('')