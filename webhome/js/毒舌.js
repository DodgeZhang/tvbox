// ==UserScript==
// @name 毒舌影视
// @namespace https://www.flash8magic.com
// @version 1.0.0
// ==/UserScript==
// {"name":"毒舌影视","type":"js","url":"https://www.flash8magic.com"}
import cheerio from 'assets://js/lib/cheerio.min.js';

const appConfig = {
    siteName: "毒舌影视",
    siteUrl: "https://www.flash8magic.com"
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
    { type_id: "5", type_name: "短剧" },
    { type_id: "6", type_name: "动作片" },
    { type_id: "7", type_name: "喜剧片" },
    { type_id: "8", type_name: "爱情片" },
    { type_id: "9", type_name: "科幻片" },
    { type_id: "10", type_name: "恐怖片" },
    { type_id: "11", type_name: "剧情片" },
    { type_id: "12", type_name: "战争片" },
    { type_id: "13", type_name: "纪录片" },
    { type_id: "14", type_name: "悬疑片" },
    { type_id: "15", type_name: "犯罪片" },
    { type_id: "16", type_name: "动画片" },
    { type_id: "17", type_name: "国产剧" },
    { type_id: "18", type_name: "港台剧" },
    { type_id: "20", type_name: "日韩剧" },
    { type_id: "21", type_name: "欧美剧" }
];

