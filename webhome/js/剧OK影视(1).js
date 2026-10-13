// 刁民制作，仅供测试，测试完毕请24小时删除！
// ================================================================
// 剧OK 爬虫 - TVBox/影视仓 drpy2 ES模块格式
// 支持: 动态域名抓取 | 多源搜索 | 4K高清播放 | 详细筛选器
// ================================================================
import cheerio from 'assets://js/lib/cheerio.min.js';

// ===== 站点配置 (siteUrl 会被 init 动态更新) =====
const appConfig = {
    siteName: "剧OK",
    siteUrl: "https://juok3.top"
};
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

// 备用域名列表 (网站换域名时自动尝试)
const fallbackDomains = [
    "https://juok3.top",
    "https://juok1.top",
    "https://juok2.top",
    "https://juok.top",
    "https://juok4.top",
    "https://juok5.top"
];

// ===== 播放源站点名映射 =====
const siteNames = {
    "qiyi": "爱奇艺", "youku": "优酷", "qq": "腾讯视频", "mgtv": "芒果TV", "imgo": "芒果TV",
    "bilibili": "B站", "bilibili1": "B站", "douyin": "抖音", "leshi": "乐视", "le": "乐视",
    "cntv": "CCTV", "sohu": "搜狐", "pptv": "PPTV", "wasu": "华数", "1905": "1905电影网"
};

// ===== 解析线路 (含4K高清) =====
const parseLines = [
    { name: "原画4K(嗅探直连)", url: "" },
    { name: "S线路(超清解析)", url: "https://super.playr.top/?url=" },
    { name: "F线路(Fongmi)", url: "https://json.fongmi.cc/web?url=" },
    { name: "JSON解析(4K)", url: "https://jx.jsonplayer.com/player/?url=" },
    { name: "爱豆解析(超清)", url: "https://jx.aidouer.net/?url=" },
    { name: "Parwix(4K)", url: "https://jx.parwix.com:4433/player/?url=" },
    { name: "XMFLV解析", url: "https://jx.xmflv.com/?url=" },
    { name: "7解析(超清)", url: "https://jx.789jiexi.com/?url=" },
    { name: "m3u8解析", url: "https://jx.m3u8.tv/jiexi/?url=" },
    { name: "盘古解析", url: "https://www.pangujiexi.cc/jiexi.php?url=" },
    { name: "懒人4K", url: "https://jx.lazy.huimifa.com/?url=" }
];

// ===== 分类列表 =====
const classList = [
    { type_id: "1", type_name: "电影" },
    { type_id: "2", type_name: "电视剧" },
    { type_id: "3", type_name: "综艺" },
    { type_id: "4", type_name: "动漫" }
];

// ===== 筛选器 =====
function getAreaFilter(catId) {
    let areaMap = {
        "1": [
            { n: "全部", v: "" }, { n: "大陆", v: "大陆" }, { n: "香港", v: "香港" },
            { n: "台湾", v: "台湾" }, { n: "泰国", v: "泰国" }, { n: "美国", v: "美国" },
            { n: "韩国", v: "韩国" }, { n: "日本", v: "日本" }, { n: "法国", v: "法国" },
            { n: "英国", v: "英国" }, { n: "德国", v: "德国" }, { n: "印度", v: "印度" },
            { n: "意大利", v: "意大利" }, { n: "西班牙", v: "西班牙" }, { n: "加拿大", v: "加拿大" },
            { n: "俄罗斯", v: "俄罗斯" }, { n: "澳大利亚", v: "澳大利亚" }, { n: "其他", v: "其他" }
        ],
        "2": [
            { n: "全部", v: "" }, { n: "大陆", v: "大陆" }, { n: "香港", v: "香港" },
            { n: "台湾", v: "台湾" }, { n: "泰国", v: "泰国" }, { n: "日本", v: "日本" },
            { n: "韩国", v: "韩国" }, { n: "美国", v: "美国" }, { n: "英国", v: "英国" },
            { n: "新加坡", v: "新加坡" }, { n: "其他", v: "其他" }
        ],
        "3": [
            { n: "全部", v: "" }, { n: "大陆", v: "大陆" }, { n: "香港", v: "香港" },
            { n: "台湾", v: "台湾" }, { n: "日本", v: "日本" }, { n: "韩国", v: "韩国" },
            { n: "美国", v: "美国" }, { n: "英国", v: "英国" }, { n: "欧美", v: "欧美" },
            { n: "其他", v: "其他" }
        ],
        "4": [
            { n: "全部", v: "" }, { n: "大陆", v: "大陆" }, { n: "日本", v: "日本" },
            { n: "美国", v: "美国" }, { n: "韩国", v: "韩国" }, { n: "其他", v: "其他" }
        ]
    };
    return { key: "area", name: "地区", value: areaMap[catId] || areaMap["1"] };
}

