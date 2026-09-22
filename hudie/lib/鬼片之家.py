# -*- coding: utf-8 -*-
import re
import sys
import json
import requests
import urllib3
from urllib.parse import quote
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        self.extend = extend
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.guipian360.org/",
            "Connection": "keep-alive",
        })
        self.session.verify = False

    def getName(self):
        return "鬼片360"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def localProxy(self, param):
        return None

    host = 'https://www.guipian360.org'

    classes_config = [
        {"type_id": "1", "type_name": "鬼片大全"},
        {"type_id": "6", "type_name": "大陆鬼片"},
        {"type_id": "9", "type_name": "港台鬼片"},
        {"type_id": "8", "type_name": "林正英鬼片"},
        {"type_id": "7", "type_name": "日韩鬼片"},
        {"type_id": "11", "type_name": "欧美鬼片"},
        {"type_id": "10", "type_name": "泰国鬼片"},
        {"type_id": "3", "type_name": "恐怖片"},
        {"type_id": "2", "type_name": "电视剧"}
    ]

    def _get(self, url):
        return self.session.get(url, timeout=15)

    def extract_videos(self, html):
        vod_list = []
        blocks = re.findall(r'<[^>]+class="[^"]*u-movie[^"]*"[\s\S]*?</(?:article|div|li)>', html)
        for block in blocks:
            href_m = re.search(r'href="([^"]+)"', block)
            title_m = re.search(r'title="([^"]+)"', block)
            if not title_m:
                title_m = re.search(r'alt="([^"]+)"', block)
            if not title_m:
                title_m = re.search(r'<h2>([^<]+)</h2>', block)
            pic_m = re.search(r'data-original="([^"]+)"', block)
            if not pic_m:
                pic_m = re.search(r'src="([^"]+)"', block)
            remark_m = re.search(r'class="zhuangtai"[^>]*>(?:<span>)?([^<]+)', block)

            if href_m and title_m:
                href = href_m.group(1)
                id_m = re.search(r'/(\d+)\.html', href)
                if not id_m:
                    continue
                vod_id = id_m.group(1)
                vod_name = title_m.group(1).split('/')[0].strip().replace('《', '').replace('》', '')
                pic = pic_m.group(1) if pic_m else ""
                if pic.startswith('/'):
                    pic = self.host + pic
                remarks = remark_m.group(1).strip() if remark_m else ""
                vod_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": pic,
                    "vod_remarks": remarks
                })
        return vod_list

    def homeContent(self, filter):
        html = self._get(self.host).text
        return {"class": self.classes_config, "list": self.extract_videos(html)}

    def homeVideoContent(self):
        html = self._get(self.host).text
        return {"list": self.extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page_num = int(pg) if str(pg).isdigit() else 1
        url = f"{self.host}/list/{tid}_{page_num}.html" if page_num > 1 else f"{self.host}/list/{tid}.html"
        html = self._get(url).text
        vlist = self.extract_videos(html)
        page_count = 99
        pg_m = re.search(r'href="/list/\d+_(\d+)\.html"[^>]*>\.\.', html)
        if pg_m:
            page_count = int(pg_m.group(1))
        return {"list": vlist, "page": page_num, "pagecount": page_count, "limit": 20, "total": 9999}

    def searchContent(self, key, quick, pg="1"):
        url = f"{self.host}/index.php?m=vod-search&wd={quote(key)}"
        html = self._get(url).text
        return {"list": self.extract_videos(html), "page": pg}

    def detailContent(self, ids):
        vod_id = ids[0]
        html = self._get(f"{self.host}/nv/{vod_id}.html").text
        soup = BeautifulSoup(html, 'html.parser')

        tabs = [a.text.strip() for a in soup.select('#tv_tab li a')]
        if not tabs:
            tabs = ["默认播放线路"]
        lists = soup.select('#tv_tab .list')
        play_urls = []
        for lst in lists:
            sub_urls = []
            for a in lst.select('ul.abc li a'):
                name = a.text.strip()
                href = a.get('href', '')
                vid_m = re.search(r'/play/(.*?)\.html', href)
                if vid_m:
                    sub_urls.append(f"{name}${vid_m.group(1)}")
            play_urls.append("#".join(sub_urls))
        if len(play_urls) < len(tabs):
            play_urls += [""] * (len(tabs) - len(play_urls))

        name_m = re.search(r'<h1[^>]*>(.*?)</h1>', html)
        vod_name = name_m.group(1).split('/')[0].strip().replace('《', '').replace('》', '') if name_m else ''
        if not vod_name:
            title_m = re.search(r'<title>(.*?)</title>', html)
            if title_m:
                vod_name = title_m.group(1).split('-')[0].strip().replace('《', '').replace('》', '')
        if not vod_name:
            vod_name = '未知影片'

        def get_meta(pattern, default=""):
            m = re.search(pattern, html)
            return m.group(1).strip() if m else default

        pic_m = re.search(r'<img[^>]+data-original="([^"]+)"', html)
        if not pic_m:
            pic_m = re.search(r'<img[^>]+src="([^"]+)"[^>]*class="lazy"', html)
        vod_pic = pic_m.group(1) if pic_m else ""
        if vod_pic.startswith('/'):
            vod_pic = self.host + vod_pic

        vod_content_m = re.search(r'<p class="jianjie-p"[^>]*>([\s\S]*?)</p>', html)
        vod_content = re.sub(r'<.*?>', '', vod_content_m.group(1)).strip() if vod_content_m else "暂无该影片的相关简介。"

        return {"list": [{
            "vod_id": vod_id, "vod_name": vod_name, "vod_pic": vod_pic, "vod_content": vod_content,
            "vod_director": get_meta(r'<span>导演：</span>(.*?)</li>', "未知"),
            "vod_actor": get_meta(r'<span>主演：</span>(.*?)</li>', "未知"),
            "vod_year": get_meta(r'<strong>(\d{4})年</strong>', "近期"),
            "vod_area": get_meta(r'地区：</span><a[^>]*>(.*?)</a>', "未知"),
            "vod_play_from": "$$$".join(tabs),
            "vod_play_url": "$$$".join(play_urls)
        }]}

    def playerContent(self, flag, id, vipFlags):
        play_url = f"{self.host}/play/{id}.html"
        html = self._get(play_url).text
        if 'var now="' not in html:
            play_url = f"{self.host}/play/{id}-0-0.html"
            html = self._get(play_url).text
        m3u8_m = re.search(r'var now="([^"]+)"', html)
        if m3u8_m:
            return {"parse": 0, "url": m3u8_m.group(1), "header": {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13)", "Referer": self.host + "/"}}
        return {"parse": 1, "url": play_url, "header": {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13)", "Referer": self.host + "/"}}
