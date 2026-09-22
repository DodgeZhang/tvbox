import sys,json,base64,requests as R
sys.path.append('..')
from base.spider import Spider as B
H="https://www.qingmaisp.com"
U="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
D=base64.b64encode(b"TVBoxQMSP00000001").decode()
T=[("M16","电影"),("M15","电视剧"),("M17","动漫"),("M18","综艺"),("M416","纪录片")]

class Spider(B):
 def _p(self,pth,pld=None,auth=1):
  h={"User-Agent":U,"Content-Type":"application/json;charset=UTF-8","client":"pc","devicetype":"web","useclient":"pc","Referer":H+"/"}
  if auth:h["token"]=self._t();h["deviceId"]=D
  d=json.dumps(pld or {}).encode()
  for _ in(0,1):
   try:r=R.post(H+pth,data=d,headers=h,timeout=15);return r.json()if r.status_code==200 and r.text else{}
   except:pass
  if auth:self._tk="";return self._p(pth,pld,0)
  return{}
 def _t(self,f=0):
  if getattr(self,"_tk",None)and not f:return self._tk
  try:self._tk=R.post(H+"/api/auth/deviceIdLogin?deviceId="+D,headers={"User-Agent":U,"client":"pc","devicetype":"web","useclient":"pc"},timeout=15).json().get("data","");return self._tk
  except:return""
 def init(self,e=""):self._e=e;return""
 def getName(self):return"青麦视频"
 def isVideoFormat(self,u):return".m3u8"in u or".mp4"in u
 def manualVideoCheck(self):return 0
 def destroy(self):pass
 def _v(self,l):
  r=[]
  for x in l:
   if not isinstance(x,dict):continue
   t=x.get("typeId","M");m=x.get("id","");k=x.get("remarks")or("全集%s集"%x.get("totalEpisode")if isinstance(x.get("totalEpisode"),int)and x.get("totalEpisode")>1 else"高清")
   r.append({"vod_id":"%s@@%s"%(t,m),"vod_name":x.get("name",""),"vod_pic":x.get("cover",""),"vod_remarks":k,"vod_year":str(x.get("year")or"")})
  return r
 def homeContent(self,f=1):return{"class":[{"type_id":a,"type_name":b}for a,b in T],"list":self._v(self._p("/api/v1/pc/screen/screenMovie",{"condition":{"sreecnTypeEnum":"HOT","typeId":"M"},"pageNum":1,"pageSize":30}).get("data",{}).get("records",[]))}
 def homeVideoContent(self):return{"list":self._v(self._p("/api/v1/pc/screen/screenMovie",{"condition":{"sreecnTypeEnum":"NEWEST","typeId":"M"},"pageNum":1,"pageSize":30}).get("data",{}).get("records",[]))}
 def categoryContent(self,tid,pg=1,f=1,ext=None):
  ext=ext or{};p=int(pg)if str(pg).isdigit()else 1;c={"typeId":str(tid),"sreecnTypeEnum":ext.get("sort","HOT"),"source":"0"}
  for k in("region","classify","year"):
   if ext.get(k):c[k]=ext[k]
  d=self._p("/api/v1/pc/screen/screenMovie",{"condition":c,"pageNum":p,"pageSize":30}).get("data",{});r=d.get("records",[]);t=d.get("total",0);n=(t+29)//30 if t else 1
  if not r and p>1:n=p-1
  return{"list":self._v(r),"page":p,"pagecount":max(n,p),"limit":30,"total":t}
 def detailContent(self,ids):
  v=ids[0]if isinstance(ids,list)else str(ids);t,m=v.split("@@");d=self._p("/api/v1/pc/play/movieDesc",{"id":m,"playerId":90,"typeId":t}).get("data",{});e=self._p("/api/v1/pc/play/movieDetails",{"id":m,"playerId":90,"episodeId":None,"typeId":t}).get("data",{});l=e.get("episodeList",[])
  o={"vod_id":v,"vod_name":d.get("name")or e.get("name",""),"vod_pic":d.get("cover",""),"vod_year":d.get("year",""),"vod_area":d.get("area",""),"vod_score":str(d.get("score")or""),"vod_actor":d.get("star",""),"vod_director":d.get("director",""),"vod_content":(d.get("introduce")or"").replace("&","／"),"type_name":d.get("classify","")}
  if l:o["vod_play_from"]="青麦视频";o["vod_play_url"]="#".join(["%s$%s@@%s@@%s"%((x.get("episode")or"第%s集"%x.get("episodeNum","?")),t,m,x.get("id",""))for x in l])
  else:o["vod_play_from"]="青麦视频";o["vod_play_url"]="正片$%s@@%s@@"%(t,m)
  return{"list":[o]}
 def searchContent(self,*a,**k):
  q=str(a[0]if a else k.get("key","")).strip()
  if not q:return{"list":[],"page":1,"pagecount":1,"limit":30,"total":0}
  d=self._p("/api/v1/pc/search/searchMovie",{"condition":{"value":q},"pageNum":1,"pageSize":30}).get("data",{});r=d.get("records",[])
  return{"list":self._v(r),"page":1,"pagecount":d.get("pages",1),"limit":30,"total":d.get("total",len(r))}
 def playerContent(self,flag,id,vipFlags=None):
  p=str(id).split("@@");t,m=p[0],p[1];e=int(p[2])if len(p)>2 and p[2]and p[2]!="null"else None;u=self._p("/api/v1/pc/play/movieDetails",{"id":m,"playerId":90,"episodeId":e,"typeId":t}).get("data",{}).get("url","")
  if not u and t!="M":u=self._p("/api/v1/pc/play/movieDetails",{"id":m,"playerId":90,"episodeId":e,"typeId":"M"}).get("data",{}).get("url","")
  for s in("～","~"):
   if s in u:u=u.split(s)[0];break
  if"*"in u:u=u.split("*",1)[1]
  return{"parse":0,"playUrl":"","url":u.strip(),"header":{"User-Agent":U,"Referer":H+"/"}}
 def localProxy(self,p):return{}
