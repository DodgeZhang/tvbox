# coding = utf-8
# !/usr/bin/python

"""
来自作者千城-爱折腾三合一爬虫 整合七星、七猫、好看三个平台短剧内容均从互联网收集而来 仅供交流学习使用
"""

from Crypto.Util.Padding import unpad
from Crypto.Util.Padding import pad
from urllib.parse import unquote, urlparse, parse_qs, urlencode, urlunparse
from Crypto.Cipher import ARC4
from urllib.parse import quote
from base.spider import Spider
from Crypto.Cipher import AES
from datetime import datetime
from bs4 import BeautifulSoup
from base64 import b64decode
import concurrent.futures
import urllib.request
import urllib.parse
import datetime
import binascii
import requests
import hashlib
import base64
import json
import time
import uuid
import sys
import re
import os

sys.path.append('..')

# ==================== 七星平台配置 ====================
QX_BASE_URL = "https://app.whjzjx.cn"
QX_HEADERS = {
    'User-Agent': 'Linux; Android 12; Pixel 3 XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.101 Mobile Safari/537.36'
}
QX_HEADERF = {
    "platform": "1",
    "user_agent": "Mozilla/5.0 (Linux; Android 9; V1938T Build/PQ3A.190705.08211809; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Safari/537.36",
    "content-type": "application/json; charset=utf-8"
}
QX_AES_KEY = "B@ecf920Od8A4df7"

# ==================== 七猫平台配置 ====================
QM_BASE_URL = "https://api-store.qmplaylet.com"
QM_BASE_URL2 = "https://api-read.qmplaylet.com"
QM_KEYS = "d3dGiJc651gSQ8w1"
QM_DATA = {
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
    "session-id": None
}
QM_CHAR_MAP = {
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

# ==================== 好看平台配置 ====================
HK_BASE_URL = "https://sv.baidu.com"
HK_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; U; Android 8.0.0; zh-cn; Mi Note 2 Build/OPR1.170623.032) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/61.0.3163.128 Mobile Safari/537.36'
}
HK_ORIGINAL_URL_TEMPLATE = "https://sv.baidu.com/appui/api?cmd=video/commonlist&log=vhk&tn=1043677m&ctn=1043677m&blur=1&mac=&imei=AL5fB&cuid=B8B02D397EF5A5D8675FF92CDEDB833B%7C0&iid=A50-GZSWENRQHEZWMLJUHFSTALJUMYZDCLLBHEYWGLLCGZTDGNZQGBRGCOJQGE-OUABVLNI&c3_aid=A00-GGDKZORUQAP5GY6JC5BBPXTPVNC74IIA-V5QNYZSV&os=android&osbranch=a0&ua=900_1600_240&ut=V1938T_9_28_vivo&uh=vivo,qcom,V1938T&apiv=7.93.0.18&appv=793001&version=7.93.0.18&life=1773081846&clife=1773081846&nlife=1773081808&hid=empty&imsi=0&user_live_rec_source=yy,baijiahao,bjh_client,pc_client,bd_client&app_cpu_abi=64&device_prefer_abi=64&is_fold_screen=0&is_tablet=0&player_params=%7B%22ps%22:-1%7D&androidId=ec1280db12795506&zid=UW60kbyg6UiIf3uhVai1IDx_sCpGqcu19NSBuVuST5hB1Ho3bCpDReYbYo3zw3ZVdgFFLm7bHyMC7Kis_fOMAnA&network=1&sids=265_2-999990_2-999991_2-999989_2-999992_2-999988_2-999993_2-999999_72-123_2&young_mode=0&oaid=&honor_oaid=&nu=1&score=0.4330356&network5g=1&mpv=1&before_agree_sids=user_growth_15&fvt=1773081342&cp_isbg=0&is_playlet=1"


