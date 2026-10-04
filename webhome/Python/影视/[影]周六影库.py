import sys
import json
import re
import requests
from bs4 import BeautifulSoup
from base.spider import Spider

class Spider(Spider):
    def getName(self):
        return "周六影库"

    def init(self, extend=""):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def homeContent(self, filter):
        result = {}
        # 手动配置主分类，适配TVBox大类菜单
        cateManual = {
            "电影": "1",
            "电视剧": "2",
            "综艺": "3",
            "动漫": "4",
            "动画片": "25",
            "体育赛事": "28"
        }
        classes = []
        for k in cateManual:
            classes.append({
                'type_name': k,
                'type_id': cateManual[k]
            })
        result['class'] = classes
        if filter:
            result['filters'] = {}
        return result

    def homeVideoContent(self):
        # 首页推荐视频，默认留空或获取最新
        return {"list": []}

    def jar_list_from_html(self, html_text):
        """
        核心解析模组：借鉴海阔影视规则，完美适配TVBox格式
        """
        soup = BeautifulSoup(html_text, 'html.parser')
        vods = []
        # 获取海阔规则对应的 .stui-vodlist 里面的 li 标签
        items = soup.select('.stui-vodlist li')
        for item in items:
            a_tag = item.select_one('a.stui-vodlist__thumb')
            if not a_tag:
                continue
            
            href = a_tag.get('href', '')
            title = a_tag.get('title', '')
            
            # 过滤广告位与无效链接
            if not href or href == '#' or '红包' in title or '广告' in title:
                continue
                
            # 兼容处理未在a标签写标题的情况
            if not title:
                h4_a = item.select_one('.stui-vodlist__title a')
                if h4_a:
                    title = h4_a.get_text(strip=True)
            
            # 提取图片路径
            img = a_tag.get('data-original', '')
            if img.startswith('//'):
                img = 'https:' + img
            elif img.startswith('/'):
                img = 'https://www.zlykw.com' + img
                
            # 提取更新状态 / 备注（对应海阔里的 .pic-text&&Text）
            remarks = ''
            remark_tag = a_tag.select_one('.pic-text')
            if remark_tag:
                remarks = remark_tag.get_text(strip=True)
                
            vods.append({
                "vod_id": href,
                "vod_name": title,
                "vod_pic": img,
                "vod_remarks": remarks
            })
        return vods

    def categoryContent(self, tid, pg, filter, extend):
        # MacCMS标准分类页处理
        if int(pg) <= 1:
            url = f"https://www.zlykw.com/vodtype/{tid}.html"
        else:
            url = f"https://www.zlykw.com/vodtype/{tid}-{pg}.html"
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        }
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = 'utf-8'
            vods = self.jar_list_from_html(res.text)
            return {
                "page": pg,
                "pagecount": int(pg) + 1,
                "limit": len(vods),
                "total": len(vods) * int(pg),
                "list": vods
            }
        except Exception as e:
            return {"list": []}

    def detailContent(self, array):
        # 详情页模组
        vod_id = array[0]
        if not vod_id.startswith('http'):
            url = "https://www.zlykw.com" + vod_id
        else:
            url = vod_id
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        }
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            title_tag = soup.select_one('.stui-content__detail .title')
            title = title_tag.get_text(strip=True) if title_tag else ""
            
            pic_tag = soup.select_one('.stui-content__thumb img')
            pic = pic_tag.get('data-original', '') if pic_tag else ""
            if pic.startswith('//'):
                pic = 'https:' + pic
            elif pic.startswith('/'):
                pic = 'https://www.zlykw.com' + pic
                
            actor, director, remarks, desc = "", "", "", ""
            detail_p = soup.select('.stui-content__detail p')
            for p in detail_p:
                text = p.get_text(strip=True)
                if "主演" in text:
                    actor = text.replace("主演：", "").replace("主演:", "")
                elif "导演" in text:
                    director = text.replace("导演：", "").replace("导演:", "")
                elif "类型" in text or "分类" in text:
                    remarks = text
                    
            desc_tag = soup.select_one('.stui-pannel_detail .detail') or soup.select_one('.detail-content')
            if desc_tag:
                desc = desc_tag.get_text(strip=True)
                
            vod = {
                "vod_id": vod_id,
                "vod_name": title,
                "vod_pic": pic,
                "type_name": remarks,
                "vod_remarks": remarks,
                "vod_actor": actor,
                "vod_director": director,
                "vod_content": desc
            }
            
            # 解析选集列表（MacCMS 的 stui-content__playlist 标签）
            play_froms = []
            play_urls = []
            panels = soup.select('.stui-pannel')
            source_idx = 1
            for panel in panels:
                playlist_ul = panel.select_one('ul.stui-content__playlist')
                if playlist_ul:
                    head = panel.select_one('.stui-pannel__head .title')
                    from_name = head.get_text(strip=True) if head else f"播放源 {source_idx}"
                    source_idx += 1
                    
                    links = playlist_ul.select('li a')
                    urls = []
                    for link in links:
                        name = link.get_text(strip=True)
                        href = link.get('href', '')
                        urls.append(f"{name}${href}")
                    
                    if urls:
                        play_froms.append(from_name)
                        play_urls.append("#".join(urls))
                        
            vod['vod_play_from'] = "$$$".join(play_froms)
            vod['vod_play_url'] = "$$$".join(play_urls)
            return {"list": [vod]}
        except Exception as e:
            return {"list": []}

    def searchContent(self, key, quick):
        """
        修复后的搜索模组：
        使用 requests.Session() 保持会话，先 GET 建立会话，再通过标准的 POST 传参提交
        """
        search_url = "https://www.zlykw.com/vodsearch/-------------.html"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
            "Origin": "https://www.zlykw.com",
            "Referer": "https://www.zlykw.com/vodsearch/-------------.html"
        }
        data = {
            "wd": key,
            "submit": ""
        }
        try:
            session = requests.Session()
            # 1. 第一步先访问搜索主页获取关键的 PHPSESSID 等安全 Cookie 校验
            session.get(search_url, headers=headers, timeout=10)
            # 2. 第二步带上会话 Cookie 发送 POST 搜索数据
            res = session.post(search_url, headers=headers, data=data, timeout=10)
            res.encoding = 'utf-8'
            
            # 调用核心解析模组，完美提取搜索结果
            vods = self.jar_list_from_html(res.text)
            return {"list": vods}
        except Exception as e:
            return {"list": []}

    def playerContent(self, flag, id, vip):
        # 播放解析模组
        if not id.startswith('http'):
            url = "https://www.zlykw.com" + id
        else:
            url = id
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
        }
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.encoding = 'utf-8'
            
            # 正则匹配 MacCMS 播放页自带的 MacPlayer 变量
            match = re.search(r'var\s+MacPlayer\s*=\s*({.*?});', res.text)
            if match:
                player_json = json.loads(match.group(1))
                play_url = player_json.get('url', '')
                
                # 判断是否是直链视频，如果是直链让TVBox自主嗅探/播放 (parse=0)，否则交由内置解析处理 (parse=1)
                parse = 1
                if play_url.startswith('http') and ('.m3u8' in play_url or '.mp4' in play_url):
                    parse = 0
                    
                return {
                    "parse": parse,
                    "url": play_url,
                    "header": {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
                    }
                }
            return {"parse": 1, "url": url, "header": ""}
        except Exception as e:
            return {"parse": 1, "url": url, "header": ""}

if __name__ == '__main__':
    # 测试搜索结果
    spider = Spider()
    print(spider.searchContent("主角", False))
