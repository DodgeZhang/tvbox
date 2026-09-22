# coding=utf-8
# !/usr/bin/python
import sys
sys.path.append('..')
from base.spider import Spider
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import quote
import ssl
import urllib.request
ssl._create_default_https_context = ssl._create_unverified_context


class Spider(Spider):
    def getName(self):
        return "丧尸片大全"

    def init(self, extend=""):
        print("============{0}============".format(extend))
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _select_one(self, node, selector):
        """兼容旧版BeautifulSoup（无select_one方法）"""
        items = node.select(selector)
        return items[0] if items else None

    def homeContent(self, filter):
        result = {}
        classes = [
            {'type_name': '丧尸电影', 'type_id': '1'},
            {'type_name': '丧尸电视剧', 'type_id': '2'},
            {'type_name': '丧尸动漫', 'type_id': '3'}
        ]
        result['class'] = classes
        if filter:
            result['filters'] = self.config['filter']
        return result

    def homeVideoContent(self):
        result = {'list': []}
        try:
            url = self.host + '/sangshidianying/1-page1.html'
            html = self.fetchHtml(url)
            if html.startswith('<!--FETCH_ERROR:'):
                err = html.replace('<!--FETCH_ERROR:', '').replace('-->', '')
                result['list'] = [{
                    "vod_id": "",
                    "vod_name": "【网络错误】" + err[:30],
                    "vod_pic": "",
                    "vod_remarks": "请切换DNS或网络"
                }]
            else:
                result['list'] = self.get_list(html)
        except Exception as e:
            print("homeVideoContent error:", e)
            result['list'] = [{
                "vod_id": "",
                "vod_name": "【解析异常】" + str(e)[:30],
                "vod_pic": "",
                "vod_remarks": "请反馈给开发者"
            }]
        return result

    def categoryContent(self, tid, pg, filter, extend):
        result = {}
        tid = str(tid)
        pg = str(pg)

        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except Exception:
                extend = {}
        if not isinstance(extend, dict):
            extend = {}

        path_map = {
            '1': 'sangshidianying',
            '2': 'sangshidianshiju',
            '3': 'sangshidongman'
        }
        path = path_map.get(tid, 'sangshidianying')

        class_val = extend.get('class', '')
        area_val = extend.get('area', '')
        year_val = extend.get('year', '')

        if class_val or area_val or year_val:
            url = self.host + '/{0}/{1}-{2}--{3}---{4}--page{5}.html'.format(
                path, tid, class_val, year_val, area_val, pg)
        else:
            url = self.host + '/{0}/{1}-page{2}.html'.format(path, tid, pg)

        try:
            html = self.fetchHtml(url)
            if html.startswith('<!--FETCH_ERROR:'):
                err = html.replace('<!--FETCH_ERROR:', '').replace('-->', '')
                videos = [{
                    "vod_id": "",
                    "vod_name": "【网络错误】" + err[:30],
                    "vod_pic": "",
                    "vod_remarks": "请切换DNS或网络"
                }]
            else:
                videos = self.get_list(html)
        except Exception as e:
            print("categoryContent error:", e)
            videos = [{
                "vod_id": "",
                "vod_name": "【解析异常】" + str(e)[:30],
                "vod_pic": "",
                "vod_remarks": "请反馈给开发者"
            }]

        # 尝试从页面解析真实页数（纯正则，不依赖bs4）
        pagecount = 9999
        if not html.startswith('<!--FETCH_ERROR:'):
            try:
                m = re.search(r'(\d+)/(\d+)', html)
                if m:
                    pagecount = int(m.group(2))
                else:
                    m = re.search(r'共\D*(\d+)\D*部', html)
                    if m:
                        total = int(m.group(1))
                        pagecount = (total + 47) // 48
            except Exception:
                pass

        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = pagecount
        result['limit'] = 48
        result['total'] = pagecount * 48
        return result

    def detailContent(self, array):
        tid = str(array[0]) if array else ''
        url = self.host + tid
        try:
            html = self.fetchHtml(url)
        except Exception as e:
            print("detailContent fetch error:", e)
            return {'list': []}
        soup = BeautifulSoup(html, 'html.parser')

        # 标题 - 多种方式兼容
        title = ''
        title_tag = self._select_one(soup, 'h1.fed-part-eone a')
        if not title_tag:
            title_tag = self._select_one(soup, 'h1 a')
        if not title_tag:
            title_tag = self._select_one(soup, 'h1')
        if title_tag:
            title = title_tag.get_text(strip=True)

        # 封面 - 多种方式兼容
        pic = ''
        pic_tag = self._select_one(soup, '.fed-list-pics')
        if pic_tag:
            pic = pic_tag.get('data-original', '') or pic_tag.get('src', '')
        if not pic:
            pic_tag = self._select_one(soup, 'img.fed-img-responsive')
            if pic_tag:
                pic = pic_tag.get('data-original', '') or pic_tag.get('src', '')
        if not pic:
            pic_tag = self._select_one(soup, 'meta[property="og:image"]')
            if pic_tag:
                pic = pic_tag.get('content', '')

        # 详情信息
        info = {}
        for li in soup.select('li.fed-part-eone'):
            text = li.get_text(strip=True)
            if '主演：' in text:
                info['actor'] = text.replace('主演：', '')
            elif '导演：' in text:
                info['director'] = text.replace('导演：', '')
            elif '分类：' in text:
                info['type'] = text.replace('分类：', '')
            elif '地区：' in text:
                info['area'] = text.replace('地区：', '')
            elif '年份：' in text:
                info['year'] = text.replace('年份：', '')

        # 剧情介绍 - 多种方式兼容
        content_text = ''
        content_div = self._select_one(soup, 'div.fed-part-esan')
        if content_div:
            content_text = content_div.get_text(strip=True)
        if not content_text:
            content_div = self._select_one(soup, '#xiangxijieshao')
            if content_div:
                content_text = content_div.get_text(strip=True)
        if not content_text:
            for elem in soup.find_all(['div', 'p', 'span']):
                txt = elem.get_text(strip=True)
                if txt.startswith('剧情：') or txt.startswith('剧情介绍'):
                    content_text = txt
                    break
        if content_text:
            info['content'] = content_text.replace('剧情：', '').replace('剧情介绍', '').replace('详细介绍', '').strip()

        # 播放源
        play_from = []
        play_url = []

        play_data_list = soup.select('.fed-play-data')
        for source_div in play_data_list:
            source_name = ''
            btn = self._select_one(source_div, '.fed-tabs-btns')
            if btn:
                source_name = btn.get_text(strip=True)
            if not source_name:
                source_name = source_div.get('data-name', '')
            if not source_name:
                continue
            if source_name == '剧情介绍':
                continue

            # 获取剧集 - 多种选择器兼容
            episodes = []
            playlist = source_div.select('.stui-content__playlist li a')
            if not playlist:
                playlist = source_div.select('.fed-drop-boxs li a')
            if not playlist:
                playlist = source_div.select('ul li a')

            for link in playlist:
                ep_name = link.get_text(strip=True)
                ep_href = link.get('href', '')
                if ep_href and ep_name:
                    episodes.append('{0}${1}'.format(ep_name, ep_href))

            if not episodes:
                continue

            play_from.append(source_name)
            play_url.append('#'.join(episodes))

        vod = {
            "vod_id": tid,
            "vod_name": title,
            "vod_pic": pic,
            "type_name": info.get('type', ''),
            "vod_year": info.get('year', ''),
            "vod_area": info.get('area', ''),
            "vod_remarks": "",
            "vod_actor": info.get('actor', ''),
            "vod_director": info.get('director', ''),
            "vod_content": info.get('content', ''),
            "vod_play_from": '$$$'.join(play_from),
            "vod_play_url": '$$$'.join(play_url)
        }

        result = {'list': [vod]}
        return result

    def searchContent(self, key, quick, pg="1"):
        result = {'list': [], 'page': 1, 'pagecount': 1, 'limit': 48, 'total': 0}
        try:
            key = str(key)
            page = int(pg) if pg else 1
            encoded_key = quote(key, safe='')
            url = self.host + '/vod-search-wd-' + encoded_key + '-page' + str(page) + '.html'
            html = self.fetchHtml(url)
            if html.startswith('<!--FETCH_ERROR:'):
                err = html.replace('<!--FETCH_ERROR:', '').replace('-->', '')
                result['list'] = [{
                    "vod_id": "",
                    "vod_name": "【网络错误】" + err[:30],
                    "vod_pic": "",
                    "vod_remarks": "请切换DNS或网络"
                }]
            else:
                result['list'] = self.get_list(html)
            result['page'] = page
            result['pagecount'] = 9999
            result['limit'] = 48
            result['total'] = 999999
        except Exception as e:
            print("searchContent error:", e)
            result['list'] = [{
                "vod_id": "",
                "vod_name": "【解析异常】" + str(e)[:30],
                "vod_pic": "",
                "vod_remarks": "请反馈给开发者"
            }]
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        id = str(id)
        url = self.host + id
        try:
            html = self.fetchHtml(url)
        except Exception as e:
            print("playerContent fetch error:", e)
            result["parse"] = 1
            result["playUrl"] = ""
            result["url"] = url
            result["header"] = ""
            return result

        # 从script中提取视频地址 - 多种模式兼容
        m3u8 = ''
        patterns = [
            r'var\s+url\s*=\s*"([^"]+)"',
            r'var\s+videoUrl\s*=\s*"([^"]+)"',
            r'var\s+play_url\s*=\s*"([^"]+)"',
            r'var\s+src\s*=\s*"([^"]+)"',
            r'"url"\s*:\s*"([^"]+\.(?:m3u8|mp4)[^"]*)"',
            r'(https?://[^\s"]+\.(?:m3u8|mp4)[^\s"]*)',
        ]
        for pattern in patterns:
            m = re.search(pattern, html)
            if m:
                m3u8 = m.group(1)
                if m3u8:
                    break

        if m3u8:
            m3u8 = m3u8.replace('\\/', '/')

        jiekou = ''
        m = re.search(r'var\s+jiekou\s*=\s*"([^"]+)"', html)
        if m:
            jiekou = m.group(1)

        if m3u8:
            if m3u8.endswith('.m3u8') or m3u8.endswith('.mp4'):
                result["parse"] = 0
                result["playUrl"] = ""
                result["url"] = m3u8
                result["header"] = ""
            else:
                result["parse"] = 1
                result["playUrl"] = ""
                result["url"] = m3u8
                result["header"] = ""
        else:
            result["parse"] = 1
            result["playUrl"] = ""
            result["url"] = url
            result["header"] = ""

        return result

    def fetchHtml(self, url):
        html = ''
        err = ''
        # 第1步：正常域名请求
        try:
            req = urllib.request.Request(url=url, headers=self.header)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', 'ignore')
            if html:
                return html
        except Exception as e:
            err = str(e)
            print("fetchHtml domain error:", e)

        # 第2步：IP直连fallback（绕过DNS污染）
        try:
            ip_url = url.replace('www.sangshipian.com', '104.21.29.161')
            hdr = dict(self.header)
            hdr['Host'] = 'www.sangshipian.com'
            req = urllib.request.Request(url=ip_url, headers=hdr)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', 'ignore')
            if html:
                return html
        except Exception as e:
            print("fetchHtml ip fallback error:", e)

        # 返回带错误标记的空内容，方便上层诊断
        if err:
            return '<!--FETCH_ERROR:' + err + '-->'
        return ''

    def get_list(self, html):
        videos = []
        # 优先使用TVBox基类内置的html+xpath解析（像1905.py一样稳定）
        try:
            if hasattr(self, 'html'):
                root = self.html(html)
                liList = root.xpath("//li[contains(@class,'fed-list-item')]")
                for li in liList:
                    a_tags = li.xpath(".//a[contains(@class,'fed-list-title')]")
                    if not a_tags:
                        continue
                    a = a_tags[0]
                    title = ''.join(a.xpath('.//text()')).strip()
                    href = a.xpath('./@href')[0] if a.xpath('./@href') else ''

                    pic = ''
                    pic_tags = li.xpath(".//a[contains(@class,'fed-list-pics')]/@data-original")
                    if pic_tags:
                        pic = pic_tags[0]
                    if not pic:
                        pic_tags = li.xpath(".//a[contains(@class,'fed-list-pics')]/@src")
                        if pic_tags:
                            pic = pic_tags[0]

                    remark = ''
                    remark_tags = li.xpath(".//span[contains(@class,'fed-list-remarks')]//text()")
                    if remark_tags:
                        remark = remark_tags[0].strip()
                    if not remark:
                        score_tags = li.xpath(".//span[contains(@class,'fed-list-score')]//text()")
                        if score_tags:
                            remark = score_tags[0].strip()

                    if title and href:
                        videos.append({
                            "vod_id": href,
                            "vod_name": title,
                            "vod_pic": pic,
                            "vod_remarks": remark
                        })
                if videos:
                    return videos
        except Exception as e:
            print("html get_list error:", e)

        # fallback到BeautifulSoup
        try:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.select('ul.fed-list-info li')
            if not items:
                items = soup.select('li.fed-list-item')
            if not items:
                items = soup.select('.fed-list-item')
            for item in items:
                a = self._select_one(item, 'a.fed-list-title')
                if not a:
                    continue
                title = a.get_text(strip=True)
                href = a.get('href', '')
                pic = ''
                pic_tag = self._select_one(item, 'a.fed-list-pics')
                if pic_tag:
                    pic = pic_tag.get('data-original', '') or pic_tag.get('src', '')
                remark = ''
                remark_tag = self._select_one(item, '.fed-list-remarks')
                if remark_tag:
                    remark = remark_tag.get_text(strip=True)
                if not remark:
                    score_tag = self._select_one(item, '.fed-list-score')
                    if score_tag:
                        remark = score_tag.get_text(strip=True)
                videos.append({
                    "vod_id": href,
                    "vod_name": title,
                    "vod_pic": pic,
                    "vod_remarks": remark
                })
        except Exception as e:
            print("bs4 get_list error:", e)
        return videos

    config = {
        "filter": {
            "1": [
                {"key": "class", "name": "类型", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "喜剧", "v": "1"},
                    {"n": "爱情", "v": "2"},
                    {"n": "动作", "v": "3"},
                    {"n": "科幻", "v": "4"},
                    {"n": "恐怖", "v": "5"},
                    {"n": "战争", "v": "6"},
                    {"n": "惊悚", "v": "7"},
                    {"n": "犯罪", "v": "8"},
                    {"n": "悬疑", "v": "9"},
                    {"n": "奇幻", "v": "10"},
                    {"n": "冒险", "v": "11"},
                    {"n": "古装", "v": "12"},
                    {"n": "鬼怪", "v": "13"}
                ]},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "大陆", "v": "dalu"},
                    {"n": "美国", "v": "meiguo"},
                    {"n": "香港", "v": "xianggang"},
                    {"n": "台湾", "v": "taiwan"},
                    {"n": "韩国", "v": "hanguo"},
                    {"n": "日本", "v": "riben"},
                    {"n": "泰国", "v": "taiguo"},
                    {"n": "新加坡", "v": "xinjiapo"},
                    {"n": "马来西亚", "v": "malaixiya"},
                    {"n": "印度", "v": "yindu"},
                    {"n": "英国", "v": "yingguo"},
                    {"n": "法国", "v": "faguo"},
                    {"n": "加拿大", "v": "jianada"}
                ]},
                {"key": "year", "name": "年代", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "2026", "v": "2026"},
                    {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"},
                    {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"},
                    {"n": "2019", "v": "2019"},
                    {"n": "2018", "v": "2018"},
                    {"n": "2017", "v": "2017"},
                    {"n": "2016", "v": "2016"},
                    {"n": "2015", "v": "2015"},
                    {"n": "2014", "v": "2014"},
                    {"n": "1999-2009", "v": "1999,2009"},
                    {"n": "90年代", "v": "1990,1999"},
                    {"n": "80年代", "v": "1980,1989"},
                    {"n": "更早", "v": "1900,1980"}
                ]}
            ],
            "2": [
                {"key": "class", "name": "类型", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "喜剧", "v": "1"},
                    {"n": "爱情", "v": "2"},
                    {"n": "动作", "v": "3"},
                    {"n": "科幻", "v": "4"},
                    {"n": "恐怖", "v": "5"},
                    {"n": "战争", "v": "6"},
                    {"n": "惊悚", "v": "7"},
                    {"n": "犯罪", "v": "8"},
                    {"n": "悬疑", "v": "9"},
                    {"n": "奇幻", "v": "10"},
                    {"n": "冒险", "v": "11"},
                    {"n": "古装", "v": "12"},
                    {"n": "鬼怪", "v": "13"}
                ]},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "大陆", "v": "dalu"},
                    {"n": "美国", "v": "meiguo"},
                    {"n": "香港", "v": "xianggang"},
                    {"n": "台湾", "v": "taiwan"},
                    {"n": "韩国", "v": "hanguo"},
                    {"n": "日本", "v": "riben"},
                    {"n": "泰国", "v": "taiguo"},
                    {"n": "新加坡", "v": "xinjiapo"},
                    {"n": "马来西亚", "v": "malaixiya"},
                    {"n": "印度", "v": "yindu"},
                    {"n": "英国", "v": "yingguo"},
                    {"n": "法国", "v": "faguo"},
                    {"n": "加拿大", "v": "jianada"}
                ]},
                {"key": "year", "name": "年代", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "2026", "v": "2026"},
                    {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"},
                    {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"},
                    {"n": "2019", "v": "2019"},
                    {"n": "2018", "v": "2018"},
                    {"n": "2017", "v": "2017"},
                    {"n": "2016", "v": "2016"},
                    {"n": "2015", "v": "2015"},
                    {"n": "2014", "v": "2014"},
                    {"n": "1999-2009", "v": "1999,2009"},
                    {"n": "90年代", "v": "1990,1999"},
                    {"n": "80年代", "v": "1980,1989"},
                    {"n": "更早", "v": "1900,1980"}
                ]}
            ],
            "3": [
                {"key": "class", "name": "类型", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "喜剧", "v": "1"},
                    {"n": "爱情", "v": "2"},
                    {"n": "动作", "v": "3"},
                    {"n": "科幻", "v": "4"},
                    {"n": "恐怖", "v": "5"},
                    {"n": "战争", "v": "6"},
                    {"n": "惊悚", "v": "7"},
                    {"n": "犯罪", "v": "8"},
                    {"n": "悬疑", "v": "9"},
                    {"n": "奇幻", "v": "10"},
                    {"n": "冒险", "v": "11"},
                    {"n": "古装", "v": "12"},
                    {"n": "鬼怪", "v": "13"}
                ]},
                {"key": "area", "name": "地区", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "大陆", "v": "dalu"},
                    {"n": "美国", "v": "meiguo"},
                    {"n": "香港", "v": "xianggang"},
                    {"n": "台湾", "v": "taiwan"},
                    {"n": "韩国", "v": "hanguo"},
                    {"n": "日本", "v": "riben"},
                    {"n": "泰国", "v": "taiguo"},
                    {"n": "新加坡", "v": "xinjiapo"},
                    {"n": "马来西亚", "v": "malaixiya"},
                    {"n": "印度", "v": "yindu"},
                    {"n": "英国", "v": "yingguo"},
                    {"n": "法国", "v": "faguo"},
                    {"n": "加拿大", "v": "jianada"}
                ]},
                {"key": "year", "name": "年代", "value": [
                    {"n": "全部", "v": ""},
                    {"n": "2026", "v": "2026"},
                    {"n": "2025", "v": "2025"},
                    {"n": "2024", "v": "2024"},
                    {"n": "2023", "v": "2023"},
                    {"n": "2022", "v": "2022"},
                    {"n": "2021", "v": "2021"},
                    {"n": "2020", "v": "2020"},
                    {"n": "2019", "v": "2019"},
                    {"n": "2018", "v": "2018"},
                    {"n": "2017", "v": "2017"},
                    {"n": "2016", "v": "2016"},
                    {"n": "2015", "v": "2015"},
                    {"n": "2014", "v": "2014"},
                    {"n": "1999-2009", "v": "1999,2009"},
                    {"n": "90年代", "v": "1990,1999"},
                    {"n": "80年代", "v": "1980,1989"},
                    {"n": "更早", "v": "1900,1980"}
                ]}
            ]
        }
    }

    header = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Referer": "https://www.sangshipian.com/"
    }

    host = "http://api.uumnet.com/tvbox/api/proxyrequest.php?url=https://www.sangshipian.com"

    def localProxy(self, param):
        action = {
            'url': '',
            'header': '',
            'param': '',
            'type': 'string',
            'after': ''
        }
        return [200, "video/MP2T", action, ""]
