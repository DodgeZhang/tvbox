import cheerio from 'assets://js/lib/cheerio.min.js';

const appConfig = {
    siteName: "星辰影视",
    siteUrl: "https://www.xyys798.com"
};
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

async function init(ext) {
    console.log("初始化爬虫:", appConfig.siteName);
}

const classList = [
    { type_id: "6", type_name: "动作片" },
    { type_id: "7", type_name: "喜剧片" },
    { type_id: "8", type_name: "爱情片" },
    { type_id: "9", type_name: "科幻片" },
    { type_id: "10", type_name: "恐怖片" },
    { type_id: "11", type_name: "剧情片" },
    { type_id: "12", type_name: "战争片" },
    { type_id: "13", type_name: "纪录片" },
    { type_id: "17", type_name: "国产剧" },
    { type_id: "18", type_name: "港台剧" },
    { type_id: "20", type_name: "日韩剧" },
    { type_id: "21", type_name: "欧美剧" },
    { type_id: "22", type_name: "海外剧" },
    { type_id: "23", type_name: "大陆综艺" },
    { type_id: "24", type_name: "港台综艺" },
    { type_id: "25", type_name: "日韩综艺" },
    { type_id: "26", type_name: "欧美综艺" },
    { type_id: "27", type_name: "国产动漫" },
    { type_id: "28", type_name: "日韩动漫" },
    { type_id: "29", type_name: "欧美动漫" },
    { type_id: "30", type_name: "其他动漫" },
    { type_id: "5", type_name: "短剧" }
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

const commonFilters = [getAreaFilter(), getYearFilter(), getLangFilter(), getTypeFilter()];

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

        // 遍历所有 .img-list，但排除 swiper-wrapper（轮播）
        $(".img-list:not(.swiper-wrapper)").each(function () {
            $(this).find("li[class*='col-md-']").each(function () {
                let $a = $(this).find("a[href*='/xcsydetail/']").first();
                let vod_id = $a.attr("href");
                if (!vod_id || seen[vod_id]) return;

                let vod_name = $a.attr("title") || "";
                let vod_pic = fixUrl($a.attr("data-original") || $a.attr("data-background") || $a.find("img").attr("data-original") || $a.find("img").attr("src") || "");
                let vod_remarks = ($a.find(".vtitle").text() || $a.find(".vname").text() || "").trim();

                if (vod_name && vod_id) {
                    seen[vod_id] = true;
                    list.push({ vod_id, vod_name, vod_pic, vod_remarks });
                }
            });
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

    if (area || year || lang || type) {
        let url = `/xcsyshow/${tid}-${area || ''}-${lang || ''}--${type || ''}---${year || ''}---${pg}---.html`;
        return appConfig.siteUrl + url;
    } else {
        return `${appConfig.siteUrl}/xcsytype/${tid}${pg > 1 ? '-' + pg : ''}.html`;
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

    // 只取第一个主分类内容区域（排除 swiper-wrapper 轮播），不包含子分类推荐
    let $mainList = $(".img-list:not(.swiper-wrapper)").first();
    
    $mainList.find("li[class*='col-md-']").each(function () {
        let $a = $(this).find("a[href*='/xcsydetail/']").first();
        let vod_id = $a.attr("href");
        if (!vod_id || vodIds[vod_id]) return;

        let vod_name = $a.attr("title") || "";
        let vod_pic = fixUrl($a.attr("data-original") || $a.find("img").first().attr("data-original") || $a.find("img").first().attr("src") || $a.attr("data-background") || "");
        
        let vod_remarks = "";
        $a.contents().each(function () {
            if (this.type === 'text') {
                let t = $(this).text().trim();
                if (t) vod_remarks = t;
            }
        });
        if (!vod_remarks) {
            vod_remarks = $a.find(".vtitle").text().trim() || $a.find(".vname").text().trim();
        }

        if (vod_name && vod_id) {
            vodIds[vod_id] = true;
            list.push({ vod_id, vod_name, vod_pic, vod_remarks });
        }
    });

    let pagecount = 1;
    $("a[href*='/xcsytype/'], a[href*='/xcsyshow/']").each(function () {
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
        const url = `${appConfig.siteUrl}/xcsysearch/-------------.html?wd=${encodeURIComponent(wd)}&page=${page}`;
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

        let vod_name = $("h1").first().text().trim() || $(".details-title").first().text().trim();

        let vod_pic = "";
        let $pic = $(".details-pic img, .video-pic img, img[src*='upload']").first();
        if ($pic.length > 0) {
            vod_pic = fixUrl($pic.attr("src") || $pic.attr("data-original") || "");
        }
        if (!vod_pic) {
            $("img").each(function () {
                let src = $(this).attr("src") || $(this).attr("data-original") || "";
                if (src.includes('upload') && !vod_pic) {
                    vod_pic = fixUrl(src);
                }
            });
        }

        let vod_director = "";
        let vod_actor = "";
        let vod_area = "";
        let vod_year = "";
        let vod_content = "";
        let vod_class = "";
        let vod_remarks = "";

        $("li").each(function () {
            let text = $(this).text();
            if (text.includes("导演：") && !vod_director) {
                vod_director = $(this).text().replace("导演：", "").trim();
            }
            if (text.includes("主演：") && !vod_actor) {
                vod_actor = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_actor) vod_actor = $(this).text().replace("主演：", "").trim();
            }
            if (text.includes("类型：") && !vod_class) {
                vod_class = $(this).find("a").map(function () { return $(this).text().trim(); }).get().filter(Boolean).join(',');
                if (!vod_class) vod_class = $(this).text().replace("类型：", "").trim();
            }
            if (text.includes("地区：") && !vod_area) {
                vod_area = $(this).text().replace("地区：", "").trim();
            }
        });

        let $intro = $(".txt-hidden, .content, .video-info-content, .details-content");
        if ($intro.length > 0) {
            vod_content = $intro.first().text().replace("简介：", "").trim();
        }

        let lines = [];
        let playlists = [];
        let seenEpisodes = new Set();

        $(".play-list-toggle").each(function (panelIndex) {
            let lineName = $(this).find("a").text().trim() || "默认";

            let $playList = $(".play-list").eq(panelIndex);
            let episodes = [];
            let epArray = [];

            $playList.find("a[href*='/xcsyplay/']").each(function () {
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

            // 改成正序：按集数号排序
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

        // 如果没有找到线路，尝试其他选择器
        if (lines.length === 0) {
            let episodes = [];
            let epArray = [];

            $("a[href*='/xcsyplay/']").each(function () {
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

            // 正序排序
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

        // 解析 player_aaaa
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

        // 尝试匹配 m3u8 URL
        let urlMatch = html.match(/"url"\s*[:=]\s*"([^"]+\.m3u8[^"]*)"/);
        if (urlMatch) {
            return JSON.stringify({
                parse: 0,
                Header: { "User-Agent": UA, "Referer": appConfig.siteUrl },
                url: urlMatch[1].replace(/\\/g, '')
            });
        }

        // 尝试 iframe
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
