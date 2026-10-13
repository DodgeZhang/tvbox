import cheerio from 'assets://js/lib/cheerio.min.js';

const appConfig = {
    siteName: "伦理专题影片",
    siteUrl: "http://yoxayg.com"
};
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

const classList = [
    { type_id: "1", type_name: "电影" },
    { type_id: "2", type_name: "电视剧" },
    { type_id: "3", type_name: "综艺" },
    { type_id: "4", type_name: "动漫" },
    { type_id: "36", type_name: "短剧" },
    { type_id: "6", type_name: "动作片" },
    { type_id: "7", type_name: "喜剧片" },
    { type_id: "8", type_name: "爱情片" },
    { type_id: "9", type_name: "科幻片" },
    { type_id: "10", type_name: "恐怖片" },
    { type_id: "11", type_name: "剧情片" },
    { type_id: "12", type_name: "战争片" },
    { type_id: "20", type_name: "记录片" },
    { type_id: "34", type_name: "伦理片" },
    { type_id: "13", type_name: "国产剧" },
    { type_id: "14", type_name: "香港剧" },
    { type_id: "15", type_name: "韩国剧" },
    { type_id: "16", type_name: "欧美剧" },
    { type_id: "21", type_name: "台湾剧" },
    { type_id: "22", type_name: "日本剧" },
    { type_id: "23", type_name: "海外剧" },
    { type_id: "24", type_name: "泰国剧" },
    { type_id: "25", type_name: "大陆综艺" },
    { type_id: "26", type_name: "港台综艺" },
    { type_id: "27", type_name: "日韩综艺" },
    { type_id: "28", type_name: "欧美综艺" },
    { type_id: "29", type_name: "国产动漫" },
    { type_id: "30", type_name: "日韩动漫" },
    { type_id: "31", type_name: "欧美动漫" },
    { type_id: "32", type_name: "港台动漫" },
    { type_id: "33", type_name: "海外动漫" }
];

const typeSlugMap = {
    "1": "dianying", "2": "dianshiju", "3": "zongyi", "4": "dongman", "6": "dongzuopian",
    "7": "xijupian", "8": "aiqingpian", "9": "kehuanpian", "10": "kongbupian", "11": "juqingpian",
    "12": "zhanzhengpian", "13": "guochanju", "14": "xianggangju", "15": "hanguoju", "16": "oumeiju",
    "20": "jilupian", "21": "taiwanju", "22": "ribenju", "23": "haiwaiju", "24": "taiguoju",
    "25": "daluzongyi", "26": "gangtaizongyi", "27": "rihanzongyi", "28": "oumeizongyi",
    "29": "guochandongman", "30": "rihandongman", "31": "oumeidongman", "32": "gangtaidongman",
    "33": "haiwaidongman", "34": "lunlipian", "36": "duanju"
};

const typeParentMap = {
    "1": 0, "2": 0, "3": 0, "4": 0, "6": 1, "7": 1, "8": 1, "9": 1, "10": 1,
    "11": 1, "12": 1, "13": 2, "14": 2, "15": 2, "16": 2, "20": 1, "21": 2, "22": 2,
    "23": 2, "24": 2, "25": 3, "26": 3, "27": 3, "28": 3, "29": 4, "30": 4,
    "31": 4, "32": 4, "33": 4, "34": 1, "36": 2
};

function topType(tid) {
    tid = parseInt(tid || 0, 10);
    if (tid === 36) return 36;
    const p = parseInt(typeParentMap[String(tid)] || 0, 10);
    return p > 0 ? p : tid;
}

function typeSlug(tid) {
    return typeSlugMap[String(parseInt(tid || 0, 10))] || ('type' + parseInt(tid || 0, 10));
}

function getAreaFilter() {
    return {
        "key": "area", "name": "地区", "value": [
            { "n": "全部", "v": "" }, { "n": "大陆", "v": "大陆" }, { "n": "香港", "v": "香港" },
            { "n": "台湾", "v": "台湾" }, { "n": "美国", "v": "美国" }, { "n": "日本", "v": "日本" },
            { "n": "韩国", "v": "韩国" }, { "n": "英国", "v": "英国" }, { "n": "法国", "v": "法国" },
            { "n": "德国", "v": "德国" }, { "n": "泰国", "v": "泰国" }, { "n": "印度", "v": "印度" },
            { "n": "其他", "v": "其他" }
        ]
    };
}

function getYearFilter() {
    let years = [{ "n": "全部", "v": "" }];
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= 2010; y--) {
        years.push({ "n": String(y), "v": String(y) });
    }
    return { "key": "year", "name": "年份", "value": years };
}

const commonFilters = [getAreaFilter(), getYearFilter()];

const myFilters = {};
classList.forEach(item => {
    myFilters[item.type_id] = commonFilters;
});

function fixUrl(u) {
    if (!u) return '';
    if (u.startsWith('http')) return u;
    if (u.startsWith('//')) return 'http:' + u;
    if (u.startsWith('/')) return appConfig.siteUrl + u;
    return u;
}

