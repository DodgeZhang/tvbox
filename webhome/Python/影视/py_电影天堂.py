# -*- coding: utf-8 -*-
# 电影天堂资源 - OK影视爬虫插件
# 站点：http://dyttzy2.tv
import sys
import re
import html as html_module
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
requests.packages.urllib3.disable_warnings()

from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "电影天堂资源"

    # ========== 分类与筛选（4大类 + sub子类筛选） ==========
    classes = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "4", "type_name": "动漫"},
        {"type_id": "3", "type_name": "综艺"}
    ]

    filter_data = {
        "1": [{"key": "sub", "name": "类型", "value": [
            {"n": "全部", "v": ""},
            {"n": "动作片", "v": "6"},
            {"n": "喜剧片", "v": "7"},
            {"n": "科幻片", "v": "9"},
            {"n": "恐怖片", "v": "10"},
            {"n": "爱情片", "v": "8"},
            {"n": "剧情片", "v": "11"},
            {"n": "战争片", "v": "12"},
            {"n": "记录片", "v": "20"},
            {"n": "动画片", "v": "37"}
        ]}],
        "2": [{"key": "sub", "name": "类型", "value": [
            {"n": "全部", "v": ""},
            {"n": "国产剧", "v": "13"},
            {"n": "欧美剧", "v": "16"},
            {"n": "香港剧", "v": "14"},
            {"n": "韩国剧", "v": "15"},
            {"n": "台湾剧", "v": "21"},
            {"n": "日本剧", "v": "22"},
            {"n": "海外剧", "v": "23"},
            {"n": "泰国剧", "v": "24"},
            {"n": "短剧", "v": "36"}
        ]}],
        "4": [{"key": "sub", "name": "类型", "value": [
            {"n": "全部", "v": ""},
            {"n": "国产动漫", "v": "29"},
            {"n": "日韩动漫", "v": "30"},
            {"n": "欧美动漫", "v": "31"},
            {"n": "港台动漫", "v": "32"},
            {"n": "海外动漫", "v": "33"}
        ]}],
        "3": [{"key": "sub", "name": "类型", "value": [
            {"n": "全部", "v": ""},
            {"n": "大陆综艺", "v": "25"},
            {"n": "港台综艺", "v": "26"},
            {"n": "日韩综艺", "v": "27"},
            {"n": "欧美综艺", "v": "28"}
        ]}]
    }
    # ============================================================

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
        "Referer": "http://dyttzy2.tv",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }
    page_size = 30

    def init(self, extend=""):
        super().init(extend)
        self.site_url = "http://dyttzy2.tv"
        self.sess = requests.Session()
        self.sess.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        self.sess.mount("http://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))

    def fetch(self, url, timeout=10):
        try:
            res = self.sess.get(url, headers=self.headers, timeout=timeout, verify=False)
            res.encoding = "utf-8"
            return res
        except Exception:
            return None

    def homeContent(self, filter=False):
        """风格：返回 class + filters + 首页推荐列表"""
        result = {"class": self.classes, "filters": self.filter_data, "list": []}
        try:
            html = self.fetch(self.site_url + "/").text
            result["list"] = self._parse_list(html)
        except Exception:
            pass
        return result

    def homeVideoContent(self):
        result = {"list": []}
        try:
            html = self.fetch(self.site_url + "/").text
            result["list"] = self._parse_list(html)
        except Exception:
            pass
        return result

    def categoryContent(self, tid, pg, filter=False, extend=None):
        """风格：通过 extend["sub"] 切换子类，无筛选时保持大类"""
        result = {"list": [], "page": int(pg) if pg else 1, "pagecount": 0, "limit": self.page_size, "total": 0}
        try:
            pg = int(pg) if pg else 1
            sub = ""
            if isinstance(extend, dict):
                sub = extend.get("sub", "")
            elif isinstance(extend, str) and extend:
                sub = extend

            # 有子类筛选用子类ID，否则用大类ID
            actual_tid = sub if sub else tid
            # 屏蔽伦理
            if str(actual_tid) == "34":
                return result

            list_url = f"{self.site_url}/index.php/vod/type/id/{actual_tid}/page/{pg}.html" if pg > 1 else f"{self.site_url}/index.php/vod/type/id/{actual_tid}.html"
            res = self.fetch(list_url)
            if not res or not res.ok:
                return result

            html = res.text
            result["list"] = self._parse_list(html)
            # 计算总页数
            total_match = re.search(r'共(\d+)条数据,当前\d+/(\d+)页', html)
            if total_match:
                result["total"] = int(total_match.group(1))
                result["pagecount"] = int(total_match.group(2))
            else:
                result["pagecount"] = pg + 1 if len(result["list"]) else pg
                result["total"] = 99999
        except Exception:
            pass
        return result

    def detailContent(self, ids):
        vod_id = ids[0] if ids else ""
        if not vod_id:
            return {"list": []}
        res = self.fetch(vod_id)
        if not res or not res.ok:
            return {"list": [{"vod_id": vod_id, "vod_name": "详情请求失败"}]}
        html = res.text

        name_match = re.search(r'<h1 class="uppercase text-lg font-bold text-green-900">(.*?)</h1>', html)
        vod_name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip() if name_match else ""

        pic_match = re.search(r'<img class="w-full h-full rounded-lg shadow-md" src="([^"]+)"', html)
        vod_pic = pic_match.group(1) if pic_match else ""

        desc_match = re.search(r'<div class="max-h-\[290px\][^"]*">(.*?)</div>', html, re.S)
        vod_content = ""
        if desc_match:
            vod_content = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
            vod_content = re.sub(r'&nbsp;|\s+', ' ', vod_content).strip()

        type_name = year = area = actor = director = remarks = ""
        for tr in re.finditer(r'<tr class="border-t border-extra-sage/50">(.*?)</tr>', html, re.S):
            tds = re.findall(r'<td[^>]*>(.*?)</td>', tr.group(1), re.S)
            if len(tds) >= 2:
                key = re.sub(r'<[^>]+>', '', tds[0]).strip()
                val = re.sub(r'<[^>]+>', '', tds[1]).strip()
                if key == "类型":
                    type_name = val
                elif key == "年代":
                    year = val
                elif key == "地区":
                    area = val
                elif key == "演员":
                    actor = val
                elif key == "导演":
                    director = val
                elif key == "状态":
                    remarks = val

        # 只保留 dyttm3u8 线路，并做 HTML 实体解码
        raw_vals = re.findall(r'<input[^>]+name="copy_dyttm3u8\[\]"[^>]+value="([^"]+)"', html)
        m3u8_vals = []
        for i, v in enumerate(raw_vals, 1):
            v = html_module.unescape(v).strip()
            if not v:
                continue
            # 若 value 纯为 URL，自动补全集数标识
            if "$" not in v:
                v = f"第{i:02d}集${v}"
            m3u8_vals.append(v)

        play_from = []
        play_url = []
        if m3u8_vals:
            play_from.append("dyttm3u8")
            play_url.append("#".join(m3u8_vals))

        detail = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "type_name": type_name,
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_remarks": remarks,
            "vod_content": vod_content,
            "vod_play_from": "$$$".join(play_from) if play_from else "",
            "vod_play_url": "$$$".join(play_url) if play_url else ""
        }
        return {"list": [detail]}

    def searchContent(self, key, quick=False, pg="1"):
        pg = int(pg) if str(pg).isdigit() else 1
        search_url = f"{self.site_url}/index.php/vod/search.html?wd={requests.utils.quote(key)}&page={pg}"
        res = self.fetch(search_url)
        video_list = []
        if res and res.ok:
            html = res.text
            rows = re.finditer(r'<tr class="bg-green-50/50[^"]*">(.*?)</tr>', html, re.S)
            for row in rows:
                row_html = row.group(1)
                # 搜索结果中屏蔽伦理片
                if ">伦理" in row_html:
                    continue
                id_match = re.search(r'href="(/index\.php/vod/detail/id/\d+\.html)"', row_html)
                pic_match = re.search(r'<img[^>]+src="([^"]+)"', row_html)
                name_match = re.search(r'<div class="overflow-hidden text-ellipsis[^"]*">(.*?)</div>', row_html)
                remark_match = re.search(r'<span class="bg-extra-sage[^"]*">(.*?)</span>', row_html)
                if id_match and pic_match and name_match:
                    vid = id_match.group(1)
                    if not vid.startswith("http"):
                        vid = self.site_url + vid
                    vname = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()
                    vpic = pic_match.group(1)
                    if vpic.startswith("//"):
                        vpic = "https:" + vpic
                    elif not vpic.startswith(("http://", "https://")):
                        vpic = self.site_url + (vpic if vpic.startswith("/") else "/" + vpic)
                    vrem = re.sub(r'<[^>]+>', '', remark_match.group(1)).strip() if remark_match else ""
                    video_list.append({
                        "vod_id": vid,
                        "vod_name": vname,
                        "vod_pic": vpic,
                        "vod_remarks": vrem,
                        "style": {"type": "rect", "ratio": 0.75}
                    })
        pagecount = pg + 1 if len(video_list) else pg
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": 99999
        }

    def playerContent(self, flag, id, vipFlags=False):
        play_url = id.split("$")[1] if "$" in id else id
        if not play_url:
            return {"parse": 0, "url": "", "header": {}}
        
        # 补全防盗链所需的 Origin / Referer，解决 403
        header = {
            "User-Agent": self.headers.get("User-Agent", ""),
            "Referer": self.site_url + "/",
            "Origin": self.site_url,
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        return {
            "parse": 0,
            "url": play_url,
            "header": header
        }

    # ========== 内部通用解析（复用） ==========
    def _parse_list(self, html):
        video_list = []
        if not html:
            return video_list
        rows = re.finditer(r'<tr class="bg-green-50/50[^"]*">(.*?)</tr>', html, re.S)
        for row in rows:
            row_html = row.group(1)
            id_match = re.search(r'href="(/index\.php/vod/detail/id/\d+\.html)"', row_html)
            pic_match = re.search(r'<img[^>]+src="([^"]+)"', row_html)
            name_match = re.search(r'<div class="overflow-hidden text-ellipsis[^"]*">(.*?)</div>', row_html)
            remark_match = re.search(r'<span class="bg-extra-sage[^"]*">(.*?)</span>', row_html)
            if id_match and pic_match and name_match:
                vod_id = id_match.group(1)
                if not vod_id.startswith("http"):
                    vod_id = self.site_url + vod_id
                vod_name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()
                vod_pic = pic_match.group(1)
                if vod_pic.startswith("//"):
                    vod_pic = "https:" + vod_pic
                elif not vod_pic.startswith(("http://", "https://")):
                    vod_pic = self.site_url + (vod_pic if vod_pic.startswith("/") else "/" + vod_pic)
                vod_remarks = re.sub(r'<[^>]+>', '', remark_match.group(1)).strip() if remark_match else ""
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks,
                    "style": {"type": "rect", "ratio": 0.75}
                })
        return video_list
