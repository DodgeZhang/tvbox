//小心儿悠悠//
var mgFilter = [{
    "key": "sort",
    "name": "排序",
    "value": [
        {"n": "最热", "v": "c2"},
        {"n": "最新", "v": "c1"}
    ]
}, {
    "key": "area",
    "name": "地区",
    "value": [
        {"n": "全部", "v": "a1"},
        {"n": "内地", "v": "10"},
        {"n": "港台", "v": "12"},
        {"n": "泰国", "v": "193"}
    ]
}, {
    "key": "year",
    "name": "年代",
    "value": [
        {"n": "全部", "v": "all"},
        {"n": "2026", "v": "2026"},
        {"n": "2025", "v": "2025"},
        {"n": "2024", "v": "2024"},
        {"n": "2023", "v": "2023"},
        {"n": "2022", "v": "2022"},
        {"n": "2021", "v": "2021"},
        {"n": "2020", "v": "2020"},
        {"n": "2019", "v": "2019"},
        {"n": "2018", "v": "2018"},
        {"n": "2010-2014", "v": "2014t2010"},
        {"n": "2000-2009", "v": "2009t2000"},
        {"n": "90年代", "v": "1990s"},
        {"n": "更早", "v": "1989e"}
    ]
}, {
    "key": "chargeInfo",
    "name": "资费",
    "value": [
        {"n": "全部", "v": "a1"},
        {"n": "免费", "v": "b1"},
        {"n": "VIP", "v": "b2"}
    ]
}];
var rule = {
    title: '百忙无果[官]',
    host: 'https://pianku.api.mgtv.com',
    homeUrl: '',
    searchUrl: 'https://mobileso.bz.mgtv.com/msite/search/v2?q=**&pn=fypage&pc=10',
    detailUrl: 'https://pcweb.api.mgtv.com/episode/list?page=1&size=50&video_id=fyid',
    searchable: 2,
    quickSearch: 0,
    filterable: 1,
    multi: 1,
    url: '/rider/list/pcweb/v3?platform=pcweb&channelId=fyclass&pn=fypage&pc=80&hudong=1&_support=10000000&kind=a1',
    filter_url: 'area={{fl.area or "a1"}}&year={{fl.year or "all"}}&sort={{fl.sort or "c2"}}&chargeInfo={{fl.chargeInfo or "a1"}}',
    headers: {
        'User-Agent': 'PC_UA'
    },
    timeout: 5000,
    class_name: '电视剧&电影&综艺&动漫&纪录片&教育&少儿',
    class_url: '2&3&1&50&51&115&10',
    filter: {
        "1": mgFilter,
        "2": mgFilter,
        "3": mgFilter,
        "10": mgFilter,
        "50": mgFilter,
        "51": mgFilter,
        "115": mgFilter
    },
    limit: 20,
    play_parse: true,
    lazy: $js.toString(() => {
        try {
            let api = input.split("?")[0];
            let response = fetch(api, {
                method: 'get',
                headers: {
                    'User-Agent': 'okhttp/3.14.9',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            });
            let bata = JSON.parse(response);
            input = {
                parse: 0,
                url: bata.url.includes("mgtv") ? bata.url : input.split("?")[0],
                jx: bata.url.includes("mgtv") ? 0 : 1,
                danmaku: "http://103.36.220.166:98/tvbox/zh.php?url=" + input.split("?")[0]
            };
        } catch (e) {
            input = {
                parse: 0,
                url: input.split("?")[0],
                jx: 1,
                danmaku: "http://103.36.220.166:98/tvbox/zh.php?url=" + input.split("?")[0]
            };
        }
    }),
    一级: 'json:data.hitDocs;title;img;updateInfo||rightCorner.text;playPartId',
    二级: $js.toString(() => {
        fetch_params.headers.Referer = "https://www.mgtv.com";
        fetch_params.headers["User-Agent"] = MOBILE_UA;
        
        let videoId = input.split('video_id=')[1].split('&')[0];
        let infoUrl = `https://pcweb.api.mgtv.com/video/info?allowedRC=1&vid=${videoId}&type=b&_support=10000000`;
        let infoData = JSON.parse(request(infoUrl));
        
        if (infoData && infoData.data && infoData.data.info) {
            let detail = infoData.data.info.detail || {};
            VOD = {
                vod_name: infoData.data.info.title || "",
                type_name: detail.kind || "",
                vod_year: detail.releaseTime || "",
                vod_area: detail.area || "",
                vod_actor: detail.leader || "",
                vod_director: detail.director || "",
                vod_content: detail.story || "",
                vod_remarks: detail.updateInfo || ""
            };
            if (detail.img) VOD.vod_pic = detail.img;
        }

        let d = [];
        let html = request(input);
        let json = JSON.parse(html);
        let host = "https://www.mgtv.com";
        let ourl = json.data.list.length > 0 ? json.data.list[0].url : json.data.series[0].url;
        if (!/^http/.test(ourl)) ourl = host + ourl;
        
        fetch_params.headers["User-Agent"] = MOBILE_UA;
        html = request(ourl);
        if (html.includes("window.location =")) {
            ourl = pdfh(html, "meta[http-equiv=refresh]&&content").split("url=")[1];
            html = request(ourl);
        }

        try {
            let details = pdfh(html, ".m-details&&Html").replace(/h1>/, "h6>").replace(/div/g, "br");
            let actor = "", director = "", time = "";
            if (/播出时间/.test(details)) {
                actor = pdfh(html, "p:eq(5)&&Text").substr(0, 25);
                director = pdfh(html, "p:eq(4)&&Text");
                time = pdfh(html, "p:eq(3)&&Text");
            } else {
                actor = pdfh(html, "p:eq(4)&&Text").substr(0, 25);
                director = pdfh(html, "p:eq(3)&&Text");
                time = "已完结";
            }
            let _img = pd(html, ".video-img&&img&&src");
            let JJ = pdfh(html, ".desc&&Text").split("牛马简介：")[1];
            VOD.vod_name = VOD.vod_name || pdfh(html, ".vt-txt&&Text");
            VOD.type_name = VOD.type_name || pdfh(html, "p:eq(0)&&Text").substr(0, 6);
            VOD.vod_area = VOD.vod_area || pdfh(html, "p:eq(1)&&Text");
            VOD.vod_actor = VOD.vod_actor || actor;
            VOD.vod_director = VOD.vod_director || director;
            VOD.vod_remarks = VOD.vod_remarks || time;
            VOD.vod_pic = VOD.vod_pic || _img;
            VOD.vod_content = VOD.vod_content || JJ;
            if (!VOD.vod_name) VOD.vod_name = VOD.type_name;
        } catch (e) {
            log("获取影片信息发生错误:" + e.message);
        }

        function getRjpg(imgUrl, xs) {
            xs = xs || 3;
            let picSize = /jpg_/.test(imgUrl) ? imgUrl.split("jpg_")[1].split(".")[0] : false;
            let rjpg = false;
            if (picSize) {
                let a = parseInt(picSize.split("x")[0]) * xs;
                let b = parseInt(picSize.split("x")[1]) * xs;
                rjpg = a + "x" + b + ".jpg";
            }
            return /jpg_/.test(imgUrl) && rjpg ? imgUrl.replace(imgUrl.split("jpg_")[1], rjpg) : imgUrl;
        }

        if (json.data.total === 1 && json.data.list.length === 1) {
            let data = json.data.list[0];
            d.push({
                title: data.t4,
                desc: data.t2,
                pic_url: getRjpg(data.img),
                url: "https://www.mgtv.com" + data.url
            });
        } else if (json.data.list.length > 1) {
            for (let i = 1; i <= json.data.total_page; i++) {
                if (i > 1) json = JSON.parse(fetch(input.replace("page=1", "page=" + i), {}));
                json.data.list.forEach(function(data) {
                    if (data.isIntact == "1") {
                        d.push({
                            title: data.t4,
                            desc: data.t2,
                            pic_url: getRjpg(data.img),
                            url: "https://www.mgtv.com" + data.url
                        });
                    }
                });
            }
        } else {
            print(input + "暂无片源");
        }
        VOD.vod_play_from = "芒果TV";
        VOD.vod_play_url = d.map(function(it) {
            return it.title + "$" + it.url;
        }).join("#");
        setResult(d);
    }),
    搜索: $js.toString(() => {
        fetch_params.headers.Referer = "https://www.mgtv.com";
        fetch_params.headers["User-Agent"] = MOBILE_UA;
        let d = [];
        let html = request(input);
        let json = JSON.parse(html);
        json.data.contents.forEach(function(data) {
            if (data.type && data.type == 'media') {
                let item = data.data[0];
                if (item.source === "imgo") {
                    let fyclass = '';
                    try {
                        fyclass = item.rpt.match(/idx=(.*?)&/)[1] + '$';
                    } catch (e) {
                        log(e.message);
                    }
                    d.push({
                        title: item.title.replace(/<B>|<\/B>/g, ''),
                        img: item.img || '',
                        content: '',
                        desc: item.desc.join(','),
                        url: fyclass + item.url.match(/.*\/(.*?)\.html/)[1]
                    });
                }
            }
        });
        setResult(d);
    })
};

