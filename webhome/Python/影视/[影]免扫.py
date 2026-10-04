# coding=utf-8
# !/usr/bin/python
# Pomo 4K原盘 TVBox爬虫
# 支持磁力链接播放（需TVBox配置磁力解析器）
import re
import sys
from urllib.parse import quote

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def init(self, extend=""):
        pass

    def getName(self):
        return "Pomo4K"

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    host = 'https://pomo.mom'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Referer': 'https://pomo.mom/',
    }

    # 分类配置
    CATEGORIES = {
        'home': {'name': '首页', 'url': ''},
        'huayu': {'name': '华语热门', 'url': 'huayurm'},
        'jiating': {'name': '家庭影院', 'url': 'jiating'},
        'donghua': {'name': '动画大电影', 'url': 'donghuadadiany'},
        'lengmen': {'name': '冷门佳片', 'url': 'lengmenjiapian'},
        'top250': {'name': 'TOP250', 'url': 'paihangbang'},
        'languang': {'name': '蓝光原盘', 'url': 'sort/12'},
        'dianshiju': {'name': '剧集', 'url': 'dianshiju'},
    }

    def homeContent(self, filter):
        result = {}
        classes = []
        for tid, info in self.CATEGORIES.items():
            classes.append({
                'type_name': info['name'],
                'type_id': tid
            })
        result['class'] = classes
        result['filters'] = {}
        return result

    def homeVideoContent(self):
        return self._parse_list(f'{self.host}/')

    def categoryContent(self, tid, pg, filter, extend):
        cat = self.CATEGORIES.get(tid)
        if not cat:
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 16, 'total': 0}

        if cat['url']:
            url = f'{self.host}/{cat["url"]}'
        else:
            url = f'{self.host}/'

        if int(pg) > 1:
            # 首页用 /page/N，其他分类用 /分类/page/N
            if cat['url']:
                url = f'{self.host}/{cat["url"]}/page/{pg}'
            else:
                url = f'{self.host}/page/{pg}'

        result = self._parse_list(url)
        result['page'] = pg
        result['pagecount'] = 9999
        result['limit'] = 16
        result['total'] = 999999
        return result

    def _parse_list(self, url):
        """解析列表页，返回视频列表"""
        try:
            resp = self.fetch(url, headers=self.headers)
            text = self._get_text(resp)
            videos = []
            seen = set()

            # 找到内容区域（All 4K Movies 或 <main> 之后）
            start = text.find('All 4K Movies')
            if start == -1:
                start = text.find('<main')
            if start == -1:
                start = 0
            section = text[start:]

            # 匹配所有 uploadfile 图片
            img_pattern = r'<img[^>]*src="([^"]*uploadfile[^"]*)"[^>]*alt="([^"]*)"[^>]*>'
            pos = 0
            while True:
                img_match = re.search(img_pattern, section[pos:])
                if not img_match:
                    break

                img_src = img_match.group(1)
                img_alt = img_match.group(2)
                img_start = pos + img_match.start()
                img_end = pos + img_match.end()

                # 向前找最近的 <a href="https://pomo.mom/数字">
                before = section[max(0, img_start - 2000):img_start]
                a_match = None
                for m in re.finditer(r'<a\s+href="https://pomo\.mom/(\d+)(?:\.html)?"', before):
                    a_match = m

                if a_match:
                    vid = a_match.group(1)
                    if vid not in seen:
                        seen.add(vid)
                        videos.append({
                            'vod_id': vid,
                            'vod_name': img_alt,
                            'vod_pic': img_src,
                            'vod_remarks': ''
                        })

                pos = img_end

            return {'list': videos}
        except Exception as e:
            print(f'[Pomo] 解析列表出错: {e}')
            return {'list': []}

    # ==================== 新增：按清晰度分组磁力链接（参考6v逻辑） ====================
    def _classify_magnet(self, title, url):
        """
        根据标题和URL判断磁力链接的清晰度分类
        返回: (line_name, display_title)
        """
        check_str = (title + ' ' + url).lower()
        
        # 判断清晰度
        if '4k' in check_str or '2160p' in check_str:
            line_name = '磁力 2160p'
        elif '1080p' in check_str:
            line_name = '磁力 1080p'
        elif '720p' in check_str:
            line_name = '磁力 720p'
        else:
            line_name = '磁力下载'
        
        # 从标题中提取文件大小信息，帮助用户选择（参考6v）
        size_match = re.search(r'([0-9]+\.?[0-9]*\s*[GMTK]B)', title, re.IGNORECASE)
        if size_match and size_match.group(1) not in title:
            display_title = f"{title} [{size_match.group(1)}]"
        else:
            display_title = title
            
        return line_name, display_title

    def detailContent(self, ids):
        try:
            vid = ids[0]
            url = f'{self.host}/{vid}.html'
            resp = self.fetch(url, headers=self.headers)
            text = self._get_text(resp)

            # 标题
            title_match = re.search(r'<h2 class="x-dbjs-title">([^<]+)</h2>', text)
            title = title_match.group(1).strip() if title_match else ''

            # 海报
            poster_match = re.search(r'<div class="x-dbjs-poster"><img src="([^"]+)"', text)
            poster = poster_match.group(1) if poster_match else ''

            # 元信息
            meta = {}
            meta_rows = re.findall(r'<div class="meta-row[^"]*"><span>([^<]+)</span>([^<]+)</div>', text)
            for label, value in meta_rows:
                label = label.strip().replace('：', '')
                meta[label] = value.strip()

            # 演员（特殊处理 actors 行）
            actors_match = re.search(r'<div class="meta-row actors[^"]*"><span>演员阵容：</span>([^<]+)</div>', text)
            actors = actors_match.group(1).strip() if actors_match else meta.get('演员阵容', '')

            # 导演
            director = meta.get('导演', '')

            # 类型
            type_name = meta.get('类型', '')

            # 年份（从时间提取）
            year = ''
            time_str = meta.get('时间', '')
            if time_str:
                year_match = re.search(r'(\d{4})', time_str)
                if year_match:
                    year = year_match.group(1)

            # 简介
            desc_match = re.search(r'<div class="x-dbjs-desc-block[^"]*"><h3[^>]*>剧情简介</h3><p>([^<]+)</p>', text)
            desc = desc_match.group(1).strip() if desc_match else ''

            # ==================== 重构：按线路分组播放源（参考6v playMap逻辑） ====================
            play_map = {}  # 等价于6v的 playMap

            # 1. 处理磁力链接（按清晰度分组）
            items = re.findall(r'<div class="download-item">(.*?)</div>\s*</div>', text, re.DOTALL)
            seen_items = set()
            for item in items:
                mag_match = re.search(r'data-url="(magnet:\?xt=urn:btih:[^"]+)"', item)
                if not mag_match:
                    continue
                mag = mag_match.group(1)
                if mag in seen_items:
                    continue
                seen_items.add(mag)

                # 提取文件名
                name_match = re.search(r'class="x-dbjs-download-link[^"]*"[^>]*>([^<]+)</a>', item)
                file_name = name_match.group(1).strip() if name_match else ''

                # 提取大小
                size_match = re.search(r'<span class="file-size">\[([^\]]+)\]</span>', item)
                size = size_match.group(1).strip() if size_match else ''

                # 构建标题
                if file_name and size:
                    play_title = f"{file_name} [{size}]"
                elif file_name:
                    play_title = file_name
                elif size:
                    play_title = f"磁力 [{size}]"
                else:
                    play_title = f"磁力{len(seen_items)}"

                # 按清晰度分类（核心改进，参考6v）
                line_name, display_title = self._classify_magnet(play_title, mag)
                
                if line_name not in play_map:
                    play_map[line_name] = []
                
                # 去重检查（同6v逻辑）
                exists = any(item.endswith(f'${mag}') for item in play_map[line_name])
                if not exists:
                    play_map[line_name].append(f"{display_title[:80]}${mag}")

            # 兜底：如果 download-item 解析失败，直接用原始磁力正则
            if not play_map:
                magnets = re.findall(r'data-url="(magnet:\?xt=urn:btih:[^"]+)"', text)
                seen_mag = set()
                for i, mag in enumerate(magnets):
                    if mag in seen_mag:
                        continue
                    seen_mag.add(mag)
                    line_name, _ = self._classify_magnet('', mag)
                    if line_name not in play_map:
                        play_map[line_name] = []
                    play_map[line_name].append(f"磁力{i+1}${mag}")

            # 2. 处理网盘链接（夸克网盘）
            pan_links = re.findall(r'data-url="(https://pan\.quark\.cn/s/[^"]+)"', text)
            if pan_links:
                play_map['夸克网盘'] = []
                seen_pan = set()
                for i, pan in enumerate(pan_links):
                    if pan in seen_pan:
                        continue
                    seen_pan.add(pan)
                    # 去重检查
                    exists = any(item.endswith(f'${pan}') for item in play_map['夸克网盘'])
                    if not exists:
                        play_map['夸克网盘'].append(f"夸克网盘{i+1}${pan}")

            # ==================== 组装播放源（参考6v sortedLines逻辑） ====================
            play_from = []
            play_url = []
            
            # 按优先级排序线路（同6v的 sortedLines）
            sorted_lines = ['磁力 2160p', '磁力 1080p', '磁力 720p', '磁力下载', '夸克网盘']
            
            for key in sorted_lines:
                if key in play_map and play_map[key]:
                    play_from.append(key)
                    play_url.append('#'.join(play_map[key]))
            
            # 处理未在排序列表中的其他线路
            for key in play_map:
                if key not in sorted_lines and play_map[key]:
                    play_from.append(key)
                    play_url.append('#'.join(play_map[key]))

            # 兜底：没有任何播放源
            if not play_from:
                play_from = ['磁力']
                play_url = [f'正片${vid}']

            vod = {
                'vod_id': vid,
                'vod_name': title,
                'type_name': type_name,
                'vod_year': year,
                'vod_remarks': f"IMDB {meta.get('IMDB', '')}" if meta.get('IMDB') else '',
                'vod_actor': actors,
                'vod_director': director,
                'vod_content': desc,
                'vod_pic': poster,
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_url),
            }

            return {'list': [vod]}
        except Exception as e:
            print(f'[Pomo] 解析详情出错: {e}')
            return {'list': []}

    def searchContent(self, key, quick, pg="1"):
        try:
            url = f'{self.host}/?keyword={quote(key)}'
            if int(pg) > 1:
                url = f'{self.host}/page/{pg}?keyword={quote(key)}'
            result = self._parse_list(url)
            result['page'] = pg
            result['pagecount'] = 9999
            result['limit'] = 16
            result['total'] = 999999
            return result
        except Exception as e:
            print(f'[Pomo] 搜索出错: {e}')
            return {'list': [], 'page': pg, 'pagecount': 1, 'limit': 16, 'total': 0}

    # ==================== 修改：对齐6v播放逻辑 ====================
    def playerContent(self, flag, id, vipFlags):
        """
        参考6v的play函数逻辑：
        - 磁力链接: parse=0, jx=0 直接返回（让播放器本地处理）
        - 其他链接: parse=0, 直接返回
        """
        if id.startswith('magnet:'):
            # 6v逻辑：parse=0, jx=0，直接返回磁力链接，不触发解析
            return {
                'parse': 0,
                'jx': 0,
                'url': id,
                'header': '',
            }
        elif id.startswith('https://pan.quark.cn'):
            # 夸克网盘仍需要外部解析
            return {
                'parse': 1,
                'url': id,
                'header': '',
            }
        else:
            # 其他链接直接返回（同6v）
            return {
                'parse': 0,
                'url': id,
                'header': '',
            }

    def localProxy(self, param):
        pass

    def _get_text(self, resp):
        """兼容不同返回类型获取文本"""
        if hasattr(resp, 'text'):
            return resp.text
        elif hasattr(resp, '_data'):
            return resp._data.decode('utf-8') if hasattr(resp._data, 'decode') else str(resp._data)
        else:
            return resp.decode('utf-8') if hasattr(resp, 'decode') else str(resp)
