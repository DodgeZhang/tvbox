# -*- coding: utf-8 -*-
import json
import time
import hashlib
import random
import requests
import re
import base64
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "火云4K"

    def init(self, extend=""):
        """初始化，支持动态修改host"""
        self.host = "https://bubutv.top"
        if isinstance(extend, str) and extend.startswith('http'):
            self.host = extend.strip().rstrip('/')
        
        # API签名配置
        self.pkg = "com.sunshine.tv"
        self.ver = "4"
        self.device_id = None
        self.device_cache_key = "com.sunshine.tv_3qys_B7k7Dt56Rn"
        self.finger = "SF-C3B2B41F6EFFFF9869176CF68F6790E8F07506FC88632C94B4F5F0430D5498CA"
        self.sk = "SK-thanks"
        
        # ==================== 4K解析配置（多接口备用） ====================
        self.parse_apis = [
            {
                'url': 'https://zy.qiaoji8.com/xiafan.php?url=',
                'name': '巧技解析',
                'headers': {'User-Agent': 'okhttp/4.9.1'},
                'priority': 1
            },
            {
                'url': 'https://jx.aidouer.net/?url=',
                'name': '爱豆解析',
                'headers': {'User-Agent': 'Mozilla/5.0'},
                'priority': 2
            },
            {
                'url': 'https://jx.parwix.com:4433/player/?url=',
                'name': 'Parwix解析',
                'headers': {'User-Agent': 'Mozilla/5.0'},
                'priority': 3
            },
            {
                'url': 'https://jx.booex.cn/?url=',
                'name': 'Booex解析',
                'headers': {'User-Agent': 'Mozilla/5.0'},
                'priority': 4
            },
            {
                'url': 'https://jx.aidouer.net/?url=',
                'name': '备用解析',
                'headers': {'User-Agent': 'Mozilla/5.0'},
                'priority': 5
            }
        ]
        self.parse_flags = ['QD4K', 'iyf', 'duanju', 'gzcj', 'GTV', 'GZYS', 'weggz', 'Ace']
        
        # 分类筛选器
        self.filters = {
            "电影": [
                {"key": "sort", "name": "排序", "value": [{"n": "最热", "v": "hits"}, {"n": "最新", "v": "addtime"}, {"n": "评分", "v": "score"}]},
                {"key": "class", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "科幻", "v": "科幻"}, {"n": "悬疑", "v": "悬疑"}, {"n": "恐怖", "v": "恐怖"}, {"n": "犯罪", "v": "犯罪"}, {"n": "战争", "v": "战争"}, {"n": "动画", "v": "动画"}, {"n": "剧情", "v": "剧情"}, {"n": "纪录", "v": "纪录"}]},
                {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"}, {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"}, {"n": "印度", "v": "印度"}, {"n": "其它", "v": "其它"}]},
                {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2017, -1)]}
            ],
            "电视剧": [
                {"key": "sort", "name": "排序", "value": [{"n": "最热", "v": "hits"}, {"n": "最新", "v": "addtime"}, {"n": "评分", "v": "score"}]},
                {"key": "class", "name": "类型", "value": [{"n": "全部", "v": ""}, {"n": "动作", "v": "动作"}, {"n": "喜剧", "v": "喜剧"}, {"n": "爱情", "v": "爱情"}, {"n": "科幻", "v": "科幻"}, {"n": "悬疑", "v": "悬疑"}, {"n": "恐怖", "v": "恐怖"}, {"n": "犯罪", "v": "犯罪"}, {"n": "战争", "v": "战争"}, {"n": "动画", "v": "动画"}, {"n": "剧情", "v": "剧情"}, {"n": "纪录", "v": "纪录"}]},
                {"key": "area", "name": "地区", "value": [{"n": "全部", "v": ""}, {"n": "大陆", "v": "大陆"}, {"n": "香港", "v": "香港"}, {"n": "台湾", "v": "台湾"}, {"n": "美国", "v": "美国"}, {"n": "韩国", "v": "韩国"}, {"n": "日本", "v": "日本"}, {"n": "泰国", "v": "泰国"}, {"n": "英国", "v": "英国"}, {"n": "法国", "v": "法国"}, {"n": "印度", "v": "印度"}, {"n": "其它", "v": "其它"}]},
                {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2017, -1)]}
            ]
        }

    # ==================== 工具函数 ====================
    
    def _get_device_id(self):
        """获取或生成设备ID"""
        if not self.device_id:
            try:
                import storage
                self.device_id = storage.get(self.device_cache_key)
            except:
                pass
            if not self.device_id or len(self.device_id) != 16:
                self.device_id = ''.join(random.choice('0123456789abcdef') for _ in range(16))
                try:
                    import storage
                    storage.set(self.device_cache_key, self.device_id)
                except:
                    pass
        return self.device_id

    def _get_headers(self):
        """生成带签名的请求头"""
        timestamp = str(int(time.time()))
        nonce = ''.join(random.choice('0123456789') for _ in range(3))
        device_id = self._get_device_id()
        
        sign_str = f"finger={self.finger}&id={self.pkg}&nonce={nonce}&sk={self.sk}&time={timestamp}&v={self.ver}"
        sign = hashlib.sha256(sign_str.encode()).hexdigest().upper()
        
        return {
            'User-Agent': 'okhttp/4.12.0',
            'Accept': 'application/json',
            'x-aid': self.pkg,
            'x-ave': self.ver,
            'x-time': timestamp,
            'x-nonc': nonce,
            'x-sign': sign,
            'x-device-id': device_id,
            'x-device-brand': 'vivo',
            'x-device-model': 'V2309A',
            'x-update-id': '0245861b-2ebf-5524-389d-f983830651ec'
        }

    def _fetch_json(self, url, params=None):
        """请求JSON数据"""
        try:
            resp = requests.get(url, headers=self._get_headers(), params=params, timeout=15)
            resp.encoding = 'utf-8'
            return resp.json()
        except Exception as e:
            print(f"[火云4K] 请求异常: {e}")
            return None

    def _build_vod(self, item):
        """构建标准视频对象"""
        return {
            'vod_id': str(item.get('vod_id', item.get('id', ''))),
            'vod_name': item.get('vod_name', item.get('title', item.get('name', '未命名'))),
            'vod_pic': item.get('vod_pic', item.get('pic', item.get('cover', ''))),
            'vod_remarks': item.get('vod_remarks', item.get('remarks', item.get('update_info', ''))),
            'vod_year': item.get('vod_year', item.get('year', ''))
        }

    # ==================== 4K解析核心函数（多接口备用） ====================
    
    def _parse_with_4k(self, url, flag=''):
        """使用4K解析接口解析视频 - 多接口备用"""
        print(f"[火云4K] 开始4K解析: {url[:100]}, flag={flag}")
        
        # 如果URL已经是视频直链，直接返回
        if self.isVideoFormat(url):
            print(f"[火云4K] URL已是直链: {url[:100]}")
            return url
        
        # 按优先级尝试多个解析接口
        for api in sorted(self.parse_apis, key=lambda x: x.get('priority', 999)):
            try:
                parse_url = api['url'] + url
                print(f"[火云4K] 尝试解析接口 [{api['priority']}]: {api['name']}")
                print(f"[火云4K] 解析URL: {parse_url[:100]}")
                
                resp = requests.get(parse_url, headers=api['headers'], timeout=30)
                resp.encoding = 'utf-8'
                content = resp.text
                
                # 打印响应前200字符用于调试
                print(f"[火云4K] 响应内容前200字符: {content[:200]}")
                
                # 1. 尝试解析JSON
                try:
                    data = json.loads(content)
                    print(f"[火云4K] JSON解析成功")
                    
                    # 尝试各种可能的字段
                    for key in ['url', 'playUrl', 'video', 'data', 'videos', 'm3u8', 'mp4']:
                        if key in data:
                            if isinstance(data[key], str) and data[key].startswith('http'):
                                if self.isVideoFormat(data[key]) or '.m3u8' in data[key]:
                                    print(f"[火云4K] 从JSON获取到视频地址: {data[key][:100]}")
                                    return data[key]
                        elif isinstance(data.get(key), dict):
                            for sub_key in ['url', 'playUrl', 'video']:
                                if sub_key in data[key] and isinstance(data[key][sub_key], str):
                                    if data[key][sub_key].startswith('http'):
                                        print(f"[火云4K] 从JSON嵌套获取到视频地址: {data[key][sub_key][:100]}")
                                        return data[key][sub_key]
                except:
                    pass
                
                # 2. 提取iframe中的播放地址
                iframe_match = re.search(r'<iframe[^>]*src=["\']([^"\']+)["\']', content)
                if iframe_match:
                    iframe_url = iframe_match.group(1)
                    if iframe_url.startswith('//'):
                        iframe_url = 'https:' + iframe_url
                    print(f"[火云4K] 找到iframe: {iframe_url[:100]}")
                    
                    # 递归解析iframe
                    try:
                        iframe_resp = requests.get(iframe_url, headers=api['headers'], timeout=30)
                        iframe_content = iframe_resp.text
                        
                        # 在iframe中查找视频地址
                        video_url = self._extract_video_url(iframe_content)
                        if video_url:
                            print(f"[火云4K] 从iframe获取到视频地址: {video_url[:100]}")
                            return video_url
                    except:
                        pass
                
                # 3. 提取视频地址
                video_url = self._extract_video_url(content)
                if video_url:
                    print(f"[火云4K] 从页面提取到视频地址: {video_url[:100]}")
                    return video_url
                
                # 4. 提取mu参数（base64编码）
                mu_match = re.search(r'[?&]mu=([^&\s"\']+)', content)
                if mu_match:
                    mu = mu_match.group(1)
                    try:
                        decoded = base64.b64decode(mu + '=' * (4 - len(mu) % 4)).decode('utf-8')
                        if decoded.startswith('http') and (self.isVideoFormat(decoded) or '.m3u8' in decoded):
                            print(f"[火云4K] Base64解码获取到视频地址: {decoded[:100]}")
                            return decoded
                    except:
                        pass
                
                print(f"[火云4K] {api['name']} 未找到视频地址，尝试下一接口")
                
            except Exception as e:
                print(f"[火云4K] {api['name']} 解析异常: {e}")
                continue
        
        print(f"[火云4K] 所有解析接口均失败")
        return None

    def _extract_video_url(self, content):
        """从HTML内容中提取视频地址"""
        # 匹配m3u8
        m3u8_patterns = [
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+/hls/[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+/index\.m3u8[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+/playlist\.m3u8[^\s"\'<>]*)',
        ]
        for pattern in m3u8_patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        
        # 匹配mp4
        mp4_patterns = [
            r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+/video/[^\s"\'<>]+\.mp4[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+/download/[^\s"\'<>]+\.mp4[^\s"\'<>]*)',
        ]
        for pattern in mp4_patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        
        # 匹配flv
        flv_match = re.search(r'(https?://[^\s"\'<>]+\.flv[^\s"\'<>]*)', content)
        if flv_match:
            return flv_match.group(1)
        
        # 匹配ts
        ts_match = re.search(r'(https?://[^\s"\'<>]+\.ts[^\s"\'<>]*)', content)
        if ts_match:
            return ts_match.group(1)
        
        return None

    def _should_use_4k(self, url, flag=''):
        """判断是否使用4K解析"""
        # 如果flag在解析列表中
        if flag in self.parse_flags:
            print(f"[火云4K] flag匹配: {flag}")
            return True
        
        # 如果URL包含主流视频网站
        keywords = ['iqiyi', 'v.qq', 'youku', 'mgtv', 'bilibili', 'le.com', 'sohu.com', 'pptv', 'cntv', 'tudou']
        for keyword in keywords:
            if keyword in url.lower():
                print(f"[火云4K] URL包含关键词: {keyword}")
                return True
        
        # 如果URL不是直链，也不是相对路径
        if url.startswith('http') and not self.isVideoFormat(url):
            print(f"[火云4K] URL不是直链: {url[:50]}")
            return True
        
        return False

    # ==================== 首页接口 ====================

    def homeContent(self, filter):
        """首页内容"""
        data = self._fetch_json(f"{self.host}/api.php/app/index/home")
        result = {"class": [], "list": []}
        
        if data and data.get('data'):
            categories = data['data'].get('categories', [])
            
            # 分类列表
            for cat in categories:
                type_name = cat.get('type_name', '')
                if type_name:
                    result['class'].append({'type_id': type_name, 'type_name': type_name})
            
            # 视频列表
            for cat in categories:
                for item in cat.get('videos', []):
                    result['list'].append(self._build_vod(item))
            
            # 筛选器
            if filter:
                result['filters'] = self.filters
        
        return result

    def homeVideoContent(self):
        """首页推荐（备用）"""
        return {"list": []}

    # ==================== 分类接口 ====================

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容"""
        try:
            pg = int(pg) if pg else 1
            extend = extend if isinstance(extend, dict) else {}
            
            # 构建请求参数
            params = {'type_name': tid, 'page': pg, 'sort': extend.get('sort', 'hits')}
            for key in ['class', 'area', 'year']:
                if key in extend and extend[key]:
                    params[key] = extend[key]
            
            data = self._fetch_json(f"{self.host}/api.php/app/filter/vod", params)
            
            videos = []
            if data:
                vod_data = data.get('data', [])
                if not isinstance(vod_data, list):
                    vod_data = vod_data.get('list', []) or vod_data.get('data', [])
                for item in vod_data:
                    videos.append(self._build_vod(item))
            
            # 修复分页：接口pageCount固定为1
            return {
                'list': videos,
                'page': pg,
                'pagecount': pg + 1 if videos else pg,
                'limit': 24,
                'total': 999999 if videos else pg * 24
            }
        except Exception as e:
            print(f"[火云4K] 分类异常: {e}")
            return {'list': [], 'page': pg, 'pagecount': 0, 'limit': 24, 'total': 0}

    # ==================== 详情接口 ====================

    def detailContent(self, ids):
        """获取详情"""
        result = []
        for vid in ids:
            data = self._fetch_json(f"{self.host}/api.php/app/vod/get_detail", {'vod_id': vid})
            if not data or not data.get('data'):
                continue
            
            raw = data['data'][0]
            vodplayer = data.get('vodplayer', [])
            
            # 解析播放源
            raw_shows = raw.get('vod_play_from', '').split('$$$')
            raw_urls = raw.get('vod_play_url', '').split('$$$')
            
            shows, play_urls = [], []
            for i, show_code in enumerate(raw_shows):
                if i >= len(raw_urls):
                    break
                
                urls_str = raw_urls[i]
                need_parse, is_show, name = 0, 0, show_code
                
                for player in vodplayer:
                    if player.get('from') == show_code:
                        is_show, need_parse = 1, player.get('decode_status', 0)
                        if show_code.lower() != player.get('show', '').lower():
                            name = f"{player.get('show', '')} ({show_code})"
                        break
                
                if is_show:
                    urls = []
                    for url_item in urls_str.split('#'):
                        if '$' in url_item:
                            episode, url_path = url_item.split('$', 1)
                            urls.append(f"{episode}${show_code}@{need_parse}@{url_path}")
                    if urls:
                        play_urls.append('#'.join(urls))
                        shows.append(name)
            
            result.append({
                'vod_id': str(raw.get('vod_id', '')),
                'vod_name': raw.get('vod_name', ''),
                'vod_pic': raw.get('vod_pic', ''),
                'vod_remarks': raw.get('vod_remarks', ''),
                'vod_year': raw.get('vod_year', ''),
                'vod_area': raw.get('vod_area', ''),
                'vod_actor': raw.get('vod_actor', ''),
                'vod_director': raw.get('vod_director', ''),
                'vod_content': raw.get('vod_content', ''),
                'vod_play_from': '$$$'.join(shows),
                'vod_play_url': '$$$'.join(play_urls)
            })
        
        return {'list': result}

    # ==================== 播放接口（多接口备用） ====================

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址 - 多接口备用"""
        print(f"[火云4K] 播放请求: flag={flag}, id={id[:100]}")
        
        try:
            parts = id.split('@')
            
            # 格式不标准时的处理
            if len(parts) < 3:
                print(f"[火云4K] 格式不标准，尝试直接解析")
                # 尝试4K解析
                if self._should_use_4k(id, flag):
                    parsed = self._parse_with_4k(id, flag)
                    if parsed:
                        return {
                            'parse': 0,
                            'url': parsed,
                            'header': {'User-Agent': 'okhttp/4.9.1'}
                        }
                # 交给播放器处理
                return {
                    'parse': 1,
                    'url': id,
                    'header': {'User-Agent': 'com.sunshine.tv/1.2.0'}
                }
            
            play_from, need_parse, raw_url = parts[0], parts[1], parts[2]
            print(f"[火云4K] 解析参数: play_from={play_from}, need_parse={need_parse}")
            print(f"[火云4K] 原始URL: {raw_url[:100]}")
            
            # ===== 优先4K解析（多接口备用） =====
            if self._should_use_4k(raw_url, play_from):
                parsed = self._parse_with_4k(raw_url, play_from)
                if parsed:
                    print(f"[火云4K] 4K解析成功: {parsed[:100]}")
                    return {
                        'parse': 0,
                        'url': parsed,
                        'header': {'User-Agent': 'okhttp/4.9.1'}
                    }
                else:
                    print(f"[火云4K] 4K解析失败，尝试原API解码")
            
            # ===== 原API解码 =====
            url = ''
            if need_parse == '1':
                try:
                    api_url = f"{self.host}/api.php/app/decode/url/"
                    resp = requests.get(api_url, headers=self._get_headers(), 
                                      params={'url': raw_url, 'vodFrom': play_from}, timeout=30)
                    resp.encoding = 'utf-8'
                    json_data = resp.json()
                    if json_data.get('data', '').startswith('http'):
                        url = json_data['data']
                        print(f"[火云4K] 原API解码成功: {url[:100]}")
                except Exception as e:
                    print(f"[火云4K] 原API解码异常: {e}")
            
            # ===== 使用原始地址 =====
            if not url:
                url = raw_url
                print(f"[火云4K] 使用原始地址: {url[:100]}")
                # 判断是否需要播放器解析
                if re.search(r'(www\.iqiyi|v\.qq|v\.youku|www\.mgtv|www\.bilibili)\.com', raw_url):
                    print(f"[火云4K] 交给播放器嗅探")
                    return {
                        'parse': 1,
                        'url': url,
                        'header': {'User-Agent': 'com.sunshine.tv/1.2.0'}
                    }
            
            return {
                'parse': 0,
                'url': url,
                'header': {'User-Agent': 'com.sunshine.tv/1.2.0'}
            }
            
        except Exception as e:
            print(f"[火云4K] 播放异常: {e}")
            return {'parse': 0, 'url': ''}

    # ==================== 搜索接口 ====================

    def searchContent(self, key, quick, pg="1"):
        """搜索"""
        try:
            pg = int(pg) if pg else 1
            if not key:
                return {'list': [], 'page': 1, 'pagecount': 0, 'limit': 0, 'total': 0}
            
            data = self._fetch_json(f"{self.host}/api.php/app/search/index", 
                                   {'wd': key, 'page': pg, 'limit': 15})
            
            videos = []
            if data:
                for item in data.get('data', []):
                    videos.append(self._build_vod(item))
            
            return {
                'list': videos,
                'page': pg,
                'pagecount': data.get('pageCount', 0) if data else 0,
                'limit': len(videos),
                'total': len(videos)
            }
        except Exception as e:
            print(f"[火云4K] 搜索异常: {e}")
            return {'list': [], 'page': 1, 'pagecount': 0, 'limit': 0, 'total': 0}

    # ==================== 辅助方法 ====================

    def isVideoFormat(self, url):
        """判断URL是否为视频直链"""
        if not url or not isinstance(url, str):
            return False
        video_exts = ['.m3u8', '.mp4', '.flv', '.ts', '.mkv', '.avi', '.mov', '.webm']
        return any(url.lower().endswith(ext) for ext in video_exts)

    def manualVideoCheck(self):
        pass

    def localProxy(self, params):
        return None

    def destroy(self):
        pass