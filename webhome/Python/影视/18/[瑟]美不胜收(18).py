# coding=utf-8
import sys
sys.path.append('..')
from base.spider import Spider  # 核心：继承TVBox基类防崩溃
import re
import json
import requests

class Spider(Spider):
    def getName(self):
        return "美不胜收(免翻)"

    def init(self, extend=""):
        pass

    # ==========================================
    # 模块 1：网络配置模块 (requests 重构版)
    # ==========================================
    def _fetch(self, url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
                'Referer': 'https://mbss3.xyz/'
            }
            # verify=False 忽略证书报错，替换掉不稳定的 ssl 库
            response = requests.get(url, headers=headers, verify=False, timeout=10)
            response.encoding = 'utf-8'
            return response.text
        except Exception:
            return ""

    # ==========================================
    # 模块 2：分类路由模块
    # ==========================================
    def homeContent(self, filter):
        classes = [
            {"type_id": "20", "type_name": "在线一区"},
            {"type_id": "21", "type_name": "国产色情"},
            {"type_id": "22", "type_name": "主播直播"},
            {"type_id": "23", "type_name": "亚洲精品"},
            {"type_id": "24", "type_name": "中文字幕"},
            {"type_id": "25", "type_name": "人妻熟女"},
            {"type_id": "26", "type_name": "强奸乱伦"},
            {"type_id": "27", "type_name": "欧美精品"},
            {"type_id": "28", "type_name": "成人动漫"},
            {"type_id": "29", "type_name": "在线二区"},
            {"type_id": "30", "type_name": "自拍偷拍"},
            {"type_id": "31", "type_name": "制服丝袜"},
            {"type_id": "32", "type_name": "变态另类"},
            {"type_id": "33", "type_name": "AI换脸"},
            {"type_id": "34", "type_name": "三级伦理"},
            {"type_id": "35", "type_name": "AV解说"},
            {"type_id": "36", "type_name": "传媒探花"},
            {"type_id": "37", "type_name": "美乳巨乳"}
        ]
        return {"class": classes}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            # 强制转换为整数，防止 OK影视 强类型检查崩溃
            page_num = int(pg)
            url = f"https://mbss3.xyz/index.php/vod/type/id/{tid}/page/{page_num}.html"
            html = self._fetch(url)
            
            videos = self._parse_cards(html)
            
            if not videos:
                return {
                    "list": [{
                        "vod_id": "error",
                        "vod_name": f"无数据, 源码长度:{len(html)}",
                        "vod_pic": "https://img.picui.cn/free/2024/06/18/66718d09a0da7.png",
                        "vod_remarks": "排查网页"
                    }],
                    "page": page_num, "pagecount": 1, "limit": 1, "total": 1
                }

            return {
                "list": videos,
                "page": page_num,
                "pagecount": 999,
                "limit": len(videos),
                "total": 9999
            }
        except Exception as e:
            return {
                "list": [{
                    "vod_id": "crash",
                    "vod_name": f"异常: {str(e)}",
                    "vod_pic": "https://img.picui.cn/free/2024/06/18/66718d09a0da7.png",
                    "vod_remarks": "代码错误"
                }],
                "page": 1, "pagecount": 1, "limit": 1, "total": 1
            }

    # ==========================================
    # 模块 3：UI卡片解析模块
    # ==========================================
    def _parse_cards(self, html):
        videos = []
        items = re.findall(r'<li.*?>(.*?)</li>', html, re.I | re.S)
        if not items:
            items = re.findall(r'(<a class="thumbnail".*?</div>)', html, re.I | re.S)

        for item in items:
            href_match = re.search(r'<a class="thumbnail" href=["\']([^"\']+)["\']', item, re.I)
            pic_match = re.search(r'data-original=["\']([^"\']+)["\']', item, re.I)
            
            if not href_match or not pic_match:
                continue
                
            vod_id = href_match.group(1)
            pic = pic_match.group(1)
            
            # 手动拼接 URL，彻底抛弃 urllib.parse 避免 NameError
            if not vod_id.startswith('http'):
                vod_id = "https://mbss3.xyz" + vod_id if vod_id.startswith('/') else "https://mbss3.xyz/" + vod_id
            
            title_match = re.search(r'<h5>\s*<a[^>]*>(.*?)</a>', item, re.I | re.S)
            vod_name = title_match.group(1).strip() if title_match else "未知视频"
            
            remark_match = re.search(r'<p class="vodtitle">(.*?)</p>', item, re.I | re.S)
            if remark_match:
                raw_remark = re.sub(r'<[^>]+>', '', remark_match.group(1)).strip()
                date_match = re.search(r'\d{4}-(\d{2}-\d{2})', raw_remark)
                view_match = re.search(r'观看:\s*(\d+)', raw_remark)
                
                tags = []
                if date_match:
                    tags.append(date_match.group(1))
                if view_match:
                    views = int(view_match.group(1))
                    if views >= 10000:
                        tags.append(f"👁{round(views/10000, 1)}w")
                    else:
                        tags.append(f"👁{views}")
                vod_remarks = " ".join(tags) if tags else "高清"
            else:
                vod_remarks = "高清"

            videos.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": pic.strip(),
                "vod_remarks": vod_remarks
            })
            
        return videos

    # ==========================================
    # 模块 4 & 5：详情与播放直连模块
    # ==========================================
    def detailContent(self, ids):
        # 修复 Chaquopy 的数组跨语言类型陷阱
        if isinstance(ids, str):
            target_url = ids
        else:
            try:
                target_url = str(ids[0])
            except Exception:
                target_url = str(ids)
        
        vod = {
            "vod_id": target_url,
            "vod_name": "美不胜收(免翻)",
            "vod_director": "YJ-Gemini",
            "vod_play_from": "YJ-Gemini 专线",
            "vod_play_url": f"原画直连${target_url}"
        }
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        try:
            detail_html = self._fetch(id)
            best_link = ""
            
            play_match = re.search(r'href=["\'](/index\.php/vod/play/[^"\']+)["\']', detail_html)
            if play_match:
                play_path = play_match.group(1)
                play_url = "https://mbss3.xyz" + play_path if play_path.startswith('/') else "https://mbss3.xyz/" + play_path
                play_html = self._fetch(play_url)
                
                mac_player = re.search(r'player_aaaa\s*=\s*(\{.*?\})', play_html)
                if mac_player:
                    try:
                        json_str = mac_player.group(1).replace('\\/', '/')
                        player_data = json.loads(json_str)
                        if "url" in player_data:
                            # 手动解码，替代 urllib.parse.unquote
                            raw_url = player_data["url"]
                            best_link = raw_url.replace('%3A', ':').replace('%2F', '/').replace('%3F', '?').replace('%3D', '=')
                    except Exception:
                        pass
                        
                if not best_link:
                    m3u8_links = re.findall(r'(https?://[^\s\'"]+\.(?:m3u8|mp4))', play_html)
                    if m3u8_links:
                        best_link = m3u8_links[0]
                        
            if not best_link:
                return {"parse": 1, "jx": 0, "url": id}

            return {
                "parse": 0, 
                "jx": 0, 
                "url": best_link,
                "header": {
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://mbss3.xyz/"
                }
            }
        except Exception as e:
            return {"parse": 0, "jx": 0, "url": f"http://error.com/error.mp4?msg={str(e)}"}

    # ==========================================
    # 模块 6：搜索模块
    # ==========================================
    def searchContent(self, key, quick):
        try:
            # 纯 Python 的 URL 编码，避免使用 urllib
            encoded_key = key.encode('utf-8').hex()
            encoded_key = '%' + '%'.join([encoded_key[i:i+2] for i in range(0, len(encoded_key), 2)])
            url = f"https://mbss3.xyz/index.php/vod/search.html?wd={encoded_key}"
            
            html = self._fetch(url)
            videos = self._parse_cards(html)
            return {"list": videos}
        except Exception:
            return {"list": []}
