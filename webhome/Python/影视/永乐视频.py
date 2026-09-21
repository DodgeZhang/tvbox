#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 永乐视频 ylsp.tv TVBox 爬虫 (MacCMS mxone主题)
# 依赖: requests(优先)/urllib兜底

try:
    from base.spider import Spider
except Exception:
    class Spider:
        def __init__(self):
            pass

import re
import json

try:
    import requests
except Exception:
    requests = None
import urllib.request
import urllib.parse


def _quote(s):
    return urllib.parse.quote(s, safe='')


class Spider(Spider):
    HOST = 'https://ylsp.tv'
    UA = 'Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 Chrome/120.0 Mobile Safari/537.36'

    CATS = [('1', '电影'), ('2', '剧集'), ('3', '综艺'), ('4', '动漫')]
    SUBS = {
        '1': [('6', '动作片'), ('7', '喜剧片'), ('8', '爱情片'), ('9', '科幻片'), ('10', '奇幻片'),
              ('11', '恐怖片'), ('12', '剧情片'), ('20', '战争片'), ('21', '纪录片'), ('26', '动画片'),
              ('22', '悬疑片'), ('23', '冒险片'), ('24', '犯罪片'), ('45', '惊悚片'), ('46', '歌舞片'),
              ('47', '灾难片'), ('48', '网络片')],
        '2': [('13', '国产剧'), ('14', '港台剧'), ('15', '日剧'), ('33', '韩剧'), ('16', '欧美剧'),
              ('34', '泰剧'), ('35', '新马剧'), ('25', '其他剧')],
        '3': [('27', '大陆综艺'), ('28', '港台综艺'), ('29', '日本综艺'), ('36', '韩国综艺'),
              ('30', '欧美综艺'), ('37', '新马泰综艺'), ('38', '其他综艺')],
        '4': [('31', '国产动漫'), ('32', '日本动漫'), ('39', '韩国动漫'), ('40', '港台动漫'),
              ('41', '新马泰动漫'), ('42', '欧美动漫'), ('43', '其他动漫')],
    }
    AREAS = ['大陆', '香港', '台湾', '日本', '韩国', '欧美', '英国', '泰国', '其它']
    LANGS = ['国语', '英语', '粤语', '韩语', '日语', '西班牙', '法语', '德语', '意大利语', '泰语', '其它']
    YEARS = [str(y) for y in range(2026, 2010, -1)] + ['更早']
    SORTS = [('time_update', '更新时间'), ('time_add', '添加时间'), ('hits', '人气'), ('score', '评分')]
    LETTERS = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')

    def init(self, ext=''):
        self.header = {'User-Agent': self.UA, 'Referer': self.HOST + '/'}

    # ---------- 网络 ----------
    def _get(self, path):
        url = path if path.startswith('http') else self.HOST + path
        try:
            if requests is not None:
                r = requests.get(url, headers=self.header, timeout=20)
                r.encoding = 'utf-8'
                return r.text
        except Exception:
            pass
        for i in range(2):
            try:
                req = urllib.request.Request(url, headers=self.header)
                return urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'ignore')
            except Exception:
                if i:
                    return ''
        return ''

    def _get_bin(self, url):
        try:
            if requests is not None:
                r = requests.get(url, headers=self.header, timeout=20, stream=True)
                return r.raw.read(64, 64)
        except Exception:
            pass
        try:
            req = urllib.request.Request(url, headers=self.header)
            return urllib.request.urlopen(req, timeout=20).read(64)
        except Exception:
            return b''

    # ---------- 工具 ----------
    @staticmethod
    def _abs(u):
        if not u:
            return ''
        if u.startswith('http'):
            return u
        return Spider.HOST + u

    @staticmethod
    def _strip(h):
        return re.sub(r'<[^>]+>', '', h or '').strip()

    def _img(self, chunk):
        m = re.search(r'data-original="([^"]+)"', chunk)
        if not m or 'loading.png' in m.group(1):
            m2 = re.search(r'src="(http[^"]+)"', chunk)
            return self._abs(m2.group(1)) if m2 else ''
        return self._abs(m.group(1))

    # ---------- 首页 ----------
    def homeContent(self, f):
        result = {'class': [], 'filters': {}}
        for cid, name in self.CATS:
            result['class'].append({'type_id': cid, 'type_name': name})
            fl = []
            if self.SUBS.get(cid):
                fl.append({'key': 'type', 'name': '类型',
                           'value': [{'n': n, 'v': v} for v, n in self.SUBS[cid]]})
            fl.append({'key': 'area', 'name': '地区', 'value': [{'n': a, 'v': a} for a in self.AREAS]})
            fl.append({'key': 'lang', 'name': '语言', 'value': [{'n': a, 'v': a} for a in self.LANGS]})
            fl.append({'key': 'year', 'name': '年份', 'value': [{'n': a, 'v': a} for a in self.YEARS]})
            fl.append({'key': 'sort', 'name': '排序', 'value': [{'n': n, 'v': v} for v, n in self.SORTS]})
            fl.append({'key': 'letter', 'name': '字母', 'value': [{'n': a, 'v': a} for a in self.LETTERS]})
            result['filters'][cid] = fl
        return result

    # ---------- 分类列表 ----------
    def categoryContent(self, tid, pg, filter, extend):
        ext = extend or {}
        tid = str(tid)
        if ext.get('type'):
            tid = str(ext['type'])
        F = [''] * 12
        F[0] = tid
        F[1] = ext.get('area', '')
        F[2] = ext.get('sort', '')
        F[4] = ext.get('lang', '')
        F[5] = ext.get('letter', '')
        F[8] = str(pg or 1)
        F[11] = ext.get('year', '')
        seg = '-'.join(_quote(x) if x else '' for x in F)
        html = self._get('/vodshow/%s/' % seg)
        return {'list': self._parse_list(html), 'page': int(pg or 1),
                'pagecount': 9999, 'limit': 72, 'total': 999999}

    def _parse_list(self, html):
        out = []
        for chunk in html.split('href="/voddetail/')[1:]:
            m = re.match(r'(\d+)/', chunk)
            if not m:
                continue
            vid = m.group(1)
            t = re.search(r'title="([^"]+)"', chunk[:400])
            name = t.group(1) if t else ''
            if not name:
                t = re.search(r'<strong>([^<]+)</strong>', chunk[:1500])
                name = t.group(1).strip() if t else ''
            if not name:
                continue
            note = re.search(r'module-item-note">([^<]*)<', chunk[:1500])
            out.append({
                'vod_id': vid,
                'vod_name': name,
                'vod_pic': self._img(chunk[:1500]),
                'vod_remarks': note.group(1).strip() if note else '',
            })
        # 去重保序
        seen, res = set(), []
        for v in out:
            if v['vod_id'] in seen:
                continue
            seen.add(v['vod_id'])
            res.append(v)
        return res

    # ---------- 详情 ----------
    def detailContent(self, ids):
        html = self._get('/voddetail/%s/' % ids[0])
        name = re.search(r'<h1>([^<]+)</h1>', html)
        poster = re.search(r'module-info-poster[\s\S]{0,1200}?data-original="([^"]+)"', html)
        desc = re.search(r'module-info-introduction-content">\s*<p>([\s\S]*?)</p>', html)
        year = re.search(r'href="/vodshow/\d+[-\w%]*?-(20\d\d)/"', html)
        area = re.search(r'module-info-tag-link"><a title="([^"]+)" href="/vodshow/\d+-%', html)
        dire = re.search(r'导演：</span><div class="module-info-item-content">([\s\S]*?)</div>', html)
        act = re.search(r'主演：</span><div class="module-info-item-content">([\s\S]*?)</div>', html)
        rel = re.search(r'上映：</span><div class="module-info-item-content">([^<]+)<', html)
        upd = re.search(r'更新：</span><div class="module-info-item-content">([^<]+)<', html)
        # 分类名: 面包屑或 vod_class
        cls = re.search(r'"vod_class":"([^"]*)"', html)
        if not cls:
            cls = re.search(r'module-info-tag-link"><a[^>]*>([^<]{1,8})</a><span class="slash"', html)

        # 线路名(按DOM顺序) + 各线路剧集
        tabs = re.findall(r'data-dropdown-value="([^"]+)"', html)
        eps = re.findall(r'href="/play/%s-(\d+)-(\d+)/"[^>]*>\s*<span>([^<]*)</span>' % ids[0], html)
        lines, cur = [], None
        for sid, nid, ep in eps:
            if sid != cur:
                cur = sid
                lines.append({'name': '', 'eps': []})
            lines[-1]['eps'].append('%s$%s-%s-%s' % (ep.strip(), ids[0], sid, nid))
        for i, ln in enumerate(lines):
            ln['name'] = tabs[i] if i < len(tabs) else ('自营%d线' % (i + 1))

        # 类型标签(奇幻/爱情/科幻)
        tags = re.findall(r'href="/vodshow/\d+---([^-/"]+)-+/"', html)
        type_name = ''
        if tags:
            try:
                type_name = ','.join(urllib.parse.unquote(t) for t in tags[:3])
            except Exception:
                type_name = ''
        if not type_name and cls:
            try:
                type_name = cls.group(1).encode().decode('unicode_escape')
            except Exception:
                type_name = cls.group(1)

        vod = {
            'vod_id': ids[0],
            'vod_name': name.group(1).strip() if name else '',
            'vod_pic': self._abs(poster.group(1)) if poster else '',
            'type_name': type_name,
            'vod_year': year.group(1) if year else '',
            'vod_area': '',
            'vod_remarks': (upd.group(1).strip() if upd else (rel.group(1).strip() if rel else '')),
            'vod_director': self._strip(dire.group(1)).replace('/', ', ') if dire else '',
            'vod_actor': self._strip(act.group(1)).replace('/', ', ') if act else '',
            'vod_content': self._strip(desc.group(1)) if desc else '',
        }
        if area:
            vod['vod_area'] = area.group(1).strip()
        froms, urls = [], []
        for ln in lines:
            froms.append(ln['name'])
            urls.append('#'.join(ln['eps']))
        vod['vod_play_from'] = '$$$'.join(froms)
        vod['vod_play_url'] = '$$$'.join(urls)
        return {'list': [vod]}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg=1):
        if str(pg or 1) != '1':
            return {'list': [], 'page': 1}
        html = self._get('/vodsearch/%s-------------/' % _quote(key))
        return {'list': self._parse_list(html), 'page': 1}

    # ---------- 播放 ----------
    def playerContent(self, flag, id, vip):
        html = ''
        # id 形如 126159-1-1
        html = self._get('/play/%s/' % id)
        m = re.search(r'player_aaaa\s*=\s*(\{[\s\S]*?\})\s*</script>', html)
        url, play_from = '', flag
        if m:
            try:
                obj = json.loads(m.group(1))
                url = obj.get('url', '').replace('\\/', '/')
                play_from = obj.get('from', flag)
            except Exception:
                pass
        if not url:  # 兜底: 直接抓页面里的 m3u8
            m2 = re.search(r'"(https?://[^"]+\.m3u8[^"]*)"', html)
            if m2:
                url = m2.group(1).replace('\\/', '/')
        return {
            'parse': '0', 'playUrl': '', 'url': url, 'flag': play_from,
            'header': {'User-Agent': self.UA, 'Referer': self.HOST + '/'},
        }

    def isVideoFormat(self, url):
        return '.m3u8' in url

    def isTextFormat(self, url):
        return False

    def destroy(self):
        pass


if __name__ == '__main__':
    import sys
    s = Spider()
    s.init('')
    if len(sys.argv) > 1 and sys.argv[1] == 'detail':
        print(json.dumps(s.detailContent([sys.argv[2]]), ensure_ascii=False)[:800])
