#!/usr/bin/env python3
# coding=utf-8
"""
五五短剧 (duanju55.com) —— TVBox / 影视仓 Python 爬虫 (parse=0 直出 m3u8/mp4)

站点说明:
  duanju55 是苹果CMS 内核, 但前端用的是自定义皮肤「shoutu39_pc」, 与标准 MacCMS
  模板差异很大, 因此本文件按实测结构解析(非通用 MacCMS 约定):

  列表卡片(三套皮肤, 均已适配):
    - 首页 / 推荐                : SecondList_*
        <a class="image_imageScaleBox SecondList_bookImage" href="/index.php/vod/detail/id/{ID}.html">
          <img alt="{标题}" src="https://img.lzipic.com/.../xxx.jpg">
        </a>
        <a class="SecondList_totalChapterNum" href=".../id/{ID}.html">已完结 / 更新至80集</a>
        <a class="SecondList_bookName" href=".../id/{ID}.html">{标题}</a>
    - 分类(type)/标签(show)类浏览 : BrowseList_*   ★ 分类页走这套, 此前未适配导致"分类无内容"
        <a class="image_imageScaleBox BrowseList_imageBox" href="/index.php/vod/detail/id/{ID}.html">
          <img class="image_imageItem" src="https://tyyswimg2.com/.../xxx.jpg">
        </a>
        <a class="BrowseList_totalChapterNum" href=".../id/{ID}.html">更新全集</a>
        <a class="BrowseList_bookName" href=".../id/{ID}.html"><span>{标题}</span><span class="BrowseList_bookRate">998人在追</span></a>
    - 搜索结果(TagBookList_*):
        <a class="image_imageScaleBox TagBookList_bookImageBox" href=".../id/{ID}.html">
          <img alt="{标题}" src="https://tyyswimg2.com/.../xxx.jpg">
        </a>
        <a class="TagBookList_totalChapterNum" href=".../id/{ID}.html">更新全集 (下)</a>
        <a class="TagBookList_bookName" href=".../id/{ID}.html"><font ...><b>{标题}</b></font></a>
    * 海报均为图床绝对 URL(img.lzipic.com / tyyswimg2.com), 无需拼站点前缀
    * 同一部剧在页面出现多次(封面<a> + 标题<a> 同 href), 按 vid 合并字段
    * 分类页标题嵌在 <span> 内, 且同 <a> 内紧随 "998人在追" 之类的热度文本, 提取时只取首个 <span> 避免混入

  详情页:
    海报 : <img class="DramaDetail_bookCover" src="https://img.lzipic.com/..."> (无 og:image)
    选集 : 按 <div class="pcDrama_contentBox"> 分组, 每组一个线路名(pcDrama_titleText 含"在线播放")
           和若干 <a class="pcDrama_catalogItem" href="/index.php/vod/play/id/{ID}/sid/{S}/nid/{N}.html">
    选集数量少(多为"全集(上)/(下)"式合集), 静态 HTML 内即全部, 无 JS 分页

  播放页(parse=0 直出):
    视频地址写在 JS 配置对象里:  var player_xxxx={"url":"https:\/\/xxx.com\/...\/index.m3u8", ...}
    encrypt 多为 0(明文, 仅 JSON 转义了 \/), 抽出来反转义 \/ -> / 即直链

URL 形态:
  - 首页         : {SITE}/
  - 分类(类型)    : {SITE}/index.php/vod/type/id/{typeid}.html          翻页 ?page={N}
  - 标签分类      : {SITE}/index.php/vod/show/class/{标签}/id/1.html     翻页 ?page={N}
  - 关键词搜索     : {SITE}/index.php/vod/search/wd/{关键词}.html
  - 详情页       : {SITE}/index.php/vod/detail/id/{id}.html
  - 播放页       : {SITE}/index.php/vod/play/id/{id}/sid/{sid}/nid/{nid}.html

部署见文件末尾说明。
"""

import base64
import gzip
from html import unescape
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

sys.path.append('..')

# ---- TVBox 运行环境提供 base.spider; 本地调试时降级为空基类 ----
try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

try:
    import requests
    HAS_REQUESTS = True
except Exception:
    HAS_REQUESTS = False


def _log(msg):
    """统一日志出口: 写到 stderr, TVBox 壳子能捕获并展示。"""
    sys.stderr.write('[duanju55] ' + str(msg) + '\n')


