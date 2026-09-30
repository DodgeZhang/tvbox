import sys
import re
import json
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
requests.packages.urllib3.disable_warnings()

from base.spider import Spider

class Spider(Spider):
    # ========== 插件基础配置 ==========
    def getName(self):
        return "黑猫动漫"

    # ========== 初始化全局配置 ==========
    def init(self, extend=""):
        super().init(extend)
        self.site_url = "https://www.bmmdmm.com"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
            "Referer": self.site_url,
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        self.sess = requests.Session()
        self.sess.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        self.sess.mount("http://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])))
        self.page_size = 24

    # ========== 通用请求方法 ==========
    def fetch(self, url, timeout=10):
        try:
            res = self.sess.get(url, headers=self.headers, timeout=timeout, verify=False)
            res.encoding = "utf-8"
            return res
        except Exception as e:
            return None

    # ========== 首页分类接口 ==========
    def homeContent(self, filter):
        cate_list = [
            {"type_name": "最新更新", "type_id": "order=更新时间"},
            {"type_name": "日本动漫", "type_id": "region=日本"},
            {"type_name": "国产动漫", "type_id": "region=中国"},
            {"type_name": "美国动漫", "type_id": "region=美国"},
            {"type_name": "剧场版", "type_id": "genre=剧场版"},
            {"type_name": "OVA版", "type_id": "genre=OVA"},
            {"type_name": "连载动漫", "type_id": "status=连载"},
            {"type_name": "完结动漫", "type_id": "status=完结"}
        ]
        return {"class": cate_list}

    # ========== 分类列表接口 ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        page_index = pg - 1
        list_url = f"{self.site_url}/list/?{tid}&pagesize=24&pageindex={page_index}"
        res = self.fetch(list_url)
        video_list = []
        
        if res and res.ok:
            html = res.text
            lpic_match = re.search(r'<div class="lpic">\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
            if lpic_match:
                ul_html = lpic_match.group(1)
                for li in re.finditer(r'<li>(.*?)</li>', ul_html, re.S):
                    li_html = li.group(1)
                    vod_id = re.search(r'<a href=["\'](/show/\d+\.html)["\']', li_html)
                    vod_name = re.search(r'<h2>.*?<a href=["\'][^"\']*["\'] title=["\']([^"\']+)["\']', li_html, re.S)
                    if not vod_name:
                        vod_name = re.search(r'<h2>.*?>([^<]+)</a>', li_html, re.S)
                    vod_pic = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', li_html)
                    vod_remarks = re.search(r'<font color="red">(.*?)</font>', li_html)
                    
                    if vod_id and vod_name and vod_pic:
                        video_list.append({
                            "vod_id": self.site_url + vod_id.group(1),
                            "vod_name": vod_name.group(1).strip(),
                            "vod_pic": vod_pic.group(1).strip(),
                            "vod_remarks": vod_remarks.group(1).strip() if vod_remarks else "",
                            "style": {"type": "rect", "ratio": 1.33}
                        })
        
        pagecount = pg + 1 if len(video_list) == self.page_size else pg
        if res and res.ok:
            total_match = re.search(r'pageindex=(\d+)"[^>]*>尾页</a>', res.text)
            if total_match:
                pagecount = int(total_match.group(1)) + 1
        
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": 99999
        }

    # ========== 视频详情接口 ==========
    def detailContent(self, ids):
        vod_id = ids[0] if ids else ""
        if not vod_id:
            return {"list": [{"vod_name": "视频ID为空"}]}
        
        detail_url = vod_id
        res = self.fetch(detail_url)
        if not res or not res.ok:
            return {"list": [{"vod_id": vod_id, "vod_name": "视频详情解析失败"}]}
        
        html = res.text
        
        title_match = re.search(r'<h1>(.*?)</h1>', html, re.S)
        vod_name = title_match.group(1).strip() if title_match else "未知名称"
        vod_name = re.sub(r'<[^>]+>', '', vod_name)
        
        pic_match = re.search(r'<div class="thumb">.*?<img[^>]+src=["\']([^"\']+)["\']', html, re.S)
        vod_pic = pic_match.group(1).strip() if pic_match else ""
        if vod_pic.startswith("//"):
            vod_pic = "https:" + vod_pic
        
        desc_match = re.search(r'<div class="info">(.*?)</div>', html, re.S)
        vod_content = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip() if desc_match else ""
        
        remarks_match = re.search(r'更新至[：:]?\s*(.*?)</p>', html, re.S)
        vod_remarks = remarks_match.group(1).strip() if remarks_match else ""
        vod_remarks = re.sub(r'<[^>]+>', '', vod_remarks)
        
        type_match = re.search(r'<label>类型:</label>.*?>([^<]+)</a>', html, re.S)
        type_name = type_match.group(1).strip() if type_match else ""
        
        # 播放线路与集数解析
        play_from_list = []
        play_url_list = []
        
        menu_matches = re.findall(r'<li[^>]*onClick="setTab\(0,\d+\)"[^>]*>(.*?)</li>', html, re.S)
        movurl_blocks = re.findall(r'<div class="movurl"[^>]*>\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
        
        for idx, block_html in enumerate(movurl_blocks):
            from_name = re.sub(r'<[^>]+>', '', menu_matches[idx]).strip() if idx < len(menu_matches) else f"播放{idx+1}"
            if not from_name:
                from_name = f"播放{idx+1}"
            play_from_list.append(from_name)
            
            ep_list = []
            for ep in re.finditer(r'<a href=["\'](/play/[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', block_html):
                ep_url = self.site_url + ep.group(1)
                ep_name = ep.group(2).strip()
                ep_list.append(f"{ep_name}${ep_url}")
            
            play_url_list.append("#".join(ep_list))
        
        if not play_from_list:
            return {"list": [{"vod_id": vod_id, "vod_name": "未找到播放线路"}]}
        
        detail_info = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_remarks": vod_remarks,
            "type_name": type_name,
            "vod_content": vod_content,
            # 核心修复：多线路分隔符必须用 $$$ 而不是 |
            "vod_play_from": "$$$".join(play_from_list),
            "vod_play_url": "$$$".join(play_url_list)
        }
        
        return {"list": [detail_info]}

    # ========== 搜索接口 ==========
    def searchContent(self, key, quick, pg=1):
        pg = int(pg) if str(pg).isdigit() else 1
        page_index = pg - 1
        search_url = f"{self.site_url}/s_all?ex=1&kw={requests.utils.quote(key)}&pageindex={page_index}"
        res = self.fetch(search_url)
        video_list = []
        
        if res and res.ok:
            html = res.text
            lpic_match = re.search(r'<div class="lpic">\s*<ul>(.*?)</ul>\s*</div>', html, re.S)
            if lpic_match:
                ul_html = lpic_match.group(1)
                for li in re.finditer(r'<li>(.*?)</li>', ul_html, re.S):
                    li_html = li.group(1)
                    vod_id = re.search(r'<a href=["\'](/show/\d+\.html)["\']', li_html)
                    vod_name = re.search(r'<h2>.*?<a href=["\'][^"\']*["\'] title=["\']([^"\']+)["\']', li_html, re.S)
                    if not vod_name:
                        vod_name = re.search(r'<h2>.*?>([^<]+)</a>', li_html, re.S)
                    vod_pic = re.search(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', li_html)
                    vod_remarks = re.search(r'<font color="red">(.*?)</font>', li_html)
                    
                    if vod_id and vod_name and vod_pic:
                        video_list.append({
                            "vod_id": self.site_url + vod_id.group(1),
                            "vod_name": vod_name.group(1).strip(),
                            "vod_pic": vod_pic.group(1).strip(),
                            "vod_remarks": vod_remarks.group(1).strip() if vod_remarks else "搜索结果",
                            "style": {"type": "rect", "ratio": 1.33}
                        })
        
        pagecount = pg + 1 if len(video_list) == self.page_size else pg
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pagecount,
            "limit": self.page_size,
            "total": len(video_list) if len(video_list) < 99999 else 99999
        }

    # ========== 播放解析接口 ==========
    def playerContent(self, flag, id, vipFlags):
        play_url = id.split("$")[1] if "$" in id else id
        if not play_url:
            return {"parse": 0, "url": "", "header": self.headers}
        
        return {
            "parse": 1,
            "url": play_url,
            "header": self.headers
        }