function getYearFilter() {
    let years = [{ n: "全部", v: "" }];
    let currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= 2010; y--) {
        years.push({ n: String(y), v: String(y) });
    }
    return { key: "year", name: "年份", value: years };
}

function getSortFilter() {
    return {
        key: "sort", name: "排序", value: [
            { n: "按最新", v: "ranklatest" },
            { n: "按热度", v: "rankhot" },
            { n: "按评分", v: "rankpoint" }
        ]
    };
}

function getTypeFilter(catId) {
    let typeMap = {
        "1": [
            { n: "全部", v: "" }, { n: "喜剧", v: "喜剧" }, { n: "爱情", v: "爱情" },
            { n: "动作", v: "动作" }, { n: "恐怖", v: "恐怖" }, { n: "科幻", v: "科幻" },
            { n: "剧情", v: "剧情" }, { n: "犯罪", v: "犯罪" }, { n: "奇幻", v: "奇幻" },
            { n: "战争", v: "战争" }, { n: "悬疑", v: "悬疑" }, { n: "动画", v: "动画" },
            { n: "文艺", v: "文艺" }, { n: "纪录", v: "纪录" }, { n: "传记", v: "传记" },
            { n: "歌舞", v: "歌舞" }, { n: "古装", v: "古装" }, { n: "历史", v: "历史" },
            { n: "惊悚", v: "惊悚" }, { n: "伦理", v: "伦理" }, { n: "西部", v: "西部" },
            { n: "冒险", v: "冒险" }, { n: "武侠", v: "武侠" }, { n: "其他", v: "其他" }
        ],
        "2": [
            { n: "全部", v: "" }, { n: "言情", v: "言情" }, { n: "剧情", v: "剧情" },
            { n: "伦理", v: "伦理" }, { n: "喜剧", v: "喜剧" }, { n: "悬疑", v: "悬疑" },
            { n: "都市", v: "都市" }, { n: "偶像", v: "偶像" }, { n: "古装", v: "古装" },
            { n: "军事", v: "军事" }, { n: "警匪", v: "警匪" }, { n: "历史", v: "历史" },
            { n: "励志", v: "励志" }, { n: "神话", v: "神话" }, { n: "谍战", v: "谍战" },
            { n: "青春", v: "青春" }, { n: "家庭", v: "家庭" }, { n: "动作", v: "动作" },
            { n: "情景", v: "情景" }, { n: "武侠", v: "武侠" }, { n: "科幻", v: "科幻" },
            { n: "年代", v: "年代" }, { n: "农村", v: "农村" }, { n: "其他", v: "其他" }
        ],
        "3": [
            { n: "全部", v: "" }, { n: "脱口秀", v: "脱口秀" }, { n: "真人秀", v: "真人秀" },
            { n: "搞笑", v: "搞笑" }, { n: "选秀", v: "选秀" }, { n: "八卦", v: "八卦" },
            { n: "访谈", v: "访谈" }, { n: "情感", v: "情感" }, { n: "生活", v: "生活" },
            { n: "晚会", v: "晚会" }, { n: "音乐", v: "音乐" }, { n: "职场", v: "职场" },
            { n: "美食", v: "美食" }, { n: "时尚", v: "时尚" }, { n: "游戏", v: "游戏" },
            { n: "少儿", v: "少儿" }, { n: "体育", v: "体育" }, { n: "纪实", v: "纪实" },
            { n: "科教", v: "科教" }, { n: "曲艺", v: "曲艺" }, { n: "歌舞", v: "歌舞" },
            { n: "财经", v: "财经" }, { n: "汽车", v: "汽车" }, { n: "播报", v: "播报" },
            { n: "旅游", v: "旅游" }, { n: "其他", v: "其他" }
        ],
        "4": [
            { n: "全部", v: "" }, { n: "热血", v: "热血" }, { n: "科幻", v: "科幻" },
            { n: "美少女", v: "美少女" }, { n: "魔幻", v: "魔幻" }, { n: "经典", v: "经典" },
            { n: "励志", v: "励志" }, { n: "少儿", v: "少儿" }, { n: "冒险", v: "冒险" },
            { n: "搞笑", v: "搞笑" }, { n: "推理", v: "推理" }, { n: "恋爱", v: "恋爱" },
            { n: "治愈", v: "治愈" }, { n: "幻想", v: "幻想" }, { n: "校园", v: "校园" },
            { n: "动物", v: "动物" }, { n: "机战", v: "机战" }, { n: "亲子", v: "亲子" },
            { n: "儿歌", v: "儿歌" }, { n: "运动", v: "运动" }, { n: "悬疑", v: "悬疑" },
            { n: "怪物", v: "怪物" }, { n: "战争", v: "战争" }, { n: "益智", v: "益智" },
            { n: "青春", v: "青春" }, { n: "童话", v: "童话" }, { n: "竞技", v: "竞技" },
            { n: "动作", v: "动作" }, { n: "社会", v: "社会" }, { n: "友情", v: "友情" },
            { n: "真人版", v: "真人版" }, { n: "电影版", v: "电影版" }, { n: "OVA版", v: "OVA版" },
            { n: "TV版", v: "TV版" }, { n: "新番动画", v: "新番动画" }, { n: "完结动画", v: "完结动画" }
        ]
    };
    return { key: "type", name: "类型", value: typeMap[catId] || typeMap["1"] };
}

