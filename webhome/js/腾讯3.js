globalThis.vod1 = function(ids) {
    let html1 = request('https://pbaccess.video.qq.com/trpc.videosearch.mobile_search.MultiTerminalSearch/MbSearch?vplatform=2', {
        body: {
            "version": "25042201",
            "clientType": 1,
            "filterValue": "",
            "uuid": "B1E50847-D25F-4C4B-BBA0-36F0093487F6",
            "retry": 0,
            "query": ids,
            "pagenum": 0,
            "isPrefetch": true,
            "pagesize": 30,
            "queryFrom": 0,
            "searchDatakey": "",
            "transInfo": "",
            "isneedQc": true,
            "preQid": "",
            "adClientInfo": "",
            "extraInfo": {
                "isNewMarkLabel": "1",
                "multi_terminal_pc": "1",
                "themeType": "1",
                "sugRelatedIds": "{}",
                "appVersion": ""
            }
        },
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.139 Safari/537.36',
            'Content-Type': 'application/json',
            'origin': 'https://v.qq.com',
            'referer': 'https://v.qq.com/'
        },
        'method': 'POST'
    }, true);
    return html1;
}

var rule = {
    title: '腾云驾雾[官]',
    host: 'https://v.%71%71.com',
    homeUrl: '/x/bu/pagesheet/list?_all=1&append=1&channel=cartoon&listpage=1&offset=0&pagesize=21&iarea=-1&sort=18',
    detailUrl: 'https://node.video.%71%71.com/x/api/float_vinfo2?cid=fyid',
    searchUrl: 'https://pbaccess.video.%71%71.com/trpc.videosearch.smartboxServer.HttpRountRecall/Smartbox?query=**&appID=3172&appKey=lGhFIPeD3HsO9xEp&pageNum=(fypage-1)&pageSize=10',
    searchUrl: '**',
    searchable: 2,
    filterable: 1,
    multi: 1,
    url: '/x/bu/pagesheet/list?_all=1&append=1&channel=fyclass&listpage=1&offset=((fypage-1)*21)&pagesize=21&iarea=-1',
    filter_url: 'sort={{fl.sort or 75}}&iyear={{fl.iyear}}&year={{fl.year}}&itype={{fl.type}}&ifeature={{fl.feature}}&iarea={{fl.area}}&itrailer={{fl.itrailer}}&gender={{fl.sex}}',
    filter: {
        "choice": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "83"},{"n": "好评","v": "81"}]
        }, {
            "key": "iyear",
            "name": "年代",
            "value": [{"n": "全部","v": "-1"},{"n": "2025","v": "2025"},{"n": "2024","v": "2024"},{"n": "2023","v": "2023"},{"n": "2022","v": "2022"},{"n": "2021","v": "2021"},{"n": "2020","v": "2020"},{"n": "2019","v": "2019"},{"n": "2018","v": "2018"},{"n": "2017","v": "2017"},{"n": "2016","v": "2016"},{"n": "2015","v": "2015"}]
        }],
        "tv": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "79"},{"n": "好评","v": "16"}]
        }, {
            "key": "feature",
            "name": "类型",
            "value": [{"n": "全部","v": "-1"},{"n": "爱情","v": "1"},{"n": "古装","v": "2"},{"n": "悬疑","v": "3"},{"n": "都市","v": "4"},{"n": "家庭","v": "5"},{"n": "喜剧","v": "6"},{"n": "传奇","v": "7"},{"n": "武侠","v": "8"},{"n": "军旅","v": "9"},{"n": "权谋","v": "10"},{"n": "革命","v": "11"},{"n": "现实","v": "13"},{"n": "青春","v": "14"},{"n": "猎奇","v": "15"},{"n": "科幻","v": "16"},{"n": "竞技","v": "17"},{"n": "玄幻","v": "18"}]
        }, {
            "key": "iyear",
            "name": "年代",
            "value": [{"n": "全部","v": "-1"},{"n": "2025","v": "2025"},{"n": "2024","v": "2024"},{"n": "2023","v": "2023"},{"n": "2022","v": "2022"},{"n": "2021","v": "2021"},{"n": "2020","v": "2020"},{"n": "2019","v": "2019"},{"n": "2018","v": "2018"},{"n": "2017","v": "2017"},{"n": "2016","v": "2016"},{"n": "2015","v": "2015"}]
        }],
        "movie": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "83"},{"n": "好评","v": "81"}]
        }, {
            "key": "type",
            "name": "类型",
            "value": [{"n": "全部","v": "-1"},{"n": "犯罪","v": "4"},{"n": "励志","v": "2"},{"n": "喜剧","v": "100004"},{"n": "热血","v": "100061"},{"n": "悬疑","v": "100009"},{"n": "爱情","v": "100005"},{"n": "科幻","v": "100012"},{"n": "恐怖","v": "100010"},{"n": "动画","v": "100015"},{"n": "战争","v": "100006"},{"n": "家庭","v": "100017"},{"n": "剧情","v": "100022"},{"n": "奇幻","v": "100016"},{"n": "武侠","v": "100011"},{"n": "历史","v": "100021"},{"n": "老片","v": "100013"},{"n": "西部","v": "3"},{"n": "记录片","v": "100020"}]
        }, {
            "key": "year",
            "name": "年代",
            "value": [{"n": "全部","v": "-1"},{"n": "2025","v": "2025"},{"n": "2024","v": "2024"},{"n": "2023","v": "2023"},{"n": "2022","v": "2022"},{"n": "2021","v": "2021"},{"n": "2020","v": "2020"},{"n": "2019","v": "2019"},{"n": "2018","v": "2018"},{"n": "2017","v": "2017"},{"n": "2016","v": "2016"},{"n": "2015","v": "2015"}]
        }],
        "variety": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "23"}]
        }, {
            "key": "iyear",
            "name": "年代",
            "value": [{"n": "全部","v": "-1"},{"n": "2025","v": "2025"},{"n": "2024","v": "2024"},{"n": "2023","v": "2023"},{"n": "2022","v": "2022"},{"n": "2021","v": "2021"},{"n": "2020","v": "2020"},{"n": "2019","v": "2019"},{"n": "2018","v": "2018"},{"n": "2017","v": "2017"},{"n": "2016","v": "2016"},{"n": "2015","v": "2015"}]
        }],
        "cartoon": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "83"},{"n": "好评","v": "81"}]
        }, {
            "key": "area",
            "name": "地区",
            "value": [{"n": "全部","v": "-1"},{"n": "内地","v": "1"},{"n": "日本","v": "2"},{"n": "欧美","v": "3"},{"n": "其他","v": "4"}]
        }, {
            "key": "type",
            "name": "类型",
            "value": [{"n": "全部","v": "-1"},{"n": "玄幻","v": "9"},{"n": "科幻","v": "4"},{"n": "武侠","v": "13"},{"n": "冒险","v": "3"},{"n": "战斗","v": "5"},{"n": "搞笑","v": "1"},{"n": "恋爱","v": "7"},{"n": "魔幻","v": "6"},{"n": "竞技","v": "20"},{"n": "悬疑","v": "17"},{"n": "日常","v": "15"},{"n": "校园","v": "16"},{"n": "真人","v": "18"},{"n": "推理","v": "14"},{"n": "历史","v": "19"},{"n": "经典","v": "3"},{"n": "其他","v": "12"}]
        }, {
            "key": "iyear",
            "name": "年代",
            "value": [{"n": "全部","v": "-1"},{"n": "2025","v": "2025"},{"n": "2024","v": "2024"},{"n": "2023","v": "2023"},{"n": "2022","v": "2022"},{"n": "2021","v": "2021"},{"n": "2020","v": "2020"},{"n": "2019","v": "2019"},{"n": "2018","v": "2018"},{"n": "2017","v": "2017"},{"n": "2016","v": "2016"},{"n": "2015","v": "2015"}]
        }],
        "child": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "76"},{"n": "好评","v": "20"}]
        }, {
            "key": "sex",
            "name": "性别",
            "value": [{"n": "全部","v": "-1"},{"n": "女孩","v": "1"},{"n": "男孩","v": "2"}]
        }, {
            "key": "area",
            "name": "地区",
            "value": [{"n": "全部","v": "-1"},{"n": "内地","v": "3"},{"n": "日本","v": "2"},{"n": "其他","v": "1"}]
        }, {
            "key": "iyear",
            "name": "年龄段",
            "value": [{"n": "全部","v": "-1"},{"n": "0-3岁","v": "1"},{"n": "4-6岁","v": "2"},{"n": "7-9岁","v": "3"},{"n": "10岁以上","v": "4"},{"n": "全年龄段","v": "7"}]
        }],
        "doco": [{
            "key": "sort",
            "name": "排序",
            "value": [{"n": "最热","v": "75"},{"n": "最新","v": "74"}]
        }, {
            "key": "itrailer",
            "name": "出品方",
            "value": [{"n": "全部","v": "-1"},{"n": "BBC","v": "1"},{"n": "国家地理","v": "4"},{"n": "HBO","v": "3175"},{"n": "NHK","v": "2"},{"n": "历史频道","v": "7"},{"n": "ITV","v": "3530"},{"n": "探索频道","v": "3174"},{"n": "ZDF","v": "3176"},{"n": "腾讯自制","v": "15"},{"n": "合作机构","v": "6"},{"n": "其他","v": "5"}]
        }, {
            "key": "type",
            "name": "类型",
            "value": [{"n": "全部","v": "-1"},{"n": "自然","v": "4"},{"n": "美食","v": "10"},{"n": "社会","v": "3"},{"n": "人文","v": "6"},{"n": "历史","v": "1"},{"n": "军事","v": "2"},{"n": "科技","v": "8"},{"n": "财经","v": "14"},{"n": "探险","v": "15"},{"n": "罪案","v": "7"},{"n": "竞技","v": "12"},{"n": "旅游","v": "11"}]
        }]
    },
    headers: {
        'User-Agent': 'PC_UA'
    },
    timeout: 5000,
    cate_exclude: '会员|游戏|全部',
    class_name: '电影&电视剧&综艺&动漫&少儿&纪录片',
    class_url: 'movie&tv&variety&cartoon&child&doco',
    limit: 20,
    play_parse: true,
    lazy: $js.toString(() => {
        try {
            // 1. 构建解析接口地址（传入当前播放页 URL）
            let apiUrl = "http://192.140.166.17:8864/api/index?parsesId=4&appid=10000&videoUrl=" + encodeURIComponent(input);
            log("解析请求: " + apiUrl);

            // 2. 请求接口
            let encrypted = fetch(apiUrl, {
                method: 'get',
                headers: { 'User-Agent': 'Mozilla/5.0' },
                timeout: 8000
            });
            log("接口原始返回: " + encrypted);

            // 3. 解析 JSON，提取 url 字段（Base64 字符串）
            let json = JSON.parse(encrypted);
            let base64Data = json.url || json.data || json.result;
            if (!base64Data) {
                throw new Error("未找到可解码的数据字段");
            }
            log("提取的 Base64 数据: " + base64Data);

            // 4. 第一次 Base64 解码（得到包含前缀和密文的完整字符串）
            let decodedStr;
            if (typeof CryptoJS !== 'undefined' && CryptoJS.enc && CryptoJS.enc.Base64) {
                let wordArray = CryptoJS.enc.Base64.parse(base64Data);
                decodedStr = wordArray.toString(CryptoJS.enc.Utf8);
                // 如果 UTF-8 解码后出现乱码，尝试 Latin1
                if (!decodedStr || decodedStr.indexOf('�') !== -1) {
                    decodedStr = wordArray.toString(CryptoJS.enc.Latin1);
                    log("第一次 Base64 解码使用 Latin1");
                }
            } else {
                decodedStr = atob(base64Data);
            }
            log("第一次 Base64 解码后: " + decodedStr);

            // 5. 删除前缀（支持多种变体）
            const prefixes = ["https://ldmax.cooom/", "http://ldmax.cooom/", "ldmax.cooom/"];
            let cleaned = decodedStr;
            for (let p of prefixes) {
                if (cleaned.startsWith(p)) {
                    cleaned = cleaned.substring(p.length);
                    break;
                }
            }
            if (cleaned === decodedStr) {
                log("未发现已知前缀，尝试直接处理");
            }
            log("去除前缀后: " + cleaned);

            // 6. 取前 16 个字符作为 seed，倒序得到 key 和 iv
            if (cleaned.length < 16) {
                throw new Error("数据过短，无法提取 key");
            }
            let seed = cleaned.substring(0, 16);
            let cipherTextBase64 = cleaned.substring(16);  // 剩余的密文（Base64 格式）
            let keyIv = seed.split('').reverse().join('');
            log("seed: " + seed + ", keyIv: " + keyIv);

            // 7. 将密文部分再次 Base64 解码，得到二进制数据
            let ciphertextWordArray;
            if (typeof CryptoJS !== 'undefined' && CryptoJS.enc && CryptoJS.enc.Base64) {
                ciphertextWordArray = CryptoJS.enc.Base64.parse(cipherTextBase64);
            } else {
                // 降级方案：使用 atob 然后转为 Latin1 字符串再解析（不推荐，但保留兼容）
                let binaryStr = atob(cipherTextBase64);
                ciphertextWordArray = CryptoJS.enc.Latin1.parse(binaryStr);
            }
            log("密文 Base64 解码完成，长度: " + (ciphertextWordArray.sigBytes || 0));

            // 8. AES-CBC-Pkcs7 解密
            if (typeof CryptoJS === 'undefined') {
                throw new Error("CryptoJS 未定义，请检查运行环境");
            }
            let key = CryptoJS.enc.Utf8.parse(keyIv);
            let iv = CryptoJS.enc.Utf8.parse(keyIv);
            let decrypted = CryptoJS.AES.decrypt(
                { ciphertext: ciphertextWordArray },
                key,
                { iv: iv, mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7 }
            );
            let playUrl = decrypted.toString(CryptoJS.enc.Utf8);
            // 如果结果包含乱码，尝试 Latin1
            if (!playUrl || playUrl.indexOf('�') !== -1) {
                playUrl = decrypted.toString(CryptoJS.enc.Latin1);
            }
            log("解密后的播放地址: " + playUrl);

            // 9. 验证并返回
            if (playUrl && playUrl.startsWith('http')) {
                input = {
                    header: { 'User-Agent': '' },
                    parse: 0,
                    url: playUrl,
                    jx: 0,
                    danmaku: ' '
                };
            } else {
                throw new Error("解密结果不是有效 URL: " + playUrl);
            }
        } catch (e) {
            log("解析异常: " + e.message);
            // 回退：使用原链接 + 内置解析
            input = {
                header: { 'User-Agent': '' },
                parse: 0,
                url: input.split("?")[0],
                jx: 1,
                danmaku: ' '
            };
        }
    }),
    推荐: '.list_item;img&&alt;img&&src;a&&Text;a&&data-float',
    一级: '.list_item;img&&alt;img&&src;a&&Text;a&&data-float',
    二级: $js.toString(() => {
        VOD = {};
        let d = [];
        let video_list = [];
        let video_lists = [];
        let list = [];
        let QZOutputJson;
        let html = fetch(input, fetch_params);
        let sourceId = /get_playsource/.test(input) ? input.match(/id=(\d*?)&/)[1] : input.split("cid=")[1];
        let cid = sourceId;
        let detailUrl = "https://v.%71%71.com/detail/m/" + cid + ".html";
        log("详情页:" + detailUrl);
        pdfh = jsp.pdfh;
        pd = jsp.pd;
        try {
            let json = JSON.parse(html);
            VOD = {
                vod_url: input,
                vod_name: json.c.title,
                type_name: json.typ.join(","),
                vod_actor: json.nam.join(","),
                vod_year: json.c.year,
                vod_content: json.c.description,
                vod_remarks: json.rec,
                vod_pic: urljoin2(input, json.c.pic)
            }
        } catch (e) {
            log("解析片名海报等基础信息发生错误:" + e.message)
        }
        if (/get_playsource/.test(input)) {
            eval(html);
            let indexList = QZOutputJson.PlaylistItem.indexList;
            indexList.forEach(function(it) {
                let dataUrl = "https://s.video.qq.com/get_playsource?id=" + sourceId + "&plat=2&type=4&data_type=3&range=" + it + "&video_type=10&plname=qq&otype=json";
                eval(fetch(dataUrl, fetch_params));
                let vdata = QZOutputJson.PlaylistItem.videoPlayList;
                vdata.forEach(function(item) {
                    d.push({
                        title: item.title,
                        pic_url: item.pic,
                        desc: item.episode_number + "\t\t\t播放量：" + item.thirdLine,
                        url: item.playUrl
                    })
                });
                video_lists = video_lists.concat(vdata)
            })
        } else {
            let json = JSON.parse(html);
            video_lists = json.c.video_ids;
            let url = "https://v.qq.com/x/cover/" + sourceId + ".html";
            if (video_lists.length === 1) {
                let vid = video_lists[0];
                url = "https://v.qq.com/x/cover/" + cid + "/" + vid + ".html";
                d.push({
                    title: "在线播放",
                    url: url
                })
            } else if (video_lists.length > 1) {
                for (let i = 0; i < video_lists.length; i += 30) {
                    video_list.push(video_lists.slice(i, i + 30))
                }
                video_list.forEach(function(it, idex) {
                    let o_url = "https://union.video.qq.com/fcgi-bin/data?otype=json&tid=1804&appid=20001238&appkey=6c03bbe9658448a4&union_platform=1&idlist=" + it.join(",");
                    let o_html = fetch(o_url, fetch_params);
                    eval(o_html);
                    QZOutputJson.results.forEach(function(it1) {
                        it1 = it1.fields;
                        let url = "https://v.qq.com/x/cover/" + cid + "/" + it1.vid + ".html";
                        d.push({
                            title: it1.title,
                            pic_url: it1.pic160x90.replace("/160", ""),
                            desc: it1.video_checkup_time,
                            url: url,
                            type: it1.category_map && it1.category_map.length > 1 ? it1.category_map[1] : ""
                        })
                    })
                })
            }
        }
        let yg = d.filter(function(it) {
            return it.type && it.type !== "正片"
        });
        let zp = d.filter(function(it) {
            return !(it.type && it.type !== "正片")
        });
        VOD.vod_play_from = yg.length < 1 ? "qq" : "qq$$$预告及花絮";
        VOD.vod_play_url = yg.length < 1 ? d.map(function(it) {
            return it.title + "$" + it.url
        }).join("#") : [zp, yg].map(function(it) {
            return it.map(function(its) {
                return its.title + "$" + its.url
            }).join("#")
        }).join("$$$");
    }),
    搜索: $js.toString(() => {
        let d = [];
        let mame = (input.split("/")[3]);
        let html = vod1(input.split("/")[3]);
        let json = JSON.parse(html);

        let list = json.data.normalList.itemList;
        console.log(json);
        log(list[0].videoInfo.title);
        list.forEach(function(it) {
            try {
                if (it.doc.id.length > 11) {
                    d.push({
                        title: it.videoInfo.title,
                        img: it.videoInfo.imgUrl,
                        url: it.doc.id,
                    });
                }
            } catch {

            }

        });
        let list2 = json.data.areaBoxList[0].itemList;
        list2.forEach(function(it) {
            try {
                if (it.doc.id.length > 11 && it.videoInfo.title.match(mame)) {
                    d.push({
                        title: it.videoInfo.title,
                        img: it.videoInfo.imgUrl,
                        url: it.doc.id,
                    });
                }
            } catch {

            }

        });
        setResult(d);
    })
}