DEFAULT_SITE = 'https://www.duanju55.com'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# 广告/统计域名: 即便出现在 iframe/src 里也不当作播放源
_AD_DOMAINS = ('doubleclick', 'googletag', 'cnzz', 'z_stat', 'baidu',
               '/ads/', 'analytics', 'static/ads', 'umeng', 'matomo')

# 分类导航。type id=1 为「短剧」主列表; 其余为已确认存在的标签分类(走 search/class)。
_C = lambda tid, name: {'type_id': tid, 'type_name': name}
CATEGORIES = [
    # 短剧主类(全部)。列表页为 BrowseList_* 皮肤
    _C('/index.php/vod/type/id/1.html', '短剧'),
    # 标签子分类: 导航真实路径为 /index.php/vod/show/class/{标签}/id/1.html (非 search/class)
    _C('/index.php/vod/show/class/' + urllib.parse.quote('男频') + '/id/1.html', '男频'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('女频') + '/id/1.html', '女频'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('都市') + '/id/1.html', '都市'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('虐渣') + '/id/1.html', '虐渣'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('励志') + '/id/1.html', '励志'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('逆袭') + '/id/1.html', '逆袭'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('古风') + '/id/1.html', '古风'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('复仇') + '/id/1.html', '复仇'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('家庭') + '/id/1.html', '家庭'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('悬疑') + '/id/1.html', '悬疑'),
    _C('/index.php/vod/show/class/' + urllib.parse.quote('奇幻') + '/id/1.html', '奇幻'),
]


