# -*- coding: utf-8 -*-
# ============================================================
# 刁民免费制作分享，请勿用于商业用途，贩卖，违法必究。
# 请于测试完24小时删除
# ============================================================
# TVBox / OK影视 / 影视仓 / WebHome 标准 Python 爬虫
# 站点: https://4k01.pianku.online (苹果CMS v10)
# ============================================================

import sys
import json
import re
import time
from urllib.parse import quote, unquote, urljoin

sys.path.append('..')

try:
    from base.spider import Spider
except ImportError:
    import requests as rq

    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r


class Spider(Spider):
    host = 'https://4k01.pianku.online'

    _backup_hosts = [
        'https://4k02.pianku.online',
        'https://pianku.online',
    ]

    _last_host_check = 0
    _host_cache_ttl = 1800

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://4k01.pianku.online/',
    }

    classes = [
        {'type_name': '电影', 'type_id': '20'},
        {'type_name': '剧集', 'type_id': '37'},
        {'type_name': '动漫', 'type_id': '43'},
        {'type_name': '综艺', 'type_id': '45'},
        {'type_name': 'B站', 'type_id': '47'},
        {'type_name': '动作片', 'type_id': '21'},
        {'type_name': '喜剧片', 'type_id': '22'},
        {'type_name': '爱情片', 'type_id': '23'},
        {'type_name': '科幻片', 'type_id': '24'},
        {'type_name': '恐怖片', 'type_id': '25'},
        {'type_name': '剧情片', 'type_id': '26'},
        {'type_name': '战争片', 'type_id': '27'},
        {'type_name': '惊悚片', 'type_id': '28'},
        {'type_name': '犯罪片', 'type_id': '29'},
        {'type_name': '冒险篇', 'type_id': '30'},
        {'type_name': '动画片', 'type_id': '31'},
        {'type_name': '悬疑片', 'type_id': '32'},
        {'type_name': '武侠片', 'type_id': '33'},
        {'type_name': '奇幻片', 'type_id': '34'},
        {'type_name': '纪录片', 'type_id': '35'},
        {'type_name': '其他片', 'type_id': '36'},
        {'type_name': '国产剧', 'type_id': '38'},
        {'type_name': '港台剧', 'type_id': '39'},
        {'type_name': '欧美剧', 'type_id': '40'},
        {'type_name': '日韩剧', 'type_id': '41'},
        {'type_name': '其他剧', 'type_id': '42'},
    ]

    # ==================== 动态域名 ====================

    def _ensure_host(self):
        now = time.time()
        if now - self._last_host_check < self._host_cache_ttl:
            return self.host
        self._last_host_check = now
        for h in [self.host] + self._backup_hosts:
            try:
                r = self.fetch(h, headers=self.headers, timeout=10)
                text = r.text if hasattr(r, 'text') else ''
                if r.status_code == 200 and ('片库' in text or 'pianku' in text or 'voddetail' in text):
                    self.host = h
                    self.headers['Referer'] = h + '/'
                    return self.host
            except Exception:
                pass
        return self.host

    def _html(self, url, require_ok=False):
        self._ensure_host()
        full = url if url.startswith('http') else self.host + url
        try:
            r = self.fetch(full, headers=self.headers, timeout=15)
            text = r.text if hasattr(r, 'text') else ''
            if require_ok and r.status_code >= 400:
                self._last_host_check = 0
                self._ensure_host()
                full = url if url.startswith('http') else self.host + url
                r = self.fetch(full, headers=self.headers, timeout=15)
                text = r.text if hasattr(r, 'text') else ''
            return text
        except Exception:
            if require_ok:
                self._last_host_check = 0
                self._ensure_host()
                try:
                    full = url if url.startswith('http') else self.host + url
                    r = self.fetch(full, headers=self.headers, timeout=15)
                    return r.text if hasattr(r, 'text') else ''
                except Exception:
                    pass
            return ''

    # ==================== 基础方法 ====================

    def getName(self):
        return '片库TV'

    def init(self, extend=''):
        self.extend = extend or ''
        self._ensure_host()

    def isVideoFormat(self, url):
        return any(x in url for x in ['.m3u8', '.mp4', '.flv', '.avi', '.mkv', '.ts'])

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    # ==================== 首页 ====================

    def homeContent(self, filter):
        return {'class': self.classes}

    def homeVideoContent(self):
        vods = []
        try:
            for tid in ['20', '37', '43', '45']:
                html = self._html('/vodtype/%s.html' % tid)
                vods.extend(self._parse_list(html)[:8])
                if len(vods) >= 30:
                    break
        except Exception:
            pass
        return {'list': vods[:30]}

    # ==================== 分类 ====================

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1)
            url = '/vodtype/%s-%d.html' % (tid, pg) if pg > 1 else '/vodtype/%s.html' % tid
            html = self._html(url, require_ok=True)
            vods = self._parse_list(html)
            has_next = '下一页' in html or 'page_link' in html and '尾页' in html
            return {
                'page': pg,
                'pagecount': pg + 1 if has_next else pg,
                'limit': len(vods) if vods else 20,
                'total': pg * len(vods),
                'list': vods,
            }
        except Exception as e:
            print('[片库TV] 分类异常: %s' % e)
            return {'page': 1, 'pagecount': 1, 'limit': 20, 'total': 20, 'list': []}

    # ==================== 详情 ====================

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            vid = re.search(r'(\d+)', vod_id)
            if not vid:
                return {'list': []}
            vid = vid.group(1)

            html = self._html('/voddetail/%s.html' % vid, require_ok=True)
            if not html:
                return {'list': []}

            # 名称
            vod_name = ''
            m = re.search(r'<h1 class="detail-title">(.*?)<', html, re.S)
            if m:
                vod_name = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if not vod_name:
                m = re.search(r'<title>(.*?)[^-]*?</title>', html, re.S)
                if m:
                    vod_name = m.group(1).strip()

            # 备注
            vod_remarks = ''
            m = re.search(r'<span class="detail-remarks">(.*?)</span>', html, re.S)
            if m:
                vod_remarks = re.sub(r'<[^>]+>', '', m.group(1)).strip()

            # 图片
            pic = ''
            m = re.search(r'<div class="detail-poster">.*?<img[^>]*src=["\']([^"\']+)["\']', html, re.S)
            if m:
                pic = m.group(1)
                if not pic.startswith('http'):
                    pic = urljoin(self.host, pic)

            # 信息
            info_map = {'分类': '', '年份': '', '导演': '', '主演': ''}
            for key in info_map:
                if key == '分类':
                    m = re.search(r'<span>%s[：:]\s*<a[^>]*>(.*?)</a></span>' % key, html, re.S)
                else:
                    m = re.search(r'<span>%s[：:]\s*([^<]+)</span>' % key, html, re.S)
                if m:
                    info_map[key] = re.sub(r'<[^>]+>', '', m.group(1)).strip()

            # 剧情
            vod_content = ''
            m = re.search(r'<div class="detail-desc">.*?<p>(.*?)</p>', html, re.S)
            if m:
                vod_content = re.sub(r'<[^>]+>', '', m.group(1)).strip()

            # 播放线路
            source_tabs = re.findall(r'class="source-tab-item"[^>]*data-target="playlist-(\d+)">(.*?)</span>', html, re.S)
            play_links = re.findall(r'href=["\'](/vodplay/\d+-\d+-\d+\.html)["\'][^>]*class=["\']play-btn-item["\'][^>]*title=["\']([^"\']*)["\']', html, re.S)

            # 按 source_id 分组
            player_map = {}
            for pl_url, pl_name in play_links:
                parts = pl_url.replace('/vodplay/', '').replace('.html', '').split('-')
                if len(parts) == 3:
                    sid, ep = parts[1], parts[2]
                    player_map.setdefault(sid, {'name': '', 'eps': []})
                    player_map[sid]['eps'].append({'name': pl_name, 'ep': ep})

            # 补充线路名称
            for target_id, name in source_tabs:
                sid = str(target_id)
                if sid in player_map:
                    player_map[sid]['name'] = name
                else:
                    player_map[sid] = {'name': name, 'eps': []}

            # 如果没有解析到播放数据，尝试从播放按钮获取
            if not player_map:
                btn = re.search(r'href=["\'](/vodplay/\d+-\d+-\d+\.html)["\'][^>]*class=["\']btn-play["\']', html, re.S)
                if btn:
                    parts = btn.group(1).replace('/vodplay/', '').replace('.html', '').split('-')
                    if len(parts) == 3:
                        sid, ep = parts[1], parts[2]
                        player_map[sid] = {'name': '默认', 'eps': [{'name': '播放', 'ep': ep}]}

            if not player_map:
                return {'list': [{
                    'vod_id': vod_id, 'vod_name': vod_name, 'vod_pic': pic,
                    'type_name': info_map['分类'], 'vod_year': info_map['年份'],
                    'vod_remarks': vod_remarks, 'vod_actor': info_map['主演'],
                    'vod_director': info_map['导演'], 'vod_content': vod_content,
                    'vod_play_from': '', 'vod_play_url': '',
                }]}

            play_from_list = []
            play_url_list = []
            for sid in sorted(player_map.keys(), key=int):
                pmap = player_map[sid]
                name = pmap.get('name', '') or '线路%s' % sid
                play_from_list.append(name)

                eps = pmap.get('eps', [])
                if eps:
                    episodes = ['%s$%s|%s|%s' % (ep['name'], vid, sid, ep['ep']) for ep in eps]
                else:
                    episodes = ['播放$%s|%s|1' % (vid, sid)]
                play_url_list.append('#'.join(episodes))

            return {'list': [{
                'vod_id': vod_id, 'vod_name': vod_name, 'vod_pic': pic,
                'type_name': info_map['分类'], 'vod_year': info_map['年份'],
                'vod_remarks': vod_remarks, 'vod_actor': info_map['主演'],
                'vod_director': info_map['导演'], 'vod_content': vod_content,
                'vod_play_from': '$$$'.join(play_from_list),
                'vod_play_url': '$$$'.join(play_url_list),
            }]}
        except Exception as e:
            print('[片库TV] 详情异常: %s' % e)
            return {'list': []}

    # ==================== 搜索 ====================

    def searchContentPage(self, key, quick, pg):
        try:
            pg = int(pg or 1)
            kw = quote(key)
            url = '/vodsearch/%s----------%d---.html' % (kw, pg) if pg > 1 else '/vodsearch/%s-------------.html' % kw
            html = self._html(url, require_ok=True)
            vods = self._parse_list(html)
            has_next = '下一页' in html or 'page_link' in html and '尾页' in html
            return {
                'page': pg,
                'pagecount': pg + 1 if has_next else pg,
                'limit': len(vods) if vods else 20,
                'total': pg * len(vods),
                'list': vods,
            }
        except Exception as e:
            print('[片库TV] 搜索异常: %s' % e)
            return {'page': 1, 'pagecount': 1, 'limit': 20, 'total': 20, 'list': []}

    # ==================== 播放 ====================

    def playerContent(self, flag, id, vipFlags):
        result = {'parse': 1, 'url': '', 'header': ''}
        try:
            play_id = str(id or '')
            if not play_id:
                return result

            parts = play_id.split('|')
            if len(parts) >= 3:
                vid, sid, ep = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                vid, sid, ep = parts[0], parts[1], '1'
            else:
                vid, sid, ep = play_id, '1', '1'

            html = self._html('/vodplay/%s-%s-%s.html' % (vid, sid, ep), require_ok=True)
            if not html:
                return result

            data = self._player_data(html)
            if not data:
                return result

            enc_url = data.get('url', '')
            if not enc_url:
                return result

            encrypt = data.get('encrypt', 0)
            if encrypt == 1:
                url = unquote(enc_url)
            elif encrypt == 2:
                import base64
                url = base64.b64decode(enc_url).decode('utf-8')
            else:
                url = enc_url

            result['url'] = url
            result['header'] = json.dumps({
                'User-Agent': self.headers['User-Agent'],
                'Referer': self.host + '/',
            })
            return result
        except Exception:
            return result

    # ==================== 本地代理 ====================

    def localProxy(self, param):
        return [404, 'text/plain', '', {}]

    # ==================== 工具方法 ====================

    def _parse_list(self, html):
        vods = []
        if not html:
            return vods
        for item in re.findall(
            r'<div class="vod-item">.*?<a href=["\'](/voddetail/(\d+)\.html)["\'][^>]*title=["\']([^"\']*)["\'][^>]*>.*?<img[^>]*src=["\']([^"\']*)["\'][^>]*>.*?<span class="remarks">(.*?)</span>.*?<h4 class="title">(.*?)</h4>.*?<p class="subtitle">(.*?)</p>.*?</a>.*?</div>',
            html, re.S
        ):
            url, vid, title, pic, remarks, title2, subtitle = item
            vods.append({
                'vod_id': vid,
                'vod_name': title or re.sub(r'<[^>]+>', '', title2).strip(),
                'vod_pic': pic if pic.startswith('http') else urljoin(self.host, pic),
                'vod_remarks': re.sub(r'<[^>]+>', '', remarks).strip(),
            })
        return vods

    def _player_data(self, html):
        try:
            m = re.search(r'var player_aaaa=(\{.*?\})</script>', html, re.S)
            if m:
                return json.loads(m.group(1))
            start = html.find('var player_aaaa=')
            if start == -1:
                return None
            brace = html.find('{', start)
            depth, end = 0, brace
            for i in range(brace, min(brace + 10000, len(html))):
                if html[i] == '{':
                    depth += 1
                elif html[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            return json.loads(html[brace:end + 1])
        except Exception:
            return None