function getAreaFilter() {
    return {
        "key": "area", "name": "地区", "value": [
            { "n": "全部", "v": "" },
            { "n": "大陆", "v": "大陆" },
            { "n": "香港", "v": "香港" },
            { "n": "台湾", "v": "台湾" },
            { "n": "美国", "v": "美国" },
            { "n": "日本", "v": "日本" },
            { "n": "韩国", "v": "韩国" },
            { "n": "英国", "v": "英国" },
            { "n": "法国", "v": "法国" },
            { "n": "德国", "v": "德国" },
            { "n": "泰国", "v": "泰国" },
            { "n": "印度", "v": "印度" },
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

function getLangFilter() {
    return {
        "key": "lang", "name": "语言", "value": [
            { "n": "全部", "v": "" },
            { "n": "国语", "v": "国语" },
            { "n": "粤语", "v": "粤语" },
            { "n": "英语", "v": "英语" },
            { "n": "日语", "v": "日语" },
            { "n": "韩语", "v": "韩语" },
            { "n": "其他", "v": "其他" }
        ]
    };
}

function getTypeFilter() {
    return {
        "key": "type", "name": "类型", "value": [
            { "n": "全部", "v": "" },
            { "n": "动作", "v": "动作" },
            { "n": "喜剧", "v": "喜剧" },
            { "n": "爱情", "v": "爱情" },
            { "n": "科幻", "v": "科幻" },
            { "n": "恐怖", "v": "恐怖" },
            { "n": "剧情", "v": "剧情" },
            { "n": "战争", "v": "战争" },
            { "n": "悬疑", "v": "悬疑" },
            { "n": "犯罪", "v": "犯罪" },
            { "n": "动画", "v": "动画" },
            { "n": "纪录", "v": "纪录" }
        ]
    };
}

function getLetterFilter() {
    return {
        "key": "letter", "name": "字母", "value": [
            { "n": "全部", "v": "" },
            { "n": "A", "v": "A" },
            { "n": "B", "v": "B" },
            { "n": "C", "v": "C" },
            { "n": "D", "v": "D" },
            { "n": "E", "v": "E" },
            { "n": "F", "v": "F" },
            { "n": "G", "v": "G" },
            { "n": "H", "v": "H" },
            { "n": "I", "v": "I" },
            { "n": "J", "v": "J" },
            { "n": "K", "v": "K" },
            { "n": "L", "v": "L" },
            { "n": "M", "v": "M" },
            { "n": "N", "v": "N" },
            { "n": "O", "v": "O" },
            { "n": "P", "v": "P" },
            { "n": "Q", "v": "Q" },
            { "n": "R", "v": "R" },
            { "n": "S", "v": "S" },
            { "n": "T", "v": "T" },
            { "n": "U", "v": "U" },
            { "n": "V", "v": "V" },
            { "n": "W", "v": "W" },
            { "n": "X", "v": "X" },
            { "n": "Y", "v": "Y" },
            { "n": "Z", "v": "Z" }
        ]
    };
}

const commonFilters = [getAreaFilter(), getYearFilter(), getLangFilter(), getTypeFilter(), getLetterFilter()];

const myFilters = {};
classList.forEach(item => {
    myFilters[item.type_id] = commonFilters;
});

async function home(filter) {
    let list = [];
    try {
        const html = (await req(appConfig.siteUrl, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        })).content;
        const $ = cheerio.load(html);
        let seen = {};

        $(".stui-vodlist__box").each(function () {
            let $a = $(this).find("a.stui-vodlist__thumb").first();
            let vod_id = $a.attr("href");
            if (!vod_id || seen[vod_id]) return;

            let vod_name = $a.attr("title") || "";
            let vod_pic = fixUrl($a.attr("data-original") || $a.find("img").attr("data-original") || $a.find("img").attr("src") || "");
            let vod_remarks = $(this).find(".pic-text").text().trim() || "";

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
    let area = extend.area || '';
    let year = extend.year || '';
    let lang = extend.lang || '';
    let type = extend.type || '';
    let letter = extend.letter || '';

    if (area || year || lang || type || letter) {
        let url = `/dsyisw/${tid}-${area}-${year}-${letter}------${pg > 1 ? '-' + pg : ''}.html`;
        return appConfig.siteUrl + url;
    } else {
        return `${appConfig.siteUrl}/dsyils/${tid}${pg > 1 ? '-' + pg : ''}.html`;
    }
}

function fixUrl(u) {
    if (!u) return '';
    if (u.startsWith('http')) return u;
    if (u.startsWith('//')) return 'https:' + u;
    if (u.startsWith('/')) return appConfig.siteUrl + u;
    return u;
}

function parseListHtml(html) {
    const $ = cheerio.load(html);
    let list = [];
    let vodIds = {};

    $(".stui-vodlist__box").each(function () {
        let $a = $(this).find("a.stui-vodlist__thumb").first();
        let vod_id = $a.attr("href");
        if (!vod_id || vodIds[vod_id]) return;

        let vod_name = $a.attr("title") || "";
        let vod_pic = fixUrl($a.attr("data-original") || $a.find("img").attr("data-original") || $a.find("img").attr("src") || "");
        let vod_remarks = $(this).find(".pic-text").text().trim() || "";

        if (vod_name && vod_id) {
            vodIds[vod_id] = true;
            list.push({ vod_id, vod_name, vod_pic, vod_remarks });
        }
    });

    let pagecount = 1;
    $("a[href*='/dsyils/'], a[href*='/dsyisw/']").each(function () {
        let href = $(this).attr("href") || '';
        let m = href.match(/-(\d+)\.html$/);
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
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
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
        const url = `${appConfig.siteUrl}/dsyiso/-------------.html?wd=${encodeURIComponent(wd)}`;
        const html = (await req(url, {
            method: "GET",
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
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
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        })).content;
        const $ = cheerio.load(html);

        let vod_name = $("h1.title").first().text().trim().replace(/[\d.分]+$/, "") || "";

        let vod_pic = "";
        let $pic = $(".stui-content__thumb img").first();
        if ($pic.length > 0) {
            vod_pic = fixUrl($pic.attr("data-original") || $pic.attr("src") || "");
        }

        let vod_director = "";
        let vod_actor = "";
        let vod_area = "";
        let vod_year = "";
        let vod_content = "";
        let vod_class = "";
        let vod_remarks = "";

        $(".stui-content__detail .data").each(function () {
            let text = $(this).text();
            if (text.includes("类型") && !vod_class) {
                vod_class = text.replace(/类型\s*[：:]\s*/, "").replace(/地区.*$/, "").trim();
            }
            if (text.includes("地区") && !vod_area) {
                vod_area = text.match(/地区\s*[：:]\s*([^年]+)/)?.[1]?.trim() || "";
            }
            if (text.includes("年份") && !vod_year) {
                vod_year = text.match(/年份\s*[：:]\s*(\d{4})/)?.[1] || "";
            }
            if (text.includes("主演") && !vod_actor) {
                vod_actor = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_actor) vod_actor = text.replace(/主演\s*[：:]/, "").trim();
            }
            if (text.includes("导演") && !vod_director) {
                vod_director = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_director) vod_director = text.replace(/导演\s*[：:]/, "").trim();
            }
        });

        let $intro = $(".desc.detail");
        if ($intro.length > 0) {
            vod_content = $intro.text().replace(/简介\s*[：:]/, "").trim();
        }

        let lines = [];
        let playlists = [];
        let seenEpisodes = new Set();

        $(".stui-playfrom__tabs li").each(function (panelIndex) {
            let lineName = $(this).find("a").text().trim() || "默认";

            let paneId = $(this).attr("data-target") || "#playfrom_" + (panelIndex + 1);
            let $playList = $(paneId);
            if (!$playList.length) $playList = $(".stui-playfrom__pane").eq(panelIndex);

            let episodes = [];
            let epArray = [];

            $playList.find("a[href*='/dsyikj/']").each(function () {
                let name = $(this).text().trim();
                let href = $(this).attr('href') || '';
                if (name && href) {
                    let episodeKey = `${name}_${href}`;
                    if (!seenEpisodes.has(episodeKey)) {
                        seenEpisodes.add(episodeKey);
                        epArray.push({ name, href });
                    }
                }
            });

            epArray.sort((a, b) => {
                let numA = parseInt(a.name.match(/第(\d+)/)?.[1] || 0);
                let numB = parseInt(b.name.match(/第(\d+)/)?.[1] || 0);
                return numA - numB;
            });

            epArray.forEach(ep => {
                episodes.push(`${ep.name}$${ep.href}`);
            });

            if (episodes.length > 0) {
                lines.push(lineName);
                playlists.push(episodes);
            }
        });

        if (lines.length === 0) {
            let episodes = [];
            let epArray = [];

            $("a[href*='/dsyikj/']").each(function () {
                let name = $(this).text().trim();
                let href = $(this).attr('href') || '';
                if (name && href) {
                    let episodeKey = `${name}_${href}`;
                    if (!seenEpisodes.has(episodeKey)) {
                        seenEpisodes.add(episodeKey);
                        epArray.push({ name, href });
                    }
                }
            });

            epArray.sort((a, b) => {
                let numA = parseInt(a.name.match(/第(\d+)/)?.[1] || 0);
                let numB = parseInt(b.name.match(/第(\d+)/)?.[1] || 0);
                return numA - numB;
            });

            epArray.forEach(ep => {
                episodes.push(`${ep.name}$${ep.href}`);
            });

            if (episodes.length > 0) {
                lines.push("默认");
                playlists.push(episodes);
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
            headers: {
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": appConfig.siteUrl
            }
        })).content;

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
            } catch (e) {
                console.error("解析player_aaaa失败:", e.message);
            }
        }

        let urlMatch = html.match(/"url"\s*[:=]\s*"([^"]+\.m3u8[^"]*)"/);
        if (urlMatch) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: urlMatch[1].replace(/\\/g, '')
            });
        }

        const $ = cheerio.load(html);
        let iframeSrc = $("iframe").attr("src");
        if (iframeSrc) {
            return JSON.stringify({
                parse: 1,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: fixUrl(iframeSrc)
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