class Spider(BaseSpider):
    # ==================== 生命周期 ====================
    def init(self, extend=""):
        """extend 可传入新域名, 站点换域名时无需改代码"""
        self.site = DEFAULT_SITE
        try:
            if extend:
                ext = extend.strip()
                if ext.startswith('{'):
                    ext = json.loads(ext).get('site', '')
                if ext.startswith('http'):
                    self.site = ext.rstrip('/')
        except Exception as e:
            _log('init 解析 extend 失败: %s' % e)
        return self

    def getName(self):
        return '五五短剧'

    def isVideoFormat(self, url):
        return bool(re.search(r'\.(m3u8|mp4|mkv|flv|avi|ts)(\?|$)', str(url), re.I))

    def manualVideoCheck(self):
        return False

    # ==================== 内部工具 ====================
    def _abs_url(self, url):
        """相对路径(以 / 开头)拼上站点前缀; 已是 http(s) 则原样返回。"""
        if not str(url).startswith('http'):
            return self.site + url
        return url

    def _fix_pic(self, pic):
        """把相对海报路径补全为站点直链(已是 http 则原样返回)。"""
        return self._abs_url(pic)

    def _fix_list_pics(self, video_list):
        """批量把列表中每张卡片的相对海报路径补全为站点直链(消除重复拼接)。"""
        for it in video_list:
            if it.get('vod_pic'):
                it['vod_pic'] = self._fix_pic(it['vod_pic'])
        return video_list

    def _get(self, url, timeout=20, headers=None, raw=False):
        """抓取页面。requests / urllib 双实现; 可覆盖请求头; raw=True 返回字节。
        网络/解析异常一律向上抛出, 由调用方捕获并记录日志(不在此裸吞)。"""
        url = self._abs_url(url)
        hd = {
            'User-Agent': UA,
            'Referer': self.site + '/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        if headers:
            hd.update(headers)
        if HAS_REQUESTS:
            r = requests.get(url, headers=hd, timeout=timeout)
            return r.content if raw else r.text
        req = urllib.request.Request(url, headers=hd)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if not raw:
                enc = resp.headers.get('Content-Encoding', '')
                if 'gzip' in enc:
                    data = gzip.decompress(data)
                data = data.decode('utf-8', 'ignore')
        return data

    @staticmethod
    def _is_ad(url):
        u = (url or '').lower()
        return any(d in u for d in _AD_DOMAINS)

    @staticmethod
    def _img_src(fragment):
        """从一段 HTML 中取第一张有效 <img> 的 src(已反转义), 占位图/广告图返回空。"""
        m = re.search(r'<img[^>]*\bsrc="([^"]+)"', fragment, re.I)
        if not m:
            return ''
        src = unescape(m.group(1)).strip()
        if not src or Spider._is_ad(src) or '占位' in src:
            return ''
        return src

    @staticmethod
    def _parse_list(html):
        """统一解析列表卡片 -> [{vod_id, vod_name, vod_pic, vod_remarks}]。
        适配三套皮肤, 按 (name, img, remark) 三个 class 分别抽取后按 vid 合并;
        同一部剧页面出现多次(封面<a> + 标题<a> 同 href)只留一条:
          - 首页/推荐              : SecondList_*        (标题=纯文本)
          - 分类(type)/标签(show)   : BrowseList_*         (标题嵌在 <span> 内)
          - 搜索结果               : TagBookList_*        (标题在 <font><b> 内)
        \\b 单词边界精确匹配 class, 避免误命中(如 TagBookList vs BookList)。"""
        items = {}

        def ensure(vid):
            if vid not in items:
                items[vid] = {'vod_id': vid, 'vod_name': '', 'vod_pic': '', 'vod_remarks': ''}
            return items[vid]

        def title_text(inner):
            """从 bookName 内部取标题: 优先第一个 <span> 文本(分类页标题嵌在 <span> 里,
            且后面紧接 <span class=bookRate>998人在追</span> 不应混入), 否则退化到去标签全文。"""
            s = re.search(r'<span[^>]*>([^<]+)</span>', inner, re.S | re.I)
            if s:
                t = s.group(1).strip()
                if t:
                    return t
            return re.sub(r'<[^>]+>', '', inner).strip()

        # (标题class, 海报class, 备注class)
        for pat_name, pat_img, pat_rem in (
            (r'SecondList_bookName', r'SecondList_bookImage', r'SecondList_totalChapterNum'),
            (r'TagBookList_bookName', r'TagBookList_bookImageBox', r'TagBookList_totalChapterNum'),
            (r'BrowseList_bookName', r'BrowseList_imageBox', r'BrowseList_totalChapterNum'),
        ):
            # 标题: <a class="..bookName.." href="..vod/detail/id/{ID}.html">文本</a>
            for m in re.finditer(
                    r'<a[^>]*class="[^"]*\b%s\b[^"]*"[^>]*href="[^"]*vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>'
                    % pat_name, html, re.S | re.I):
                e = ensure(m.group(1))
                t = title_text(m.group(2))
                if t and not e['vod_name']:
                    e['vod_name'] = t
            # 海报: 同名 class 的封面 <a> 内部 <img src>
            for m in re.finditer(
                    r'<a[^>]*class="[^"]*\b%s\b[^"]*"[^>]*href="[^"]*vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>'
                    % pat_img, html, re.S | re.I):
                e = ensure(m.group(1))
                pic = Spider._img_src(m.group(0))
                if pic and not e['vod_pic']:
                    e['vod_pic'] = pic
            # 备注(集数/状态): 同 class 锚点文本
            for m in re.finditer(
                    r'<a[^>]*class="[^"]*\b%s\b[^"]*"[^>]*href="[^"]*vod/detail/id/(\d+)\.html"[^>]*>(.*?)</a>'
                    % pat_rem, html, re.S | re.I):
                e = ensure(m.group(1))
                r = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                if r and not e['vod_remarks']:
                    e['vod_remarks'] = r
        return list(items.values())

    @staticmethod
    def _parse_pagination(html, default=999):
        """尝试从页面提取真实总页数(取翻页链接里 page= 的最大页码), 提取不到则回退 default。"""
        nums = []
        for h in re.findall(r'href="([^"]+)"', html):
            if 'page=' in h:
                m = re.search(r'page=(\d+)', h)
                if m:
                    try:
                        nums.append(int(m.group(1)))
                    except Exception:
                        pass
        return max(nums) if nums else default

    # ==================== 首页 ====================
    def homeContent(self, filter):
        html = self._get('/')
        classes = [dict(c) for c in CATEGORIES]
        video_list = self._fix_list_pics(self._parse_list(html))
        return {'class': classes, 'list': video_list}

    # ==================== 分类 / 列表 ====================
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        url = tid + ('?page=%d' % pg if pg > 1 else '')
        try:
            html = self._get(url)
        except Exception as e:
            _log('categoryContent 抓取失败 %s: %s' % (url, e))
            html = ''
        video_list = self._parse_list(html)
        pagecount = self._parse_pagination(html)
        return {
            'list': self._fix_list_pics(video_list),
            'page': pg,
            'pagecount': pagecount,
            'limit': 24,
            'total': 24 * pagecount,
        }

    # ==================== 搜索 ====================
    def searchContent(self, key, quick, pg):
        pg = int(pg) if str(pg).isdigit() else 1
        # 搜索结果页为 TagBookList_* 皮肤, 关键词走 /index.php/vod/search/wd/{关键词}.html
        url = '/index.php/vod/search/wd/' + urllib.parse.quote(key)
        if pg > 1:
            url += '?page=%d' % pg
        try:
            html = self._get(url)
        except Exception as e:
            _log('searchContent 抓取失败 %s: %s' % (key, e))
            html = ''
        video_list = self._parse_list(html)
        return {'list': self._fix_list_pics(video_list)}

    # ==================== 详情 / 选集 ====================
    def detailContent(self, ids):
        vid = ids[0] if isinstance(ids, (list, tuple)) else ids
        try:
            html = self._get('/index.php/vod/detail/id/%s.html' % vid)
        except Exception as e:
            _log('detailContent 抓取失败 %s: %s' % (vid, e))
            html = ''

        # 标题: <title>剧名-...</title> 取第一段
        vod_name = ''
        tm = re.search(r'<title>(.*?)</title>', html, re.I)
        if tm:
            vod_name = re.split(r'[-_|]', tm.group(1))[0].strip()

        # 海报: DramaDetail_bookCover 的 src(图床绝对 URL); 兜底 og:image
        vod_pic = ''
        im = re.search(r'<img[^>]*class="[^"]*\bDramaDetail_bookCover\b[^"]*"[^>]*\bsrc="([^"]+)"', html, re.I)
        if im:
            vod_pic = self._fix_pic(unescape(im.group(1)).strip())
        if not vod_pic:
            pm = re.search(r'property="og:image"[^>]+content="([^"]+)"', html, re.I)
            if pm:
                vod_pic = self._fix_pic(unescape(pm.group(1)).strip())

        # 简介
        vod_content = ''
        cm = re.search(r'class="[^"]*(?:detail-content|vod-content|content|descr|intro)[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I)
        if cm:
            vod_content = re.sub(r'<[^>]+>', '', cm.group(1)).strip()

        # 选集: 按 pcDrama_contentBox 分组, 每组 线路名(pcDrama_titleText) + 选集(pcDrama_catalogItem)
        sources, urls = [], []
        boxes = []
        for m in re.finditer(r'<div class="pcDrama_contentBox', html):
            s = m.start()
            nxt = html.find('<div class="pcDrama_contentBox', s + 10)
            boxes.append(html[s: nxt if nxt > 0 else len(html)])
        for box in boxes:
            tm = re.search(r'pcDrama_titleText">(.*?)</h3>', box, re.S | re.I)
            if not tm:
                continue
            line = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
            eps = re.findall(
                r'<a[^>]*class="[^"]*\bpcDrama_catalogItem\b[^"]*"[^>]*'
                r'href="([^"]*vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)\.html)"[^>]*>(.*?)</a>',
                box, re.S | re.I)
            if not eps:
                continue
            items = []
            for href, _v, sid, nid, name in eps:
                items.append((int(nid), (name.strip() or ('第%02d集' % int(nid))), href))
            items.sort(key=lambda x: x[0])
            sources.append(line)
            ep_str = '#'.join('{}${}'.format(ep_name, self._abs_url(href))
                               for _nid, ep_name, href in items)
            urls.append(ep_str)

        if not sources:
            return {'list': [{'vod_id': vid, 'vod_name': vod_name, 'vod_pic': vod_pic,
                              'vod_content': vod_content, 'vod_play_from': '', 'vod_play_url': ''}]}

        return {'list': [{
            'vod_id': vid,
            'vod_name': vod_name,
            'vod_pic': vod_pic,
            'vod_content': vod_content,
            'vod_play_from': '$$$'.join(sources),
            'vod_play_url': '$$$'.join(urls),
        }]}

    # ==================== 播放解析(parse=0 直出) ====================
    @staticmethod
    def _extract_media(html):
        """从播放页抽取可播直链(parse=0)。
        多策略: 1) player_xxxx 配置对象的 url 字段(明文, 反转义 \\/); 2) 直接 .m3u8/.mp4;
        3) url:"..." 字段(支持 base64); 4) iframe/video/source。过滤广告域名, 优先 m3u8。"""
        cands = []
        # 1) player_xxxx 配置对象: var player_xxxx={... "url":"https:\/\/..." ...}
        #    注意 JS 对象含嵌套 {}, 用 .*? 非贪婪跨过; 键是 "url"(带引号), 不是裸 url:
        for m in re.finditer(r'var\s+player_\w+\s*=\s*\{.*?"url"\s*:\s*"([^"]*)"', html, re.S | re.I):
            u = m.group(1).replace('\\/', '/')
            if 'http' in u:
                cands.append(u if u.startswith('http') else ('https:' + u if u.startswith('//') else u))
        # 2) 直接媒体链接
        for u in re.findall(r'(?:https?:)?//[^\s"\'<>]+\.(?:m3u8|mp4)(?:\?[^"\'\s<>]*)?', html, re.I):
            cands.append(u if u.startswith('http') else 'https:' + u)
        # 3) "url":"..." 字段(支持 base64 编码); 键带引号, 避免误匹配 wapurl 等
        for m in re.finditer(r'["\']url["\']\s*:\s*["\']([^"\']+)["\']', html, re.I):
            v = m.group(1).strip().replace('\\/', '/')
            if v.startswith('http'):
                cands.append(v)
            elif re.fullmatch(r'[A-Za-z0-9+/=]{16,}', v):
                try:
                    d = base64.b64decode(v + '=' * (-len(v) % 4)).decode('utf-8', 'ignore')
                    if 'http' in d and ('.m3u8' in d or '.mp4' in d):
                        cands.append(d if d.startswith('http') else ('https:' + d if d.startswith('//') else d))
                except Exception:
                    pass
        # 4) iframe / video / source 标签
        for pat in (r'<iframe[^>]+src=["\']([^"\']+)["\']',
                    r'<video[^>]+src=["\']([^"\']+)["\']',
                    r'<source[^>]+src=["\']([^"\']+)["\']'):
            for m in re.finditer(pat, html, re.I):
                cands.append(m.group(1).strip())

        media = [u for u in cands if u.startswith('http') and not Spider._is_ad(u)]
        if not media:
            return ''
        m3u8 = [u for u in media if '.m3u8' in u.lower()]
        if m3u8:
            return m3u8[0]
        mp4 = [u for u in media if '.mp4' in u.lower()]
        if mp4:
            return mp4[0]
        # 其余(可能是外部播放器页/iframe): 原样返回, 由 playerContent 再抓一层
        return media[0]

    def _resolve_player(self, url, depth=0):
        """抓取播放页并抽取直链; 若命中的是外部播放器页/iframe, 再向下抓一层(最多 1 层)。"""
        try:
            html = self._get(url, headers={'Referer': self.site + '/'})
        except Exception as e:
            _log('播放页抓取失败 %s: %s' % (url, e))
            return ''
        media = self._extract_media(html)
        if not media:
            return ''
        if '.m3u8' in media.lower() or '.mp4' in media.lower():
            return media
        # 命中外部播放器页: 再抓一层
        if depth < 1 and media.startswith('http'):
            return self._resolve_player(media, depth + 1)
        return media

    def playerContent(self, flag, id, vipFlags):
        """直出可播放直链(parse=0)。"""
        url = self._abs_url(str(id))
        media = self._resolve_player(url)
        if not media:
            return {'parse': 0, 'url': '', 'header': {'User-Agent': UA}}
        header = {'User-Agent': UA, 'Referer': self.site + '/'}
        return {'parse': 0, 'url': media, 'header': header}


# ==================== 部署说明 ====================
# 1. 将本文件放入 TVBox / 影视仓 的 spider 目录(通常需按壳要求命名, 如 spider.py)。
# 2. 站点换域名时, 在订阅 extend 参数里传新域名即可, 例如: {"site":"https://新域名"}
# 3. 依赖: 运行环境自带 requests; 若没有则自动回退标准库 urllib, 无需额外安装。
# 4. 本版为直播放版(parse=0): playerContent 抓取播放页, 从 player_xxxx 配置对象抽出
#    .m3u8/.mp4 直链回传, 播放器无需再解析; 选集地址来自详情页 /vod/play/ 链接。
# 5. 列表/详情解析针对本站 shoutu39_pc 皮肤实测校准(SecondList_* 与 TagBookList_* 两套列表皮肤)。
# ===================================================

if __name__ == '__main__':
    sp = Spider()
    sp.init()
    print('name:', sp.getName())
