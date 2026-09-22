# coding=utf-8
# !/usr/bin/python

"""

作者 丢丢喵推荐 🚓 内容均从互联网收集而来 仅供交流学习使用 版权归原创者所有 如侵犯了您的权益 请通知作者 将及时删除侵权内容
                    ====================Diudiumiao====================

"""

from Crypto.Util.Padding import unpad
from Crypto.Util.Padding import pad
from urllib.parse import unquote
from Crypto.Cipher import ARC4
from urllib.parse import quote
from base.spider import Spider
from Crypto.Cipher import AES
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64decode
import urllib.request
import urllib.parse
import datetime
import binascii
import requests
import hashlib
import base64
import json
import time
import sys
import re
import os

sys.path.append('..')

xurl = "https://api-store.qmplaylet.com"

xurl1 = "https://api-read.qmplaylet.com"

keys = "d3dGiJc651gSQ8w1"

data = {
        "static_score": "0.8",
        "uuid": "00000000-7fc7-08dc-0000-000000000000",
        "device-id": "20250220125449b9b8cac84c2dd3d035c9052a2572f7dd0122edde3cc42a70",
        "mac": "",
        "sourceuid": "aa7de295aad621a6",
        "refresh-type": "0",
        "model": "22021211RC",
        "wlb-imei": "",
        "client-id": "aa7de295aad621a6",
        "brand": "Redmi",
        "oaid": "",
        "oaid-no-cache": "",
        "sys-ver": "12",
        "trusted-id": "",
        "phone-level": "H",
        "imei": "",
        "wlb-uid": "aa7de295aad621a6",
        "session-id": str(int(time.time() * 1000)),
        }

json_str = json.dumps(data, separators=(',', ':'))
encoded = base64.b64encode(json_str.encode()).decode()

char_map = {
        '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E', '4': 'r',
        '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J', 'A': '9', 'B': 's',
        'C': 'a', 'D': 'I', 'E': '0', 'F': 'o', 'G': 'y', 'H': '_', 'I': 'H',
        'J': 'G', 'K': 'i', 'L': 't', 'M': 'g', 'N': 'N', 'O': 'A', 'P': '8',
        'Q': 'F', 'R': 'k', 'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q',
        'X': 'C', 'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u',
        'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T', 'k': '-',
        'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1', 'q': 'V', 'r': 'v',
        's': 'j', 't': 'Q', 'u': '7', 'v': 'D', 'w': 'w', 'x': 'n', 'y': 'L',
        'z': 'e'
           }

qm_params = ''
for c in encoded:
    qm_params += char_map.get(c, c)

params_str = (
    "AUTHORIZATION=" +
    "app-version=10001" +
    "application-id=com.duoduo.read" +
    "channel=unknown" +
    "is-white=" +
    "net-env=5" +
    "platform=android" +
    f"qm-params={qm_params}" +
    f"reg={keys}"
             )

signs = hashlib.md5(params_str.encode()).hexdigest()

headerx = {
    'net-env': '5',
    'reg': '',
    'channel': 'unknown',
    'is-white': '',
    'platform': 'android',
    'application-id': 'com.duoduo.read',
    'authorization': '',
    'app-version': '10001',
    'user-agent': 'webviewversion/0',
    'qm-params': qm_params,
    'sign': signs
          }

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'
          }

# 全局变量用于缓存百度跳转信息
baidu_name_cache = ""
baidu_jump_cache = ""