// 为每个分类生成对应的筛选器
const myFilters = {};
classList.forEach(function (item) {
    myFilters[item.type_id] = [
        getTypeFilter(item.type_id),
        getAreaFilter(item.type_id),
        getYearFilter(),
        getSortFilter()
    ];
});

// ===== 工具函数 =====
function fixUrl(u) {
    if (!u) return '';
    if (u.startsWith('http')) return u;
    if (u.startsWith('//')) return 'https:' + u;
    if (u.startsWith('/')) return appConfig.siteUrl + u;
    return u;
}

// URL 编码 (兼容引擎不支持 encodeURIComponent 的情况)
function encodeQuery(s) {
    try {
        if (typeof encodeURIComponent === 'function') {
            return encodeURIComponent(s);
        }
    } catch (e) { }
    // 手动编码备用方案
    let result = '';
    for (let i = 0; i < s.length; i++) {
        let c = s.charCodeAt(i);
        if (c < 128) {
            result += s.charAt(i);
        } else if (c < 2048) {
            result += '%' + ((c >> 6) | 192).toString(16).toUpperCase();
            result += '%' + ((c & 63) | 128).toString(16).toUpperCase();
        } else {
            result += '%' + ((c >> 12) | 224).toString(16).toUpperCase();
            result += '%' + (((c >> 6) & 63) | 128).toString(16).toUpperCase();
            result += '%' + ((c & 63) | 128).toString(16).toUpperCase();
        }
    }
    return result;
}

