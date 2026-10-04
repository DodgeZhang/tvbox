# -*- coding: utf-8 -*-
# 光社漫画 TVBox爬虫 - 修复版
# 解决：①图片加密(纯Python解密) ②按视频播放 ③章节排序
import sys
import re
import json
import os
import base64
import requests
import urllib3

sys.path.append('..')
from base.spider import Spider

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Spider(Spider):

    RE_HREF = re.compile(r'href=["\']([^"\']+)["\']')
    RE_IMG = re.compile(r'src=["\']([^"\']+)["\']')
    RE_MID = re.compile(r'data-mid=["\'](\d+)["\']')

    API_HOST = "https://v2.apikk.top"

    IMG_HOSTS = {
        1: "https://c-nd1-1.6wm.top",
        2: "https://c-nd2-1.6wm.top",
        3: "https://c-nd3-1.6wm.top",
        "default": "https://c-nd3-1.6wm.top"
    }

    # ===== 解密常量（从 chapter-decoder.js 逆向提取）=====
    PREFIX1 = 'J7r'    # 外层前缀标记
    SUFFIX1 = 'nQ'     # 外层后缀标记
    PREFIX2 = 'kD'     # 内层前缀标记
    SUFFIX2 = 'W4s'    # 内层后缀标记
    BLOCKSIZE = 7      # 分块反转的块大小
    # 自定义字母表 -> 标准base64字母表的映射
    CUSTOM_ALPHA = '_-9876543210abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    STANDARD_ALPHA = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'

    def getName(self):
        return "光社漫画"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def getHeader(self):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://m.g-mh.org/",
            "Origin": "https://m.g-mh.org"
        }

    def fetch(self, url):
        try:
            return requests.get(url, headers=self.getHeader(), timeout=10, verify=False)
        except:
            return None

    def homeContent(self, filter):
        cats = [
            {"type_name": "复仇", "type_id": "fuchou"},
            {"type_name": "古风", "type_id": "gufeng"},
            {"type_name": "奇幻", "type_id": "qihuan"},
            {"type_name": "逆袭", "type_id": "nixi"},
            {"type_name": "异能", "type_id": "yineng"},
            {"type_name": "穿越", "type_id": "chuanyue"},
            {"type_name": "热血", "type_id": "rexue"},
            {"type_name": "纯爱", "type_id": "chunai"},
            {"type_name": "系统", "type_id": "xitong"},
            {"type_name": "重生", "type_id": "zhongsheng"},
            {"type_name": "冒险", "type_id": "maoxian"},
            {"type_name": "灵异", "type_id": "lingyi"},
            {"type_name": "恋爱", "type_id": "lianai"},
            {"type_name": "玄幻", "type_id": "xuanhuan"},
            {"type_name": "科幻", "type_id": "kehuan"},
            {"type_name": "悬疑", "type_id": "xuanyi"},
            {"type_name": "修仙", "type_id": "xiuxian"},
            {"type_name": "战斗", "type_id": "zhandou"}
        ]
        return {"class": cats, "filters": {}}

    def homeVideoContent(self):
        return self.categoryContent("fuchou", "1", None, {})

    def categoryContent(self, tid, pg, filter, extend):
        url = f"https://m.g-mh.org/manga-tag/{tid}/page/{pg}"
        return self._parse_list_content(url, pg)

    def searchContent(self, key, quick, pg="1"):
        url = f"https://m.g-mh.org/s/{key}?page={pg}"
        return self._parse_list_content(url, pg)

    def _parse_list_content(self, url, pg):
        vlist = []
        try:
            r = self.fetch(url)
            if not r or r.status_code != 200:
                return {"list": []}
            r.encoding = 'utf-8'
            html = r.text
            blocks = html.split('class="pb-2"')[1:]
            for block in blocks:
                sub_block = block.split('<div class="pb-2"')[0] if '<div class="pb-2"' in block else block
                href_match = self.RE_HREF.search(sub_block)
                if not href_match: continue
                href = href_match.group(1)
                name_match = re.search(r'<h3[^>]*>(.*?)</h3>', sub_block, re.S)
                if not name_match: continue
                name = name_match.group(1).strip()
                pic = ""
                pic_match = self.RE_IMG.search(sub_block)
                if pic_match: pic = pic_match.group(1)
                vlist.append({
                    'vod_id': href,
                    'vod_name': name,
                    'vod_pic': pic,
                    'vod_remarks': ''
                })
            return {"list": vlist, "page": pg, "pagecount": 9999, "limit": 30, "total": 999999}
        except Exception:
            return {"list": []}

    def detailContent(self, ids):
        vid = ids[0]
        url = f"https://m.g-mh.org{vid}" if not vid.startswith('http') else vid
        try:
            r = self.fetch(url)
            if not r: return {"list": []}
            r.encoding = 'utf-8'
            html = r.text

            name = ""
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
            if h1: name = re.sub(r'<[^>]+>', '', h1.group(1)).strip()

            pic = ""
            img = re.search(r'class="rounded-lg"[^>]*src=["\']([^"\']+)["\']', html)
            if img: pic = img.group(1)

            desc = ""
            d_match = re.search(r'class="text-medium[^"]*"[^>]*>(.*?)<', html, re.S)
            if d_match: desc = d_match.group(1).strip()

            mid = ""
            mid_match = self.RE_MID.search(html)
            if mid_match:
                mid = mid_match.group(1)

            mslug = ""
            slug_match = re.search(r'data-link-base=["\']/manga/([^"\']+)["\']', html)
            if slug_match:
                mslug = slug_match.group(1)
            else:
                canon = re.search(r'href=["\']https://m\.g-mh\.org/manga/([^"\']+)["\']', html)
                if canon:
                    mslug = canon.group(1)

            if not mid:
                return {"list": []}

            api_url = f"{self.API_HOST}/api/v2/manga/get?mid={mid}&mode=all"
            api_res = requests.get(api_url, headers=self.getHeader(), verify=False, timeout=10)

            chapter_list = []
            if api_res.status_code == 200:
                data = api_res.json()
                chapters = []
                if 'data' in data and 'chapters' in data['data']:
                    chapters = data['data']['chapters']

                for ch in chapters:
                    cid = ch.get('id')
                    title = ch.get('attributes', {}).get('title', f"第{cid}话")
                    cslug = ch.get('attributes', {}).get('slug', '')
                    chapter_url = f"https://m.g-mh.org/manga/{mslug or mid}/{cslug or cid}"
                    chapter_list.append(f"{title}${chapter_url}")

            # 章节排序：非正片保持网站原序在前，正片按章节号升序在后
            def get_chapter_info(clist):
                non_main = []
                main = []
                for item in clist:
                    if '$' not in item:
                        continue
                    name_part, url_part = item.split('$', 1)
                    name_part = name_part.strip()
                    num_match = re.search(r'第?\s*(\d+(?:\.\d+)?)\s*[话卷章节回]', name_part)
                    if num_match:
                        main.append((name_part, url_part, float(num_match.group(1))))
                    else:
                        non_main.append((name_part, url_part))
                return non_main, main

            if chapter_list:
                non_main, main = get_chapter_info(chapter_list)
                main.sort(key=lambda x: x[2])
                chapter_list = [f"{n}${u}" for n, u in non_main] + [f"{n}${u}" for n, u, _ in main]

            play_url = "#".join(chapter_list)
            play_url_rev = "#".join(chapter_list[::-1]) if chapter_list else ""

            return {
                "list": [{
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": pic,
                    "type_name": "漫画",
                    "vod_content": desc,
                    "vod_play_from": "正序(Mange)$$$正序(Pics)$$$倒序(Mange)$$$倒序(Pics)",
                    "vod_play_url": f"{play_url}$$${play_url}$$${play_url_rev}$$${play_url_rev}"
                }]
            }
        except Exception:
            return {"list": []}

    def playerContent(self, *args):
        if len(args) < 2:
            return {'parse': 1, 'url': '', 'header': ''}
        flag = args[0]
        url = args[1]

        try:
            r = self.fetch(url)
            if not r or r.status_code != 200:
                return {'parse': 1, 'url': url, 'header': ''}
            r.encoding = 'utf-8'
            html = r.text

            mid = ""
            mid_match = re.search(r'data-mid=["\'](\d+)["\']', html)
            if mid_match:
                mid = mid_match.group(1)

            cid = ""
            cid_match = re.search(r'data-cs=["\'](\d+)["\']', html)
            if cid_match:
                cid = cid_match.group(1)

            if not mid or not cid:
                cid_match2 = re.search(r'data-current-chapter-id=["\'](\d+)["\']', html)
                if cid_match2:
                    cid = cid_match2.group(1)
                mid_match2 = re.search(r'data-mid=["\'](\d+)["\']', html)
                if mid_match2:
                    mid = mid_match2.group(1)

            if not mid or not cid:
                return {'parse': 1, 'url': url, 'header': ''}

            api_url = f"{self.API_HOST}/api/v2/chapter/getinfo?m={mid}&c={cid}"
            api_res = requests.get(api_url, headers=self.getHeader(), verify=False, timeout=10)

            if api_res.status_code == 200:
                data = api_res.json()
                enc_str = ""
                line = 1
                try:
                    info = data['data']['info']
                    enc_str = info['images']['images']
                    line = info['images'].get('line', 1)
                except:
                    pass

                if enc_str:
                    img_paths = self._decode_images(enc_str)

                    if img_paths:
                        img_host = self.IMG_HOSTS.get(line, self.IMG_HOSTS["default"])
                        img_list = []
                        for item in img_paths:
                            if isinstance(item, dict) and 'url' in item:
                                path = item['url']
                            elif isinstance(item, str):
                                path = item
                            else:
                                continue
                            if path.startswith('/'):
                                img_list.append(f"{img_host}{path}")
                            elif path.startswith('http'):
                                img_list.append(path)
                            else:
                                img_list.append(f"{img_host}/{path}")

                        if img_list:
                            if len(img_list) == 1:
                                img_list = img_list * 2
                            pics_data = "&&".join(img_list)
                            protocol = 'mange://' if 'mange' in str(flag).lower() else 'pics://'
                            return {
                                "parse": 0,
                                "playUrl": "",
                                "url": f'{protocol}{pics_data}',
                                "header": json.dumps({
                                    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1",
                                    "Referer": "https://m.g-mh.org/"
                                })
                            }
        except Exception:
            pass

        return {'parse': 1, 'url': url, 'header': ''}

    def _charmap(self, s):
        """自定义字母表 -> 标准base64字母表"""
        t = str.maketrans(self.CUSTOM_ALPHA, self.STANDARD_ALPHA)
        return s.translate(t)

    def _reorder(self, s):
        """分块反转：奇数块（0-based）反转"""
        parts = []
        for i in range(0, len(s), self.BLOCKSIZE):
            block = s[i:i + self.BLOCKSIZE]
            if (i // self.BLOCKSIZE) % 2 == 1:
                parts.append(block[::-1])
            else:
                parts.append(block)
        return ''.join(parts)

    def _decode_images(self, enc_str):
        """纯Python解密图片地址（不依赖quickjs/node）"""
        try:
            # Step 1: 去掉外层标记 PREFIX1 + ... + SUFFIX1
            inner = enc_str[len(self.PREFIX1):-len(self.SUFFIX1)]

            # Step 2: 在inner中定位内层标记 PREFIX2(kD) 和 SUFFIX2(W4s)
            w4s_pos = inner.find(self.SUFFIX2)
            if w4s_pos < 0:
                return []

            lastPart = inner[w4s_pos + len(self.SUFFIX2):]

            # 在 W4s 之前找所有 kD 位置，逐一尝试解密
            # （加密串中可能存在多个 kD 子串，只有正确的那个能解出合法JSON）
            kd_positions = []
            start = 0
            while True:
                pos = inner.find(self.PREFIX2, start, w4s_pos)
                if pos == -1:
                    break
                kd_positions.append(pos)
                start = pos + 1

            if not kd_positions:
                return []

            for kd_pos in kd_positions:
                firstPart = inner[:kd_pos]
                middle = inner[kd_pos + len(self.PREFIX2):w4s_pos]
                reorder_input = lastPart + firstPart + middle

                # Step 3: 分块反转
                reordered = self._reorder(reorder_input)

                # Step 4: 字符映射（自定义字母表 -> 标准base64）
                mapped = self._charmap(reordered)

                # Step 5: 补齐base64 padding 并解码
                pad = (4 - len(mapped) % 4) % 4
                padded = mapped + '=' * pad
                b64_str = padded.replace('-', '+').replace('_', '/')
                try:
                    decoded = base64.b64decode(b64_str).decode('utf-8')
                    result = json.loads(decoded)
                    if isinstance(result, list) and len(result) > 0:
                        return result
                except Exception:
                    continue

            return []
        except Exception:
            return []

    def localProxy(self, param):
        pass