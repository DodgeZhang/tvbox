# -*- coding: utf-8 -*-
import json
import sys
import re
import requests
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    
    def getName(self):
        return "包子漫画"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass

    def getHeader(self):
        # 【修改1】伪装成 PC 端 Chrome 浏览器，避免被识别为手机端强制跳APP
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://cn.bzmanga.com/"
        }

    def homeContent(self, filter):
        classes = [
            {"type_name": "最新上架", "type_id": "new"},
            {"type_name": "全部漫画", "type_id": "all"},
            {"type_name": "地区", "type_id": "region"},
            {"type_name": "进度", "type_id": "status"},
            {"type_name": "题材", "type_id": "type"}
        ]
        
        filters = {}
        filters['region'] = [{"key": "val", "name": "地区", "value": [{"n": "国漫", "v": "cn"},{"n": "日本", "v": "jp"},{"n": "欧美", "v": "en"}]}]
        filters['status'] = [{"key": "val", "name": "进度", "value": [{"n": "连载中", "v": "serial"},{"n": "已完结", "v": "pub"}]}]
        
        types = [
            {"n": "都市", "v": "dushi"}, {"n": "冒险", "v": "mouxian"},
            {"n": "热血", "v": "rexie"}, {"n": "爱情", "v": "aiqing"},
            {"n": "恋爱", "v": "lianai"}, {"n": "耽美", "v": "danmei"},
            {"n": "武侠", "v": "wuxia"}, {"n": "格斗", "v": "gedou"},
            {"n": "科幻", "v": "kehuan"}, {"n": "魔幻", "v": "mohuan"},
            {"n": "侦探", "v": "zhentan"}, {"n": "推理", "v": "tuili"},
            {"n": "玄幻", "v": "xuanhuan"}, {"n": "日常", "v": "richang"},
            {"n": "生活", "v": "shenghuo"}, {"n": "搞笑", "v": "gaoxiao"},
            {"n": "校园", "v": "xiaoyuan"}, {"n": "奇幻", "v": "qihuan"}
        ]
        filters['type'] = [{"key": "val", "name": "类型", "value": types}]
        
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        return self.categoryContent("new", "1", None, {})

    def categoryContent(self, tid, pg, filter, extend):
        if tid == "new":
            url = f"https://cn.bzmanga.com/list/new/" if pg == "1" else f"https://cn.bzmanga.com/list/new/?page={pg}"
        elif tid == "all":
            url = f"https://cn.bzmanga.com/classify?page={pg}"
        else:
            val = extend.get('val', '')
            if not val:
                if tid == "region": val = "cn"
                elif tid == "status": val = "serial"
                elif tid == "type": val = "dushi"
            
            param_key = tid
            if tid == "status": param_key = "state"
            
            url = f"https://cn.bzmanga.com/classify?{param_key}={val}&page={pg}"

        try:
            r = requests.get(url, headers=self.getHeader())
            soup = BeautifulSoup(r.text, 'html.parser')
            items = soup.select('.comics-card')
            
            videos = []
            for item in items:
                link_tag = item.select_one('a.comics-card__poster')
                if not link_tag: continue
                vid = link_tag['href']
                
                cover_tag = item.select_one('amp-img')
                cover = ""
                if cover_tag:
                    cover = cover_tag.get('src', '')
                    if ".w=" in cover:
                        cover = cover.split('.w=')[0]
                
                title_tag = item.select_one('.comics-card__title')
                name = title_tag.text.strip() if title_tag else ""
                
                videos.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": cover,
                    "vod_remarks": ""
                })
            
            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 36,
                "total": 999999
            }
        except Exception as e:
            return {"list": []}

    def detailContent(self, ids):
        vid = ids[0]
        url = f"https://cn.bzmanga.com{vid}" if not vid.startswith('http') else vid
        
        try:
            r = requests.get(url, headers=self.getHeader())
            soup = BeautifulSoup(r.text, 'html.parser')
            
            name = soup.select_one('.comics-detail__title').text.strip() if soup.select_one('.comics-detail__title') else "未知"
            author = soup.select_one('.comics-detail__author').text.strip() if soup.select_one('.comics-detail__author') else ""
            desc = soup.select_one('.comics-detail__desc').text.strip() if soup.select_one('.comics-detail__desc') else ""
            
            cover = ""
            cover_tag = soup.select_one('amp-img')
            if cover_tag:
                cover = cover_tag.get('src', '').split('.w=')[0]

            chapter_items = soup.select('.comics-chapters__item')
            
            # 解析原始列表
            raw_url_list = []
            for item in chapter_items:
                a_tag = item.select_one('a')
                if not a_tag: 
                    if item.name == 'a': a_tag = item
                    else: continue
                
                chapter_name = a_tag.text.strip()
                raw_href = a_tag.get('href', '')
                
                real_chapter_url = ""
                
                # 兼容多种链接格式
                match = re.search(r'comic_id=(\d+).*chapter_slot=(\d+)', raw_href)
                if match:
                    c_id = match.group(1)
                    c_slot = match.group(2)
                    real_chapter_url = f"https://cn.dzmanga.com/comic/chapter/{c_id}/0_{c_slot}.html"
                else:
                    if raw_href.startswith("/"):
                        real_chapter_url = f"https://cn.dzmanga.com{raw_href}"
                    elif "http" in raw_href:
                        real_chapter_url = raw_href.replace("cn.bzmanga.com", "cn.dzmanga.com")
                    else:
                        real_chapter_url = f"https://cn.dzmanga.com/{raw_href}"
                
                raw_url_list.append(f"{chapter_name}${real_chapter_url}")
            
            # 双向排序
            desc_list = list(raw_url_list)       # 倒序(原始)
            asc_list = list(raw_url_list)
            asc_list.reverse()                   # 正序(反转)
            
            str_desc = "#".join(desc_list)
            str_asc = "#".join(asc_list)

            return {
                "list": [{
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": cover,
                    "type_name": "漫画",
                    "vod_year": "",
                    "vod_area": "",
                    "vod_remarks": author,
                    "vod_actor": "",
                    "vod_director": "",
                    "vod_content": desc,
                    "vod_play_from": "正序(Mange)$$$正序(Pics)$$$倒序(Mange)$$$倒序(Pics)", 
                    "vod_play_url": f"{str_asc}$$${str_asc}$$${str_desc}$$${str_desc}"
                }]
            }
        except Exception as e:
            return {"list": []}

    def searchContent(self, key, quick, pg="1"):
        url = f"https://cn.bzmanga.com/search?q={key}"
        try:
            r = requests.get(url, headers=self.getHeader())
            soup = BeautifulSoup(r.text, 'html.parser')
            
            items = soup.select('.comics-card')
            videos = []
            for item in items:
                link_tag = item.select_one('a.comics-card__poster')
                if not link_tag: continue
                vid = link_tag['href']
                
                cover_tag = item.select_one('amp-img')
                cover = ""
                if cover_tag:
                    cover = cover_tag.get('src', '').split('.w=')[0]
                
                title_tag = item.select_one('.comics-card__title')
                name = title_tag.text.strip() if title_tag else ""
                
                videos.append({
                    "vod_id": vid,
                    "vod_name": name,
                    "vod_pic": cover,
                    "vod_remarks": ""
                })
            return {'list': videos}
        except:
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        url = id
        headers = self.getHeader()
        headers['Referer'] = url
        
        try:
            r = requests.get(url, headers=headers, timeout=10)
            html = r.text # 获取源码，用于正则提取
            soup = BeautifulSoup(html, 'html.parser')
            
            img_list = []
            
            # --- 策略A：尝试常规 DOM 解析 ---
            # PC端可能没有 .comic-contain 也没有 amp-img，而是普通的 img
            container = soup.select_one('.comic-contain')
            if not container:
                container = soup.select_one('body') # 如果没找到容器，就搜 body
                
            if container:
                imgs = container.select('amp-img')
                if not imgs:
                    imgs = container.select('img') # 尝试普通 img
                
                for img in imgs:
                    src = img.get('src') or img.get('data-src')
                    if src:
                        # 过滤垃圾图
                        if "next_chapter" in src or "prev_chapter" in src or "icon" in src or "logo" in src:
                            continue
                        if src.startswith("//"):
                            src = "https:" + src
                        img_list.append(src)
            
            # --- 【修改2】策略B：暴力正则提取 (针对“去APP看”的限制) ---
            # 如果策略A没找到图片，或者只找到了很少的图片（可能是被遮挡了），就用正则从源码里抓
            # 包子漫画的图片通常是 static-tw.baozimh.com 域名
            if len(img_list) < 2:
                # 匹配 http 或 https 开头的图片链接，支持 jpg/png/webp
                # 排除 .js, .css, .html 等非图片链接
                # 核心特征：static-tw.baozimh.com
                pattern = r'(https?://[^"\'\s]+static[^"\'\s]+\.(?:jpg|png|webp|jpeg)(?:\?[^"\'\s]*)?)'
                matches = re.findall(pattern, html)
                
                for m in matches:
                    if m not in img_list:
                         # 再次过滤可能的缩略图或垃圾图
                        if "cover" in m: continue # 排除封面
                        img_list.append(m)

            # 去重
            unique_imgs = []
            [unique_imgs.append(i) for i in img_list if i not in unique_imgs]

            novel_data = "&&".join(unique_imgs)
            
            protocol = "pics" if "Pics" in flag else "mange"
            
            return {
                "parse": 0,
                "playUrl": "",
                "url": f'{protocol}://{novel_data}',
                "header": ""
            }
        except Exception as e:
            return {
                "parse": 0,
                "playUrl": "",
                "url": "",
                "header": ""
            }

    def localProxy(self, param):
        pass
