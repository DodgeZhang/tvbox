# coding=utf-8
#!/usr/bin/python
import requests
import json
import hashlib
import time
import random
import uuid
import re
import base64
from base.spider import Spider
import sys
from urllib.parse import quote, unquote
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

sys.path.append('..')

class Spider(Spider):
    
    def getName(self):
        return "聚合短剧[短]"
    
    def init(self, extend):
        # 全局配置 - 严格复制JavaScript版本
        self.aggConfig = {
            'keys': 'd3dGiJc651gSQ8w1',
            'charMap': {
                '+': 'P', '/': 'X', '0': 'M', '1': 'U', '2': 'l', '3': 'E', '4': 'r', '5': 'Y', '6': 'W', '7': 'b', '8': 'd', '9': 'J',
                'A': '9', 'B': 's', 'C': 'a', 'D': 'I', 'E': '0', 'F': 'o', 'G': 'y', 'H': '_', 'I': 'H', 'J': 'G', 'K': 'i', 'L': 't',
                'M': 'g', 'N': 'N', 'O': 'A', 'P': '8', 'Q': 'F', 'R': 'k', 'S': '3', 'T': 'h', 'U': 'f', 'V': 'R', 'W': 'q', 'X': 'C',
                'Y': '4', 'Z': 'p', 'a': 'm', 'b': 'B', 'c': 'O', 'd': 'u', 'e': 'c', 'f': '6', 'g': 'K', 'h': 'x', 'i': '5', 'j': 'T',
                'k': '-', 'l': '2', 'm': 'z', 'n': 'S', 'o': 'Z', 'p': '1', 'q': 'V', 'r': 'v', 's': 'j', 't': 'Q', 'u': '7', 'v': 'D',
                'w': 'w', 'x': 'n', 'y': 'L', 'z': 'e'
            },
            'headers': {
                'niuniu': {
                    'Cache-Control': 'no-cache',
                    'Content-Type': 'application/json;charset=UTF-8',
                    'User-Agent': 'okhttp/4.12.0'
                },
                'default': {
                    'User-Agent': 'okhttp/3.12.11',
                    'content-type': 'application/json; charset=utf-8'
                }
            },
            'platform': {
                '百度': {
                    'host': 'https://api.jkyai.top',
                    'url1': '/API/bddjss.php?name=fyclass&page=fypage',
                    'url2': '/API/bddjss.php?id=fyid',
                    'search': '/API/bddjss.php?name=**&page=fypage'
                },
                '甜圈': {
                    'host': 'https://mov.cenguigui.cn',
                    'url1': '/duanju/api.php?classname',
                    'url2': '/duanju/api.php?book_id',
                    'search': '/duanju/api.php?name'
                },
                '锦鲤': {
                    'host': 'https://api.jinlidj.com',
                    'search': '/api/search',
                    'url2': '/api/detail'
                },
                '番茄': {
                    'host': 'https://reading.snssdk.com',
                    'url1': '/reading/bookapi/bookmall/cell/change/v',
                    'url2': 'https://fqgo.52dns.cc/catalog',
                    'search': 'https://fqgo.52dns.cc/search'
                },
                '星芽': {
                    'host': 'https://app.whjzjx.cn',
                    'url1': '/cloud/v2/theater/home_page?theater_class_id',
                    'url2': '/v2/theater_parent/detail',
                    'search': '/v3/search',
                    'loginUrl': 'https://u.shytkjgs.com/user/v1/account/login'
                },
                '西饭': {
                    'host': 'https://xifan-api-cn.youlishipin.com',
                    'url1': '/xifan/drama/portalPage',
                    'url2': '/xifan/drama/getDuanjuInfo',
                    'search': '/xifan/search/getSearchList'
                },
                '软鸭': {
                    'host': 'https://api.xingzhige.com',
                    'url1': '/API/playlet',
                    'search': '/API/playlet'
                },
                '七猫': {
                    'host': 'https://api-store.qmplaylet.com',
                    'url1': '/api/v1/playlet/index',
                    'url2': 'https://api-read.qmplaylet.com/player/api/v1/playlet/info',
                    'search': '/api/v1/playlet/search'
                },
                '牛牛': {
                    'host': 'https://new.tianjinzhitongdaohe.com',
                    'url1': '/api/v1/app/screen/screenMovie',
                    'url2': '/api/v1/app/play/movieDetails',
                    'search': '/api/v1/app/search/searchMovie'
                },
                '围观': {
                    'host': 'https://api.drama.9ddm.com',
                    'url1': '/drama/home/shortVideoTags',
                    'url2': '/drama/home/shortVideoDetail',
                    'search': '/drama/home/search'
                },
                '碎片': {
                    'host': 'https://free-api.bighotwind.cc',
                    'url1': '/papaya/papaya-api/theater/tags',
                    'url2': '/papaya/papaya-api/videos/info',
                    'search': '/papaya/papaya-api/videos/page'
                }
            },
            'platformList': [
                {'name': '甜圈短剧', 'id': '甜圈'},
                {'name': '锦鲤短剧', 'id': '锦鲤'},
                {'name': '番茄短剧', 'id': '番茄'},
                {'name': '星芽短剧', 'id': '星芽'},
                {'name': '西饭短剧', 'id': '西饭'},
                {'name': '软鸭短剧', 'id': '软鸭'},
                {'name': '七猫短剧', 'id': '七猫'},
                {'name': '牛牛短剧', 'id': '牛牛'},
                {'name': '百度短剧', 'id': '百度'},
                {'name': '围观短剧', 'id': '围观'},
                {'name': '碎片剧场', 'id': '碎片'}
            ],
            'search': {
                'limit': 30,  # 统一搜索结果数量限制
                'timeout': 6000  # 统一超时时间
            }
        }
        
        # 初始化星芽token
        self.xingya_headers = self.aggConfig['headers']['default'].copy()
        try:
            data = {'device': '24250683a3bdb3f118dff25ba4b1cba1a'}
            headers = {
                'User-Agent': 'okhttp/4.10.0',
                'platform': '1',
                'Content-Type': 'application/json'
            }
            response = requests.post(self.aggConfig['platform']['星芽']['loginUrl'], 
                                   headers=headers, 
                                   data=json.dumps(data), 
                                   timeout=10)
            res = response.json()
            token = res.get('data', {}).get('token')
            if token:
                self.xingya_headers['authorization'] = token
        except:
            pass
    
    def isVideoFormat(self, url):
        pass
    
    def manualVideoCheck(self):
        pass
    
    def homeContent(self, filter):
        result = {}
        # 返回平台分类
        classes = []
        for platform in self.aggConfig['platformList']:
            classes.append({
                'type_id': platform['id'],
                'type_name': platform['name']
            })
        
        result['class'] = classes
        return result
    
    def homeVideoContent(self):
        result = {'list': []}
        return result
    
    def categoryContent(self, tid, pg, filter, extend):
        result = {
            'list': [],
            'page': pg,
            'pagecount': 9999,
            'limit': 24,
            'total': 999999
        }
        
        # 修复参数传递问题
        area = ''
        if isinstance(extend, dict):
            area = extend.get('area', '')
        elif isinstance(extend, str) and extend:
            area = extend
        
        plat_config = self.aggConfig['platform'].get(tid)
        if not plat_config:
            return result
        
        try:
            if tid == '百度':
                # 关键修复：使用正确的headers
                headers = self.aggConfig['headers']['default']
                
                # 检查area是否为空，如果为空使用默认值
                if not area:
                    area = '逆袭'  # 使用JavaScript版本的默认值
                
                url = plat_config['host'] + plat_config['url1'].replace('fyclass', area).replace('fypage', str(pg))
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    try:
                        res = response.json()
                        data_list = res.get('data', [])
                        if isinstance(data_list, list):
                            for it in data_list:
                                result['list'].append({
                                    'vod_id': f"{tid}@{it.get('id', '')}",
                                    'vod_name': it.get('title', '无标题'),
                                    'vod_pic': it.get('cover', ''),
                                    'vod_remarks': f"更新至{it.get('totalChapterNum', 0)}集",
                                    'vod_content': ''
                                })
                        else:
                            # 如果data不是列表，尝试处理为单个对象
                            if isinstance(data_list, dict) and 'title' in data_list:
                                result['list'].append({
                                    'vod_id': f"{tid}@{data_list.get('id', '')}",
                                    'vod_name': data_list.get('title', '无标题'),
                                    'vod_pic': data_list.get('cover', ''),
                                    'vod_remarks': f"更新至{data_list.get('totalChapterNum', 0)}集",
                                    'vod_content': ''
                                })
                    except Exception as json_err:
                        # 尝试重新解析响应
                        try:
                            text = response.text
                            # 尝试提取JSON
                            import re
                            match = re.search(r'({.*})', text)
                            if match:
                                res = json.loads(match.group(1))
                                data_list = res.get('data', [])
                                if isinstance(data_list, list):
                                    for it in data_list:
                                        result['list'].append({
                                            'vod_id': f"{tid}@{it.get('id', '')}",
                                            'vod_name': it.get('title', '无标题'),
                                            'vod_pic': it.get('cover', ''),
                                            'vod_remarks': f"更新至{it.get('totalChapterNum', 0)}集",
                                            'vod_content': ''
                                        })
                        except:
                            pass
            
            elif tid == '软鸭':
                # 关键修复：使用正确的headers
                headers = self.aggConfig['headers']['default']
                
                # 检查area是否为空，如果为空使用默认值
                if not area:
                    area = '战神'  # 使用JavaScript版本的默认值
                
                url = f"{plat_config['host']}{plat_config['url1']}/?keyword={quote(area)}&page={pg}"
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    try:
                        res = response.json()
                        data_list = res.get('data', [])
                        if isinstance(data_list, list):
                            for item in data_list:
                                purl = f"{item.get('title', '')}@{item.get('cover', '')}@{item.get('author', '')}@{item.get('type', '')}@{item.get('desc', '')}@{item.get('book_id', '')}"
                                result['list'].append({
                                    'vod_id': f"{tid}@{quote(purl)}",
                                    'vod_name': item.get('title', '无标题'),
                                    'vod_pic': item.get('cover', ''),
                                    'vod_remarks': item.get('type', ''),
                                    'vod_content': item.get('author', '')
                                })
                        else:
                            # 如果data不是列表，尝试处理为单个对象
                            if isinstance(data_list, dict) and data_list.get('title'):
                                purl = f"{data_list.get('title', '')}@{data_list.get('cover', '')}@{data_list.get('author', '')}@{data_list.get('type', '')}@{data_list.get('desc', '')}@{data_list.get('book_id', '')}"
                                result['list'].append({
                                    'vod_id': f"{tid}@{quote(purl)}",
                                    'vod_name': data_list.get('title', '无标题'),
                                    'vod_pic': data_list.get('cover', ''),
                                    'vod_remarks': data_list.get('type', ''),
                                    'vod_content': data_list.get('author', '')
                                })
                    except Exception as json_err:
                        # 尝试重新解析响应
                        try:
                            text = response.text
                            # 尝试提取JSON
                            import re
                            match = re.search(r'({.*})', text)
                            if match:
                                res = json.loads(match.group(1))
                                data_list = res.get('data', [])
                                if isinstance(data_list, list):
                                    for item in data_list:
                                        purl = f"{item.get('title', '')}@{item.get('cover', '')}@{item.get('author', '')}@{item.get('type', '')}@{item.get('desc', '')}@{item.get('book_id', '')}"
                                        result['list'].append({
                                            'vod_id': f"{tid}@{quote(purl)}",
                                            'vod_name': item.get('title', '无标题'),
                                            'vod_pic': item.get('cover', ''),
                                            'vod_remarks': item.get('type', ''),
                                            'vod_content': item.get('author', '')
                                        })
                        except:
                            pass
            
            elif tid == '番茄':
                try:
                    import datetime
                    now = datetime.datetime.now()
                    session_id = now.strftime('%Y%m%d%H%M%S')[:16].replace('-', '').replace('T', '').replace(':', '')
                    
                    url = f"{plat_config['host']}{plat_config['url1']}?change_type=0&selected_items={area}&tab_type=8&cell_id=6952850996422770718&version_tag=video_feed_refactor&device_id=1423244030195267&aid=1967&app_name=novelapp&ssmix=a&session_id={session_id}"
                    if int(pg) > 1:
                        url += f"&offset={(int(pg) - 1) * 12}"
                    
                    headers = self.aggConfig['headers']['default']
                    
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        res = response.json()
                        items = []
                        
                        if res.get('data', {}).get('cell_view', {}).get('cell_data'):
                            items = res['data']['cell_view']['cell_data']
                        elif res.get('search_tabs'):
                            for tab in res.get('search_tabs', []):
                                if tab.get('title') == '短剧' and tab.get('data'):
                                    items = tab['data']
                                    break
                        elif isinstance(res.get('data'), list):
                            items = res['data']
                        elif res.get('data'):
                            items = [res['data']]
                        else:
                            items = [res] if res else []
                        
                        for item in items:
                            video_data = item
                            if 'video_data' in item and isinstance(item['video_data'], list) and len(item['video_data']) > 0:
                                video_data = item['video_data'][0]
                            
                            vod_id = video_data.get('series_id', video_data.get('book_id', video_data.get('id', '')))
                            if vod_id:
                                result['list'].append({
                                    'vod_id': f"{tid}@{vod_id}",
                                    'vod_name': video_data.get('title', '无标题'),
                                    'vod_pic': video_data.get('cover', video_data.get('horiz_cover', '')),
                                    'vod_remarks': video_data.get('sub_title', video_data.get('rec_text', '')),
                                    'vod_content': ''
                                })
                except:
                    pass
            
            elif tid == '西饭':
                try:
                    if '@' in area:
                        type_id, type_name = area.split('@', 1)
                    else:
                        type_id, type_name = area, ''
                    
                    ts = int(time.time())
                    request_id = f"{ts}aa498144140ef297"
                    
                    url = f"{plat_config['host']}{plat_config['url1']}?reqType=aggregationPage&offset={(int(pg)-1)*30}&categoryId={type_id}&quickEngineVersion=-1&scene=&categoryNames={quote(type_name)}&categoryVersion=1&density=1.5&pageID=page_theater&version=2001001&androidVersionCode=28&requestId={request_id}&appId=drama&teenMode=false&userBaseMode=false&session=eyJpbmZvIjp7InVpZCI6IiIsInJ0IjoiMTc0MDY1ODI5NCIsInVuIjoiT1BHXzFlZGQ5OTZhNjQ3ZTQ1MjU4Nzc1MTE2YzFkNzViN2QwIiwiZnQiOiIxNzQwNjU4Mjk0In19&feedssession=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dHlwIjowLCJidWlkIjoxNjMzOTY4MTI2MTQ4NjQxNTM2LCJhdWQiOiJkcmFtYSIsInZlciI6MiwicmF0IjoxNzQwNjU4Mjk0LCJ1bm0iOiJPUEdfMWVkZDk5NmE2NDdlNDUyNTg3NzUxMTZjMWQ3NWI3ZDAiLCJpZCI6IjNiMzViZmYzYWE0OTgxNDQxNDBlZjI5N2JkMDY5NGNhIiwiZXhwIjoxNzQxMjYzMDk0LCJkYyI6Imd6cXkifQ.JS3QY6ER0P2cQSxAE_OGKSMIWNAMsYUZ3mJTnEpf-Rc"
                    
                    headers = self.aggConfig['headers']['default']
                    
                    response = requests.get(url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        res = response.json()
                        elements = res.get('result', {}).get('elements', [])
                        
                        for soup in elements:
                            contents = soup.get('contents', [])
                            for vod in contents:
                                dj = vod.get('duanjuVo', {})
                                if dj:
                                    result['list'].append({
                                        'vod_id': f"{tid}@{dj.get('duanjuId', '')}#{dj.get('source', '')}",
                                        'vod_name': dj.get('title', '无标题'),
                                        'vod_pic': dj.get('coverImageUrl', ''),
                                        'vod_remarks': f"{dj.get('total', 0)}集",
                                        'vod_content': ''
                                    })
                except:
                    pass
            
            # 其他平台保持不变
            elif tid == '甜圈':
                url = plat_config['host'] + plat_config['url1'] + f"={area}&offset={pg}"
                response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=10)
                
                if response.status_code == 200:
                    res = response.json()
                    for it in res.get('data', []):
                        result['list'].append({
                            'vod_id': f"{tid}@{it.get('book_id', '')}",
                            'vod_name': it.get('title', '无标题'),
                            'vod_pic': it.get('cover', ''),
                            'vod_remarks': it.get('copyright', ''),
                            'vod_content': it.get('sub_title', '')
                        })
            
            elif tid == '锦鲤':
                body = {
                    'page': pg,
                    'limit': 24,
                    'type_id': area,
                    'year': '',
                    'keyword': ''
                }
                
                response = requests.post(
                    plat_config['host'] + plat_config['search'],
                    headers=self.aggConfig['headers']['default'],
                    json=body,
                    timeout=10
                )
                
                if response.status_code == 200:
                    res = response.json()
                    for item in res.get('data', {}).get('list', []):
                        result['list'].append({
                            'vod_id': f"{tid}@{item.get('vod_id', '')}",
                            'vod_name': item.get('vod_name', '无标题'),
                            'vod_pic': item.get('vod_pic', ''),
                            'vod_remarks': f"{item.get('vod_total', 0)}集",
                            'vod_content': item.get('vod_tag', '')
                        })
            
            elif tid == '星芽':
                # 修复这里的f-string语法错误
                url = f"{plat_config['host']}{plat_config['url1']}={area}&type=1&class2_ids=0&page_num={pg}&page_size=24"
                response = requests.get(url, headers=self.xingya_headers, timeout=10)
                
                if response.status_code == 200:
                    res = response.json()
                    for it in res.get('data', {}).get('list', []):
                        theater = it.get('theater', {})
                        detail_url = f"{plat_config['host']}{plat_config['url2']}?theater_parent_id={theater.get('id', '')}"
                        result['list'].append({
                            'vod_id': f"{tid}@{detail_url}",
                            'vod_name': theater.get('title', '无标题'),
                            'vod_pic': theater.get('cover_url', ''),
                            'vod_remarks': f"{theater.get('total', 0)}集",
                            'vod_content': f"播放量:{theater.get('play_amount_str', '0')}"
                        })
            
            elif tid == '七猫':
                try:
                    sign_str = f"operation=1playlet_privacy=1tag_id={area}{self.aggConfig['keys']}"
                    sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
                    
                    url = f"{plat_config['host']}{plat_config['url1']}?tag_id={area}&playlet_privacy=1&operation=1&sign={sign}"
                    
                    # 获取七猫请求头
                    headers = self._get_header_x()
                    
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        res = response.json()
                        for item in res.get('data', {}).get('list', []):
                            result['list'].append({
                                'vod_id': f"{tid}@{quote(item.get('playlet_id', ''))}",
                                'vod_name': item.get('title', '无标题'),
                                'vod_pic': item.get('image_link', ''),
                                'vod_remarks': f"{item.get('total_episode_num', 0)}集",
                                'vod_content': item.get('tags', '')
                            })
                except:
                    pass
            
            elif tid == '牛牛':
                body = {
                    'condition': {'classify': area, 'typeId': 'S1'},
                    'pageNum': str(pg),
                    'pageSize': 24
                }
                
                response = requests.post(
                    plat_config['host'] + plat_config['url1'],
                    headers=self.aggConfig['headers']['niuniu'],
                    json=body,
                    timeout=10
                )
                
                if response.status_code == 200:
                    res = response.json()
                    for item in res.get('data', {}).get('records', []):
                        result['list'].append({
                            'vod_id': f"{tid}@{item.get('id', '')}",
                            'vod_name': item.get('name', '无标题'),
                            'vod_pic': item.get('cover', ''),
                            'vod_remarks': f"{item.get('totalEpisode', 0)}集",
                            'vod_content': ''
                        })
            
            elif tid == '围观':
                body = {
                    'audience': '全部受众',
                    'page': pg,
                    'pageSize': 30,
                    'searchWord': '',
                    'subject': '全部主题'
                }
                
                response = requests.post(
                    plat_config['host'] + plat_config['search'],
                    headers=self.aggConfig['headers']['default'],
                    json=body,
                    timeout=10
                )
                
                if response.status_code == 200:
                    res = response.json()
                    for it in res.get('data', []):
                        result['list'].append({
                            'vod_id': f"{tid}@{it.get('oneId', '')}",
                            'vod_name': it.get('title', '无标题'),
                            'vod_pic': it.get('vertPoster', ''),
                            'vod_remarks': f"集数:{it.get('episodeCount', 0)} 播放:{it.get('viewCount', 0)}",
                            'vod_content': it.get('description', '')
                        })
            
            elif tid == '碎片':
                try:
                    # 碎片剧场需要先获取token
                    open_id = hashlib.md5(self._guid().encode('utf-8')).hexdigest()[:16]
                    api = "https://free-api.bighotwind.cc/papaya/papaya-api/oauth2/uuid"
                    body = {"openId": open_id}
                    key = self._enc_hex(str(int(time.time() * 1000)))
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'key': key
                    }
                    
                    token_response = requests.post(
                        api,
                        headers=headers,
                        json=body,
                        timeout=10
                    )
                    
                    if token_response.status_code == 200:
                        token_data = token_response.json()
                        token = token_data.get('data', {}).get('token', '')
                        
                        if token:
                            headers = self.aggConfig['headers']['default'].copy()
                            headers['Authorization'] = token
                            
                            url = f"{plat_config['host']}{plat_config['search']}?type=5&tagId=&pageNum={pg}&pageSize=24"
                            
                            response = requests.get(url, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                res = response.json()
                                for it in res.get('list', []):
                                    compound_id = f"{it.get('itemId', '')}@{it.get('videoCode', '')}"
                                    result['list'].append({
                                        'vod_id': f"{tid}@{compound_id}",
                                        'vod_name': it.get('title', '无标题'),
                                        'vod_pic': f"https://speed.rouzwv.com/papaya/papaya-file/files/download/{it.get('imageKey', '')}/{it.get('imageName', '')}",
                                        'vod_remarks': f"集数:{it.get('episodesMax', 0)} 播放:{it.get('hitShowNum', 0)}",
                                        'vod_content': it.get('content', it.get('description', ''))
                                    })
                except:
                    pass
        
        except Exception as e:
            pass
        
        return result
    
    def detailContent(self, ids):
        result = {'list': []}
        
        if not ids or len(ids) == 0:
            return result
        
        vod_id = ids[0]
        
        if vod_id == 'update_info':
            vod = {
                'vod_id': vod_id,
                'vod_name': '更新日志',
                'vod_pic': 'https://resource-cdn.tuxiaobei.com/video/FtWhs2mewX_7nEuE51_k6zvg极awl.png',
                'vod_content': '聚合短剧更新日志',
                'vod_play_from': '聚合短剧',
                'vod_play_url': '随机小视频$http://api.yujn.cn/api/zzxjj.php'
            }
            result['list'] = [vod]
            return result
        
        if '@' not in vod_id:
            vod = {
                'vod_id': vod_id,
                'vod_name': '聚合短剧',
                'vod_pic': 'https://resource-cdn.tuxiaobei.com/video/FtWhs2mewX_7nEuE51_k6zvg极awl.png',
                'vod_content': '聚合多个短剧平台的资源',
                'vod_play_from': '聚合短剧',
                'vod_play_url': '更新日志$http://api.yujn.cn/api/zzxjj.php'
            }
            result['list'] = [vod]
            return result
        
        parts = vod_id.split('@', 1)
        platform = parts[0]
        id_param = parts[1]
        
        plat_config = self.aggConfig['platform'].get(platform)
        if not plat_config:
            return result
        
        try:
            if platform == '百度':
                # 关键修复：使用正确的headers
                url = plat_config['host'] + plat_config['url2'].replace('fyid', id_param)
                headers = self.aggConfig['headers']['default']
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    
                    play_urls = []
                    for idx, item in enumerate(res.get('data', [])):
                        title = item.get('title', f'第{idx+1}集')
                        video_id = item.get('video_id', '')
                        if video_id:
                            play_urls.append(f"{title}${video_id}")
                    
                    vod = {
                        'vod_id': vod_id,
                        'vod_name': res.get('title', ''),
                        'vod_pic': res.get('data', [{}])[0].get('cover', ''),
                        'type_name': '短剧',
                        'vod_year': f"更新至{res.get('total', 0)}集",
                        'vod_area': '',
                        'vod_remarks': '',
                        'vod_actor': '',
                        'vod_director': '',
                        'vod_content': '',
                        'vod_play_from': '百度短剧',
                        'vod_play_url': '#'.join(play_urls) if play_urls else ''
                    }
                    result['list'] = [vod]
            
            elif platform == '甜圈':
                url = plat_config['host'] + plat_config['url2'] + f"={id_param}"
                response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    
                    play_urls = []
                    for idx, item in enumerate(res.get('data', [])):
                        title = item.get('title', f'第{idx+1}集')
                        video_id = item.get('video_id', '')
                        if video_id:
                            play_urls.append(f"{title}${video_id}")
                    
                    vod = {
                        'vod_id': vod_id,
                        'vod_name': res.get('book_name', ''),
                        'vod_pic': res.get('book_pic', ''),
                        'type_name': res.get('category', ''),
                        'vod_year': res.get('time', ''),
                        'vod_area': '',
                        'vod_remarks': res.get('duration', ''),
                        'vod_actor': res.get('author', ''),
                        'vod_director': '',
                        'vod_content': res.get('desc', ''),
                        'vod_play_from': '甜圈短剧',
                        'vod_play_url': '#'.join(play_urls) if play_urls else ''
                    }
                    result['list'] = [vod]
            
            elif platform == '锦鲤':
                url = plat_config['host'] + plat_config['url2'] + f"/{id_param}"
                response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    list_data = res.get('data', {})
                    
                    play_urls = []
                    player_data = list_data.get('player', {})
                    if isinstance(player_data, dict):
                        for key, url_val in player_data.items():
                            play_urls.append(f"{key}${url_val}")
                    
                    vod = {
                        'vod_id': vod_id,
                        'vod_name': list_data.get('vod_name', ''),
                        'vod_pic': list_data.get('vod_pic', ''),
                        'type_name': list_data.get('vod_class', ''),
                        'vod_year': list_data.get('vod_year', ''),
                        'vod_area': list_data.get('vod_area', ''),
                        'vod_remarks': list_data.get('vod_remarks', ''),
                        'vod_actor': list_data.get('vod_actor', ''),
                        'vod_director': list_data.get('vod_director', ''),
                        'vod_content': list_data.get('vod_blurb', ''),
                        'vod_play_from': '锦鲤短剧',
                        'vod_play_url': '#'.join(play_urls) if play_urls else ''
                    }
                    result['list'] = [vod]
            
            elif platform == '番茄':
                url = plat_config['url2'] + f"?book_id={id_param}"
                response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    
                    play_urls = []
                    for item in res.get('data', {}).get('item_data_list', []):
                        title = item.get('title', '')
                        item_id = item.get('item_id', '')
                        if title and item_id:
                            play_urls.append(f"{title}${item_id}")
                    
                    book_info = res.get('data', {}).get('book_info', {})
                    vod = {
                        'vod_id': vod_id,
                        'vod_name': book_info.get('book_name', ''),
                        'vod_pic': book_info.get('thumb_url', book_info.get('audio_thumb_uri', '')),
                        'type_name': book_info.get('tags', ''),
                        'vod_year': book_info.get('create_time', ''),
                        'vod_area': '',
                        'vod_remarks': f"更新至{len(res.get('data', {}).get('item_data_list', []))}集",
                        'vod_actor': '',
                        'vod_director': '',
                        'vod_content': book_info.get('abstract', book_info.get('book_abstract_v2', '')),
                        'vod_play_from': '番茄短剧',
                        'vod_play_url': '#'.join(play_urls) if play_urls else ''
                    }
                    result['list'] = [vod]
            
            elif platform == '西饭':
                if '#' in id_param:
                    duanju_id, source = id_param.split('#', 1)
                else:
                    duanju_id, source = id_param, ''
                
                url = f"{plat_config['host']}{plat_config['url2']}?duanjuId={duanju_id}&source={source}&openFrom=homescreen&type=&pageID=page_inner_flow&density=1.5&version=2001001&androidVersionCode=28&requestId=1740658944980aa498144140ef297&appId=drama&teenMode=false&userBaseMode=false&session=eyJpbmZvIjp7InVpZCI6IiIsInJ0IjoiMTc0MDY1ODI5NCIsInVuIjoiT1BHXzFlZGQ5OTZhNjQ3ZTQ1MjU4Nzc1MTE2YzFkNzViN2QwIiwiZnQiOiIxNzQwNjU4Mjk0In19&feedssession=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dHlwIjowLCJidWlkIjoxNjMzOTY4MTI2MTQ4NjQxNTM2LCJhdWQiOiJkcmFtYSIsInZlciI6MiwicmF0IjoxNzQwNjU4Mjk4LCJ1bm0iOiJPUEdfMWVkZDk5NmE2NDdlNDUyNTg3NzUxMTY2YzFkNzViN2QwIiwiZXhwIjoxNzQxMjYzMDk0LCJkYyI6Imd6cXkifQ.JS3QY6ER0P2cQSxAE_OGKSMIWNAMsYUZ3mJTnEpf-Rc"
                
                response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    data = res.get('result', {})
                    
                    play_urls = []
                    for ep in data.get('episodeList', []):
                        play_urls.append(f"{ep.get('index', '')}${ep.get('playUrl', '')}")
                    
                    vod = {
                        'vod_id': vod_id,
                        'vod_name': data.get('title', ''),
                        'vod_pic': data.get('coverImageUrl', ''),
                        'vod_content': data.get('desc', '未知'),
                        'vod_remarks': f"{data.get('total', 0)}集",
                        'vod_play_from': '西饭短剧',
                        'vod_play_url': '#'.join(play_urls) if play_urls else ''
                    }
                    result['list'] = [vod]
            
            elif platform == '软鸭':
                # 关键修复：使用正确的headers
                try:
                    did = unquote(id_param)
                    parts = did.split('@')
                    if len(parts) >= 6:
                        title, img, author, type_name, desc, book_id = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]
                    else:
                        title, img, author, type_name, desc, book_id = '', '', '', '', '', id_param
                    
                    url = f"{plat_config['host']}{plat_config['url1']}/?book_id={book_id}"
                    headers = self.aggConfig['headers']['default']
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        res = response.json()
                        play_urls = []
                        video_list = res.get('data', {}).get('video_list', [])
                        for ep in video_list:
                            play_urls.append(f"{ep.get('title', '')}${ep.get('video_id', '')}")
                        
                        vod = {
                            'vod_id': vod_id,
                            'vod_name': title,
                            'vod_pic': img,
                            'vod_actor': author,
                            'vod_remarks': type_name,
                            'vod_content': desc,
                            'vod_play_from': '软鸭短剧',
                            'vod_play_url': '#'.join(play_urls) if play_urls else ''
                        }
                        result['list'] = [vod]
                except:
                    pass
            
            elif platform == '七猫':
                try:
                    did = unquote(id_param)
                    sign = hashlib.md5(f"playlet_id={did}{self.aggConfig['keys']}".encode('utf-8')).hexdigest()
                    url = f"{plat_config['url2']}?playlet_id={did}&sign={sign}"
                    headers = self._get_header_x()
                    
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    if response.status_code == 200:
                        res = response.json()
                        data = res.get('data', {})
                        play_urls = []
                        for it in data.get('play_list', []):
                            play_urls.append(f"{it.get('sort', '')}${it.get('video_url', '')}")
                        
                        vod = {
                            'vod_id': vod_id,
                            'vod_name': data.get('title', '未知标题'),
                            'vod_pic': data.get('image_link', '未知图片'),
                            'vod_remarks': f"{data.get('tags', '')} {data.get('total_episode_num', 0)}集",
                            'vod_content': data.get('intro', '未知剧情'),
                            'vod_play_from': '七猫短剧',
                            'vod_play_url': '#'.join(play_urls) if play_urls else ''
                        }
                        result['list'] = [vod]
                except:
                    pass
            
            elif platform == '牛牛':
                body = {
                    'id': id_param,
                    'source': 0,
                    'typeId': 'S1',
                    'userId': '223664'
                }
                
                response = requests.post(
                    plat_config['host'] + plat_config['url2'],
                    headers=self.aggConfig['headers']['niuniu'],
                    json=body,
                    timeout=10
                )
                
                if response.status_code == 200:
                    res = response.json()
                    data = res.get('data', {})
                    play_urls = []
                    for ep in data.get('episodeList', []):
                        play_urls.append(f"{ep.get('episode', '')}${id_param}@{ep.get('id', '')}")
                    
                    vod = {
                        'vod_id': vod_id,
                        'vod_name': data.get('name', '未知名称'),
                        'vod_pic': data.get('cover', ''),
                        'vod_content': data.get('introduce', '暂无剧情'),
                        'vod_play_from': '牛牛短剧',
                        'vod_play_url': '#'.join(play_urls) if play_urls else '暂无播放地址$0'
                    }
                    result['list'] = [vod]
            
            elif platform == '围观':
                url = f"{plat_config['host']}{plat_config['url2']}?oneId={id_param}&page=1&pageSize=1000"
                response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=10)
                
                if response.status_code == 200:
                    res = response.json()
                    data = res.get('data', [])
                    if data:
                        first_episode = data[0]
                        play_urls = []
                        for episode in data:
                            # 直接传递playSetting给playerContent处理
                            play_setting = episode.get('playSetting', '')
                            play_urls.append(f"{episode.get('title', '')}第{episode.get('playOrder', '')}集${play_setting}")
                        
                        vod = {
                            'vod_id': vod_id,
                            'vod_name': first_episode.get('title', ''),
                            'vod_pic': first_episode.get('vertPoster', ''),
                            'vod_remarks': f"共{len(data)}集",
                            'vod_content': f"播放量:{first_episode.get('collectionCount', 0)} 评论:{first_episode.get('commentCount', 0)}",
                            'vod_play_from': '围观短剧',
                            'vod_play_url': '#'.join(play_urls) if play_urls else ''
                        }
                        result['list'] = [vod]
            
            elif platform == '碎片':
                try:
                    open_id = hashlib.md5(self._guid().encode('utf-8')).hexdigest()[:16]
                    api = "https://free-api.bighotwind.cc/papaya/papaya-api/oauth2/uuid"
                    body = {"openId": open_id}
                    key = self._enc_hex(str(int(time.time() * 1000)))
                    
                    headers = {
                        'Content-Type': 'application/json',
                        'key': key
                    }
                    
                    token_response = requests.post(api, headers=headers, json=body, timeout=10)
                    
                    if token_response.status_code == 200:
                        token_data = token_response.json()
                        token = token_data.get('data', {}).get('token', '')
                        
                        if token:
                            headers = self.aggConfig['headers']['default'].copy()
                            headers['Authorization'] = token
                            
                            item_id, video_code = id_param.split('@', 1) if '@' in id_param else ('', id_param)
                            url = f"{plat_config['host']}{plat_config['url2']}?videoCode={video_code}&itemId={item_id}"
                            
                            response = requests.get(url, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                res = response.json()
                                data = res.get('data', res)
                                
                                play_urls = []
                                episodes = data.get('episodesList', [])
                                for episode in episodes:
                                    episode_title = f"第{episode.get('episodes', '')}集"
                                    play_url = ""
                                    
                                    resolution_list = episode.get('resolutionList', [])
                                    if resolution_list:
                                        # 按分辨率从高到低排序
                                        resolution_list.sort(key=lambda x: x.get('resolution', 0), reverse=True)
                                        best_resolution = resolution_list[0]
                                        play_url = f"https://speed.rouzwv.com/papaya/papaya-file/files/download/{best_resolution.get('fileKey', '')}/{best_resolution.get('fileName', '')}"
                                    
                                    if play_url:
                                        play_urls.append(f"{episode_title}${play_url}")
                                
                                vod = {
                                    'vod_id': vod_id,
                                    'vod_name': data.get('title', ''),
                                    'vod_pic': f"https://speed.rouzwv.com/papaya/papaya-file/files/download/{data.get('imageKey', '')}/{data.get('imageName', '')}",
                                    'vod_remarks': f"共{data.get('episodesMax', 0)}集",
                                    'vod_content': data.get('content', data.get('description', f"播放量:{data.get('hitShowNum', 0)} 点赞:{data.get('likeNum', 0)}")),
                                    'vod_play_from': '碎片剧场',
                                    'vod_play_url': '#'.join(play_urls) if play_urls else ''
                                }
                                result['list'] = [vod]
                except:
                    pass
        
        except Exception as e:
            pass
        
        return result
    
    def playerContent(self, flag, id, vipFlags):
        result = {
            "parse": 0,
            "url": id,
            "header": {"User-Agent": "Mozilla/5.0"}
        }
        
        try:
            if '百度' in flag:
                response = requests.get(f"https://api.jkyai.top/API/bddjss.php?video_id={id}", 
                                       headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    item = response.json()
                    qualities = item.get('data', {}).get('qualities', [])
                    
                    quality_order = ["1080p", "sc", "sd"]
                    quality_names = {"1080p": "蓝光", "sc": "超清", "sd": "标清"}
                    
                    urls = []
                    for quality_key in quality_order:
                        for quality in qualities:
                            if quality.get('quality') == quality_key:
                                urls.append(quality_names.get(quality_key, quality_key))
                                urls.append(quality.get('download_url', ''))
                                break
                    
                    if urls:
                        result["url"] = urls
            
            elif '甜圈' in flag:
                result["url"] = f"https://mov.cenguigui.cn/duanju/api.php?video_id={id}&type=mp4"
            
            elif '锦鲤' in flag:
                response = requests.get(f"{id}&auto=1", 
                                       headers={'referer': 'https://www.jinlidj.com/'}, 
                                       timeout=10)
                html = response.text
                match = re.search(r'let data\s*=\s*({[^;]*});', html)
                if match:
                    try:
                        data_json = json.loads(match.group(1))
                        result["url"] = data_json.get('url', id)
                    except:
                        result["url"] = id
            
            elif '番茄' in flag:
                response = requests.get(f"https://fqgo.52dns.cc/video?item_ids={id}", 
                                       headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    video_model = res.get('data', {}).get(id, {}).get('video_model')
                    if video_model:
                        try:
                            video_data = json.loads(video_model)
                            url = video_data.get('video_list', {}).get('video_1', {}).get('main_url', '')
                            if url:
                                # 尝试base64解码
                                try:
                                    decoded = base64.b64decode(url).decode('utf-8')
                                    result["url"] = decoded
                                except:
                                    result["url"] = url
                        except:
                            pass
            
            elif '软鸭' in flag:
                response = requests.get(f"{self.aggConfig['platform']['软鸭']['host']}/API/playlet/?video_id={id}&quality=1080p", 
                                       headers=self.aggConfig['headers']['default'], timeout=10)
                if response.status_code == 200:
                    res = response.json()
                    result["url"] = res.get('data', {}).get('video', {}).get('url', '')
            
            elif '牛牛' in flag:
                if '@' in id:
                    video_id, episode_id = id.split('@', 1)
                else:
                    video_id, episode_id = id, ''
                
                body = {
                    'episodeId': episode_id,
                    'id': video_id,
                    'source': 0,
                    'typeId': 'S1',
                    'userId': '223664'
                }
                
                response = requests.post(
                    f"{self.aggConfig['platform']['牛牛']['host']}/api/v1/app/play/movieDetails",
                    headers=self.aggConfig['headers']['niuniu'],
                    json=body,
                    timeout=10
                )
                
                if response.status_code == 200:
                    res = response.json()
                    result["url"] = res.get('data', {}).get('url', '')
                    result["header"] = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.87 Safari/537.36'}
            
            elif '围观' in flag:
                # 解析playSetting JSON
                try:
                    play_setting = json.loads(id) if isinstance(id, str) else id
                    urls = []
                    
                    if play_setting.get('super'):
                        urls.append("超清")
                        urls.append(play_setting['super'])
                    if play_setting.get('high'):
                        urls.append("高清")
                        urls.append(play_setting['high'])
                    if play_setting.get('normal'):
                        urls.append("流畅")
                        urls.append(play_setting['normal'])
                    
                    if urls:
                        result["url"] = urls
                except:
                    result["url"] = id
        
        except Exception as e:
            pass
        
        return result
    
    # 修复搜索功能 - 合并两个searchContent方法为一个
    def searchContent(self, key, quick, pg=1):
        """
        搜索功能 - 兼容2个参数和3个参数的调用
        参考盘友圈.py的实现方式
        """
        print(f"🔍 聚合短剧搜索被调用: key={key}, quick={quick}, pg={pg}")
        # 确保pg参数为字符串类型
        if isinstance(pg, int):
            pg = str(pg)
        return self.searchContentPage(key, quick, pg)
    
    def searchContentPage(self, key, quick, page='1'):
        """
        搜索分页功能
        """
        print(f"🔍 聚合短剧搜索分页: key={key}, quick={quick}, page={page}")
        
        # 确保page是字符串类型
        if not isinstance(page, str):
            page = str(page)
            
        result = {
            'list': [],
            'page': page,
            'pagecount': 9999,
            'limit': 30,
            'total': 999999
        }
        
        if not key or not key.strip():
            print("⚠️ 搜索关键词为空")
            return result
        
        search_key = key.strip()
        search_limit = self.aggConfig['search']['limit']
        search_timeout = self.aggConfig['search']['timeout'] / 1000  # 转换为秒
        
        print(f"🔍 开始搜索: {search_key}, 页码: {page}")
        
        # 使用线程池并发搜索所有平台，模仿JavaScript的Promise.allSettled
        def search_platform(platform_info):
            plat_id = platform_info['id']
            plat_name = platform_info['name']
            plat_config = self.aggConfig['platform'].get(plat_id)
            if not plat_config:
                return {'platform': plat_name, 'results': []}
            
            try:
                results = []
                
                if plat_id == '百度':
                    url = plat_config['host'] + plat_config['search'].replace('**', quote(search_key)).replace('fypage', page)
                    headers = self.aggConfig['headers']['default']
                    response = requests.get(url, headers=headers, timeout=search_timeout)
                    if response.status_code == 200:
                        data = response.json()
                        if data and data.get('data'):
                            for item in data.get('data', []):
                                results.append({
                                    'vod_id': f"{plat_id}@{item.get('id', '')}",
                                    'vod_name': item.get('title', ''),
                                    'vod_pic': item.get('cover', ''),
                                    'vod_remarks': f"百度短剧 | {item.get('totalChapterNum', 0)}集"
                                })
                
                elif plat_id == '甜圈':
                    url = plat_config['host'] + plat_config['search'] + f"={quote(search_key)}&offset={page}"
                    response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=search_timeout)
                    if response.status_code == 200:
                        data = response.json()
                        if data and data.get('data'):
                            for item in data.get('data', []):
                                results.append({
                                    'vod_id': f"{plat_id}@{item.get('book_id', '')}",
                                    'vod_name': item.get('title', ''),
                                    'vod_pic': item.get('cover', ''),
                                    'vod_remarks': f"甜圈短剧 | {item.get('copyright', '')}"
                                })
                
                elif plat_id == '锦鲤':
                    body = {
                        'page': int(page),
                        'limit': search_limit,
                        'type_id': '',
                        'year': '',
                        'keyword': search_key
                    }
                    
                    response = requests.post(
                        plat_config['host'] + plat_config['search'],
                        headers=self.aggConfig['headers']['default'],
                        json=body,
                        timeout=search_timeout
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data and data.get('data') and data['data'].get('list'):
                            for item in data['data']['list']:
                                results.append({
                                    'vod_id': f"{plat_id}@{item.get('vod_id', '')}",
                                    'vod_name': item.get('vod_name', ''),
                                    'vod_pic': item.get('vod_pic', ''),
                                    'vod_remarks': f"锦鲤短剧 | {item.get('vod_total', 0)}集"
                                })
                
                elif plat_id == '番茄':
                    try:
                        url = f"{plat_config['search']}?keyword={quote(search_key)}&page={page}"
                        response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=search_timeout)
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('data') and isinstance(data['data'], list):
                                for item in data['data']:
                                    results.append({
                                        'vod_id': f"{plat_id}@{item.get('series_id', '')}",
                                        'vod_name': item.get('title', ''),
                                        'vod_pic': item.get('cover', ''),
                                        'vod_remarks': f"番茄短剧 | {item.get('sub_title', '')}"
                                    })
                    except Exception as e:
                        # 打印错误信息便于调试
                        print(f"⚠️ 番茄短剧搜索失败: {str(e)}")
                        pass
                
                elif plat_id == '星芽':
                    url = f"{plat_config['host']}{plat_config['search']}"
                    body = {'text': search_key}
                    response = requests.post(url, headers=self.xingya_headers, json=body, timeout=search_timeout)
                    if response.status_code == 200:
                        data = response.json()
                        if data and data.get('data') and data['data'].get('theater') and data['data']['theater'].get('search_data'):
                            for item in data['data']['theater']['search_data']:
                                detail_url = f"{plat_config['host']}{plat_config['url2']}?theater_parent_id={item.get('id', '')}"
                                results.append({
                                    'vod_id': f"{plat_id}@{detail_url}",
                                    'vod_name': item.get('title', ''),
                                    'vod_pic': item.get('cover_url', ''),
                                    'vod_remarks': f"星芽短剧 | {item.get('total', 0)}集"
                                })
                
                elif plat_id == '西饭':
                    try:
                        ts = int(time.time())
                        url = f"{plat_config['host']}{plat_config['search']}?reqType=search&offset={(int(page)-1)*search_limit}&keyword={quote(search_key)}&quickEngineVersion=-1&scene=&categoryVersion=1&density=1.5&pageID=page_theater&version=2001001&androidVersionCode=28&requestId={ts}aa498144140ef297&appId=drama&teenMode=false&userBaseMode=false&session=eyJpbmZvIjp7InVpZCI6IiIsInJ0IjoiMTc0MDY1ODI5NCIsInVuIjoiT1BHXzFlZGQ5OTZhNjQ3ZTQ1MjU4Nzc1MTE2YzFkNzViN2QwIiwiZnQiOiIxNzQwNjU4Mjk4In19&feedssession=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1dHlwIjowLCJidWlkIjoxNjMzOTY4MTI2MTQ4NjQxNTM2LCJhdWQiOiJkcmFtYSIsInZlciI6MiwicmF0IjoxNzQwNjU4Mjk4LCJ1bm0iOiJPUEdfMWVkZDk5NmE2NDdlNDUyNTg3NzUxMTY2YzFkNzViN2QwIiwiZXhwIjoxNzQxMjYzMDk0LCJkYyI6Imd6cXkifQ.JS3QY6ER0P2cQSxAE_OGKSMIWNAMsYUZ3mJTnEpf-Rc"
                        response = requests.get(url, headers=self.aggConfig['headers']['default'], timeout=search_timeout)
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('result') and data['result'].get('elements'):
                                for vod in data['result']['elements']:
                                    dj = vod.get('duanjuVo', {})
                                    if dj:
                                        results.append({
                                            'vod_id': f"{plat_id}@{dj.get('duanjuId', '')}#{dj.get('source', '')}",
                                            'vod_name': dj.get('title', ''),
                                            'vod_pic': dj.get('coverImageUrl', ''),
                                            'vod_remarks': f"西饭短剧 | {dj.get('total', 0)}集"
                                        })
                    except Exception as e:
                        print(f"⚠️ 西饭短剧搜索失败: {str(e)}")
                        pass
                
                elif plat_id == '软鸭':
                    try:
                        url = f"{plat_config['host']}{plat_config['search']}/?keyword={quote(search_key)}&page={page}"
                        headers = self.aggConfig['headers']['default']
                        response = requests.get(url, headers=headers, timeout=search_timeout)
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('data'):
                                for item in data['data']:
                                    purl = f"{item.get('title', '')}@{item.get('cover', '')}@{item.get('author', '')}@{item.get('type', '')}@{item.get('desc', '')}@{item.get('book_id', '')}"
                                    results.append({
                                        'vod_id': f"{plat_id}@{quote(purl)}",
                                        'vod_name': item.get('title', ''),
                                        'vod_pic': item.get('cover', ''),
                                        'vod_remarks': f"软鸭短剧 | {item.get('type', '')}"
                                    })
                    except Exception as e:
                        print(f"⚠️ 软鸭短剧搜索失败: {str(e)}")
                        pass
                
                elif plat_id == '七猫':
                    try:
                        sign_str = f"operation=2playlet_privacy=1search_word={search_key}{self.aggConfig['keys']}"
                        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
                        url = f"{plat_config['host']}{plat_config['search']}?search_word={quote(search_key)}&playlet_privacy=1&operation=2&sign={sign}"
                        headers = self._get_header_x()
                        response = requests.get(url, headers=headers, timeout=search_timeout)
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('data') and data['data'].get('list'):
                                for item in data['data']['list']:
                                    results.append({
                                        'vod_id': f"{plat_id}@{quote(item.get('playlet_id', ''))}",
                                        'vod_name': item.get('title', ''),
                                        'vod_pic': item.get('image_link', ''),
                                        'vod_remarks': f"七猫短剧 | {item.get('total_episode_num', 0)}集"
                                    })
                    except Exception as e:
                        print(f"⚠️ 七猫短剧搜索失败: {str(e)}")
                        pass
                
                elif plat_id == '牛牛':
                    try:
                        body = {
                            'condition': {'name': search_key, 'typeId': 'S1'},
                            'pageNum': page,
                            'pageSize': search_limit
                        }
                        response = requests.post(
                            plat_config['host'] + plat_config['search'],
                            headers=self.aggConfig['headers']['niuniu'],
                            json=body,
                            timeout=search_timeout
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('data') and data['data'].get('records'):
                                for item in data['data']['records']:
                                    results.append({
                                        'vod_id': f"{plat_id}@{item.get('id', '')}",
                                        'vod_name': item.get('name', ''),
                                        'vod_pic': item.get('cover', ''),
                                        'vod_remarks': f"牛牛短剧 | {item.get('totalEpisode', 0)}集"
                                    })
                    except Exception as e:
                        print(f"⚠️ 牛牛短剧搜索失败: {str(e)}")
                        pass
                
                elif plat_id == '围观':
                    try:
                        body = {
                            'audience': '',
                            'page': int(page),
                            'pageSize': search_limit,
                            'searchWord': search_key,
                            'subject': ''
                        }
                        response = requests.post(
                            plat_config['host'] + plat_config['search'],
                            headers=self.aggConfig['headers']['default'],
                            json=body,
                            timeout=search_timeout
                        )
                        if response.status_code == 200:
                            data = response.json()
                            if data and data.get('data') and isinstance(data['data'], list):
                                for item in data['data']:
                                    results.append({
                                        'vod_id': f"{plat_id}@{item.get('oneId', '')}",
                                        'vod_name': item.get('title', ''),
                                        'vod_pic': item.get('vertPoster', ''),
                                        'vod_remarks': f"围观短剧 | {item.get('episodeCount', 0)}集"
                                    })
                    except Exception as e:
                        print(f"⚠️ 围观短剧搜索失败: {str(e)}")
                        pass
                
                elif plat_id == '碎片':
                    try:
                        open_id = hashlib.md5(self._guid().encode('utf-8')).hexdigest()[:16]
                        api = "https://free-api.bighotwind.cc/papaya/papaya-api/oauth2/uuid"
                        body = {"openId": open_id}
                        key = self._enc_hex(str(int(time.time() * 1000)))
                        headers = {'Content-Type': 'application/json', 'key': key}
                        token_response = requests.post(api, headers=headers, json=body, timeout=search_timeout)
                        
                        if token_response.status_code == 200:
                            token_data = token_response.json()
                            token = token_data.get('data', {}).get('token', '')
                            
                            if token:
                                headers = self.aggConfig['headers']['default'].copy()
                                headers['Authorization'] = token
                                url = f"{plat_config['host']}{plat_config['search']}?type=5&tagId=&pageNum={page}&pageSize={search_limit}&title={quote(search_key)}"
                                response = requests.get(url, headers=headers, timeout=search_timeout)
                                
                                if response.status_code == 200:
                                    data = response.json()
                                    if data and data.get('list'):
                                        for item in data['list']:
                                            compound_id = f"{item.get('itemId', '')}@{item.get('videoCode', '')}"
                                            results.append({
                                                'vod_id': f"{plat_id}@{compound_id}",
                                                'vod_name': item.get('title', ''),
                                                'vod_pic': f"https://speed.rouzwv.com/papaya/papaya-file/files/download/{item.get('imageKey', '')}/{item.get('imageName', '')}",
                                                'vod_remarks': f"碎片剧场 | {item.get('episodesMax', 0)}集"
                                            })
                    except:
                        pass
                
                print(f"✅ {plat_name} 搜索完成: 找到 {len(results)} 个结果")
                return {'platform': plat_name, 'results': results}
                
            except Exception as e:
                # 打印错误信息便于调试
                print(f"❌ {plat_name} 搜索失败: {str(e)}")
                return {'platform': plat_name, 'results': []}
        
        # 使用线程池并发执行搜索
        print(f"🔍 开始并发搜索 {len(self.aggConfig['platformList'])} 个平台")
        with ThreadPoolExecutor(max_workers=len(self.aggConfig['platformList'])) as executor:
            future_to_platform = {executor.submit(search_platform, platform): platform for platform in self.aggConfig['platformList']}
            
            for future in concurrent.futures.as_completed(future_to_platform):
                platform = future_to_platform[future]
                try:
                    search_result = future.result()
                    if search_result and search_result.get('results'):
                        result['list'].extend(search_result['results'])
                        print(f"✅ 已添加 {platform['name']} 的 {len(search_result['results'])} 个结果")
                except Exception as e:
                    # 平台搜索失败，继续处理其他平台
                    print(f"❌ {platform['name']} 搜索结果处理失败: {str(e)}")
                    pass
        
        print(f"🔍 搜索完成: 共找到 {len(result['list'])} 个原始结果")
        
        # JavaScript版本中的过滤：只保留标题中包含关键词的结果
        if True:  # 默认启用搜索匹配
            filtered_results = []
            for item in result['list']:
                title = item.get('vod_name', '').lower()
                if search_key.lower() in title:
                    filtered_results.append(item)
            
            # 打印调试信息
            print(f"🔍 搜索过滤: 原始结果 {len(result['list'])} 条，过滤后 {len(filtered_results)} 条")
            result['list'] = filtered_results
        
        # 去重
        seen = set()
        unique_videos = []
        for video in result['list']:
            if video['vod_id'] not in seen:
                seen.add(video['vod_id'])
                unique_videos.append(video)
        
        result['list'] = unique_videos
        result['total'] = len(unique_videos)
        
        print(f"🎉 最终搜索结果: {len(unique_videos)} 个去重后的结果")
        return result
    
    def localProxy(self, params):
        if params['type'] == "m3u8":
            return self.proxyM3u8(params)
        elif params['type'] == "media":
            return self.proxyMedia(params)
        elif params['type'] == "ts":
            return self.proxyTs(params)
        return None
    
    # 辅助函数
    def _md5(self, text):
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _guid(self):
        return str(uuid.uuid4())
    
    def _enc_hex(self, txt):
        # 简化版AES加密
        return hashlib.md5(txt.encode('utf-8')).hexdigest()
    
    def _get_header_x(self):
        # 七猫请求头生成
        try:
            # 生成七猫参数
            session_id = str(int(time.time()))
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
                "session-id": session_id
            }
            
            json_str = json.dumps(data)
            base64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            
            qm_params = ''
            for c in base64_str:
                qm_params += self.aggConfig['charMap'].get(c, c)
            
            params_str = f"AUTHORIZATION=app-version=10001application-id=com.duoduo.readchannel=unknownis-white=net-env=5platform=androidqm-params={qm_params}reg={self.aggConfig['keys']}"
            sign = hashlib.md5(params_str.encode('utf-8')).hexdigest()
            
            return {
                'net-env': '5', 'reg': '', 'channel': 'unknown', 'is-white': '', 'platform': 'android',
                'application-id': 'com.duoduo.read', 'authorization': '', 'app-version': '10001',
                'user-agent': 'webviewversion/0', 'qm-params': qm_params, 'sign': sign
            }
        except:
            return self.aggConfig['headers']['default'].copy()