// 解析 Next.js __next_f.push 数据
function unescapeNextData(html) {
    let pushes = html.match(/self\.__next_f\.push\(\[1,"(.*?)"\]\)/g) || [];
    let allData = "";
    for (let i = 0; i < pushes.length; i++) {
        try {
            let m = pushes[i].match(/self\.__next_f\.push\(\[1,"(.*?)"\]\)/);
            if (m) {
                let s = m[1]
                    .replace(/\\\\/g, "\\")
                    .replace(/\\"/g, '"')
                    .replace(/\\n/g, "\n")
                    .replace(/\\u0026/g, "&");
                allData += s;
            }
        } catch (e) { }
    }
    return allData;
}

// HTTP 请求封装
async function fetchUrl(url) {
    try {
        let resp = await req(url, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        });
        return resp.content;
    } catch (e) {
        console.error("请求失败: " + url + " - " + e.message);
        return "";
    }
}

// 构建分类列表 URL (含筛选参数)
function buildCategoryUrl(tid, pg, extend) {
    extend = extend || {};
    let params = ["catId=" + tid, "page=" + pg, "size=24"];
    if (extend.type) params.push("type=" + encodeQuery(extend.type));
    if (extend.area) params.push("area=" + encodeQuery(extend.area));
    if (extend.year) params.push("year=" + extend.year);
    if (extend.sort) params.push("sort=" + extend.sort);
    return appConfig.siteUrl + "/api/filter?" + params.join("&");
}

// ===== 初始化 (动态域名抓取) =====
async function init(ext) {
    console.log("初始化爬虫: " + appConfig.siteName);

    // 动态抓取域名: 遍历备用域名, 从首页提取 siteUrl
    for (let i = 0; i < fallbackDomains.length; i++) {
        try {
            let resp = await req(fallbackDomains[i] + "/", {
                method: "GET",
                headers: { "User-Agent": UA, "Accept": "text/html" }
            });
            let html = resp.content || "";
            if (html.length < 500) continue;

            // 从 Next.js 数据中提取 siteUrl
            let allData = unescapeNextData(html);
            let siteUrlMatch = allData.match(/"siteUrl":"([^"]+)"/);
            if (siteUrlMatch && siteUrlMatch[1]) {
                appConfig.siteUrl = siteUrlMatch[1];
                console.log("动态域名获取成功: " + appConfig.siteUrl);
                return;
            }
            // 没找到 siteUrl, 使用当前成功的域名
            appConfig.siteUrl = fallbackDomains[i];
            console.log("使用备用域名: " + appConfig.siteUrl);
            return;
        } catch (e) {
            console.error("域名 " + fallbackDomains[i] + " 尝试失败: " + e.message);
        }
    }
    console.error("所有备用域名均不可用, 使用默认: " + appConfig.siteUrl);
}

// ===== 首页推荐 =====
async function home(filter) {
    let list = [];
    try {
        let html = await fetchUrl(appConfig.siteUrl + "/api/filter?catId=1&page=1&size=30");
        let data = JSON.parse(html);
        let movies = data.movies || [];
        for (let i = 0; i < movies.length; i++) {
            let m = movies[i];
            let upinfo = "";
            if (m.upinfo) {
                let up = typeof m.upinfo === "number" ? m.upinfo : parseInt(m.upinfo) || 0;
                let tot = typeof m.total === "number" ? m.total : parseInt(m.total) || 0;
                if (up > 0) {
                    upinfo = tot > 0 && up >= tot ? ("全" + tot + "集") : ("更新至" + up + "集");
                } else if (tot > 0) {
                    upinfo = "全" + tot + "集";
                }
            } else if (m.total) {
                upinfo = "全" + m.total + "集";
            }
            list.push({
                vod_id: "/detail/1/" + (m.id || ""),
                vod_name: m.title || "",
                vod_pic: fixUrl(m.cdncover || m.cover || ""),
                vod_remarks: upinfo
            });
        }
    } catch (e) {
        console.error("首页推荐获取失败: " + e.message);
    }

    return JSON.stringify({
        class: classList,
        filters: myFilters,
        list: list
    });
}

