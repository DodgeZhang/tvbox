# -*- coding: utf-8 -*-
import re, json
from urllib.parse import quote
from lxml import etree
from base.spider import Spider

class Spider(Spider):
	def getName(self): return "阳光影视"

	def init(self, extend=""):
		self.host = "https://www.yangguangbd.com"
		self.headers = {"User-Agent": "Mozilla/5.0", "Referer": self.host + "/"}
		self.categories = [
			{"type_id": "dying", "type_name": "电影"},
			{"type_id": "dshiju", "type_name": "电视剧"},
			{"type_id": "dman", "type_name": "动漫"},
			{"type_id": "zying", "type_name": "综艺"},
			{"type_id": "jilupian", "type_name": "纪录片"},
			{"type_id": "duanju", "type_name": "短剧"},
		]

	def _get(self, url):
		try:
			r = self.fetch(url, headers=self.headers, timeout=15)
			return r.text
		except Exception:
			return ""

	def _fix(self, u):
		if not u: return ""
		if u.startswith("//"): return "https:" + u
		if u.startswith("/"): return self.host + u
		return u

	def _cards(self, html):
		if not html: return []
		tree = etree.HTML(html)
		out, seen = [], set()
		for a in tree.xpath('//a[contains(@class,"stui-vodlist__thumb")]'):
			try:
				m = re.search(r'/ygn/(\d+)\.html', a.get("href", ""))
				if not m or m.group(1) in seen: continue
				seen.add(m.group(1))
				pic = a.get("data-original") or a.get("data-src") or (a.xpath('.//img/@data-original') or ["", ])[0] or (a.xpath('.//img/@src') or ["", ])[0]
				title = a.get("title", "").strip() or "".join(a.xpath('.//img/@alt')).strip() or "".join(a.xpath('.//text()')).strip()
				out.append({"vod_id": m.group(1), "vod_name": title, "vod_pic": self._fix(pic)})
			except Exception:
				continue
		return out

	def homeContent(self, filter):
		html = self._get(self.host)
		return {"class": self.categories, "list": self._cards(html), "filters": {}}

	def homeVideoContent(self):
		return self.categoryContent("dying", "1", "1", {})

	def categoryContent(self, tid, pg, filter, extend):
		pg = int(pg or 1)
		url = f"{self.host}/ygx/{tid}-----------.html" if pg == 1 else f"{self.host}/ygx/{tid}--------{pg}---.html"
		html = self._get(url)
		return {"page": pg, "pagecount": 9999, "limit": 36, "total": 999999, "list": self._cards(html)}

	def detailContent(self, ids):
		vid = ids[0]
		html = self._get(f"{self.host}/ygn/{vid}.html")
		result = {"list": []}
		if not html: return result
		tree = etree.HTML(html)
		name = "".join(tree.xpath('//h1/text()')).strip()
		pic = "".join(tree.xpath('//div[contains(@class,"stui-content__thumb")]//img/@data-original | //div[contains(@class,"stui-content__thumb")]//img/@src'))
		sources, urls, seen = [], [], set()
		boxes = tree.xpath('//div[contains(@class,"stui-pannel-box")][.//ul[contains(@class,"stui-content__playlist")]]')
		for b in boxes:
			src = "".join(b.xpath('.//h2[contains(@class,"title")]//text()')).strip() or f"线路{len(sources)+1}"
			eps = []
			for a in b.xpath('.//ul[contains(@class,"stui-content__playlist")]//a'):
				href = a.get("href", "")
				if not href or href in seen: continue
				seen.add(href)
				eps.append(f'{"".join(a.xpath(".//text()")).strip()}${self._fix(href)}')
			if eps:
				sources.append(src)
				urls.append("#".join(eps))
		info = {"vod_id": vid, "vod_name": name, "vod_pic": self._fix(pic),
				"vod_play_from": "$$$".join(sources), "vod_play_url": "$$$".join(urls)}
		info.update(self._meta(tree))
		result["list"].append(info)
		return result

	def searchContent(self, key, quick, pg="1"):
		url = f"{self.host}/ygs/{quote(key)}-------------.html"
		return {"list": self._cards(self._get(url)), "page": int(pg)}

	def playerContent(self, flag, id, vipFlags):
		html = self._get(self._fix(id))
		play = ""
		if html:
			m = re.search(r'player_\w+\s*=\s*(\{.*?\})\s*</script', html, re.S)
			if m:
				try:
					play = json.loads(m.group(1).replace('\\/', '/')).get('url') or ""
				except Exception:
					play = ""
			if not play:
				mm = re.search(r'(?:https?:)?//[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
				if mm:
					play = mm.group(0)
					if play.startswith("//"): play = "https:" + play
		header = {"User-Agent": "Mozilla/5.0"}
		if play:
			hm = re.search(r'https?://([^/]+)', play)
			header["Referer"] = f"https://{hm.group(1)}/" if hm else self.host
		return {"parse": 0, "url": play, "header": json.dumps(header)}

	def isVideoFormat(self, url): return ".m3u8" in url or ".mp4" in url

	def manualVideoCheck(self): return False

	def _meta(self, tree):
		txt = "\n".join(tree.xpath('//div[contains(@class,"stui-content__detail")]//p//text()'))
		m = {}
		for key, ck in [('vod_actor','主演'),('vod_director','导演'),('vod_area','地区'),('vod_year','年份'),('vod_remarks','状态'),('vod_class','类型')]:
			mm = re.search(ck + r'\s*[:：]\s*([^\n]+)', txt)
			if mm: m[key] = mm.group(1).strip()
		return m

	def localProxy(self, param): return None

	def destroy(self): return None