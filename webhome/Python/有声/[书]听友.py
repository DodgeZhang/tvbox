import re
import sys
import json
import time
import hashlib
import requests
from urllib import parse
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider as BaseSpider

# 可选：如果安装了 cryptography 库，可以支持 XChaCha20-Poly1305
try:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    HAS_XCHACHA = True
except ImportError:
    HAS_XCHACHA = False

class Spider(BaseSpider):

    def getName(self):
        return self.name

    def init(self, extend=''):
        self.name = '听友FM'
        self.site = 'https://tingyou.fm'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36',
            'Referer': self.site + '/',
            'Origin': self.site,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        # 硬编码的认证信息（仅供测试，建议通过环境变量覆盖）
        self.hardcoded_auth = 'Bearer gAAAAABpxTyveIsV3svITKMLKF6NdvuVhbJzxnWPJFmeav8M502s6toC4ryey8_DGOVK62SyVzJ1eDpcYA7Snr8kkcp5V40NaDyAudniva8y-Ac7MOBxPS9Ly1hlXxJ86s3xO9eg8HW9OPtoPIAIVJu19MSWo52zlVLeBlMBO903FQ-ZJBCVZuZdzg_Cok1d1_-C819LqDAfh_RzkMQmzBYxa6yCnhh_VImejRNaqSyb8sNYf-zYl009OaDGLNG8srEhaix7sVlN55n_9lhoxEVontCRN8rdaA=='
        self.hardcoded_cookie = 'dfp=f-c28yu:f-FTCFtTJZeXVY2UuWHmawNVQqrdGrZPVkiLIbYEqzXTnAgPfIngVZ4rn1sO+Y0AaxEryBUXuyhA5JUyUw7x0NcW/UEhTsbrYcpf30YWJPMcuN/edHp0T/fMMcMC07yROtEupjp6qCgfAZkU7zlDvWRx3cGG90tcQvvMXkEiCm4qKaq8zTTCTIAKeWjVdIjzis; Hm_lvt_487a45d5a76f87740d9bd6c64551f918=1774497846,1774517403,1774531868; HMACCOUNT=6848F17C0F59F642; Hm_lpvt_487a45d5a76f87740d9bd6c64551f918=1774533196'

        # AES-GCM 密钥（十六进制）
        self.payload_key_hex = 'ea9d9d4f9a983fe6f6382f29c7b46b8d6dc47abc6da36662e6ddff8c78902f65'
        self.payload_version = 1

    def get_auth_token(self):
        import os
        return os.environ.get('TINGYOU_AUTH') or os.environ.get('TINGYOU_ANON_AUTH') or self.hardcoded_auth

    def get_cookie(self):
        import os
        return os.environ.get('TINGYOU_COOKIE') or os.environ.get('TINGYOU_ANON_COOKIE') or self.hardcoded_cookie

    def hex_to_bytes(self, hex_str):
        hex_str = hex_str.strip()
        return bytes.fromhex(hex_str)

    def bytes_to_hex(self, byte_data):
        return byte_data.hex()

    def decrypt_payload_hex(self, hex_data):
        raw = self.hex_to_bytes(hex_data)
        if len(raw) < 29:
            raise ValueError('payload too short')
        version = raw[0]
        key_bytes = self.hex_to_bytes(self.payload_key_hex)

        if version == 1:
            for iv_start, cipher_start in [(1, 13), (0, 12), (2, 14)]:
                try:
                    iv = raw[iv_start:iv_start+12]
                    ciphertext = raw[cipher_start:]
                    cipher = AES.new(key_bytes, AES.MODE_GCM, nonce=iv)
                    plain = cipher.decrypt(ciphertext)
                    try:
                        plain = unpad(plain, 16)
                    except:
                        pass
                    return plain.decode('utf-8')
                except Exception:
                    continue
            raise Exception('v1 decrypt failed')
        elif version == 2:
            if not HAS_XCHACHA:
                raise Exception('version=2 response requires cryptography library')
            nonce = raw[1:25]
            ciphertext = raw[25:]
            reversed_cipher = ciphertext[::-1]
            for use_reverse, use_aad in [(True, False), (False, False), (True, True), (False, True)]:
                try:
                    aad = raw[:1] if use_aad else None
                    ctext = reversed_cipher if use_reverse else ciphertext
                    short_nonce = nonce[:12]
                    chacha = ChaCha20Poly1305(key_bytes)
                    plain = chacha.decrypt(short_nonce, ctext, aad)
                    return plain.decode('utf-8')
                except Exception:
                    continue
            raise Exception('v2 decrypt failed')
        else:
            raise Exception('unsupported payload version: {}'.format(version))

    def api_request(self, method, path, body=None, extra_headers=None):
        url = path if path.startswith('http') else self.site + (path if path.startswith('/') else '/' + path)
        headers = self.headers.copy()
        headers.update(extra_headers or {})
        headers['X-Payload-Version'] = str(self.payload_version)
        req_data = None
        if body is not None:
            plain = body if isinstance(body, str) else json.dumps(body)
            req_data = plain
            headers['Content-Type'] = 'text/plain'

        resp = requests.request(method, url, headers=headers, data=req_data, timeout=20)
        data = resp.text
        try:
            data_json = resp.json()
        except:
            data_json = data

        if isinstance(data_json, dict) and 'payload' in data_json and isinstance(data_json['payload'], str):
            try:
                plain = self.decrypt_payload_hex(data_json['payload'])
                try:
                    data_json = json.loads(plain)
                except:
                    data_json = plain
            except Exception as e:
                print('decrypt error:', e)
                raise

        if isinstance(data, str) and re.match(r'^[0-9a-fA-F]+$', data) and len(data) > 32:
            try:
                plain = self.decrypt_payload_hex(data)
                try:
                    data_json = json.loads(plain)
                except:
                    data_json = plain
            except Exception:
                pass

        if resp.status_code >= 400:
            raise Exception('HTTP {}: {}'.format(resp.status_code, str(data_json)[:500]))
        return data_json

    def api_post(self, name_or_path, body, extra_headers=None):
        path = name_or_path
        if not path.startswith('/'):
            path = '/api/' + path.lstrip('/')
        return self.api_request('POST', path, body, extra_headers)

    def decode_nuxt_value(self, table, node, seen=None):
        """解码 NUXT 数据中的响应式包装"""
        if seen is None:
            seen = {}
        
        markers = {"ShallowReactive", "Reactive", "Ref", "EmptyRef", "Set", "Map", "Date", "RegExp", "BigInt", "null", "undefined", "NaN", "-0", "Infinity", "-Infinity"}
        
        def inner(value):
            if isinstance(value, int) and value >= 0 and value < len(table):
                if value in seen:
                    return seen[value]
                raw = table[value]
                
                if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], str) and raw[0] in markers:
                    marker = raw[0]
                    if marker in ["ShallowReactive", "Reactive", "Ref"]:
                        result = inner(raw[1]) if len(raw) > 1 else None
                        seen[value] = result
                        return result
                    if marker in ["EmptyRef", "null", "undefined", "NaN"]:
                        seen[value] = None
                        return None
                
                if isinstance(raw, list):
                    out = []
                    seen[value] = out
                    for item in raw:
                        out.append(inner(item))
                    return out
                
                if isinstance(raw, dict):
                    out = {}
                    seen[value] = out
                    for k, v in raw.items():
                        out[k] = inner(v)
                    return out
                
                seen[value] = raw
                return raw
            
            if isinstance(value, list):
                return [inner(item) for item in value]
            if isinstance(value, dict):
                out = {}
                for k, v in value.items():
                    out[k] = inner(v)
                return out
            return value
        
        return inner(node)

    def parse_nuxt_home_data(self, html):
        """解析首页数据，获取各个分类的专辑列表"""
        match = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', html, re.DOTALL)
        if not match:
            return None
        
        try:
            payload = json.loads(match.group(1))
            root = self.decode_nuxt_value(payload, 1)
            
            # 根据您提供的数据结构，首页数据在 root.data 中
            data = root.get('data', {})
            
            # 提取各个 tab 下的专辑
            result = {
                'latest': [],   # 最新
                'hot': [],      # 最热
                'recommend': [], # 推荐
                'serial': [],   # 连载
                'story': []     # 故事
            }
            
            # 处理首页各个模块的 albums 数据
            for tab in ['latest', 'hot', 'recommend', 'serial', 'story']:
                tab_data = data.get(f'index-home-tabs', {}).get(tab, {})
                items = tab_data.get('items', [])
                for item in items:
                    if isinstance(item, dict) and 'id' in item:
                        album = {
                            'vod_id': str(item.get('id')),
                            'vod_name': item.get('title', ''),
                            'vod_pic': item.get('cover', ''),
                            'vod_remarks': f"{item.get('chapterTotal', 0)}期" if item.get('chapterTotal') else ''
                        }
                        if album['vod_pic'] and not album['vod_pic'].startswith('http'):
                            album['vod_pic'] = self.site + album['vod_pic']
                        result[tab].append(album)
            
            return result
        except Exception as e:
            print('parse_nuxt_home_data error:', e)
            return None

    def parse_nuxt_category_data(self, html, category_id):
        """解析分类页面数据"""
        match = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', html, re.DOTALL)
        if not match:
            return None
        
        try:
            payload = json.loads(match.group(1))
            root = self.decode_nuxt_value(payload, 1)
            
            # 分类数据通常在 root.data 中，key 为 categoryAlbums-{id}
            data = root.get('data', {})
            data_key = f'categoryAlbums-{category_id}'
            category_data = data.get(data_key, {})
            
            items = category_data.get('data', [])
            
            albums = []
            for item in items:
                if isinstance(item, dict) and 'id' in item:
                    status_text = "连载中" if item.get('status') == 1 else "已完结" if item.get('status') == 0 else ""
                    remark_parts = []
                    if item.get('count'):
                        remark_parts.append(f"{item.get('count')}期")
                    if status_text:
                        remark_parts.append(status_text)
                    if item.get('teller'):
                        remark_parts.append(item.get('teller'))
                    
                    album = {
                        'vod_id': str(item.get('id')),
                        'vod_name': item.get('title', ''),
                        'vod_pic': item.get('cover_url', ''),
                        'vod_remarks': ' · '.join(remark_parts)
                    }
                    if album['vod_pic'] and not album['vod_pic'].startswith('http'):
                        album['vod_pic'] = self.site + album['vod_pic']
                    albums.append(album)
            
            return {
                'page': category_data.get('page', 1),
                'pages': category_data.get('pages', 1),
                'total': category_data.get('total', len(albums)),
                'list': albums
            }
        except Exception as e:
            print('parse_nuxt_category_data error:', e)
            return None

    # ---------- 首页分类 ----------
    def homeContent(self, filter):
        class_list = []
        try:
            url = self.site + '/'
            resp = requests.get(url, headers=self.headers, timeout=15)
            html = resp.text
            
            # 从页面中提取分类链接
            pattern = r'<a[^>]*href=["\']/categories/(\d+)[^>]*>([^<]+)</a>'
            matches = re.findall(pattern, html)
            seen = set()
            for type_id, type_name in matches:
                if type_id in seen:
                    continue
                seen.add(type_id)
                if '全部分类' in type_name or type_name.strip() == '':
                    continue
                class_list.append({
                    'type_id': type_id,
                    'type_name': type_name.strip()
                })
            
            # 如果没有提取到，使用默认分类
            if not class_list:
                default_cats = [
                    {'type_id': '46', 'type_name': '有声小说'},
                    {'type_id': '11', 'type_name': '武侠小说'},
                    {'type_id': '19', 'type_name': '言情通俗'},
                    {'type_id': '21', 'type_name': '相声小品'},
                    {'type_id': '14', 'type_name': '恐怖惊悚'},
                    {'type_id': '17', 'type_name': '官场商战'},
                    {'type_id': '15', 'type_name': '历史军事'},
                    {'type_id': '9', 'type_name': '百家讲坛'}
                ]
                class_list = default_cats
        except Exception as e:
            print('homeContent error:', e)
            class_list = []
        return {"class": class_list, "filters": {}}

    # ---------- 首页视频推荐 ----------
    def homeVideoContent(self):
        videos = []
        try:
            url = self.site + '/'
            resp = requests.get(url, headers=self.headers, timeout=15)
            html = resp.text
            
            # 尝试解析 NUXT 数据
            nuxt_data = self.parse_nuxt_home_data(html)
            if nuxt_data:
                # 合并所有 tab 的数据，去重
                all_videos = []
                seen_ids = set()
                for tab in ['latest', 'hot', 'recommend', 'serial', 'story']:
                    for video in nuxt_data[tab]:
                        if video['vod_id'] not in seen_ids:
                            seen_ids.add(video['vod_id'])
                            all_videos.append(video)
                videos = all_videos[:50]
            
            # 如果没有 NUXT 数据，回退到 DOM 解析
            if not videos:
                pattern = r'<a[^>]*href=["\']/albums/(\d+)[^>]*>.*?<img[^>]*src=["\']([^"\']+)["\'][^>]*>.*?<p[^>]*>([^<]*)</p>'
                matches = re.findall(pattern, html, re.DOTALL)
                for vod_id, pic, name in matches[:50]:
                    if pic.startswith('data:'):
                        continue
                    videos.append({
                        'vod_id': vod_id,
                        'vod_name': name.strip() or f'专辑{vod_id}',
                        'vod_pic': pic if pic.startswith('http') else self.site + pic,
                        'vod_remarks': ''
                    })
        except Exception as e:
            print('homeVideoContent error:', e)
            return {'list': [], 'parse': 0, 'jx': 0}
        return {'list': videos, 'parse': 0, 'jx': 0}

    # ---------- 分类内容 ----------
    def categoryContent(self, cid, page, filter, ext):
        tid = ext.get('cid', cid)
        url = f"{self.site}/categories/{tid}?sort=comprehensive&page={page}"
        videos = []
        total = 0
        pagecount = 1
        
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            html = resp.text
            
            # 尝试解析 NUXT 数据
            category_data = self.parse_nuxt_category_data(html, tid)
            
            if category_data and category_data['list']:
                videos = category_data['list']
                total = category_data.get('total', len(videos))
                pagecount = category_data.get('pages', 1)
            else:
                # 回退到 DOM 解析
                pattern = r'<a[^>]*href=["\']/albums/(\d+)[^>]*>.*?<img[^>]*src=["\']([^"\']+)["\'][^>]*>.*?<p[^>]*>([^<]*)</p>'
                matches = re.findall(pattern, html, re.DOTALL)
                for vod_id, pic, name in matches[:50]:
                    if pic.startswith('data:'):
                        continue
                    videos.append({
                        'vod_id': vod_id,
                        'vod_name': name.strip() or f'专辑{vod_id}',
                        'vod_pic': pic if pic.startswith('http') else self.site + pic,
                        'vod_remarks': ''
                    })
                total = len(videos)
                pagecount = max(1, (total + 50 - 1) // 50) if videos else 1
                
        except Exception as e:
            print('categoryContent error:', e)
            return {'list': [], 'page': int(page), 'pagecount': 1, 'total': 0, 'msg': ''}
        
        return {
            'list': videos,
            'page': int(page),
            'pagecount': pagecount,
            'total': total,
            'parse': 0,
            'jx': 0
        }

    # ---------- 详情 ----------
    # ---------- 详情 ----------
    def detailContent(self, did):
        vid = did[0]
        info = []
        try:
            from bs4 import BeautifulSoup
            
            url = f"{self.site}/albums/{vid}"
            print(f"detail url: {url}")
            resp = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # 基础信息 - 从 album-pannel 获取
            panel = soup.find("section", class_="album-pannel")
            if panel:
                # 名称
                vod_name = panel.find("h1").get_text(strip=True) if panel.find("h1") else f"专辑{vid}"
                print(f"vod_name: {vod_name}")
                
                # 封面
                img = panel.find("img")
                vod_pic = img.get("src") or img.get("data-src") or ""
                if vod_pic.startswith("//"):
                    vod_pic = "https:" + vod_pic
                elif vod_pic.startswith("/"):
                    vod_pic = self.site + vod_pic
                print(f"vod_pic: {vod_pic[:100] if vod_pic else 'not found'}")
                
                # 简介 - 多种class尝试
                vod_content = ""
                for class_name in ["album-desc", "desc", "intro", "album-intro"]:
                    desc_elem = soup.find(class_=class_name)
                    if desc_elem:
                        vod_content = desc_elem.get_text(strip=True)
                        break
                if not vod_content:
                    # 尝试 meta description
                    meta_desc = soup.find("meta", {"name": "description"})
                    if meta_desc:
                        vod_content = meta_desc.get("content", "")
                print(f"vod_content: {vod_content[:100] if vod_content else 'not found'}")
                
                # 分类
                type_name = ""
                for span in panel.select(".pods span"):
                    txt = span.get_text(strip=True)
                    if txt.startswith("分类:"):
                        type_name = txt.replace("分类:", "").strip()
                        break
                print(f"type_name: {type_name}")
                
                # 章节列表 - 关键部分
                play_urls = []
                
                # 方式1: ul.chapter-list > li.chapter-item
                chapter_items = soup.select("ul.chapter-list > li.chapter-item")
                print(f"Found {len(chapter_items)} chapters via ul.chapter-list")
                
                if chapter_items:
                    for idx, li in enumerate(chapter_items):
                        # 提取标题
                        title_elem = li.find(class_="title")
                        if not title_elem:
                            title_elem = li.find("p")
                        if not title_elem:
                            title_elem = li.find("div", class_="item-content")
                        
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                        else:
                            title = f"第{idx+1}集"
                        
                        # 提取章节序号
                        chapter_idx = idx + 1
                        num_match = re.search(r'(\d+)', title)
                        if num_match:
                            chapter_idx = int(num_match.group(1))
                        
                        play_urls.append(f"{title}${vid}|{chapter_idx}")
                
                # 方式2: 如果上面没找到，尝试其他选择器
                if not play_urls:
                    # 尝试 .chapter-list li
                    chapter_items = soup.select(".chapter-list li")
                    print(f"Found {len(chapter_items)} chapters via .chapter-list li")
                    
                    for idx, li in enumerate(chapter_items):
                        title_elem = li.find(class_="title") or li.find("p") or li.find("a")
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                        else:
                            title = f"第{idx+1}集"
                        
                        chapter_idx = idx + 1
                        num_match = re.search(r'(\d+)', title)
                        if num_match:
                            chapter_idx = int(num_match.group(1))
                        
                        play_urls.append(f"{title}${vid}|{chapter_idx}")
                
                # 方式3: 直接找所有包含 /audios/ 的链接
                if not play_urls:
                    audio_links = soup.select("a[href*='/audios/']")
                    print(f"Found {len(audio_links)} audio links")
                    
                    seen = set()
                    for link in audio_links:
                        href = link.get("href", "")
                        match = re.search(r'/audios/(\d+)/(\d+)', href)
                        if match and match.group(1) == str(vid):
                            chapter_idx = int(match.group(2))
                            if chapter_idx in seen:
                                continue
                            seen.add(chapter_idx)
                            title = link.get_text(strip=True) or f"第{chapter_idx}集"
                            play_urls.append(f"{title}${vid}|{chapter_idx}")
                    
                    # 按序号排序
                    play_urls.sort(key=lambda x: int(x.split('|')[1].split('}')[0]) if x.split('|')[1].split('}')[0].isdigit() else 0)
                
                # 方式4: 尝试从 script 标签解析 JSON 数据
                if not play_urls:
                    print("Trying to extract from script tags...")
                    script_tags = soup.find_all("script")
                    for script in script_tags:
                        if script.string and '__NUXT_DATA__' in script.string:
                            try:
                                # 尝试提取 NUXT 数据
                                json_str = script.string
                                match = re.search(r'({.*})', json_str, re.DOTALL)
                                if match:
                                    data = json.loads(match.group(1))
                                    # 递归查找 chapters
                                    def find_chapters(obj, depth=0):
                                        results = []
                                        if isinstance(obj, dict):
                                            if 'chapters' in obj and isinstance(obj['chapters'], list):
                                                results.extend(obj['chapters'])
                                            for v in obj.values():
                                                results.extend(find_chapters(v, depth+1))
                                        elif isinstance(obj, list):
                                            for item in obj:
                                                results.extend(find_chapters(item, depth+1))
                                        return results
                                    
                                    chapters = find_chapters(data)
                                    print(f"Found {len(chapters)} chapters from NUXT")
                                    
                                    for idx, chapter in enumerate(chapters):
                                        if isinstance(chapter, dict):
                                            title = chapter.get('title', chapter.get('name', f'第{idx+1}集'))
                                            chapter_idx = chapter.get('chapter_idx', chapter.get('index', idx+1))
                                            play_urls.append(f"{title}${vid}|{chapter_idx}")
                                        elif isinstance(chapter, str):
                                            play_urls.append(f"第{idx+1}集${vid}|{idx+1}")
                            except Exception as e:
                                print(f"NUXT parse error: {e}")
                
                # 去重并保留顺序
                seen = set()
                unique_play_urls = []
                for url in play_urls:
                    if url not in seen:
                        seen.add(url)
                        unique_play_urls.append(url)
                play_urls = unique_play_urls
                
                print(f"Total episodes found: {len(play_urls)}")
                
                if play_urls:
                    vod_play_url = "#".join(play_urls)
                    info.append({
                        "type_name": type_name,
                        "vod_id": vid,
                        "vod_name": vod_name,
                        "vod_remarks": "",
                        "vod_year": "",
                        "vod_area": "",
                        "vod_actor": "",
                        "vod_director": "",
                        "vod_content": vod_content,
                        "vod_pic": vod_pic,
                        "vod_play_from": "听友FM",
                        "vod_play_url": vod_play_url
                    })
                    print(f"Success: {len(play_urls)} episodes added")
                else:
                    print("WARNING: No episodes found!")
                    info.append({
                        "type_name": type_name,
                        "vod_id": vid,
                        "vod_name": vod_name,
                        "vod_remarks": "",
                        "vod_year": "",
                        "vod_area": "",
                        "vod_actor": "",
                        "vod_director": "",
                        "vod_content": vod_content,
                        "vod_pic": vod_pic,
                        "vod_play_from": "",
                        "vod_play_url": ""
                    })
            else:
                print("ERROR: album-pannel not found")
                return {"list": [], "msg": "页面结构异常"}
                
        except Exception as e:
            print(f'detailContent error: {e}')
            import traceback
            traceback.print_exc()
            return {"list": [], "msg": str(e)}
        
        return {"list": info, "parse": 0, "jx": 0}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, page='1'):
        videos = []
        try:
            url = f"{self.site}/search?q={parse.quote(key)}"
            resp = requests.get(url, headers=self.headers, timeout=15)
            html = resp.text
            
            # 尝试解析 NUXT 数据中的搜索结果
            match = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>([\s\S]*?)</script>', html, re.DOTALL)
            if match:
                try:
                    payload = json.loads(match.group(1))
                    root = self.decode_nuxt_value(payload, 1)
                    
                    def find_albums(obj, depth=0):
                        results = []
                        if isinstance(obj, dict):
                            if 'id' in obj and 'title' in obj and 'cover_url' in obj:
                                results.append(obj)
                            else:
                                for v in obj.values():
                                    results.extend(find_albums(v, depth+1))
                        elif isinstance(obj, list):
                            for item in obj:
                                results.extend(find_albums(item, depth+1))
                        return results
                    
                    items = find_albums(root)
                    seen_ids = set()
                    for item in items[:50]:
                        vod_id = str(item.get('id', ''))
                        if vod_id and vod_id not in seen_ids:
                            seen_ids.add(vod_id)
                            vod_pic = item.get('cover_url', item.get('cover', ''))
                            if vod_pic and not vod_pic.startswith('http'):
                                vod_pic = self.site + vod_pic
                            videos.append({
                                'vod_id': vod_id,
                                'vod_name': item.get('title', item.get('name', f'专辑{vod_id}')),
                                'vod_pic': vod_pic,
                                'vod_remarks': item.get('desc', '')[:50] if item.get('desc') else ''
                            })
                except Exception as e:
                    print('search parse nuxt error:', e)
            
            # 如果没有结果，回退 DOM 解析
            if not videos:
                pattern = r'<a[^>]*href=["\']/albums/(\d+)[^>]*>.*?<img[^>]*src=["\']([^"\']+)["\'][^>]*>.*?<p[^>]*>([^<]*)</p>'
                matches = re.findall(pattern, html, re.DOTALL)
                for vod_id, pic, name in matches[:50]:
                    if pic.startswith('data:'):
                        continue
                    videos.append({
                        'vod_id': vod_id,
                        'vod_name': name.strip() or f'专辑{vod_id}',
                        'vod_pic': pic if pic.startswith('http') else self.site + pic,
                        'vod_remarks': ''
                    })
        except Exception as e:
            print('searchContent error:', e)
            return {'list': [], 'msg': ''}
        return {'list': videos, 'parse': 0, 'jx': 0}

    # ---------- 播放 (优化 API 请求与解密) ----------
    def playerContent(self, flag, pid, vipFlags):
        parts = pid.split('|')
        if len(parts) != 2:
            return {'url': pid, 'parse': 1, 'jx': 0, 'header': self.headers}
        album_id, chapter_idx = parts

        # 获取认证信息
        auth = self.get_auth_token()
        cookie = self.get_cookie()
        
        print(f"[Play] Start for album={album_id}, chapter={chapter_idx}")
        print(f"[Play] Auth present: {bool(auth)}, Cookie present: {bool(cookie)}")

        # 尝试通过 API 获取直链
        if auth:
            try:
                # 1. 调用 play_token 接口
                req_body = {'album_id': int(album_id), 'chapter_idx': int(chapter_idx)}
                extra_headers = {
                    'Authorization': auth,
                    'Accept': 'application/json, text/plain, */*',
                    'Content-Type': 'application/json',
                    'X-Payload-Version': '2',  # 使用 v2 版本，可能需要 XChaCha 解密
                    'Origin': self.site,
                    'Referer': f"{self.site}/albums/{album_id}",
                }
                if cookie:
                    extra_headers['Cookie'] = cookie
                
                print(f"[Play] Requesting API: {self.site}/api/play_token")
                # 直接使用 requests 发送，不走 api_post 以便打印原始响应
                response = requests.post(
                    f"{self.site}/api/play_token",
                    headers=extra_headers,
                    json=req_body,
                    timeout=15
                )
                
                print(f"[Play] API Response Status: {response.status_code}")
                print(f"[Play] API Response Headers: {dict(response.headers)}")
                
                # 获取原始响应文本
                raw_text = response.text
                print(f"[Play] API Raw Response (first 500 chars): {raw_text[:500]}")
                
                # 2. 解析响应，处理可能的加密 payload
                data = None
                try:
                    data = response.json()
                except:
                    data = raw_text
                
                # 3. 处理加密的 payload 字段
                play_url = None
                if isinstance(data, dict) and 'payload' in data:
                    print("[Play] Encrypted payload detected, decrypting...")
                    try:
                        decrypted = self.decrypt_payload_hex(data['payload'])
                        print(f"[Play] Decrypted payload (first 500): {decrypted[:500]}")
                        # 尝试将解密后的文本转为 JSON
                        try:
                            data = json.loads(decrypted)
                        except:
                            data = decrypted
                    except Exception as e:
                        print(f"[Play] Decryption failed: {e}")
                
                # 4. 从最终数据中提取音频 URL
                if data:
                    print(f"[Play] Final data type: {type(data)}")
                    # 递归查找 URL 的函数
                    def find_audio_url(obj, depth=0):
                        if depth > 10:  # 防止过深递归
                            return None
                        if isinstance(obj, dict):
                            # 优先查找明确的 URL 字段
                            for key in ['url', 'src', 'play_url', 'audio_url', 'file', 'path', 'media_url', 'link']:
                                if key in obj and obj[key] and isinstance(obj[key], str):
                                    val = obj[key]
                                    if val.startswith('http') and any(ext in val.lower() for ext in ['.m3u8', '.mp3', '.m4a', '.aac', '.flac', '/stream']):
                                        print(f"[Play] Found URL at key '{key}': {val[:100]}")
                                        return val
                            # 递归查找子对象
                            for k, v in obj.items():
                                res = find_audio_url(v, depth+1)
                                if res:
                                    return res
                        elif isinstance(obj, list):
                            for item in obj:
                                res = find_audio_url(item, depth+1)
                                if res:
                                    return res
                        return None
                    
                    play_url = find_audio_url(data)
                    if not play_url and isinstance(data, str) and data.startswith('http'):
                        play_url = data
                
                if play_url:
                    print(f"[Play] Success! Final play URL: {play_url}")
                    return {
                        'url': play_url,
                        'parse': 0,  # 直链，无需解析
                        'jx': 0,
                        'header': {'User-Agent': self.headers['User-Agent'], 'Referer': self.site}
                    }
                else:
                    print("[Play] Failed to extract URL from API response")
                    
            except Exception as e:
                print(f"[Play] API Request Failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("[Play] No auth token available, cannot call API")
        
        # 最终的降级方案：返回播放页 URL，但 parse=1 让系统尝试嗅探（尽管可能失败）
        fallback_url = f"{self.site}/audios/{album_id}/{chapter_idx}"
        print(f"[Play] Fallback to page URL (parse=1): {fallback_url}")
        return {
            'url': fallback_url,
            'parse': 1,
            'jx': 0,
            'header': self.headers
        }

if __name__ == '__main__':
    spider = Spider()
    spider.init()
    
    # 测试首页分类
    print("=== 测试首页分类 ===")
    home = spider.homeContent(False)
    print(json.dumps(home, ensure_ascii=False, indent=2))
    
    # 测试首页视频
    print("\n=== 测试首页视频 ===")
    home_video = spider.homeVideoContent()
    print(f"获取到 {len(home_video['list'])} 个视频")
    if home_video['list']:
        print(json.dumps(home_video['list'][:3], ensure_ascii=False, indent=2))
    
    # 测试分类页（以46为例）
    print("\n=== 测试分类页 (46-有声小说) ===")
    category = spider.categoryContent('46', '1', {}, {'cid': '46'})
    print(f"获取到 {len(category['list'])} 个视频")
    if category['list']:
        print(json.dumps(category['list'][:3], ensure_ascii=False, indent=2))