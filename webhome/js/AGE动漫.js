// 本资源来源于互联网公开渠道，仅可用于个人学习爬虫技术。
// 严禁将其用于任何商业用途，下载后请于 24 小时内删除，搜索结果均来自源站，本人不承担任何责任。
let e = "https://web.agespa-01.com:8443",
    t = "https://ageapi.omwjhz.com:18888";
const a = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        Accept: "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        Origin: e,
        Pragma: "no-cache",
        Referer: `${e}`,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="143", "Google Chrome";v="143"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"'
    },
    r = "function" == typeof js2Proxy && "function" == typeof desX && "function" != typeof getProxy;
async function n(e) {}
async function l(e) {
    let t = [{
        type_id: "1",
        type_name: "动漫"
    }];
    void 0 !== r && r && t.unshift({
        type_id: "home",
        type_name: "首页"
    });
    try {
        if (!e) return JSON.stringify({
            class: t,
            filters: {}
        });
        let a = {
            1: [{
                name: "region",
                label: "地区",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "日本",
                    value: "日本"
                }, {
                    text: "中国",
                    value: "中国"
                }, {
                    text: "欧美",
                    value: "欧美"
                }]
            }, {
                name: "genre",
                label: "版本",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "TV",
                    value: "TV"
                }, {
                    text: "剧场版",
                    value: "剧场版"
                }, {
                    text: "OVA",
                    value: "OVA"
                }]
            }, {
                name: "letter",
                label: "首字母",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "A",
                    value: "A"
                }, {
                    text: "B",
                    value: "B"
                }, {
                    text: "C",
                    value: "C"
                }, {
                    text: "D",
                    value: "D"
                }, {
                    text: "E",
                    value: "E"
                }, {
                    text: "F",
                    value: "F"
                }, {
                    text: "G",
                    value: "G"
                }, {
                    text: "H",
                    value: "H"
                }, {
                    text: "I",
                    value: "I"
                }, {
                    text: "J",
                    value: "J"
                }, {
                    text: "K",
                    value: "K"
                }, {
                    text: "L",
                    value: "L"
                }, {
                    text: "M",
                    value: "M"
                }, {
                    text: "N",
                    value: "N"
                }, {
                    text: "O",
                    value: "O"
                }, {
                    text: "P",
                    value: "P"
                }, {
                    text: "Q",
                    value: "Q"
                }, {
                    text: "R",
                    value: "R"
                }, {
                    text: "S",
                    value: "S"
                }, {
                    text: "T",
                    value: "T"
                }, {
                    text: "U",
                    value: "U"
                }, {
                    text: "V",
                    value: "V"
                }, {
                    text: "W",
                    value: "W"
                }, {
                    text: "X",
                    value: "X"
                }, {
                    text: "Y",
                    value: "Y"
                }, {
                    text: "Z",
                    value: "Z"
                }]
            }, {
                name: "year",
                label: "年份",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "2026",
                    value: "2026"
                }, {
                    text: "2025",
                    value: "2025"
                }, {
                    text: "2024",
                    value: "2024"
                }, {
                    text: "2023",
                    value: "2023"
                }, {
                    text: "2022",
                    value: "2022"
                }, {
                    text: "2021",
                    value: "2021"
                }, {
                    text: "2020",
                    value: "2020"
                }, {
                    text: "2019",
                    value: "2019"
                }, {
                    text: "2018",
                    value: "2018"
                }, {
                    text: "2017",
                    value: "2017"
                }, {
                    text: "2016",
                    value: "2016"
                }, {
                    text: "2015",
                    value: "2015"
                }, {
                    text: "2014",
                    value: "2014"
                }, {
                    text: "2013",
                    value: "2013"
                }, {
                    text: "2012",
                    value: "2012"
                }, {
                    text: "2011",
                    value: "2011"
                }, {
                    text: "2010",
                    value: "2010"
                }, {
                    text: "2009",
                    value: "2009"
                }, {
                    text: "2008",
                    value: "2008"
                }, {
                    text: "2007",
                    value: "2007"
                }, {
                    text: "2006",
                    value: "2006"
                }, {
                    text: "2005",
                    value: "2005"
                }, {
                    text: "2004",
                    value: "2004"
                }, {
                    text: "2003",
                    value: "2003"
                }, {
                    text: "2002",
                    value: "2002"
                }, {
                    text: "2001",
                    value: "2001"
                }, {
                    text: "2000以前",
                    value: "2000"
                }]
            }, {
                name: "season",
                label: "季度",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "1月",
                    value: "1"
                }, {
                    text: "4月",
                    value: "4"
                }, {
                    text: "7月",
                    value: "7"
                }, {
                    text: "10月",
                    value: "10"
                }]
            }, {
                name: "status",
                label: "状态",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "连载",
                    value: "连载"
                }, {
                    text: "完结",
                    value: "完结"
                }, {
                    text: "未播放",
                    value: "未播放"
                }]
            }, {
                name: "label",
                label: "类型",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "搞笑",
                    value: "搞笑"
                }, {
                    text: "运动",
                    value: "运动"
                }, {
                    text: "励志",
                    value: "励志"
                }, {
                    text: "热血",
                    value: "热血"
                }, {
                    text: "战斗",
                    value: "战斗"
                }, {
                    text: "竞技",
                    value: "竞技"
                }, {
                    text: "校园",
                    value: "校园"
                }, {
                    text: "青春",
                    value: "青春"
                }, {
                    text: "爱情",
                    value: "爱情"
                }, {
                    text: "恋爱",
                    value: "恋爱"
                }, {
                    text: "冒险",
                    value: "冒险"
                }, {
                    text: "后宫",
                    value: "后宫"
                }, {
                    text: "百合",
                    value: "百合"
                }, {
                    text: "治愈",
                    value: "治愈"
                }, {
                    text: "萝莉",
                    value: "萝莉"
                }, {
                    text: "魔法",
                    value: "魔法"
                }, {
                    text: "悬疑",
                    value: "悬疑"
                }, {
                    text: "推理",
                    value: "推理"
                }, {
                    text: "奇幻",
                    value: "奇幻"
                }, {
                    text: "科幻",
                    value: "科幻"
                }, {
                    text: "游戏",
                    value: "游戏"
                }, {
                    text: "神魔",
                    value: "神魔"
                }, {
                    text: "恐怖",
                    value: "恐怖"
                }, {
                    text: "血腥",
                    value: "血腥"
                }, {
                    text: "机战",
                    value: "机战"
                }, {
                    text: "战争",
                    value: "战争"
                }, {
                    text: "犯罪",
                    value: "犯罪"
                }, {
                    text: "历史",
                    value: "历史"
                }, {
                    text: "社会",
                    value: "社会"
                }, {
                    text: "职场",
                    value: "职场"
                }, {
                    text: "剧情",
                    value: "剧情"
                }, {
                    text: "伪娘",
                    value: "伪娘"
                }, {
                    text: "耽美",
                    value: "耽美"
                }, {
                    text: "童年",
                    value: "童年"
                }, {
                    text: "教育",
                    value: "教育"
                }, {
                    text: "亲子",
                    value: "亲子"
                }, {
                    text: "真人",
                    value: "真人"
                }, {
                    text: "歌舞",
                    value: "歌舞"
                }, {
                    text: "肉番",
                    value: "肉番"
                }, {
                    text: "美少女",
                    value: "美少女"
                }, {
                    text: "轻小说",
                    value: "轻小说"
                }, {
                    text: "吸血鬼",
                    value: "吸血鬼"
                }, {
                    text: "女性向",
                    value: "女性向"
                }, {
                    text: "泡面番",
                    value: "泡面番"
                }, {
                    text: "欢乐向",
                    value: "欢乐向"
                }]
            }, {
                name: "resource",
                label: "资源",
                data: [{
                    text: "全部",
                    value: "all"
                }, {
                    text: "BDRIP",
                    value: "BDRIP"
                }, {
                    text: "AGERIP",
                    value: "AGERIP"
                }]
            }, {
                name: "order",
                label: "排序",
                data: [{
                    text: "更新时间",
                    value: "time"
                }, {
                    text: "名称",
                    value: "name"
                }, {
                    text: "点击量",
                    value: "点击量"
                }]
            }].map(e => ({
                key: e.name,
                name: e.label,
                init: e.data[0].value,
                value: e.data.map(e => ({
                    n: e.text,
                    v: e.value
                }))
            }))
        };
        return JSON.stringify({
            class: t,
            filters: a
        })
    } catch (e) {
        return JSON.stringify({
            class: t,
            filters: {}
        })
    }
}
async function o() {
    try {
        const e = `${t}/v2/home-list`,
            r = await req(e, {
                headers: a,
                timeout: 8e3
            });
        if (!r || !r.content) return JSON.stringify({
            list: []
        });
        let n = "string" == typeof r.content ? JSON.parse(r.content) : r.content,
            l = new Map;
        const o = (e, t, a, r) => {
            if (!e) return;
            const n = e.toString().replace(/\/detail\//i, "");
            l.has(n) || l.set(n, {
                vod_id: n,
                vod_name: t || "",
                vod_pic: a || "",
                vod_remarks: r || ""
            })
        };
        if (Array.isArray(n.recommend) && n.recommend.forEach(e => {
                o(e.AID, e.Title, e.PicSmall, e.NewTitle)
            }), Array.isArray(n.latest) && n.latest.forEach(e => {
                o(e.AID, e.Title, e.PicSmall, e.NewTitle)
            }), n.week_list && "object" == typeof n.week_list) {
            ["1", "2", "3", "4", "5", "6", "0"].forEach(e => {
                const t = n.week_list[e];
                Array.isArray(t) && t.forEach(e => {
                    o(e.id, e.name, "", e.namefornew)
                })
            })
        }
        const i = Array.from(l.values());
        return JSON.stringify({
            list: i
        })
    } catch (e) {
        return JSON.stringify({
            list: []
        })
    }
}
async function i(e, r, n, l) {
    try {
        if ("home" === e) {
            let e = JSON.parse(await o());
            return JSON.stringify({
                list: e.list || [],
                page: 1,
                pagecount: 1
            })
        }
        const n = l.genre || "all",
            i = l.label || "all",
            s = l.letter || "all",
            c = l.order || "time",
            u = l.region || "all",
            v = l.resource || "all",
            p = l.season || "all",
            x = l.status || "all",
            d = l.year || "all",
            h = 20,
            m = `${t}/v2/catalog?genre=${encodeURIComponent(n)}&label=${encodeURIComponent(i)}&letter=${encodeURIComponent(s)}&order=${encodeURIComponent(c)}&region=${encodeURIComponent(u)}&resource=${encodeURIComponent(v)}&season=${encodeURIComponent(p)}&status=${encodeURIComponent(x)}&year=${encodeURIComponent(d)}&page=${r}&size=${h}`,
            g = await req(m, {
                headers: a,
                timeout: 8e3
            });
        if (!g || !g.content) return JSON.stringify({
            list: [],
            page: parseInt(r),
            pagecount: parseInt(r)
        });
        let f = "string" == typeof g.content ? JSON.parse(g.content) : g.content;
        if (!f.videos) return JSON.stringify({
            list: [],
            page: parseInt(r),
            pagecount: parseInt(r)
        });
        const y = f.videos.map(e => ({
                vod_id: e.id.toString(),
                vod_name: e.name,
                vod_pic: e.cover,
                vod_remarks: e.uptodate || e.status
            })),
            A = f.total || 0,
            S = A > 0 ? Math.ceil(A / h) : parseInt(r);
        return JSON.stringify({
            list: y,
            page: parseInt(r),
            pagecount: S
        })
    } catch (e) {
        return JSON.stringify({
            list: [],
            page: parseInt(r),
            pagecount: parseInt(r)
        })
    }
}
async function s(e, r, n = 1) {
    try {
        const r = encodeURIComponent(e),
            l = `${t}/v2/search?query=${r}&page=${n}`,
            o = await req(l, {
                headers: a,
                timeout: 8e3
            });
        if (!o || !o.content) return JSON.stringify({
            list: [],
            page: parseInt(n),
            pagecount: parseInt(n)
        });
        let i = "string" == typeof o.content ? JSON.parse(o.content) : o.content;
        if (!i.data || !i.data.videos) return JSON.stringify({
            list: [],
            page: parseInt(n),
            pagecount: parseInt(n)
        });
        const s = i.data.videos.map(e => ({
                vod_id: e.id.toString(),
                vod_name: e.name,
                vod_pic: e.cover,
                vod_remarks: e.uptodate || e.status
            })),
            c = i.data.totalPage || parseInt(n);
        return JSON.stringify({
            list: s,
            page: parseInt(n),
            pagecount: c
        })
    } catch (e) {
        return JSON.stringify({
            list: [],
            page: parseInt(n),
            pagecount: parseInt(n)
        })
    }
}
async function c(e) {
    try {
        const r = `${t}/v2/detail/${e}`,
            n = await req(r, {
                headers: a,
                timeout: 8e3
            });
        if (!n || !n.content) return JSON.stringify({
            list: []
        });
        let l = "string" == typeof n.content ? JSON.parse(n.content) : n.content;
        const o = l.video || {},
            i = o.playlists || {},
            s = l.player_label_arr || {},
            c = (l.player_vip || "").split(","),
            u = l.player_jx || {
                vip: "",
                zj: ""
            };
        let v = [],
            p = [];
        for (const e in i) {
            const t = s[e] || e;
            v.push(`${t}(${e})`);
            const a = c.includes(e) ? u.vip || "" : u.zj || "";
            let r = [];
            (i[e] || []).forEach(e => {
                if (Array.isArray(e) && e.length >= 2) {
                    const t = e[0],
                        n = e[1],
                        l = a ? `${a}${n}` : n;
                    r.push(`${t}$${l}`)
                }
            }), p.push(r.join("#"))
        }
        const x = {
            vod_id: o.id ? o.id.toString() : e.toString(),
            vod_name: o.name || "",
            vod_pic: o.cover || "",
            type_name: o.type || "",
            vod_year: o.year ? o.year.toString() : "",
            vod_area: o.area || "",
            vod_remarks: o.uptodate || o.status || "",
            vod_actor: "",
            vod_director: "",
            vod_content: o.intro_clean || o.intro || "",
            vod_play_from: v.join("$$$"),
            vod_play_url: p.join("$$$")
        };
        return JSON.stringify({
            list: [x]
        })
    } catch (e) {
        return JSON.stringify({
            list: []
        })
    }
}
async function u(e, t, r) {
    try {
        let e = await async function(e) {
            try {
                function t(e) {
                    const t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
                    let a = [];
                    for (let t = 0; t < e.length; t += 2) a.push(parseInt(e.substring(t, t + 2), 16));
                    let r = "",
                        n = 0,
                        l = a.length;
                    for (; n < l;) {
                        let e, o, i = 255 & a[n++];
                        if (n === l) {
                            r += t.charAt(i >> 2) + t.charAt((3 & i) << 4) + "==";
                            break
                        }
                        if (e = a[n++], n === l) {
                            r += t.charAt(i >> 2) + t.charAt((3 & i) << 4 | (240 & e) >> 4) + t.charAt((15 & e) << 2) + "=";
                            break
                        }
                        o = a[n++], r += t.charAt(i >> 2) + t.charAt((3 & i) << 4 | (240 & e) >> 4) + t.charAt((15 & e) << 2 | (192 & o) >> 6) + t.charAt(63 & o)
                    }
                    return r
                }

                function a(e) {
                    const t = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
                        a = new Uint8Array(256);
                    for (let e = 0; e < t.length; e++) a[t.charCodeAt(e)] = e;
                    let r = [];
                    for (let t = 0; t < e.length; t += 4) {
                        let n = a[e.charCodeAt(t)] << 18 | a[e.charCodeAt(t + 1)] << 12 | a[e.charCodeAt(t + 2)] << 6 | a[e.charCodeAt(t + 3)];
                        r.push(n >> 16 & 255), "=" !== e[t + 2] && r.push(n >> 8 & 255), "=" !== e[t + 3] && r.push(255 & n)
                    }
                    return r.map(e => ("00" + e.toString(16)).slice(-2)).join("").toUpperCase()
                }

                function r() {
                    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, e => {
                        const t = 16 * Math.random() | 0;
                        return ("x" === e ? t : 3 & t | 8).toString(16)
                    })
                }
                const n = function() {
                        const e = "ni po jie ni ** ",
                            r = "AES/CBC/PKCS7";
                        return {
                            encrypt: t => a(aesX(r, !0, t, !1, e, e, !0)),
                            decrypt: a => aesX(r, !1, t(a), !0, e, e, !1)
                        }
                    }(),
                    l = e.match(/(https?:\/\/[^/]+)/),
                    o = l ? l[1] : "",
                    i = e.match(/https?:\/\/([^/:]+)/),
                    s = i ? i[1] : "",
                    c = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                        "accept-language": "zh-CN,zh;q=0.9",
                        "cache-control": "no-cache",
                        pragma: "no-cache",
                        "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"Windows"',
                        "sec-fetch-storage-access": "none"
                    },
                    u = (await req(e, {
                        method: "get",
                        headers: {
                            ...c,
                            Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                            priority: "u=0, i",
                            referer: "https://web.agespa-01.com:8443/",
                            "sec-fetch-dest": "iframe",
                            "sec-fetch-mode": "navigate",
                            "sec-fetch-site": "cross-site",
                            "sec-fetch-user": "?1",
                            "upgrade-insecure-requests": "1"
                        }
                    })).content;
                if (!u) throw new Error("");
                const v = u.match(/var Vurl\s*=\s*['"]([^'"]+)['"]/),
                    p = v ? v[1] : "";
                if (/^(https?:\/\/|\/\/)\S+/i.test(p)) return p.startsWith("//") ? "https:" + p : p;
                const x = u.match(/var Time\s*=\s*"([^"]+)"/),
                    d = u.match(/var Version\s*=\s*"([^"]+)"/),
                    h = u.match(/var Ref\s*=\s*"([^"]+)"/),
                    m = u.match(/var Api\s*=\s*"([^"]+)"/),
                    g = u.match(/<meta\s+http-equiv="Content-Type"[^>]+id="([^"]+)"/i),
                    f = u.match(/<meta\s+name="viewport"[^>]+id="([^"]+)"/i),
                    y = x ? x[1] : Math.floor(Date.now() / 1e3).toString(),
                    A = d ? d[1] : "V3.2",
                    S = h ? h[1] : "aHR0cHM6Ly93ZWIuYWdlc3BhLTAxLmNvbTo4NDQzLw==",
                    C = m ? m[1] : `${o}/vip`,
                    N = g ? g[1] : "",
                    _ = f ? f[1] : "",
                    I = r(),
                    $ = {
                        url: p,
                        wap: "0",
                        ios: "0",
                        host: s,
                        referer: S,
                        time: y
                    },
                    w = n.encrypt(JSON.stringify($)),
                    O = `${s} | ${I} | ${y} | ${A} | ${w}`,
                    J = n.encrypt(O),
                    b = `${C}/Api.php`,
                    R = await req(b, {
                        method: "post",
                        postType: "form",
                        headers: {
                            ...c,
                            Accept: "application/json, text/javascript, */*; q=0.01",
                            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                            origin: o,
                            priority: "u=1, i",
                            "sec-fetch-dest": "empty",
                            "sec-fetch-mode": "cors",
                            "sec-fetch-site": "same-origin",
                            "video-parse-sign": J,
                            "video-parse-time": y,
                            "video-parse-uuid": I,
                            "video-parse-version": A,
                            "x-requested-with": "XMLHttpRequest"
                        },
                        data: {
                            Params: w
                        }
                    });
                let U = {};
                if (U = "string" == typeof R.content ? JSON.parse(R.content) : R.content, 1 !== U.Status) throw new Error("");
                let q = "";
                if (10 === U.Code) {
                    let E = (N + _).replace("viewport", "");
                    q = U.Code + E + U.Appkey + U.Version
                } else q = U.Code + U.Appkey + U.Version;
                let T = md5X(q),
                    k = aesX("AES/CBC/PKCS7", !1, t(U.Data), !0, T.substring(0, 16), T.substring(16, 32), !1),
                    j = JSON.parse(k),
                    P = "";
                return P = 10 === U.Code ? n.decrypt(j.url) : j.url, decodeURIComponent(P)
            } catch (M) {
                return ""
            }
        }(t);
        if (e) return JSON.stringify({
            parse: 0,
            url: e,
            header: {
                "User-Agent": a["User-Agent"]
            }
        })
    } catch (e) {}
    return JSON.stringify({
        parse: 1,
        url: t,
        header: {}
    })
}
export function __jsEvalReturn() {
    return {
        init: n,
        home: l,
        homeVod: o,
        category: i,
        search: s,
        detail: c,
        play: u
    }
}