async function home(filter) {
    let list = [];
    try {
        const html = (await req(appConfig.siteUrl, {
            method: "GET",
            headers: { "User-Agent": UA }
        })).content;
        const $ = cheerio.load(html);
        let seen = {};

        $(".tpl-card[href]").each(function () {
            let vod_id = $(this).attr("href");
            if (!vod_id || seen[vod_id]) return;

            let vod_name = $(this).attr("title") || $(this).find("strong").first().text().trim() || "";
            vod_name = vod_name.replace(/免费在线观看$/, "");
            let vod_pic = fixUrl($(this).find("img").first().attr("src") || "");
            let vod_remarks = $(this).find("em").first().text().trim();

            if (vod_name && vod_id) {
                seen[vod_id] = true;
                list.push({ vod_id, vod_name, vod_pic, vod_remarks });
            }
        });
    } catch (e) {
        console.error("首页推荐获取失败:", e.message);
    }

    return JSON.stringify({
        class: classList,
        filters: myFilters,
        list: list.slice(0, 30)
    });
}

function buildCategoryUrl(tid, pg, extend) {
    extend = extend || {};
    let top = topType(tid);
    let topSlug = typeSlug(top);
    let childSlug = (tid != top) ? typeSlug(tid) : '';

    let path;
    if (childSlug && tid != 36) {
        path = `/${topSlug}/${childSlug}/`;
    } else {
        path = `/${topSlug}/`;
    }

    if (pg > 1) {
        path += `page-${pg}.html`;
    }

    let area = extend.area || '';
    let year = extend.year || '';
    if (area || year) {
        let params = [];
        if (area) params.push('area=' + encodeURIComponent(area));
        if (year) params.push('year=' + encodeURIComponent(year));
        return appConfig.siteUrl + `/api_proxy.php?ac=list&t=${tid}&pg=${pg}&${params.join('&')}`;
    }

    return appConfig.siteUrl + path;
}

function parseListHtml(html) {
    const $ = cheerio.load(html);
    let list = [];
    let vodIds = {};

    $(".tpl-card.card-poster, .tpl-card.card-wide").each(function () {
        let $a = $(this);
        let vod_id = $a.attr("href");
        if (!vod_id || vodIds[vod_id]) return;

        let vod_name = $a.attr("title") || $a.find("strong").first().text().trim() || "";
        vod_name = vod_name.replace(/免费在线观看$/, "");
        let vod_pic = fixUrl($a.find("img").first().attr("src") || "");
        let vod_remarks = $a.find("em").first().text().trim() || $a.find("small").first().text().trim();

        if (vod_name && vod_id) {
            vodIds[vod_id] = true;
            list.push({ vod_id, vod_name, vod_pic, vod_remarks });
        }
    });

    if (list.length === 0) {
        try {
            let data = JSON.parse(html);
            if (data.list && Array.isArray(data.list)) {
                data.list.forEach(item => {
                    let vod_id = `/${typeSlug(topType(item.type_id))}/${(item.vod_en || item.vod_name || '').toLowerCase().replace(/[^a-z0-9]+/g, '')}.html`;
                    let vod_name = item.vod_name || "";
                    let vod_pic = item.vod_pic || "";
                    let vod_remarks = item.vod_remarks || "";
                    if (vod_name) {
                        list.push({ vod_id, vod_name, vod_pic, vod_remarks });
                    }
                });
            }
        } catch (e) {
        }
    }

    let pagecount = 1;
    $(".pagination a").each(function () {
        let href = $(this).attr("href") || '';
        let m = href.match(/page-(\d+)/);
        if (m) {
            let p = parseInt(m[1]);
            if (p > pagecount) pagecount = p;
        }
    });

    return { list, pagecount };
}