class Spider(Spider):
    global xurl
    global xurl1
    global keys
    global headerx
    global headers
    global baidu_name_cache
    global baidu_jump_cache

    def getName(self):
        return "首页"

    def init(self, extend):
        global baidu_name_cache, baidu_jump_cache
        # 初始化时获取百度跳转信息并缓存
        try:
            response = requests.get(url='https://m.baidu.com/', headers=headers, timeout=5)
            response.encoding = 'utf-8'
            code = response.text
            baidu_name_cache = self.extract_middle_text(code, "s1='", "'", 0)
            baidu_jump_cache = self.extract_middle_text(code, "s2='", "'", 0)
        except:
            baidu_name_cache = ""
            baidu_jump_cache = ""

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def extract_middle_text(self, text, start_str, end_str, pl, start_index1: str = '', end_index2: str = ''):
        if pl == 3:
            plx = []
            while True:
                start_index = text.find(start_str)
                if start_index == -1:
                    break
                end_index = text.find(end_str, start_index + len(start_str))
                if end_index == -1:
                    break
                middle_text = text[start_index + len(start_str):end_index]
                plx.append(middle_text)
                text = text.replace(start_str + middle_text + end_str, '')
            if len(plx) > 0:
                purl = ''
                for i in range(len(plx)):
                    matches = re.findall(start_index1, plx[i])
                    output = ""
                    for match in matches:
                        match3 = re.search(r'(?:^|[^0-9])(\d+)(?:[^0-9]|$)', match[1])
                        if match3:
                            number = match3.group(1)
                        else:
                            number = 0
                        if 'http' not in match[0]:
                            output += f"#{match[1]}${number}{xurl}{match[0]}"
                        else:
                            output += f"#{match[1]}${number}{match[0]}"
                    output = output[1:]
                    purl = purl + output + "$$$"
                purl = purl[:-3]
                return purl
            else:
                return ""
        else:
            start_index = text.find(start_str)
            if start_index == -1:
                return ""
            end_index = text.find(end_str, start_index + len(start_str))
            if end_index == -1:
                return ""

        if pl == 0:
            middle_text = text[start_index + len(start_str):end_index]
            return middle_text.replace("\\", "")

        if pl == 1:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                jg = ' '.join(matches)
                return jg

        if pl == 2:
            middle_text = text[start_index + len(start_str):end_index]
            matches = re.findall(start_index1, middle_text)
            if matches:
                new_list = [f'{item}' for item in matches]
                jg = '$$$'.join(new_list)
                return jg

    def homeContent(self, filter):
        result = {"class": []}

        sign_string = f"operation=1playlet_privacy=1tag_id=0{keys}"
        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()

        url = f"{xurl}/api/v1/playlet/index?tag_id=0&playlet_privacy=1&operation=1&sign={sign}"
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        duoxuan = ['0', '1', '2', '3', '4']
        for duo in duoxuan:
            js = data['data']['tag_categories'][int(duo)]['tags']

            for vod in js:

                name = vod['tag_name']
                if "推荐" in name:
                    continue

                id = vod['tag_id']

                result["class"].append({"type_id": id, "type_name": "" + name})

        return result

    def homeVideoContent(self):
        videos = []

        sign_string = f"operation=1playlet_privacy=1tag_id=0{keys}"
        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()

        url = f"{xurl}/api/v1/playlet/index?tag_id=0&playlet_privacy=1&operation=1&sign={sign}"
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        data = data['data']['list']

        for vod in data:

            # 获取标题，确保不为空
            name = vod.get('title', '')
            if not name:
                name = vod.get('name', '未知标题')
            name = str(name).strip()

            # 获取ID
            id = vod.get('playlet_id', '')
            if not id:
                id = vod.get('id', '')

            # 获取封面
            pic = vod.get('image_link', '')
            if not pic:
                pic = vod.get('cover', '')

            # 获取热度值作为备注
            remark = vod.get('hot_value', '')
            if not remark:
                remark = vod.get('view_count', '')

            video = {
                "vod_id": str(id),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": str(remark) if remark else ''
                    }
            videos.append(video)

        result = {'list': videos}
        return result

    def categoryContent(self, cid, pg, filter, ext):
        result = {}
        videos = []

        if pg:
            page = int(pg)
        else:
            page = 1

        if page == 1:
            sign_string = f"operation=1playlet_privacy=1tag_id={cid}{keys}"
            sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
            url = f'{xurl}/api/v1/playlet/index?tag_id={cid}&playlet_privacy=1&operation=1&sign={sign}'

        else:
            sign_string = f"next_id={str(page)}operation=1playlet_privacy=1tag_id={cid}{keys}"
            sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
            url = f'{xurl}/api/v1/playlet/index?tag_id={cid}&next_id={str(page)}&playlet_privacy=1&operation=1&sign={sign}'

        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        data = detail.json()

        data = data['data']['list']

        for vod in data:

            name = vod.get('title', '')
            if not name:
                name = vod.get('name', '未知标题')
            name = str(name).strip()

            id = vod.get('playlet_id', '')
            if not id:
                id = vod.get('id', '')

            pic = vod.get('image_link', '')
            if not pic:
                pic = vod.get('cover', '')

            remark = vod.get('hot_value', '')
            if not remark:
                remark = vod.get('view_count', '')

            video = {
                "vod_id": str(id),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": str(remark) if remark else ''
                    }
            videos.append(video)

        result = {'list': videos}
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def detailContent(self, ids):
        did = ids[0]
        result = {}
        videos = []
        xianlu = '七猫专线'  # 统一使用七猫专线
        bofang = ''

        sign_string = f"playlet_id={did}{keys}"
        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()

        urls = f'{xurl1}/player/api/v1/playlet/info?playlet_id={did}&sign={sign}'
        detail = requests.get(url=urls, headers=headerx)
        detail.encoding = "utf-8"
        detail = detail.json()

        # 获取标题（使用API返回的标题）
        title = detail.get('data', {}).get('title', '')
        if not title:
            title = detail.get('data', {}).get('name', '未知标题')

        blurb = detail.get('data', {}).get('intro') or "暂无剧情简介"
        content = '剧情📢' + str(blurb)

        jisu = detail.get('data', {}).get('total_episode_num', '未知')
        jisu = str(jisu) + '全集'

        leixing = detail.get('data', {}).get('tags', '未知')

        remarks = str(leixing) + " " + str(jisu)

        # 使用七猫的播放列表
        soup = detail.get('data', {}).get('play_list', [])

        if soup:
            for sou in soup:
                video_url = sou.get('video_url', '')
                sort_name = sou.get('sort', '')
                if video_url and sort_name:
                    bofang = bofang + str(sort_name) + '$' + str(video_url) + '#'
            bofang = bofang[:-1] if bofang else ''
        else:
            # 如果没有播放列表，使用跳转链接
            global baidu_jump_cache
            bofang = baidu_jump_cache

        videos.append({
            "vod_id": str(did),
            "vod_name": str(title),
            "vod_remarks": remarks,
            "vod_content": content,
            "vod_play_from": xianlu,
            "vod_play_url": bofang
                     })

        result['list'] = videos
        return result

    def playerContent(self, flag, id, vipFlags):
        result = {}
        play_url = ""

        # 获取百度跳转信息（使用缓存）
        global baidu_jump_cache
        baidu_jump = baidu_jump_cache

        # 判断是否是外部跳转链接（百度等）
        if 'baidu.com' in str(id) or 'tuios.com' in str(id) or 'qmplaylet' in str(id):
            # 如果是外部跳转链接，直接使用
            play_url = str(id)
        # 判断是否是直接的HTTP链接
        elif str(id).startswith('http'):
            play_url = str(id)
        # 如果是内部播放ID，需要重新获取详情
        else:
            try:
                # 获取该ID对应的详情信息
                sign_string = f"playlet_id={id}{keys}"
                sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
                detail_url = f'{xurl1}/player/api/v1/playlet/info?playlet_id={id}&sign={sign}'
                detail_response = requests.get(url=detail_url, headers=headerx, timeout=5)
                detail_response.encoding = "utf-8"
                detail_data = detail_response.json()

                # 获取标题
                title = detail_data.get('data', {}).get('title', '')
                if not title:
                    title = detail_data.get('data', {}).get('name', '')

                # 统一使用七猫专线的播放列表
                play_list = detail_data.get('data', {}).get('play_list', [])

                if play_list:
                    for idx, item in enumerate(play_list):
                        video_url = item.get('video_url', '')
                        sort_name = item.get('sort', '')
                        if video_url and sort_name:
                            if play_url:
                                play_url += '#'
                            play_url += str(sort_name) + '$' + str(video_url)
                else:
                    # 如果没有play_list，使用原始ID
                    play_url = str(id)

            except Exception as e:
                # 如果出错，使用跳转链接或原始ID
                play_url = baidu_jump if baidu_jump else str(id)

        result["parse"] = 0
        result["playUrl"] = ''
        result["url"] = play_url if play_url else str(id)
        result["header"] = headers

        return result

    def searchContentPage(self, key, quick, pg):
        result = {}
        videos = []

        if pg:
            page = int(pg)
        else:
            page = 1

        sign_string = f"extend=page={str(page)}read_preference=0track_id=ec1280db127955061754851657967wd={key}{keys}"
        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()

        url = f'{xurl}/api/v1/playlet/search?extend=&page={str(page)}&wd={key}&read_preference=0&track_id=ec1280db127955061754851657967&sign={sign}'
        detail = requests.get(url=url, headers=headerx)
        detail.encoding = "utf-8"
        detail = detail.json()

        data = detail['data']['list']

        for vod in data:

            name = vod.get('title', '')
            if not name:
                name = vod.get('name', '未知标题')
            name = re.sub(r'<[^>]+>', '', str(name))
            name = ' '.join(name.split())

            id = vod.get('id', '')

            pic = vod.get('image_link', '')
            if not pic:
                pic = vod.get('cover', '')

            remark = vod.get('total_num', '')

            video = {
                "vod_id": str(id),
                "vod_name": name,
                "vod_pic": pic,
                "vod_remarks": str(remark) if remark else ''
                    }
            videos.append(video)

        result['list'] = videos
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 90
        result['total'] = 999999
        return result

    def searchContent(self, key, quick, pg="1"):
        return self.searchContentPage(key, quick, '1')

    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None