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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.guipianwu.com/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
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

    host = 'https://www.guipianwu.com'

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
        """适配 guipianwu.com 的 .video-item 结构"""
        vod_list = []
        soup = BeautifulSoup(html, 'html.parser')
        for item in soup.select('.video-item'):
            a_tag = item.select_one('a.video-link')
            if not a_tag:
                a_tag = item.select_one('a')
            if not a_tag:
                continue
            href = a_tag.get('href', '')
            title = a_tag.get('title', '')
            if not title:
                h2 = a_tag.select_one('.video-con-tit, h2')
                title = h2.get_text(strip=True) if h2 else ''
            id_m = re.search(r'/nv/(\d+)\.html', href)
            if not id_m or not title:
                continue
            vod_id = id_m.group(1)
            pic = ''
            pic_div = a_tag.select_one('.item-pic, .list-poster')
            if pic_div:
                pic = pic_div.get('data-original', '') or pic_div.get('data-background', '') or ''
            if not pic:
                img = a_tag.select_one('img')
                if img:
                    pic = img.get('data-original', '') or img.get('src', '') or ''
            if pic and pic.startswith('/'):
                pic = self.host + pic
            remark = ''
            dur = a_tag.select_one('.video-duration, .zhuangtai')
            if dur:
                remark = dur.get_text(strip=True)
            vod_list.append({
                "vod_id": vod_id,
                "vod_name": title.replace('《', '').replace('》', ''),
                "vod_pic": pic,
                "vod_remarks": remark
            })
        return vod_list

    def homeContent(self, filter):
        html = self._get(self.host).text
        vlist = self.extract_videos(html)
        return {
            "class": self.classes_config,
            "list": vlist
        }

    def homeVideoContent(self):
        html = self._get(self.host).text
        return {"list": self.extract_videos(html)}

    def categoryContent(self, tid, pg, filter, extend):
        page_num = int(pg) if str(pg).isdigit() else 1
        if page_num > 1:
            url = f"{self.host}/list/{tid}_{page_num}.html"
        else:
            url = f"{self.host}/list/{tid}.html"
        html = self._get(url).text
        vlist = self.extract_videos(html)
        page_count = 99
        pg_m = re.search(r'href="/list/\d+_(\d+)\.html"[^>]*>\.\.', html)
        if pg_m:
            page_count = int(pg_m.group(1))
        return {
            "list": vlist,
            "page": page_num,
            "pagecount": page_count,
            "limit": 20,
            "total": 9999
        }

    def searchContent(self, key, quick, pg="1"):
        url = f"{self.host}/index.php?m=vod-search&wd={quote(key)}"
        html = self._get(url).text
        return {"list": self.extract_videos(html), "page": pg}

    def detailContent(self, ids):
        vod_id = ids[0]
        html = self._get(f"{self.host}/nv/{vod_id}.html").text
        soup = BeautifulSoup(html, 'html.parser')

        tabs = []
        tab_els = soup.select('.player-from-box .swiper-slide')
        if not tab_els:
            tab_els = soup.select('#tv_tab li a')
        tabs = [el.get_text(strip=True) for el in tab_els if el.get_text(strip=True)]
        if not tabs:
            tabs = ["默认播放线路"]

        play_urls = []
        lists = soup.select('.ewave-playlist-content')
        if not lists:
            lists = soup.select('#tv_tab .list')
        for lst in lists:
            sub_urls = []
            links = lst.select('.ewave-playlist-sort-content a')
            if not links:
                links = lst.select('ul.abc li a')
            if not links:
                links = lst.select('a')
            for a in links:
                name = a.get_text(strip=True)
                href = a.get('href', '')
                vid_m = re.search(r'/play/(.*?)\.html', href)
                if vid_m:
                    sub_urls.append(f"{name}${vid_m.group(1)}")
            play_urls.append("#".join(sub_urls))
        if len(play_urls) < len(tabs):
            play_urls += [""] * (len(tabs) - len(play_urls))

        h1 = soup.select_one('h1')
        vod_name = h1.get_text(strip=True).split('/')[0].replace('《', '').replace('》', '') if h1 else ''
        if not vod_name:
            title_m = re.search(r'<title>(.*?)</title>', html)
            if title_m:
                vod_name = title_m.group(1).split('-')[0].strip().replace('《', '').replace('》', '')
        if not vod_name:
            vod_name = '未知影片'

        vod_pic = ''
        img = soup.select_one('.detail-img img, img[data-original]')
        if img:
            vod_pic = img.get('data-original', '') or img.get('src', '') or ''
        if vod_pic.startswith('/'):
            vod_pic = self.host + vod_pic

        vod_content = "暂无该影片的相关简介。"
        for li in soup.select('.desc li'):
            if '简介' in li.get_text():
                vod_content = li.get_text().replace('简介：', '').replace('简介:', '').strip()
                break

        def get_meta(label, default=""):
            for li in soup.select('.desc li'):
                txt = li.get_text()
                if label in txt:
                    m = re.search(rf'{label}\s*[：:]\s*(.*)', txt)
                    if m:
                        return m.group(1).strip()
            return default

        vod = {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_director": get_meta("导演", "未知"),
            "vod_actor": get_meta("主演", "未知"),
            "vod_year": get_meta("年份", "近期"),
            "vod_area": get_meta("地区", "未知"),
            "vod_play_from": "$$$".join(tabs),
            "vod_play_url": "$$$".join(play_urls)
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        play_url = f"{self.host}/play/{id}.html"
        html = self._get(play_url).text
        m3u8_m = re.search(r'var now="([^"]+)"', html)
        if m3u8_m:
            return {"parse": 0, "url": m3u8_m.group(1), "header": {"User-Agent": self.session.headers["User-Agent"], "Referer": self.host + "/"}}
        return {"parse": 1, "url": play_url, "header": {"User-Agent": self.session.headers["User-Agent"], "Referer": self.host + "/"}}
