# -*- coding: utf-8 -*-
"""
黄豆短剧爬虫
站点: https://www.hdmgdj.com
"""

import json
import urllib.parse

import requests

try:
    from base.spider import Spider as BaseSpider
except ImportError:
    class BaseSpider:
        pass


class Spider(BaseSpider):
    """黄豆短剧爬虫"""

    BASE_URL = 'https://xqjzvcvt.top'
    API_BASE = 'https://hdmgdj.com/api'

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.hdmgdj.com/',
        'Origin': 'https://www.hdmgdj.com',
    }

    _filter_cache = {}  # 分类筛选缓存

    def __init__(self):
        super().__init__()
        self.name = ""
        self.error_play_url = "https://kjjsaas-sh.oss-cn-shanghai.aliyuncs.com/u/3401405881/20240818-936952-fc31b16575e80a7562cdb1f81a39c6b0.mp4"
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ==================== 标准接口 ====================

    def init(self, extend="{}"):
        """初始化"""
        if extend:
            try:
                self.extend = json.loads(extend)
                if 'name' in self.extend:
                    self.name = self.extend['name']
                if 'base_url' in self.extend:
                    self.BASE_URL = self.extend['base_url']
                    self.API_BASE = self.extend['base_url'] + '/api'
            except Exception as e:
                print(e)
        return None

    def getName(self):
        """获取爬虫名称"""
        return "黄豆短剧"

    def homeContent(self, filter):
        """首页"""
        result = {
            "class": [],
            "filters": {},
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            # 获取频道首页数据（包含分类和推荐）
            channel_data = self._get('/channel/home?platform=mobile&size=20')
            if channel_data and isinstance(channel_data, dict):
                # 分类：用 sections 里的 l3 分类（有实际内容的）
                sections = channel_data.get('sections', [])
                if isinstance(sections, list):
                    for idx, sec in enumerate(sections):
                        l3_id = sec.get('l3Id')
                        name = sec.get('name', '')
                        if l3_id and name:
                            # 在第三个分类位置插入硬编码"擦边漫剧"
                            if idx == 2:
                                result["class"].append({
                                    "type_id": "recommend",
                                    "type_name": "擦边漫剧",
                                })
                            result["class"].append({
                                "type_id": f"l3_{l3_id}",
                                "type_name": name,
                            })
                    # 如果分类不足2个，在末尾追加
                    if len(sections) < 2:
                        result["class"].append({
                            "type_id": "recommend",
                            "type_name": "擦边漫剧",
                        })

                # 首页推荐：把各个板块的内容合并
                for sec in sections:
                    dramas = sec.get('dramas', [])
                    if isinstance(dramas, list):
                        for item in dramas:
                            result["list"].append(self._parse_vod(item))

                # 如果 sections 里没有数据，用 guess/feature
                if not result["list"]:
                    home_data = self._get('/home')
                    if home_data and isinstance(home_data, dict):
                        guess_list = home_data.get('guess', [])
                        if isinstance(guess_list, list):
                            for item in guess_list:
                                result["list"].append(self._parse_vod(item))
                        feature_list = home_data.get('feature', [])
                        if isinstance(feature_list, list):
                            for item in feature_list:
                                result["list"].append(self._parse_vod(item))

        except Exception as e:
            print(e)

        return result

    def categoryContent(self, tid, pg, filter, extend):
        """分类页"""
        result = {
            "page": pg,
            "pagecount": 999,
            "limit": 20,
            "total": 99999,
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            # 推荐分类：全部短剧，不带 l3Id 筛选
            if tid == 'recommend':
                data = self._get(f'/dramas?platform=mobile&page={pg}&size=20')
            else:
                # 其他分类：l3_{id}
                l3_id = tid.replace('l3_', '')
                data = self._get(f'/dramas?platform=mobile&l3Id={l3_id}&sort=最新&page={pg}&size=20')
            if data and isinstance(data, dict):
                lst = data.get('list', [])
                total = data.get('total', 0)
                result["total"] = total
                result["pagecount"] = (total + 19) // 20 if total else 999
                for item in lst:
                    result["list"].append(self._parse_vod(item))

        except Exception as e:
            print(e)

        return result

    def detailContent(self, ids):
        """详情页"""
        result = {
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            vid = ids[0]
            data = self._get(f'/dramas/{vid}')

            if data and isinstance(data, dict):
                episodes = data.get('episodes', [])

                # 组装播放地址
                play_url_parts = []
                for ep in episodes:
                    ep_title = ep.get('title', f"第{ep.get('ep', 0)}集")
                    play_url = ep.get('playUrl', '')
                    if play_url:
                        play_url_parts.append(f"{ep_title}${play_url}")

                cover = data.get('cover', '')
                # 加密海报走本地代理解密
                if cover and ('encryptimages' in cover or '.bng' in cover):
                    try:
                        cover = f"{self.getProxyUrl()}&url={urllib.parse.quote(cover)}"
                    except Exception:
                        pass

                vod = {
                    "vod_id": str(data['id']),
                    "vod_name": data.get('t', ''),
                    "vod_pic": cover,
                    "type_name": data.get('sub', ''),
                    "vod_year": '',
                    "vod_area": '',
                    "vod_remarks": f"{data.get('serial', '')}·{data.get('plays', '')}播放",
                    "vod_actor": '',
                    "vod_director": "".join([chr(22007), chr(21596), chr(32), chr(47), chr(32), chr(21776), chr(19977)]),
                    "vod_content": data.get('summary', '') or data.get('t', ''),
                    "vod_play_from": '黄豆短剧',
                    "vod_play_url": '#'.join(play_url_parts),
                }
                result["list"].append(vod)

        except Exception as e:
            print(e)

        return result

    def searchContent(self, key, quick, pg="1"):
        """搜索"""
        result = {
            "page": pg,
            "pagecount": 999,
            "limit": 20,
            "total": 99999,
            "list": [],
            "parse": 0,
            "jx": 0,
        }

        try:
            data = self._get(f'/search?kw={urllib.parse.quote(key)}&page={pg}&size=20')
            if data and isinstance(data, dict):
                lst = data.get('list', [])
                total = data.get('total', 0)
                result["total"] = total
                result["pagecount"] = (total + 19) // 20 if total else 0
                for item in lst:
                    result["list"].append(self._parse_vod(item))

        except Exception as e:
            print(e)

        return result

    def playerContent(self, flag, id, vipFlags):
        """播放页 - 直接返回 m3u8 data URI"""
        result = {
            "parse": 0,
            "playUrl": "",
            "url": self.error_play_url,
            "jx": 0,
            "header": "",
        }

        if id:
            # 直接在 playerContent 里生成解密后的 m3u8，用 data URI 返回
            # 这样播放地址就不是 127.0.0.1 代理了
            m3u8_content = self._build_m3u8_with_key(id)
            if m3u8_content:
                import base64
                m3u8_b64 = base64.b64encode(m3u8_content.encode('utf-8')).decode('ascii')
                result["url"] = "data:application/vnd.apple.mpegurl;base64," + m3u8_b64
                result["parse"] = 0

        return result

    def _build_m3u8_with_key(self, url):
        """构建 m3u8 内容（key 内嵌为 base64 data URI，ts 用原始绝对地址）"""
        import hashlib
        import re
        import base64
        if not url:
            return None

        try:
            r = self.session.get(url, timeout=15, verify=False)
            content = r.text

            # 计算 key
            key_bytes = self._get_key_bytes(url)
            if key_bytes:
                key_b64 = base64.b64encode(key_bytes).decode('ascii')
                key_data_uri = "data:text/plain;base64," + key_b64
                content = re.sub(
                    r'(#EXT-X-KEY:.*?URI=")[^"]*(")',
                    r'\1' + key_data_uri + r'\2',
                    content
                )

            # 把相对路径的 ts 改成绝对路径
            base_url = url.rsplit('/', 1)[0] + '/'
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    if line.startswith('http'):
                        new_lines.append(line)
                    else:
                        new_lines.append(base_url + line)
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)
            return content
        except Exception as e:
            print(f"_build_m3u8_with_key error: {e}")
            return None

    def _get_key_bytes(self, url):
        """从 m3u8 URL 计算解密 key"""
        import hashlib
        import re
        m = re.search(r'/hls/([0-9a-f]{64})/', url)
        if not m:
            return None
        video_id = m.group(1)
        ver_match = re.search(r'[?&]version=([^&#]+)', url)
        version = ver_match.group(1) if ver_match else 'v1'
        prefix = "xnaichanping"
        key_str = prefix + video_id + version
        return hashlib.md5(key_str.encode()).digest()

    def localProxy(self, param):
        """本地代理 - 解密海报图片"""
        try:
            url = param['url']
            r = self.session.get(url, timeout=15, verify=False)
            decrypted = self._aes_decrypt_img(r.content, url)
            # 确定图片类型
            content_type = "image/jpeg"
            if decrypted[:8] == b'\x89PNG\r\n\x1a\n':
                content_type = "image/png"
            elif decrypted[:6] in (b'GIF87a', b'GIF89a'):
                content_type = "image/gif"
            elif decrypted[:4] == b'RIFF' and decrypted[8:12] == b'WEBP':
                content_type = "image/webp"
            return [200, content_type, decrypted]
        except Exception as e:
            print(f"localProxy error: {e}")
            return [500, 'text/html', b'']

    def _aes_decrypt_img(self, encrypted, url):
        """AES 解密图片 - 网站自定义 CBC 算法"""
        import hashlib
        import re
        from Crypto.Cipher import AES

        # 提取 imageId (64位哈希)
        m = re.search(r'([0-9a-f]{64})', url)
        if not m:
            return encrypted
        image_id = m.group(1)

        # 提取 version
        ver_match = re.search(r'[?&]version=([^&#]+)', url)
        version = ver_match.group(1) if ver_match else 'v1'

        # 计算解密 key
        prefix = "xnaichanping"
        key_str = prefix + image_id + version
        key_bytes = hashlib.md5(key_str.encode()).digest()

        # 网站自定义 CBC 解密 (mC 函数)
        t = len(encrypted) // 16
        if t < 1:
            return encrypted

        iv = bytes(16)  # IV=0

        # 取最后一块 XOR 16
        last_block = encrypted[(t - 1) * 16:t * 16]
        a = bytes([b ^ 16 for b in last_block])

        # 加密 a
        cipher_enc = AES.new(key_bytes, AES.MODE_CBC, iv)
        o = cipher_enc.encrypt(a)[:16]

        # 扩展密文并解密
        extended = encrypted + o
        cipher_dec = AES.new(key_bytes, AES.MODE_CBC, iv)
        c = cipher_dec.decrypt(extended)

        # 自定义 CBC：每块 XOR 前一块密文
        u = bytearray(len(c))
        u[:16] = c[:16]
        for f in range(1, t):
            for h in range(16):
                u[f * 16 + h] = c[f * 16 + h] ^ encrypted[(f - 1) * 16 + h]

        # 去掉 padding
        d = u[-1]
        if 1 <= d <= 16:
            u = u[:-d]

        return bytes(u)

    # ==================== 内部方法 ====================

    def _parse_vod(self, item):
        """解析视频条目 - 海报用 getProxyUrl 代理解密"""
        cover = item.get('cover', '')
        # 加密海报走本地代理解密
        if cover and ('encryptimages' in cover or '.bng' in cover):
            try:
                cover = f"{self.getProxyUrl()}&url={urllib.parse.quote(cover)}"
            except Exception:
                pass
        return {
            "vod_id": str(item['id']),
            "vod_name": item.get('t', ''),
            "vod_pic": cover,
            "vod_remarks": f"{item.get('serial', '')}·{item.get('eps', 0)}集",
        }

    def _get(self, path):
        """发送 GET 请求"""
        url = self.API_BASE + path
        try:
            r = self.session.get(url, timeout=15, verify=False)
            resp = r.json()
            if resp.get('code') == 0 and resp.get('data') is not None:
                return resp['data']
            return None
        except Exception as e:
            print(e)
            return None


# 调试用
if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    s = Spider()
    s.init()

    print('=== 首页 ===')
    home = s.homeContent(True)
    print(f'分类: {len(home["class"])}个')
    for c in home['class']:
        print(f'  {c["type_id"]}: {c["type_name"]}')
    print(f'推荐: {len(home["list"])}个')
    for v in home['list'][:5]:
        print(f'  {v["vod_id"]}: {v["vod_name"]} - {v["vod_remarks"]}')
    print()

    print('=== 分类1（都市）第1页 ===')
    cr = s.categoryContent('1', 1, True, {})
    print(f'总数: {cr["total"]}, 本页: {len(cr["list"])}个')
    for v in cr['list'][:5]:
        print(f'  {v["vod_id"]}: {v["vod_name"]}')
    print()

    print('=== 搜索 穿越 ===')
    sr = s.searchContent('穿越', False, '1')
    print(f'结果: {len(sr["list"])}个, 总数: {sr["total"]}')
    for v in sr['list'][:5]:
        print(f'  {v["vod_id"]}: {v["vod_name"]}')
    print()

    if sr['list']:
        vid = sr['list'][0]['vod_id']
        print(f'=== 详情 {vid} ===')
        dr = s.detailContent([vid])
        if dr['list']:
            v = dr['list'][0]
            print(f'标题: {v["vod_name"]}')
            print(f'分类: {v["type_name"]}')
            print(f'备注: {v["vod_remarks"]}')
            print(f'播放源: {v["vod_play_from"]}')
            play_urls = v["vod_play_url"].split('#')
            print(f'集数: {len(play_urls)}集')
            print(f'第一集: {play_urls[0][:80]}...')