// ===== 分类列表 =====
async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};
    let list = [];
    let pagecount = 1;

    try {
        let url = buildCategoryUrl(tid, pg, extend);
        let html = await fetchUrl(url);
        let data = JSON.parse(html);
        let movies = data.movies || [];

        for (let i = 0; i < movies.length; i++) {
            let m = movies[i];
            let upinfo = "";
            if (m.upinfo) {
                let up = typeof m.upinfo === "number" ? m.upinfo : parseInt(m.upinfo) || 0;
                let tot = typeof m.total === "number" ? m.total : parseInt(m.total) || 0;
                if (up > 0) {
                    upinfo = tot > 0 && up >= tot ? ("全" + tot + "集") : ("更新至" + up + "集");
                } else if (tot > 0) {
                    upinfo = "全" + tot + "集";
                }
            } else if (m.total) {
                upinfo = "全" + m.total + "集";
            }
            list.push({
                vod_id: "/detail/" + tid + "/" + (m.id || ""),
                vod_name: m.title || "",
                vod_pic: fixUrl(m.cdncover || m.cover || ""),
                vod_remarks: upinfo
            });
        }

        if (movies.length >= 24) {
            pagecount = pg + 1;
        } else {
            pagecount = pg;
        }
    } catch (e) {
        console.error("分类列表获取失败: " + e.message);
    }

    return JSON.stringify({ list: list, pagecount: pagecount });
}

// ===== 搜索 (多源 + 编码兼容) =====
async function search(wd, quick, page) {
    page = page || 1;
    let list = [];
    let pagecount = 1;

    try {
        // 构建搜索URL - 使用 encodeQuery 兼容编码
        let encodedWd = encodeQuery(wd);
        let url = appConfig.siteUrl + "/api/search?q=" + encodedWd + "&page=" + page;
        let html = await fetchUrl(url);
        let data = JSON.parse(html);
        let results = data.results || [];

        for (let i = 0; i < results.length; i++) {
            let r = results[i];

            // 判断数据源类型: 360kan 源 vs B线路/D线路源
            if (r.isExternal) {
                // B线路/D线路: 已是TVBox标准格式, 直接使用
                let title = (r.vod_name || "").replace(/<[^>]+>/g, "");
                let cover = fixUrl(r.vod_pic || "");
                let desc = (r.vod_year || "") + " " + (r.vod_area || "") + " " + (r.vod_remarks || "");
                desc = desc.trim();

                // 构建外部源播放ID: EXT|{vod_play_from}|{vod_play_url}
                let playFrom = r.vod_play_from || "";
                let playUrl = r.vod_play_url || "";
                let extId = "EXT|" + playFrom + "|" + playUrl;

                list.push({
                    vod_id: extId,
                    vod_name: title + " [" + (r.sourceName || "外部") + "]",
                    vod_pic: cover,
                    vod_remarks: r.vod_remarks || desc
                });
            } else {
                // 360kan 源: 需要通过详情页解析
                let title = (r.titleTxt || r.title || "").replace(/<[^>]+>/g, "");
                let cover = fixUrl(r.cover || "");
                let enId = r.en_id || r.id || "";
                let catId = r.cat_id || "1";
                let desc = r.year || "";
                if (r.coverInfo && r.coverInfo.txt) desc += " " + r.coverInfo.txt;

                list.push({
                    vod_id: "/detail/" + catId + "/" + enId,
                    vod_name: title,
                    vod_pic: cover,
                    vod_remarks: desc
                });
            }
        }

        // 搜索API没有分页信息, 只有第一页有结果
        pagecount = 1;
    } catch (e) {
        console.error("搜索失败: " + e.message);
        // 如果编码搜索失败, 尝试未编码搜索
        try {
            let url2 = appConfig.siteUrl + "/api/search?q=" + wd + "&page=" + page;
            let html2 = await fetchUrl(url2);
            let data2 = JSON.parse(html2);
            let results2 = data2.results || [];
            for (let i = 0; i < results2.length; i++) {
                let r = results2[i];
                if (r.isExternal) continue;
                let title = (r.titleTxt || r.title || "").replace(/<[^>]+>/g, "");
                let cover = fixUrl(r.cover || "");
                let enId = r.en_id || r.id || "";
                let catId = r.cat_id || "1";
                let desc = r.year || "";
                if (r.coverInfo && r.coverInfo.txt) desc += " " + r.coverInfo.txt;
                list.push({
                    vod_id: "/detail/" + catId + "/" + enId,
                    vod_name: title,
                    vod_pic: cover,
                    vod_remarks: desc
                });
            }
            pagecount = 1;
        } catch (e2) {
            console.error("搜索备用方案也失败: " + e2.message);
        }
    }

    return JSON.stringify({ list: list, pagecount: pagecount });
}

