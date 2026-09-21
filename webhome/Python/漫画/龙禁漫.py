# -*- coding: utf-8 -*-
import sys
import re
import json
import urllib.request
import urllib.parse
import gzip
import io

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    """龙禁漫漫画爬虫 - 皮卡丘标准格式"""

    def getName(self):
        return "龙禁漫"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def getHeader(self):
        return {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
            "Referer": "https://long92.org/",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

    def fetch(self, url, method='GET', data=None, headers=None):
        """统一请求方法 - 仅使用标准库"""
        try:
            h = headers if headers else self.getHeader()
            
            parsed = urllib.parse.urlparse(url)
            encoded_path = urllib.parse.quote(parsed.path, safe='/')
            url = urllib.parse.urlunparse((
                parsed.scheme,
                parsed.netloc,
                encoded_path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            
            req = urllib.request.Request(url, method=method.upper())
            
            for key, value in h.items():
                req.add_header(key, value)
            
            if method.upper() == 'POST' and data:
                if isinstance(data, dict):
                    data = urllib.parse.urlencode(data).encode('utf-8')
                req.data = data
            
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read()
                content_encoding = response.info().get('Content-Encoding', '').lower()
                
                if 'gzip' in content_encoding:
                    try:
                        content = gzip.decompress(content)
                    except Exception:
                        try:
                            buf = io.BytesIO(content)
                            with gzip.GzipFile(fileobj=buf) as f:
                                content = f.read()
                        except Exception:
                            pass
                
                result = content.decode('utf-8', errors='ignore')
                return result
        except Exception as e:
            print(f"[ERROR] 请求失败: {url}, 错误: {e}")
            return None

    def homeContent(self, filter):
        """首页分类"""
        result = {
            "class": [
                {"type_id": "newbook", "type_name": "最近更新"},
                
                {"type_id": "bookcata/韩漫/ob/time/st/all", "type_name": "韩漫"},
                {"type_id": "bookcata/日漫/ob/time/st/all", "type_name": "日漫"},
                {"type_id": "bookcata/3D漫画/ob/time/st/all", "type_name": "3D漫画"},
                {"type_id": "bookcata/美女/ob/time/st/all", "type_name": "美女"},
                {"type_id": "bookcata/单本/ob/time/st/all", "type_name": "单本"},
                {"type_id": "bookrank", "type_name": "排行榜"}
            ]
        }
        return result

    def homeVideoContent(self):
        """首页推荐内容"""
        return self.categoryContent("newbook", "1", False, None)

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容"""
        try:
            base_url = "https://long92.org"
            
            if tid == "newbook":
                url = f"{base_url}/newbook"
                if int(pg) > 1:
                    url += f"/page/{pg}"
            elif tid == "bookrank":
                url = f"{base_url}/bookrank"
                if int(pg) > 1:
                    url += f"/page/{pg}"
            else:
                url = f"{base_url}/{tid}"
                if int(pg) > 1:
                    url += f"/page/{pg}"
            
            html = self.fetch(url)
            if not html:
                return {"list": []}
            
            vlist = self.parseList(html)
            
            return {
                "list": vlist,
                "page": pg,
                "pagecount": 9999,
                "limit": 20,
                "total": 999999
            }
        except Exception as e:
            print(f"[ERROR] categoryContent error: {e}")
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        """搜索内容"""
        try:
            search_key = urllib.parse.quote(key)
            url = f"https://long92.org/cata.php?key={search_key}"
            if int(pg) > 1:
                url += f"&page={pg}"
            
            html = self.fetch(url)
            if not html:
                return {"list": []}
            
            vlist = self.parseList(html)
            
            return {
                "list": vlist,
                "page": pg,
                "pagecount": 9999,
                "limit": 20,
                "total": 999999
            }
        except Exception as e:
            print(f"[ERROR] searchContent error: {e}")
            return {"list": []}

    def detailContent(self, ids):
        """详情内容"""
        try:
            vid = ids[0]
            if not vid.startswith("http"):
                vid = self.fixUrl(vid)
            
            html = self.fetch(vid)
            if not html:
                return {"list": []}
            
            # 提取标题
            name = "未知漫画"
            name_match = re.search(r'<h1[^>]*class=["\'][^"\']*module-info-title[^"\']*["\'][^>]*>(.*?)</h1>', html, re.S)
            if name_match:
                name = self.cleanHtml(name_match.group(1))
            
            if name == "未知漫画":
                name_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
                if name_match:
                    name = self.cleanHtml(name_match.group(1))
            
            # 提取作者
            author = ""
            author_match = re.search(r'<div[^>]*class=["\'][^"\']*module-info-item-content[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            if author_match:
                author = self.cleanHtml(author_match.group(1))
            
            # 提取标签
            tags = re.findall(r'<div[^>]*class=["\'][^"\']*module-info-tag-link[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            tag = " ".join([self.cleanHtml(t) for t in tags])
            
            # 提取简介
            desc = ""
            desc_match = re.search(r'<div[^>]*class=["\'][^"\']*module-info-introduction-content[^"\']*show-desc[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            if not desc_match:
                desc_match = re.search(r'<div[^>]*class=["\'][^"\']*module-info-introduction-content[^"\']*["\'][^>]*>(.*?)</div>', html, re.S)
            if desc_match:
                desc = self.cleanHtml(desc_match.group(1))
            
            # 提取封面
            pic = ""
            pic_match = re.search(r'<div[^>]*class=["\'][^"\']*module-item-cover[^"\']*["\'][^>]*data-original=["\']([^"\']+)["\']', html)
            if not pic_match:
                pic_match = re.search(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']', html)
            if pic_match:
                pic = self.fixUrl(pic_match.group(1))
            
            # 提取章节列表
            chapters = []
            # 主匹配：带 class 和 title 的标准章节链接
            chapter_items = re.findall(
                r'<a[^>]*class=["\'][^"\']*module-play-list-link[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']+)["\']',
                html, re.S
            )
            
            # 备用1：匹配 /manhua/{id}/{hash}.html 并提取标签文本
            if not chapter_items:
                chapter_items = re.findall(
                    r'<a[^>]*href=["\'](/manhua/\d+/[^"\']+\.html)["\'][^>]*>(.*?)</a>',
                    html, re.S
                )
                filtered = []
                for ch_url, ch_title_html in chapter_items:
                    ch_title = self.cleanHtml(ch_title_html)
                    if ch_title and any(k in ch_title for k in ["章", "话", "第", "卷", "话"]):
                        filtered.append((ch_url, ch_title))
                chapter_items = filtered
            
            # 备用2：更宽泛的 title 匹配
            if not chapter_items:
                chapter_items = re.findall(
                    r'<a[^>]*href=["\'](/manhua/\d+/[^"\']+\.html)["\'][^>]*title=["\']([^"\']+)["\']',
                    html, re.S
                )
            
            for item in chapter_items:
                if len(item) == 2:
                    ch_url, ch_name = item
                    ch_url = self.fixUrl(ch_url)
                    ch_name = self.cleanHtml(ch_name)
                    if ch_name and ch_url:
                        chapters.append(f"{ch_name}${ch_url}")
            
            # 网站通常最新章节在前，阅读器需要正序，故反转
            chapters.reverse()
            
            play_url = "#".join(chapters) if chapters else ""
            
            return {
                "list": [{
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": pic,
                    "type_name": tag,
                    "vod_actor": author,
                    "vod_content": desc,
                    "vod_play_from": "龙禁漫",
                    "vod_play_url": play_url
                }]
            }
        except Exception as e:
            print(f"[ERROR] detailContent error: {e}")
            import traceback
            traceback.print_exc()
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        """播放内容 - 提取图片"""
        try:
            url = id if id.startswith("http") else f"https://long92.org{id}"
            
            html = self.fetch(url)
            if not html:
                return {"parse": 1, "url": url, "header": self.getHeader()}
            
            img_list = []
            
            # 龙禁漫阅读页图片使用 data-src
            imgs = re.findall(r'<img[^>]*data-src=["\']([^"\']+)["\']', html)
            if imgs:
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        img_list.append(self.fixUrl(src))
            
            # 备用：data-original
            if not img_list:
                imgs = re.findall(r'<img[^>]*data-original=["\']([^"\']+)["\']', html)
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        img_list.append(self.fixUrl(src))
            
            # 备用：src
            if not img_list:
                imgs = re.findall(r'<img[^>]*src=["\']([^"\']+)["\']', html)
                for src in imgs:
                    if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                        if 'error.png' not in src and 'logo' not in src and '/imgs/' not in src:
                            img_list.append(self.fixUrl(src))
            
            # 去重保序
            seen = set()
            unique_imgs = []
            for img in img_list:
                if img not in seen:
                    seen.add(img)
                    unique_imgs.append(img)
            
            if unique_imgs:
                return {
                    "parse": 0,
                    "playUrl": "",
                    "url": f"pics://{'&&'.join(unique_imgs)}",
                    "header": ""
                }
            else:
                return {"parse": 1, "url": url, "header": self.getHeader()}
        except Exception as e:
            print(f"[ERROR] playerContent error: {e}")
            return {"parse": 1, "url": id, "header": self.getHeader()}

    def localProxy(self, param):
        pass

    # ============ 工具方法 ============

    def parseList(self, html):
        """解析列表页"""
        vlist = []
        try:
            if not html or len(html) < 100:
                return vlist
            
            # 主匹配：module-poster-item module-item
            pattern = r'<a[^>]*class=["\'][^"\']*module-poster-item[^"\']*["\'][^>]*href=["\']([^"\']+)["\'][^>]*title=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
            items = re.findall(pattern, html, re.S | re.I)
            
            if not items:
                pattern = r'<a[^>]*href=["\'](/manhua/\d+\.html)["\'][^>]*title=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*module-item[^"\']*["\'][^>]*>(.*?)</a>'
                items = re.findall(pattern, html, re.S | re.I)
            
            print(f"[DEBUG] 匹配到 {len(items)} 个漫画项")
            
            for item in items:
                try:
                    if len(item) == 3:
                        href, title, content = item
                    else:
                        continue
                    
                    link = self.fixUrl(href)
                    
                    # 提取封面
                    pic = ""
                    pic_match = re.search(r'data-original=["\']([^"\']+)["\']', content)
                    if pic_match:
                        pic = self.fixUrl(pic_match.group(1))
                    
                    if not pic:
                        pic_match = re.search(r'src=["\']([^"\']+)["\']', content)
                        if pic_match:
                            pic_src = pic_match.group(1)
                            if 'error.png' not in pic_src:
                                pic = self.fixUrl(pic_src)
                    
                    # 提取更新信息
                    note = ""
                    note_match = re.search(r'<div[^>]*class=["\'][^"\']*module-item-note[^"\']*["\'][^>]*>(.*?)</div>', content, re.S)
                    if note_match:
                        note = self.cleanHtml(note_match.group(1))
                    
                    vlist.append({
                        "vod_id": link,
                        "vod_name": title.strip(),
                        "vod_pic": pic,
                        "vod_remarks": note
                    })
                except Exception:
                    continue
            
            # 备用模式：向前查找图片
            if not vlist:
                print("[DEBUG] 使用备用模式匹配")
                links = re.findall(r'<a[^>]*href=["\'](/manhua/\d+\.html)["\'][^>]*title=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S)
                print(f"[DEBUG] 备用模式找到 {len(links)} 个链接")
                
                for href, title, content in links:
                    try:
                        link = self.fixUrl(href)
                        
                        pos = html.find(f'href="{href}"')
                        if pos == -1:
                            pos = html.find(f"href='{href}'")
                        
                        pic = ""
                        if pos > 0:
                            prev_html = html[max(0, pos-500):pos]
                            pic_match = re.search(r'data-original=["\']([^"\']+)["\']', prev_html)
                            if pic_match:
                                pic = self.fixUrl(pic_match.group(1))
                        
                        note = ""
                        note_match = re.search(r'<div[^>]*class=["\'][^"\']*module-item-note[^"\']*["\'][^>]*>(.*?)</div>', content, re.S)
                        if note_match:
                            note = self.cleanHtml(note_match.group(1))
                        
                        vlist.append({
                            "vod_id": link,
                            "vod_name": title.strip(),
                            "vod_pic": pic,
                            "vod_remarks": note
                        })
                    except Exception:
                        continue
            
        except Exception as e:
            print(f"[ERROR] parseList error: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[DEBUG] parseList返回: {len(vlist)}个结果")
        return vlist

    def cleanHtml(self, text):
        """清除HTML标签"""
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'")
        return text.strip()

    def fixUrl(self, url):
        """补全URL"""
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "https:" + url
        return "https://long92.org" + url


# ==================== 测试代码 ====================
if __name__ == '__main__':
    spider = Spider()
    
    print("=== 测试首页分类 ===")
    home = spider.homeContent(filter=True)
    print(f"分类数量: {len(home['class'])}")
    
    print("\n=== 测试首页内容 ===")
    home_video = spider.homeVideoContent()
    print(f"获取到 {len(home_video['list'])} 条数据")
    if home_video['list']:
        print("第一条:", home_video['list'][0])
    
    print("\n=== 测试分类内容 ===")
    cat = spider.categoryContent("bookcata/韩漫/ob/time/st/all", "1", False, None)
    print(f"获取到 {len(cat['list'])} 条数据")
    
    print("\n=== 测试搜索 ===")
    search = spider.searchContent("特色新视界", False, "1")
    print(f"搜索结果: {len(search['list'])} 条")