async function category(tid, pg, filter, extend) {
    pg = pg || 1;
    extend = extend || {};

    let url = buildCategoryUrl(tid, pg, extend);

    try {
        const html = (await req(url, {
            method: "GET",
            headers: { "User-Agent": UA, "Referer": appConfig.siteUrl }
        })).content;
        const result = parseListHtml(html);
        return JSON.stringify(result);
    } catch (e) {
        console.error("分类列表获取失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function search(wd, quick, page) {
    page = page || 1;
    try {
        const url = `${appConfig.siteUrl}/search-${encodeURIComponent(wd)}${page > 1 ? '-page-' + page : ''}.html`;
        const html = (await req(url, {
            method: "GET",
            headers: { "User-Agent": UA, "Referer": appConfig.siteUrl }
        })).content;
        const result = parseListHtml(html);
        return JSON.stringify(result);
    } catch (e) {
        console.error("搜索失败:", e.message);
        return JSON.stringify({ list: [], pagecount: 0 });
    }
}

async function detail(id) {
    try {
        const html = (await req(appConfig.siteUrl + id, {
            method: "GET",
            headers: { "User-Agent": UA, "Referer": appConfig.siteUrl }
        })).content;
        const $ = cheerio.load(html);

        let vod_name = $("h1").first().text().trim();

        let vod_pic = fixUrl($(".detail-poster img").first().attr("src") || "");

        let vod_director = "";
        let vod_actor = "";
        let vod_area = "";
        let vod_year = "";
        let vod_content = "";
        let vod_class = "";
        let vod_remarks = "";

        $(".detail-tags span").each(function () {
            let text = $(this).text().trim();
            if (/^\d{4}$/.test(text) && !vod_year) vod_year = text;
            else if (/大陆|香港|台湾|美国|日本|韩国|英国|法国|德国|泰国|印度|其他/.test(text) && !vod_area) vod_area = text;
            else if (!vod_class && text !== vod_year && text !== vod_area && !/更新至|集|期|TC|HD|正片/.test(text)) vod_class = text;
        });

        vod_remarks = $(".detail-poster span").first().text().trim();

        $(".detail-meta p").each(function () {
            let text = $(this).text();
            if (text.includes("主演：") && !vod_actor) {
                vod_actor = text.replace("主演：", "").trim();
            }
            if (text.includes("导演：") && !vod_director) {
                vod_director = text.replace("导演：", "").trim();
            }
        });

        let $intro = $(".detail-intro");
        if ($intro.length > 0) {
            vod_content = $intro.first().text().replace("简介：", "").trim();
        }
        if (!vod_content) {
            $intro = $(".article-text");
            if ($intro.length > 0) {
                vod_content = $intro.first().text().trim();
            }
        }

        let lines = [];
        let playlists = [];
        let epArray = [];

        $(".episode-grid a").each(function () {
            let name = $(this).text().trim();
            let href = $(this).attr('href') || '';
            if (name && href) {
                epArray.push({ name, href });
            }
        });

        epArray.sort((a, b) => {
            let numA = parseInt(a.name.match(/第(\d+)/)?.[1] || 0);
            let numB = parseInt(b.name.match(/第(\d+)/)?.[1] || 0);
            return numA - numB;
        });

        let episodes = epArray.map(ep => `${ep.name}$${ep.href}`);

        if (episodes.length > 0) {
            lines.push("默认");
            playlists.push(episodes);
        } else {
            let playHref = $(".detail-actions a.btn-primary").attr("href") || "";
            if (playHref) {
                lines.push("默认");
                playlists.push([`正片$${playHref}`]);
            }
        }

        if (lines.length === 0) {
            lines.push("默认");
            playlists.push([`暂无播放地址$${id}`]);
        }

        const { vod_play_from, vod_play_url } = buildVodPlayData(lines, playlists);

        return JSON.stringify({
            list: [{
                vod_id: id,
                vod_name,
                vod_pic,
                vod_actor,
                vod_director,
                vod_remarks,
                vod_year,
                vod_area,
                vod_content,
                vod_class,
                vod_play_from,
                vod_play_url
            }]
        });
    } catch (error) {
        console.error(`解析详情页异常 [ID: ${id}]:`, error);
        return JSON.stringify({ list: [] });
    }
}

function buildVodPlayData(lines, playlists) {
    const processedPlaylists = playlists.map(eps => eps.join('#'));
    return {
        vod_play_from: lines.filter(Boolean).join('$$$'),
        vod_play_url: processedPlaylists.join('$$$')
    };
}

async function play(flag, id, flags) {
    try {
        if (id.startsWith("http")) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: id
            });
        }

        const html = (await req(`${appConfig.siteUrl}${id}`, {
            method: "GET",
            headers: { "User-Agent": UA, "Referer": appConfig.siteUrl }
        })).content;

        // 方式1：从 noscript 中提取 m3u8 URL
        let noscriptMatch = html.match(/<noscript>.*?当前播放地址[：:]\s*(https?:\/\/[^\s<"]+\.m3u8[^\s<"]*)/);
        if (noscriptMatch) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: noscriptMatch[1]
            });
        }

        // 方式2：从 JS 中提取 var src="..."
        let srcMatch = html.match(/var\s+src\s*=\s*["'](https?:\/\/[^"']+\.m3u8[^"']*)/);
        if (srcMatch) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: srcMatch[1]
            });
        }

        // 方式3：直接匹配 m3u8 URL
        let urlMatch = html.match(/(https?:\/\/[^"'\s<>]+\.m3u8[^"'\s<>]*)/);
        if (urlMatch) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: urlMatch[1]
            });
        }

        // 方式4：player_aaaa
        let playerMatch = html.match(/var player_aaaa\s*=\s*(\{.+?\});/);
        if (playerMatch) {
            try {
                let playerData = JSON.parse(playerMatch[1]);
                if (playerData.url) {
                    return JSON.stringify({
                        parse: 0,
                        Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                        url: playerData.url
                    });
                }
            } catch (e) {}
        }

        // 方式5：video 标签的 src
        const $ = cheerio.load(html);
        let videoSrc = $("video").attr("src") || $("video source").attr("src");
        if (videoSrc) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: fixUrl(videoSrc)
            });
        }

        return JSON.stringify({
            parse: 1,
            Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
            url: appConfig.siteUrl + id
        });
    } catch (e) {
        console.error("播放失败:", e);
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