class Spider(Spider):
    """三合一爬虫主类"""
    
    def __init__(self):
        super().__init__()
        self.qx_authorization = None
        self.qm_headers = None
        self._init_all()
    
    def _init_all(self):
        self._init_qixing()
        self._init_qimao()
    
    def _init_qixing(self):
        try:
            times = int(time.time() * 1000)
            data = {
                "device": "2a50580e69d38388c94c93605241fb306",
                "package_name": "com.jz.xydj",
                "android_id": "ec1280db12795506",
                "install_first_open": True,
                "first_install_time": 1752505243345,
                "last_update_time": 1752505243345,
                "report_link_url": "",
                "authorization": "",
                "timestamp": times
            }
            plain_text = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
            key_bytes = QX_AES_KEY.encode('utf-8')
            plain_bytes = plain_text.encode('utf-8')
            cipher = AES.new(key_bytes, AES.MODE_ECB)
            padded_data = pad(plain_bytes, AES.block_size)
            ciphertext = cipher.encrypt(padded_data)
            encrypted = base64.b64encode(ciphertext).decode('utf-8')
            
            response = requests.post("https://u.shytkjgs.com/user/v3/account/login", 
                                    headers=QX_HEADERF, data=encrypted, timeout=10)
            if response.status_code == 200:
                response_data = response.json()
                if 'data' in response_data and 'token' in response_data['data']:
                    self.qx_authorization = response_data['data']['token']
        except:
            self.qx_authorization = None
    
    def _init_qimao(self):
        try:
            QM_DATA["session-id"] = str(int(time.time() * 1000))
            json_str = json.dumps(QM_DATA, separators=(',', ':'))
            encoded = base64.b64encode(json_str.encode()).decode()
            
            qm_params = ''
            for c in encoded:
                qm_params += QM_CHAR_MAP.get(c, c)
            
            params_str = (
                "AUTHORIZATION=" +
                "app-version=10001" +
                "application-id=com.duoduo.read" +
                "channel=unknown" +
                "is-white=" +
                "net-env=5" +
                "platform=android" +
                f"qm-params={qm_params}" +
                f"reg={QM_KEYS}"
            )
            signs = hashlib.md5(params_str.encode()).hexdigest()
            
            self.qm_headers = {
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
        except:
            self.qm_headers = None
    
    def getName(self):
        return "三合一爬虫"
    
    def init(self, extend):
        pass
    
    def isVideoFormat(self, url):
        pass
    
    def manualVideoCheck(self):
        pass
    
    def homeContent(self, filter):
        classes = []
        
        classes.extend([
            {"type_id": "qx_1", "type_name": "七星-剧场"},
            {"type_id": "qx_3", "type_name": "七星-新剧"},
            {"type_id": "qx_2", "type_name": "七星-热播"},
            {"type_id": "qx_7", "type_name": "七星-星选"},
            {"type_id": "qx_5", "type_name": "七星-阳光"}
        ])
        
        if self.qm_headers:
            try:
                sign_string = f"operation=1playlet_privacy=1tag_id=0{QM_KEYS}"
                sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
                url = f"{QM_BASE_URL}/api/v1/playlet/index?tag_id=0&playlet_privacy=1&operation=1&sign={sign}"
                detail = requests.get(url=url, headers=self.qm_headers, timeout=10)
                if detail.status_code == 200:
                    data = detail.json()
                    duoxuan = ['0', '1', '2', '3', '4']
                    for duo in duoxuan:
                        if int(duo) < len(data['data']['tag_categories']):
                            js = data['data']['tag_categories'][int(duo)]['tags']
                            for vod in js:
                                name = vod['tag_name']
                                if "推荐" not in name:
                                    classes.append({
                                        "type_id": f"qm_{vod['tag_id']}",
                                        "type_name": f"七猫-{name}"
                                    })
            except:
                pass
        
        try:
            payload = {"data": json.dumps({"from": "feed"})}
            urlz = f'{HK_BASE_URL}/haokan/ui-feed/playletShelfFeed'
            response = requests.post(url=urlz, headers=HK_HEADERS, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for vod in data['data']['playlet_tags']:
                    classes.append({
                        "type_id": f"hk_{vod['tag_id']}",
                        "type_name": f"好看-{vod['name']}"
                    })
                classes.append({"type_id": "hk_2", "type_name": "好看-新剧"})
        except:
            pass
        
        return {"class": classes}
    
    def homeVideoContent(self):
        videos = []
        
        if self.qx_authorization:
            try:
                headers = {'authorization': self.qx_authorization, 'platform': '1', 'version_name': '3.8.3.1'}
                url = f'{QX_BASE_URL}/v1/theater/home_page?theater_class_id=1&class2_id=4&page_num=1&page_size=12'
                detail = requests.get(url=url, headers=headers, timeout=10)
                if detail.status_code == 200:
                    data = detail.json()
                    for vod in data['data']['list']:
                        videos.append({
                            "vod_id": f"qx_{vod['theater']['id']}",
                            "vod_name": vod['theater']['title'],
                            "vod_pic": vod['theater']['cover_url'],
                            "vod_remarks": vod['theater'].get('play_amount_str', '七星热播')
                        })
            except:
                pass
        
        if self.qm_headers:
            try:
                sign_string = f"operation=1playlet_privacy=1tag_id=0{QM_KEYS}"
                sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
                url = f"{QM_BASE_URL}/api/v1/playlet/index?tag_id=0&playlet_privacy=1&operation=1&sign={sign}"
                detail = requests.get(url=url, headers=self.qm_headers, timeout=10)
                if detail.status_code == 200:
                    data = detail.json()
                    for vod in data['data']['list'][:12]:
                        videos.append({
                            "vod_id": f"qm_{vod['playlet_id']}",
                            "vod_name": vod['title'],
                            "vod_pic": vod['image_link'],
                            "vod_remarks": vod.get('hot_value', '七猫热播')
                        })
            except:
                pass
        
        return {'list': videos}
    
    def categoryContent(self, cid, pg, filter, ext):
        videos = []
        
        if cid.startswith('qx_'):
            real_cid = cid.replace('qx_', '')
            if self.qx_authorization:
                try:
                    headers = {'authorization': self.qx_authorization, 'platform': '1', 'version_name': '3.8.3.1'}
                    url = f'{QX_BASE_URL}/v1/theater/home_page?theater_class_id={real_cid}&page_num={pg}&page_size=24'
                    detail = requests.get(url=url, headers=headers, timeout=10)
                    if detail.status_code == 200:
                        data = detail.json()
                        for vod in data['data']['list']:
                            videos.append({
                                "vod_id": f"qx_{vod['theater']['id']}",
                                "vod_name": vod['theater']['title'],
                                "vod_pic": vod['theater']['cover_url'],
                                "vod_remarks": vod['theater'].get('theme', '七星')
                            })
                except:
                    pass
        
        elif cid.startswith('qm_'):
            real_cid = cid.replace('qm_', '')
            if self.qm_headers:
                try:
                    page = int(pg) if pg else 1
                    if page == 1:
                        sign_string = f"operation=1playlet_privacy=1tag_id={real_cid}{QM_KEYS}"
                        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
                        url = f'{QM_BASE_URL}/api/v1/playlet/index?tag_id={real_cid}&playlet_privacy=1&operation=1&sign={sign}'
                    else:
                        sign_string = f"next_id={str(page)}operation=1playlet_privacy=1tag_id={real_cid}{QM_KEYS}"
                        sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
                        url = f'{QM_BASE_URL}/api/v1/playlet/index?tag_id={real_cid}&next_id={str(page)}&playlet_privacy=1&operation=1&sign={sign}'
                    
                    detail = requests.get(url=url, headers=self.qm_headers, timeout=10)
                    if detail.status_code == 200:
                        data = detail.json()
                        for vod in data['data']['list']:
                            videos.append({
                                "vod_id": f"qm_{vod['playlet_id']}",
                                "vod_name": vod['title'],
                                "vod_pic": vod['image_link'],
                                "vod_remarks": vod.get('hot_value', '七猫')
                            })
                except:
                    pass
        
        elif cid.startswith('hk_'):
            real_cid = cid.replace('hk_', '')
            try:
                payload = {"tag_id": real_cid, "pn": int(pg), "rn": 24}
                urlz = f'{HK_BASE_URL}/haokan/ui-feed/playletTagsFeed'
                response = requests.post(url=urlz, headers=HK_HEADERS, data=payload, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for vod in data['data']['list']:
                        videos.append({
                            "vod_id": f"hk_{vod['playlet_id']}",
                            "vod_name": vod['playlet_title'],
                            "vod_pic": vod['playlet_poster'],
                            "vod_remarks": vod.get('episodes_num_text', '好看')
                        })
            except:
                pass
        
        return {
            'list': videos,
            'page': pg,
            'pagecount': 9999,
            'limit': 90,
            'total': 999999
        }
    
    def detailContent(self, ids):
        did = ids[0]
        videos = []
        
        if did.startswith('qx_'):
            real_did = did.replace('qx_', '')
            result = self._get_qixing_detail(real_did)
            if result:
                videos.append(result)
        
        elif did.startswith('qm_'):
            real_did = did.replace('qm_', '')
            result = self._get_qimao_detail(real_did)
            if result:
                videos.append(result)
        
        elif did.startswith('hk_'):
            real_did = did.replace('hk_', '')
            result = self._get_haokan_detail(real_did)
            if result:
                videos.append(result)
        
        return {'list': videos}
    
    def _get_qixing_detail(self, did):
        try:
            headers = {'authorization': self.qx_authorization, 'platform': '1', 'version_name': '3.8.3.1'}
            url = f'{QX_BASE_URL}/v2/theater_parent/detail?theater_parent_id={did}'
            detail = requests.get(url=url, headers=headers, timeout=10)
            
            if detail.status_code == 200:
                data = detail.json()
                content = '千城-爱折腾剧情：' + data['data'].get('introduction', '暂无剧情')
                area = data['data'].get('desc_tags', ['未知'])[0]
                remarks = data['data'].get('filing', '未知')
                
                bofang = ''
                if 'theaters' in data['data'] and data['data']['theaters']:
                    for sou in data['data']['theaters']:
                        vid = sou['son_video_url']
                        name = sou['num']
                        bofang = bofang + str(name) + '$' + vid + '#'
                    bofang = bofang[:-1] if bofang.endswith('#') else bofang
                    xianlu = '七星线路'
                else:
                    if 'video_url' in data['data'] and data['data']['video_url']:
                        bofang = '1$' + data['data']['video_url']
                        xianlu = '七星线路'
                    else:
                        bofang = ''
                        xianlu = '七星线路'
                
                return {
                    "vod_id": did,
                    "vod_content": content,
                    "vod_remarks": remarks,
                    "vod_area": area,
                    "vod_play_from": xianlu,
                    "vod_play_url": bofang
                }
        except:
            pass
        return None
    
    def _get_qimao_detail(self, did):
        if not self.qm_headers:
            return None
        
        try:
            sign_string = f"playlet_id={did}{QM_KEYS}"
            sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
            urls = f'{QM_BASE_URL2}/player/api/v1/playlet/info?playlet_id={did}&sign={sign}'
            detail = requests.get(url=urls, headers=self.qm_headers, timeout=10)
            
            if detail.status_code == 200:
                detail_data = detail.json()
                blurb = detail_data.get('data', {}).get('intro') or "未知"
                content = '千城-爱折腾剧情介绍：' + blurb
                jisu = detail_data['data'].get('total_episode_num', "未知")
                jisu = str(jisu) + '全集'
                leixing = detail_data['data'].get('tags', "未知")
                remarks = leixing + " " + jisu
                
                bofang = ''
                if 'play_list' in detail_data['data'] and detail_data['data']['play_list']:
                    for sou in detail_data['data']['play_list']:
                        vid = sou['video_url']
                        name = sou['sort']
                        bofang = bofang + name + '$' + vid + '#'
                    bofang = bofang[:-1]
                    xianlu = '七猫线路'
                else:
                    bofang = ''
                    xianlu = '七猫线路'
                
                return {
                    "vod_id": did,
                    "vod_remarks": remarks,
                    "vod_content": content,
                    "vod_play_from": xianlu,
                    "vod_play_url": bofang
                }
        except:
            pass
        return None
    
    def _get_haokan_detail(self, did):
        try:
            all_episodes = self._get_haokan_episodes(did)
            bofang = ''
            for video_data in all_episodes:
                if 'content' in video_data and 'title' in video_data['content']:
                    name = video_data['content']['title']
                    clarity_urls = video_data['content'].get('clarityUrl', [])
                    if clarity_urls:
                        if len(clarity_urls) > 2:
                            vid = clarity_urls[2]['url']
                        elif len(clarity_urls) > 1:
                            vid = clarity_urls[1]['url']
                        else:
                            vid = clarity_urls[0]['url']
                        bofang = bofang + name + "$" + vid + "#"
            
            bofang = bofang[:-1] if bofang.endswith('#') else bofang
            
            return {
                "vod_id": did,
                "vod_play_from": "好看线路",
                "vod_play_url": bofang,
                "vod_content": "千城-爱折腾",
                "vod_remarks": "好看专线"
            }
        except:
            pass
        return None
    
    def _get_haokan_episodes(self, series_id):
        episodes = []
        try:
            parsed_url = urlparse(HK_ORIGINAL_URL_TEMPLATE)
            query_params = {k: v[0] for k, v in parse_qs(parsed_url.query, keep_blank_values=True).items()}
            
            query_params['cuid'] = uuid.uuid4().hex.upper()[:32] + "%7C0"
            query_params['androidId'] = uuid.uuid4().hex[:16]
            query_params['zid'] = uuid.uuid4().hex
            
            cleaned_url = urlunparse(parsed_url._replace(query=urlencode(query_params, doseq=True)))
            
            current_timestamp = str(int(time.time() * 1000))
            inner_params = {
                "source_from": "kanju_shelf_playlet",
                "enable_enter_playlet": "0",
                "seek_time": "0",
                "hotspot": "0",
                "page_value": "playlet",
                "auto_show_hot_point_panel": "0",
                "type": "playlet",
                "commonlist_id": current_timestamp,
                "scene": "",
                "vid": "",
                "enable_atlas": "0",
                "mark_pn": "",
                "uk": "",
                "ctime": "0",
                "from": "playlet_talos",
                "id": series_id,
                "rn": "50",
                "pn": "1",
                "direction": "3"
            }
            payload = {"video/commonlist": "&".join([f"{k}={v}" for k, v in inner_params.items()])}
            
            response = requests.post(cleaned_url, data=payload, headers=HK_HEADERS, timeout=10)
            if response.status_code == 200:
                response_json = response.json()
                data_section = response_json.get('video/commonlist', {}).get('data', {})
                episodes = data_section.get('list', data_section.get('results', []))
        except:
            pass
        return episodes
    
    def playerContent(self, flag, id, vipFlags):
        result = {
            "parse": 0,
            "playUrl": '',
            "url": id,
            "header": {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; Pixel 3 XL) AppleWebKit/537.36'
            }
        }
        return result
    
    def searchContent(self, key, quick, pg="1"):
        videos = []
        
        if self.qx_authorization:
            try:
                headers = {'authorization': self.qx_authorization, 'platform': '1', 'version_name': '3.8.3.1'}
                payload = {"text": key}
                url = f"{QX_BASE_URL}/v3/search"
                detail = requests.post(url=url, headers=headers, json=payload, timeout=10)
                if detail.status_code == 200:
                    data = detail.json()
                    for vod in data['data']['theater']['search_data']:
                        videos.append({
                            "vod_id": f"qx_{vod['id']}",
                            "vod_name": vod['title'],
                            "vod_pic": vod['cover_url'],
                            "vod_remarks": vod.get('score_str', '七星')
                        })
            except:
                pass
        
        if self.qm_headers:
            try:
                page = int(pg)
                sign_string = f"extend=page={str(page)}read_preference=0track_id=ec1280db127955061754851657967wd={key}{QM_KEYS}"
                sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest()
                url = f'{QM_BASE_URL}/api/v1/playlet/search?extend=&page={str(page)}&wd={key}&read_preference=0&track_id=ec1280db127955061754851657967&sign={sign}'
                detail = requests.get(url=url, headers=self.qm_headers, timeout=10)
                if detail.status_code == 200:
                    detail_data = detail.json()
                    for vod in detail_data['data']['list']:
                        name = re.sub(r'<[^>]+>', '', vod['title'])
                        name = ' '.join(name.split())
                        videos.append({
                            "vod_id": f"qm_{vod['id']}",
                            "vod_name": name,
                            "vod_pic": vod['image_link'],
                            "vod_remarks": vod.get('total_num', '七猫')
                        })
            except:
                pass
        
        try:
            payload = {"search_word": key}
            urlz = f'{HK_BASE_URL}/haokan/ui-interact/playlet/search/sugs'
            response = requests.post(url=urlz, headers=HK_HEADERS, data=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for vod in data['data']:
                    videos.append({
                        "vod_id": f"hk_{vod['id']}",
                        "vod_name": vod['title'],
                        "vod_pic": vod['cover_url'],
                        "vod_remarks": "好看"
                    })
        except:
            pass
        
        return {
            'list': videos,
            'page': pg,
            'pagecount': 9999,
            'limit': 90,
            'total': 999999
        }
    
    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None