// ===== 详情页 =====
async function detail(id) {
    try {
        // 外部源搜索结果: EXT|{playFrom}|{playUrl}
        if (id.startsWith("EXT|")) {
            let parts = id.split("|");
            let playFrom = parts[1] || "外部线路";
            let playUrl = parts[2] || "";
            // 解析播放URL
            let eps = playUrl.split("#");
            let epList = [];
            for (let i = 0; i < eps.length; i++) {
                epList.push(eps[i]);
            }
            return JSON.stringify({
                list: [{
                    vod_id: id,
                    vod_name: "外部资源",
                    vod_pic: "",
                    vod_remarks: "",
                    vod_play_from: playFrom,
                    vod_play_url: playUrl
                }]
            });
        }

        // 站内详情: /detail/{cat}/{enId}
        let idMatch = id.match(/\/detail\/(\d+)\/([a-zA-Z0-9]+)/);
        let cat = idMatch ? idMatch[1] : "1";
        let entId = idMatch ? idMatch[2] : "";

        let html = await fetchUrl(appConfig.siteUrl + id);
        let allData = unescapeNextData(html);

        // 提取标题
        let vod_name = "";
        let titleMatch = allData.match(/"og:title","content":"([^"]+)"/);
        if (titleMatch) {
            vod_name = titleMatch[1].replace(/_剧OK$/, "").replace(/高清完整版.*$/, "").trim();
            if (vod_name.startsWith("《")) vod_name = vod_name.replace(/^《/, "").replace(/》.*$/, "");
        }

        // 提取封面
        let vod_pic = "";
        let coverMatch = allData.match(/"og:image","content":"([^"]+)"/);
        if (coverMatch) vod_pic = coverMatch[1];

        // 提取简介
        let vod_content = "";
        let descMatch = allData.match(/"og:description","content":"([^"]+)"/);
        if (descMatch) vod_content = descMatch[1];

        // 提取年份
        let vod_year = "";
        let yearMatch = allData.match(/"year":"(\d{4})"/);
        if (yearMatch) vod_year = yearMatch[1];

        // 提取地区
        let vod_area = "";
        let areaMatch = allData.match(/"href":"\/category\/[a-z]+\?area=([^"]+)"/);
        if (areaMatch) vod_area = areaMatch[1];

        // 提取类型
        let vod_class = "";
        let typeMatch = allData.match(/"href":"\/category\/[a-z]+\?type=([^"]+)"/g);
        if (typeMatch) {
            vod_class = typeMatch.map(function (mm) {
                return mm.match(/type=([^"]+)/)[1];
            }).join(" ");
        }

        // 提取导演
        let vod_director = "";
        let dirMatches = allData.match(/"director":\[(\{[^}]+\})/g);
        if (dirMatches) {
            let names = [];
            for (let i = 0; i < dirMatches.length; i++) {
                let nm = dirMatches[i].match(/"name":"([^"]+)"/);
                if (nm) names.push(nm[1]);
            }
            vod_director = names.join(",");
        }

        // 提取演员
        let vod_actor = "";
        let actMatches = allData.match(/"actor":\[(\{[^}]+\})/g);
        if (actMatches) {
            let names = [];
            for (let i = 0; i < actMatches.length; i++) {
                let nm = actMatches[i].match(/"name":"([^"]+)"/);
                if (nm) names.push(nm[1]);
            }
            vod_actor = names.join(",");
        }

        // 提取播放站点
        let initialSite = "";
        let initMatch = allData.match(/"initialSite":"([^"]+)"/);
        if (initMatch) initialSite = initMatch[1];

        let sites = [];
        let sitesMatch = allData.match(/"sites":\[([^\]]+)\]/);
        if (sitesMatch) {
            let siteArr = sitesMatch[1].match(/"([a-z0-9]+)"/g);
            if (siteArr) {
                sites = siteArr.map(function (st) { return st.replace(/"/g, ""); });
            }
        }
        if (sites.length === 0 && initialSite) sites = [initialSite];

        // 提取总集数
        let total = 0;
        let totalMatch = allData.match(/"total":"?(\d+)"?/);
        if (totalMatch) total = parseInt(totalMatch[1]);

        // 提取剧集列表 (playlink_num + url)
        let episodes = [];
        let epRegex = /"playlink_num":"(\d+)"[^}]*?"url":"(http[^"]+)"/g;
        let em;
        while ((em = epRegex.exec(allData)) !== null) {
            episodes.push({ num: em[1], url: em[2] });
        }

        // 如果没有剧集数据, 尝试从播放页获取
        let primarySite = initialSite || (sites.length > 0 ? sites[0] : "");
        if (episodes.length === 0 && primarySite) {
            try {
                let purl = appConfig.siteUrl + "/play/" + cat + "/" + entId + "/1?s=" + primarySite;
                let phtml = await fetchUrl(purl);
                let pData = unescapeNextData(phtml);
                let dm = pData.match(/"default_url":"(http[^"]+)"/);
                if (dm) {
                    episodes.push({ num: "1", url: dm[1] });
                }
                if (sites.length === 0) {
                    let as = pData.match(/"availableSites":\[([^\]]+)\]/);
                    if (as) {
                        let arr = as[1].match(/"([a-z0-9]+)"/g);
                        if (arr) sites = arr.map(function (st) { return st.replace(/"/g, ""); });
                    }
                }
                if (total === 0) {
                    let tm = pData.match(/"total":"?(\d+)"?/);
                    if (tm) total = parseInt(tm[1]);
                }
            } catch (e) { }
        }

        // 构建播放线路
        let lines = [];
        let playlists = [];

        if (episodes.length > 0) {
            for (let pi = 0; pi < parseLines.length; pi++) {
                let epList = [];
                for (let ei = 0; ei < episodes.length; ei++) {
                    let ep = episodes[ei];
                    let epTitle = episodes.length > 1 ? ("第" + ep.num + "集") : "正片";
                    epList.push(epTitle + "$JX" + pi + "|" + ep.url);
                }
                lines.push(parseLines[pi].name);
                playlists.push(epList);
            }

            for (let si = 0; si < sites.length; si++) {
                let st = sites[si];
                if (st === primarySite && episodes.length > 0) continue;
                let epList = [];
                let cnt = total > 0 ? total : episodes.length;
                for (let n = 1; n <= cnt; n++) {
                    let epTitle = cnt > 1 ? ("第" + n + "集") : "正片";
                    epList.push(epTitle + "$PLAY|" + cat + "|" + entId + "|" + n + "|" + st);
                }
                lines.push("源-" + (siteNames[st] || st));
                playlists.push(epList);
            }
        } else {
            lines.push(siteNames[primarySite] || "默认线路");
            playlists.push(["播放$PLAY|" + cat + "|" + entId + "|1|" + (primarySite || "qiyi")]);
        }

        let vod_play_from = lines.join("$$$");
        let vod_play_url = playlists.map(function (eps) { return eps.join("#"); }).join("$$$");

        let vod_remarks = "";
        if (episodes.length > 0) {
            vod_remarks = cat === "1" ? "电影" : ("共" + episodes.length + "集");
        }

        return JSON.stringify({
            list: [{
                vod_id: id,
                vod_name: vod_name,
                vod_pic: vod_pic,
                vod_actor: vod_actor,
                vod_director: vod_director,
                vod_remarks: vod_remarks,
                vod_year: vod_year,
                vod_area: vod_area,
                vod_content: vod_content,
                vod_class: vod_class,
                vod_play_from: vod_play_from,
                vod_play_url: vod_play_url
            }]
        });
    } catch (error) {
        console.error("解析详情页异常 [ID: " + id + "]: " + error);
        return JSON.stringify({ list: [] });
    }
}

