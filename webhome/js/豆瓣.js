/*
@header({
  searchable: 0,
  filterable: 0,
  quickSearch: 0,
  title: '豆瓣推荐',
  lang: 'cat'
})
*/

let siteName = "豆瓣推荐"
let siteKey = ""
let siteType = 0

const headers = {
  "Host": "frodo.douban.com",
  "Connection": "Keep-Alive",
  "Referer": "https://servicewechat.com/wx2f9b06c1de1ccfca/84/page-frame.html",
  "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36 MicroMessenger/7.0.9.501 NetType/WIFI MiniProgramEnv/Windows WindowsWechat",
}

async function request(url, options = {}) {
  const reqHeaders = { ...headers, ...options.headers }
  let postType = reqHeaders["Content-Type"]?.includes("json")
    ? "json"
    : reqHeaders["Content-Type"]?.includes("form")
      ? "form"
      : ""

  try {
    const response = await req(url, {
      method: options.method || "GET",
      headers: reqHeaders,
      data: options.data,
      postType: postType,
      timeout: options.timeout || 15000,
    })
    return response?.content || response?.data || response
  } catch {
    return null
  }
}

async function init(cfg) {
  siteName = cfg.skey?.split("_")[1] || cfg.skey || "豆瓣推荐"
  siteKey = cfg.skey
  siteType = cfg.stype
}

function home(filter) {
  let classes = [
    { type_id: "hot_gaia", type_name: "热门电影" },
    { type_id: "tv_hot", type_name: "热播剧集" },
    { type_id: "show_hot", type_name: "热播综艺" },
  ]
  return JSON.stringify({ class: classes })
}

async function homeVod() {
  return await category("hot_gaia", 1, null, null)
}

async function category(tid, pg, filter, extend) {
  if (pg <= 0) pg = 1
  const limit = 20
  const start = (pg - 1) * limit
  let url = ""
  let listKey = "items"

  if (tid === "hot_gaia") {
    url = `https://frodo.douban.com/api/v2/movie/hot_gaia?apikey=0ac44ae016490db2204ce0a042db2916&sort=recommend&area=${encodeURIComponent("全部")}&start=${start}&count=${limit}`
    listKey = "items"
  } else if (tid === "tv_hot") {
    url = `https://frodo.douban.com/api/v2/subject_collection/tv_hot/items?apikey=0ac44ae016490db2204ce0a042db2916&start=${start}&count=${limit}`
    listKey = "subject_collection_items"
  } else if (tid === "show_hot") {
    url = `https://frodo.douban.com/api/v2/subject_collection/show_hot/items?apikey=0ac44ae016490db2204ce0a042db2916&start=${start}&count=${limit}`
    listKey = "subject_collection_items"
  } else {
    url = `https://frodo.douban.com/api/v2/movie/hot_gaia?apikey=0ac44ae016490db2204ce0a042db2916&sort=recommend&area=${encodeURIComponent("全部")}&start=${start}&count=${limit}`
    listKey = "items"
  }

  let html = await request(url)
  let list = []
  if (html) {
    try {
      let data = JSON.parse(html)
      let items = data[listKey]
      if (items && Array.isArray(items)) {
        list = items.map((item) => {
          let vod_pic = item.pic?.normal || item.pic?.large || ""
          if (vod_pic) {
            vod_pic = `${vod_pic}@Referer=https://api.douban.com/@User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36`
          }

          let vod_remarks = ""
          if (item.rating && item.rating.value != null) {
            vod_remarks = "评分：" + item.rating.value
          }

          let vod_id = "msearch:" + (item.id || "")

          return {
            vod_id: vod_id,
            vod_name: item.title || "",
            vod_pic: vod_pic,
            vod_remarks: vod_remarks,
          }
        })
        
        // 过滤掉没有图片的条目 (同 Douban.java filterItemsWithoutPic)
        list = list.filter(item => item.vod_pic !== "")
      }
    } catch (e) {
        console.log("豆瓣推荐解析错误", e)
    }
  }

  return JSON.stringify({
    page: parseInt(pg),
    pagecount: 999,
    limit: 20,
    total: 99999,
    list: list,
  })
}

async function detail(id) {
  return JSON.stringify({ list: [] })
}

async function play(flag, id, flags) {
  return JSON.stringify({ parse: 0, url: "" })
}

async function search(wd, quick, pg) {
  return JSON.stringify({ list: [] })
}

export function __jsEvalReturn() {
  return { init, home, homeVod, category, detail, play, search }
}
