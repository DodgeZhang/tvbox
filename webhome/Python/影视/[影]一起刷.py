# -*- coding: utf-8 -*-
"""
兼容 FongMi/TV (T3) 和 WebHomeTV/PeekPro (T4) 的 Python Spider
站点: 一起刷 (yqs1.app / yqs2.app)
CMS: Vite+Vue SPA + 后端 API (POST + AES-CBC 加密响应)
特点:
  - API 服务器通过 DNS TXT 记录动态获取
  - 每个请求需要 MD5 签名
  - 响应体为 AES-CBC 加密的 Base64 字符串
  - 解密密钥: MD5('kandian'+'ying123')
  - 签名: MD5(MD5(request_id + SECRET) + SECRET)
"""
import sys
import re
import json
import uuid
import time
import hashlib
import base64
import requests as rq
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append('..')

# ===== 兼容导入 =====
try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def fetch(self, url, headers=None, **kw):
            kw.pop('timeout', None)
            r = rq.get(url, headers=headers, timeout=15, **kw)
            r.encoding = 'utf-8'
            return r

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


class Spider(Spider):

    PAGE_HOSTS = [
        'https://yqs1.app',
        'https://yqs2.app',
    ]
    SIGN_SECRET = 'kandianying123'
    VERSION = '1.1.9'
    APP_ID = '1'
    DEVICE_INFO = 'h5'
    DNS_URL = 'https://dns.alidns.com/resolve?name=host.movieyqs.com&short=true&type=16&t={t}'

    def getName(self):
        return "一起刷"

    def init(self, extend=""):
        if isinstance(extend, list):
            self.extend = ''
        else:
            self.extend = extend or ''
        self.uuid = uuid.uuid4().hex
        self.ua = 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        self._decrypt_key = hashlib.md5(('kandian' + 'ying123').encode()).hexdigest()
        self._api_base = None
        self._photo_domain = None
        self._session = rq.Session()
        self._session.verify = False
        self._session.headers.update({
            'User-Agent': self.ua,
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
        })
        self._detectApiBase()
        self._initPhotoDomain()

    # ========== API 服务器探测 (DNS TXT) ==========
    def _detectApiBase(self):
        try:
            t = time.time()
            r = rq.get(self.DNS_URL.format(t=t), timeout=8, verify=False,
                       headers={'User-Agent': self.ua})
            dns_result = r.json()
            txt = dns_result[0].replace('"', '').replace(' ', '')
            decoded = json.loads(base64.b64decode(txt))
            urls = decoded.get('url', [])
            # 随机打乱并测试
            import random
            random.shuffle(urls)
            for api_url in urls:
                try:
                    r = rq.get(api_url + '/ping',
                               headers={'Content-Type': 'application/json'},
                               timeout=5, verify=False)
                    if r.status_code == 200 and r.text.strip() == 'pong':
                        self._api_base = api_url
                        self._api_servers = urls
                        return
                except Exception:
                    continue
        except Exception:
            pass
        # 兜底
        self._api_base = 'https://yqsb.ejjjaakq.com'
        self._api_servers = [self._api_base]

    def _getApiBase(self):
        if self._api_base:
            return self._api_base
        self._detectApiBase()
        return self._api_base

    # ========== 图片域名 ==========
    def _initPhotoDomain(self):
        try:
            j = self._apiPost('/api/init', {'ad_type': '0', 'channel_code': 'guanfang'})
            data = j.get('data', {}) if isinstance(j, dict) else {}
            domains = data.get('photo_domain', [])
            if isinstance(domains, list) and domains:
                self._photo_domain = domains[0]
        except Exception:
            pass
        if not self._photo_domain:
            self._photo_domain = 'https://fmt.fhsafwd.com'

    def _getPhotoDomain(self):
        if self._photo_domain:
            return self._photo_domain
        self._initPhotoDomain()
        return self._photo_domain

    # ========== 签名 & 加密 ==========
    def _makeSign(self, request_id):
        s1 = hashlib.md5((request_id + self.SIGN_SECRET).encode()).hexdigest()
        return hashlib.md5((s1 + self.SIGN_SECRET).encode()).hexdigest()

    def _decrypt(self, text):
        text = text.strip()
        if not text:
            return {}
        if text.startswith('{'):
            try:
                return json.loads(text)
            except Exception:
                pass
        if not HAS_CRYPTO:
            return {'_raw': text[:100]}
        try:
            key = self._decrypt_key[:16].encode('utf-8')
            iv = self._decrypt_key[16:32].encode('utf-8')
            raw = base64.b64decode(text)
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(raw), AES.block_size)
            return json.loads(decrypted.decode('utf-8'))
        except Exception:
            return {}

    # ========== 网络请求 ==========
    def _apiPost(self, path, data=None, page_host=None):
        if not page_host:
            page_host = self.PAGE_HOSTS[0]
        api_base = self._getApiBase()
        request_id = uuid.uuid4().hex[:32]
        sign = self._makeSign(request_id)
        payload = {
            'app_id': self.APP_ID,
            'version': self.VERSION,
            'device_info': self.DEVICE_INFO,
            'request_id': request_id,
            'sign': sign,
            'uuid': self.uuid,
        }
        if data:
            payload.update(data)
        try:
            r = self._session.post(
                api_base + path, json=payload,
                headers={'Origin': page_host, 'Referer': page_host + '/'},
                timeout=20
            )
            return self._decrypt(r.text)
        except Exception:
            # 尝试备用 API 服务器
            for svr in (self._api_servers or []):
                if svr == api_base:
                    continue
                try:
                    r = self._session.post(
                        svr + path, json=payload,
                        headers={'Origin': page_host, 'Referer': page_host + '/'},
                        timeout=20
                    )
                    return self._decrypt(r.text)
                except Exception:
                    continue
            return {}

    def _fixPic(self, pic):
        if not pic:
            return pic
        if pic.startswith('//'):
            return 'https:' + pic
        if pic.startswith('http://'):
            return pic.replace('http://', 'https://', 1)
        if pic.startswith('https://'):
            return pic
        # 相对路径 image/xxx -> photo_domain/image/xxx
        if not pic.startswith('http'):
            return self._getPhotoDomain() + '/' + pic.lstrip('/')
        return pic

    def _videoItem(self, d):
        return {
            'vod_id': str(d.get('videoid', '')),
            'vod_name': d.get('title', ''),
            'vod_pic': self._fixPic(d.get('verticalurl', '') or d.get('vertical_url', '') or d.get('horizontalurl', '') or d.get('horizontal_url', '')),
            'vod_remarks': d.get('remark', '') or d.get('hdvideomark', ''),
        }

    # ========== 构建子分类筛选器 ==========
    def _buildFilters(self, classes):
        """为每个分类构建多维筛选器(新规范第15节)。
        维度: 专题(subject) + 地区(region_val) + 年份(year) + 排序(filter_type)
        专题从 classify/view 获取,其余从 /api/filter 获取。"""
        filters = {}

        # 1. 从 /api/filter 获取全局筛选维度(地区/年份/排序)
        sort_dim = None
        region_dim = None
        year_dim = None
        try:
            jf = self._apiPost('/api/filter')
            fdata = jf.get('data', {}) if isinstance(jf, dict) else {}
            flist = fdata.get('filters', []) if isinstance(fdata, dict) else []
            for f in flist:
                if not isinstance(f, dict):
                    continue
                param = f.get('filter_param', '')
                tags = f.get('filter_tag', []) or []
                opts = [{'n': t.get('name', ''), 'v': t.get('id', '')} for t in tags if isinstance(t, dict)]
                if param == 'filter_type' and opts:
                    sort_dim = {'key': 'sort', 'name': '排序', 'value': opts}
                elif param == 'region_val' and opts:
                    region_dim = {'key': 'region', 'name': '地区', 'value': opts}
                elif param == 'year' and opts:
                    year_dim = {'key': 'year', 'name': '年份', 'value': opts}
        except Exception:
            pass

        # 2. 并发获取每个分类的专题列表
        def _fetch_one(cid):
            try:
                j = self._apiPost('/api/classify/view', {'classify_id': int(cid)})
                data = j.get('data', {}) if isinstance(j, dict) else {}
                return cid, data.get('subjectlist', []) or []
            except Exception:
                return cid, []

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(_fetch_one, c['type_id']): c for c in classes}
            for fut in as_completed(futures):
                cid, subjects = fut.result()
                dims = []
                # 专题维度
                if subjects:
                    opts = [{'n': '全部', 'v': ''}]
                    for subj in subjects:
                        if not isinstance(subj, dict):
                            continue
                        sid = subj.get('subjectid', '')
                        sname = subj.get('name', '')
                        if sid and sname:
                            opts.append({'n': sname, 'v': str(sid)})
                    if len(opts) > 1:
                        dims.append({'key': 'subject', 'name': '专题', 'value': opts})
                # 地区维度
                if region_dim:
                    dims.append(region_dim)
                # 年份维度
                if year_dim:
                    dims.append(year_dim)
                # 排序维度
                if sort_dim:
                    dims.append(sort_dim)
                if dims:
                    filters[str(cid)] = dims
        return filters

    # ========== 首页 ==========
    def homeContent(self, filter):
        result = {}
        # 分类
        j = self._apiPost('/api/index/header')
        classes = []
        classifies = []
        if isinstance(j, dict):
            classifies = j.get('data', {}).get('classifylist', []) or []
        for c in classifies:
            classes.append({
                'type_id': str(c.get('classifyid', '')),
                'type_name': c.get('classifyname', ''),
            })
        result['class'] = classes
        # 始终返回 filters(新规范15.3:不要用 if filter 条件判断,
        # 部分客户端传 filter=False 会导致筛选器不显示)
        result['filters'] = self._buildFilters(classes)
        result['list'] = self._homeList()
        return result

    def _homeList(self):
        videos = []
        seen = set()
        j = self._apiPost('/api/index/body')
        data = j.get('data', {}) if isinstance(j, dict) else {}
        if not isinstance(data, dict):
            return videos
        # hotvodlist
        for d in (data.get('hotvodlist') or []):
            vid = str(d.get('videoid', ''))
            if vid and vid not in seen:
                seen.add(vid)
                videos.append(self._videoItem(d))
        # subjectlist 中的视频
        for subj in (data.get('subjectlist') or []):
            for d in (subj.get('video_list') or []):
                vid = str(d.get('videoid', ''))
                if vid and vid not in seen:
                    seen.add(vid)
                    videos.append(self._videoItem(d))
        return videos[:30]

    def homeVideoContent(self):
        return {"list": self._homeList()}

    # ========== 分类列表 ==========
    def categoryContent(self, tid, pg, filter, extend):
        # 解析 extend(新规范15.4:兼容 dict 和 JSON 字符串)
        ext = {}
        if extend:
            if isinstance(extend, dict):
                ext = extend
            elif isinstance(extend, str):
                try:
                    ext = json.loads(extend)
                except Exception:
                    ext = {}
        try:
            pg = int(pg or 1)
        except (ValueError, TypeError):
            pg = 1

        # 使用 /api/vod/search 实现服务端分页(支持 classify_id + subject_id + 筛选)
        params = {
            'page_num': pg,
            'classify_id': str(tid),
        }
        # 读取筛选条件
        subject_id = ext.get('subject', '')
        region_val = ext.get('region', '')
        year = ext.get('year', '')
        filter_type = ext.get('sort', '')
        if subject_id:
            params['subject_id'] = str(subject_id)
        if region_val:
            params['region_val'] = str(region_val)
        if year:
            params['year'] = str(year)
        if filter_type:
            params['filter_type'] = str(filter_type)

        j = self._apiPost('/api/vod/search', params)
        data = j.get('data', {}) if isinstance(j, dict) else {}
        vlist = data.get('video_list', []) if isinstance(data, dict) else []
        videos = [self._videoItem(d) for d in vlist if isinstance(d, dict)]
        total_pages = data.get('total_pages', 1) if isinstance(data, dict) else 1
        try:
            total_pages = int(total_pages)
        except (ValueError, TypeError):
            total_pages = 1
        total = data.get('total', len(videos)) if isinstance(data, dict) else len(videos)
        return {
            "list": videos,
            "page": pg,
            "pagecount": total_pages,
            "limit": 15,
            "total": total,
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        if isinstance(ids, str):
            ids = [ids]
        vod_id = ids[0]
        try:
            vod_id_int = int(vod_id)
        except (ValueError, TypeError):
            return {"list": []}

        j = self._apiPost('/api/vod/info', {'video_id': vod_id_int})
        data = j.get('data', {}) if isinstance(j, dict) else {}
        if not isinstance(data, dict) or not data:
            return {"list": []}

        # 构建多线路播放链接
        play_from_list = []
        play_url_list = []
        player_list = data.get('player_list', []) or []
        for pl in player_list:
            if not isinstance(pl, dict):
                continue
            player_name = pl.get('player_name', '默认')
            play_line_id = pl.get('play_line_id', '')
            ep_list = pl.get('ep_list', []) or []
            if not ep_list:
                continue
            play_from_list.append(player_name)
            urls = []
            for ep in ep_list:
                if not isinstance(ep, dict):
                    continue
                ep_id = ep.get('ep_id', '')
                ep_name = ep.get('ep_name', '')
                play_link = '{vid}${line_id}|{ep_id}'.format(
                    vid=vod_id, line_id=play_line_id, ep_id=ep_id)
                urls.append('{name}${link}'.format(name=ep_name, link=play_link))
            if urls:
                play_url_list.append('#'.join(urls))

        # actor / director / tag
        actor_list = data.get('actor_list', []) or []
        director_list = data.get('director_list', []) or []
        tag_list = data.get('tag_list', []) or []
        area_name = data.get('area_name', '')
        year = data.get('year', '')

        def _name(item):
            if isinstance(item, dict):
                return item.get('name', '') or item.get('tag_name', '') or str(item)
            return str(item)

        vod = {
            "vod_id": str(vod_id),
            "vod_name": data.get('video_name', ''),
            "vod_pic": self._fixPic(data.get('vertical_url', '') or data.get('horizontal_url', '')),
            "type_name": ', '.join(_name(t) for t in tag_list) if tag_list else '',
            "vod_year": str(year) if year else '',
            "vod_area": area_name,
            "vod_remarks": data.get('remark', ''),
            "vod_actor": ', '.join(_name(a) for a in actor_list),
            "vod_director": ', '.join(_name(d) for d in director_list),
            "vod_content": data.get('introduction', ''),
            "vod_play_from": '$$$'.join(play_from_list),
            "vod_play_url": '$$$'.join(play_url_list),
        }
        return {"list": [vod]}

    # ========== 搜索 ==========
    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        j = self._apiPost('/api/search/search', {
            'keyword': key,
            'next_value': '' if int(pg) <= 1 else str(pg),
        })
        data = j.get('data', {}) if isinstance(j, dict) else {}
        vlist = data.get('video_list', []) if isinstance(data, dict) else []
        videos = [self._videoItem(d) for d in vlist if isinstance(d, dict)]
        has_next = data.get('has_next', False) if isinstance(data, dict) else False
        pagecount = int(pg) + 1 if has_next else int(pg)
        return {
            "list": videos,
            "page": int(pg),
            "pagecount": pagecount,
            "limit": 20,
            "total": len(videos),
        }

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags):
        sid = str(id or '')
        # id 格式: {vid}${line_id}|{ep_id}
        line_id = ''
        ep_id = ''
        m = re.match(r'^(\d+)\$(\d+)\|(\d+)$', sid)
        if m:
            vid = m.group(1)
            line_id = m.group(2)
            ep_id = m.group(3)
        else:
            return {"parse": 1, "playUrl": "", "url": sid}

        j = self._apiPost('/api/vod/play_url', {
            'ep_id': int(ep_id),
            'resolution': 'sd',
            'play_line_id': int(line_id),
        })
        data = j.get('data', {}) if isinstance(j, dict) else {}
        play_url = ''
        if isinstance(data, dict):
            play_url = data.get('play_url', '')
        elif isinstance(data, str):
            play_url = data

        if play_url:
            play_url = play_url.replace('\\/', '/')
            return {
                "parse": 0,
                "playUrl": play_url,
                "url": play_url,
                "header": {
                    "User-Agent": self.ua,
                    "Referer": self.PAGE_HOSTS[0] + '/',
                },
            }

        return {"parse": 1, "playUrl": "", "url": sid}

    # ========== 清理 ==========
    def destroy(self):
        if self._session:
            self._session.close()

    def close(self):
        self.destroy()


if __name__ == '__main__':
    spider = Spider()
    spider.init()