// ===== 播放解析 =====
async function play(flag, id, flags) {
    try {
        let header = { "User-Agent": UA, "Referer": appConfig.siteUrl };

        // 外部源: EXT|{playFrom}|{playUrl} -> 直接播放
        if (id.startsWith("EXT|")) {
            let parts = id.split("|");
            let playUrl = parts[2] || "";
            // 解析播放地址: 格式 第1集$url
            let urlParts = playUrl.split("$");
            let realUrl = urlParts.length > 1 ? urlParts[1] : playUrl;
            if (realUrl.startsWith("http")) {
                return JSON.stringify({ parse: 0, header: header, url: realUrl });
            }
            return JSON.stringify({ parse: 1, header: header, url: realUrl });
        }

        // JX 解析线路: 格式 JX{idx}|{url}
        if (id.startsWith("JX")) {
            let pipeIdx = id.indexOf("|");
            let idx = parseInt(id.substring(2, pipeIdx));
            let realUrl = id.substring(pipeIdx + 1);
            let parser = parseLines[idx] ? parseLines[idx].url : "";

            if (!parser) {
                return JSON.stringify({ parse: 1, header: header, url: realUrl });
            } else {
                return JSON.stringify({ parse: 1, header: header, url: parser + realUrl });
            }
        }

        // PLAY 站点线路: 格式 PLAY|{cat}|{entId}|{epNum}|{site}
        if (id.startsWith("PLAY|")) {
            let parts = id.split("|");
            let cat = parts[1], entId = parts[2], epNum = parts[3], site = parts[4];
            let playUrl = appConfig.siteUrl + "/play/" + cat + "/" + entId + "/" + epNum + "?s=" + site;

            try {
                let html = await fetchUrl(playUrl);
                let allData = unescapeNextData(html);
                let dm = allData.match(/"default_url":"(http[^"]+)"/);
                if (dm) {
                    return JSON.stringify({ parse: 1, header: header, url: parseLines[1].url + dm[1] });
                }
                return JSON.stringify({ parse: 1, header: header, url: playUrl });
            } catch (e) {
                return JSON.stringify({ parse: 1, header: header, url: playUrl });
            }
        }

        // 直接 HTTP URL
        if (id.startsWith("http")) {
            return JSON.stringify({ parse: 1, header: header, url: id });
        }

        // 站内路径
        let playUrl = id.startsWith("/") ? (appConfig.siteUrl + id) : id;
        try {
            let html = await fetchUrl(playUrl);
            let allData = unescapeNextData(html);
            let dm = allData.match(/"default_url":"(http[^"]+)"/);
            if (dm) {
                return JSON.stringify({ parse: 1, header: header, url: parseLines[1].url + dm[1] });
            }
            return JSON.stringify({ parse: 1, header: header, url: playUrl });
        } catch (e) {
            return JSON.stringify({ parse: 1, header: header, url: playUrl });
        }
    } catch (e) {
        console.error("播放解析失败: " + e);
        return JSON.stringify({ parse: 0, url: "" });
    }
}

export default {
    init,
    home,
    category,
    detail,
    search,
    play
};
