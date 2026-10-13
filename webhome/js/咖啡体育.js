// @name 咖啡直播
// @author modified by ChatGPT
// @description 咖啡直播体育赛事直播 + 录像回放
// @version 1.3.0

//const host = 'https://kafeizhibo.com';
const host = 'https://kafeizhibo.cc';
const headers = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': host + '/pc/live',
    'Origin': host
};

// ========== 工具函数 ==========

function fixUrl(path) {
    if (!path) return '';
    const value = String(path).trim();
    if (!value) return '';
    if (value.startsWith('http')) return value;
    if (value.startsWith('//')) return 'https:' + value;
    return host + (value.startsWith('/') ? '' : '/') + value;
}

function safeText(value, fallback = '') {
    if (value === undefined || value === null) return fallback;
    return String(value).trim();
}

function safeNumber(value, fallback = '') {
    if (value === undefined || value === null || value === '') return fallback;
    return String(value);
}

function cleanName(name) {
    return safeText(name, '播放').replace(/[$#]/g, ' ').trim() || '播放';
}

function cleanPlayUrl(url) {
    return safeText(url).replace(/#/g, '%23');
}

function buildQuery(params = {}) {
    const arr = [];
    for (const [key, value] of Object.entries(params)) {
        if (value === undefined || value === null || value === '') continue;
        arr.push(`${encodeURIComponent(key)}=${encodeURIComponent(value)}`);
    }
    return arr.join('&');
}

function getContent(res) {
    if (!res) return '';
    if (typeof res === 'string') return res;
    if (typeof res.content === 'string') return res.content;
    if (typeof res.body === 'string') return res.body;
    if (typeof res.data === 'string') return res.data;
    if (typeof res.content === 'object') return JSON.stringify(res.content);
    if (typeof res.body === 'object') return JSON.stringify(res.body);
    if (typeof res.data === 'object') return JSON.stringify(res.data);
    return '';
}

async function requestText(url, params = {}, extraHeaders = {}) {
    const query = buildQuery(params);
    const finalUrl = query ? `${url}${url.includes('?') ? '&' : '?'}${query}` : url;
    const r = await req(finalUrl, {
        headers: Object.assign({}, headers, extraHeaders)
    });
    return getContent(r);
}

async function requestJson(url, params = {}, extraHeaders = {}) {
    const text = await requestText(url, params, extraHeaders);
    if (!text) return null;
    return JSON.parse(text);
}

async function requestJsonSafe(url, params = {}, extraHeaders = {}) {
    try {
        return await requestJson(url, params, extraHeaders);
    } catch (e) {
        return null;
    }
}

async function requestTextSafe(url, params = {}, extraHeaders = {}) {
    try {
        return await requestText(url, params, extraHeaders);
    } catch (e) {
        return '';
    }
}

function isOk(data) {
    return data && (
        data.code === 200 ||
        data.code === '200' ||
        data.status === 200 ||
        data.status === '200' ||
        data.success === true ||
        data.data !== undefined
    );
}

function pick(obj, keys = [], fallback = '') {
    if (!obj || typeof obj !== 'object') return fallback;
    for (const key of keys) {
        if (obj[key] !== undefined && obj[key] !== null && obj[key] !== '') {
            return obj[key];
        }
    }
    return fallback;
}

function todayString() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function uniqueByVodId(list = []) {
    const seen = new Set();
    const result = [];
    list.forEach(item => {
        if (!item || !item.vod_id) return;
        const key = String(item.vod_id);
        if (seen.has(key)) return;
        seen.add(key);
        result.push(item);
    });
    return result;
}

function encodeLiveId(item = {}) {
    try {
        return 'live|' + encodeURIComponent(JSON.stringify(item));
    } catch (e) {
        return 'live|' + encodeURIComponent(JSON.stringify({
            id: pick(item, ['id', 'match_id', 'matchId', 'room_id', 'roomId'])
        }));
    }
}

function decodeLiveId(id) {
    const raw = String(id || '');
    if (!raw.startsWith('live|')) return null;
    try {
        return JSON.parse(decodeURIComponent(raw.slice(5)));
    } catch (e) {
        return null;
    }
}

function isMediaUrl(url) {
    const value = safeText(url).toLowerCase();
    if (!value) return false;
    return value.includes('.m3u8') ||
        value.includes('m3u8?') ||
        value.includes('.flv') ||
        value.includes('flv?') ||
        value.includes('.mp4') ||
        value.includes('mp4?') ||
        value.startsWith('rtmp') ||
        value.startsWith('rtsp') ||
        value.startsWith('p2p') ||
        value.startsWith('mitv');
}

function isLivePageUrl(url) {
    const value = safeText(url).toLowerCase();
    return value.includes('/pc/room/') || value.includes('/room/');
}

function normalizeTypeValue(tid) {
    const raw = String(tid || '');
    if (raw === 'live') return '';
    if (raw === 'live_hot') return '';
    if (raw === 'live_football') return '1';
    if (raw === 'live_basketball') return '2';
    if (raw === 'live_tennis') return '3';
    if (raw === 'live_billiards') return '4';
    if (raw === 'live_nba') return '';
    if (raw === 'all') return '';
    if (raw === 'football') return '1';
    if (raw === 'basketball') return '2';
    if (raw === 'nba') return '';
    return raw;
}

function joinTitle(home, away, league) {
    const h = safeText(home, '');
    const a = safeText(away, '');
    const l = safeText(league, '赛事');

    if (h && a) return `${l} ${h} vs ${a}`;
    if (h) return `${l} ${h}`;
    if (a) return `${l} ${a}`;
    return l;
}

// ========== 分类配置 ==========

const classes = [
    { type_id: 'live', type_name: '全部直播' },
    { type_id: 'live_hot', type_name: '热门直播' },
    { type_id: 'live_football', type_name: '足球直播' },
    { type_id: 'live_basketball', type_name: '篮球直播' },
    { type_id: 'live_nba', type_name: 'NBA直播' },
    { type_id: 'live_tennis', type_name: '网球直播' },
    { type_id: 'live_billiards', type_name: '台球直播' },
    { type_id: 'all', type_name: '全部录像' },
    { type_id: 'football', type_name: '足球录像' },
    { type_id: 'basketball', type_name: '篮球录像' },
    { type_id: 'nba', type_name: 'NBA录像' }
];

const leagueAll = [
    { n: '全部', v: '' },
    { n: 'NBA', v: 'NBA' },
    { n: 'CBA', v: 'CBA' },
    { n: '英超', v: '英超' },
    { n: '西甲', v: '西甲' },
    { n: '意甲', v: '意甲' },
    { n: '德甲', v: '德甲' },
    { n: '法甲', v: '法甲' },
    { n: '欧冠', v: '欧冠' },
    { n: '中超', v: '中超' },
    { n: '中乙', v: '中乙' }
];

const filters = {
    live: [{ key: 'league', name: '联赛', value: leagueAll }],
    live_hot: [{ key: 'league', name: '联赛', value: leagueAll }],
    live_football: [{ key: 'league', name: '联赛', value: leagueAll }],
    live_basketball: [{ key: 'league', name: '联赛', value: leagueAll }],
    live_nba: [{ key: 'league', name: '联赛', value: [{ n: 'NBA', v: 'NBA' }] }],
    all: [{ key: 'league', name: '联赛', value: leagueAll }],
    football: [{ key: 'league', name: '联赛', value: leagueAll }],
    basketball: [{ key: 'league', name: '联赛', value: leagueAll }],
    nba: [{ key: 'league', name: '联赛', value: [{ n: 'NBA', v: 'NBA' }] }]
};

// ========== 通用数据提取 ==========

function findBestArray(node, depth = 0) {
    if (!node || depth > 6) return [];
    if (Array.isArray(node)) return node;
    if (typeof node !== 'object') return [];

    const keys = [
        'list', 'items', 'rows', 'data', 'records',
        'matches', 'matchList', 'schedules', 'scheduleList',
        'lives', 'liveList', 'rooms', 'roomList',
        'events', 'result'
    ];

    for (const key of keys) {
        if (Array.isArray(node[key])) return node[key];
        const arr = findBestArray(node[key], depth + 1);
        if (arr.length) return arr;
    }

    for (const value of Object.values(node)) {
        const arr = findBestArray(value, depth + 1);
        if (arr.length) return arr;
    }

    return [];
}

function getDataArray(data) {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    if (isOk(data)) return findBestArray(data.data);
    return findBestArray(data);
}

function getLeagueText(item) {
    return safeText(pick(item, [
        'league_name', 'leagueName', 'league',
        'competition_name', 'competitionName',
        'event_name', 'eventName',
        'match_type', 'matchType'
    ]), '');
}

function getSportTypeText(item) {
    return safeText(pick(item, [
        'type', 'type_id', 'typeId',
        'sport_type', 'sportType',
        'category_id', 'categoryId',
        'sport', 'category'
    ]), '');
}

function liveTitleText(item = {}) {
    const title = safeText(pick(item, ['title', 'name', 'match_name', 'matchName'], ''));
    const league = getLeagueText(item);
    const home = safeText(pick(item, ['home_team', 'homeTeam', 'home_name', 'homeName', 'team1', 'home'], ''));
    const away = safeText(pick(item, ['away_team', 'awayTeam', 'away_name', 'awayName', 'team2', 'away'], ''));
    return [title, league, home, away].filter(Boolean).join(' ');
}

function isLiveItem(item) {
    if (!item || typeof item !== 'object') return false;

    const status = safeText(pick(item, [
        'status', 'match_status', 'matchStatus',
        'state', 'live_status', 'liveStatus',
        'status_text', 'statusText'
    ])).toLowerCase();

    const liveFlag = pick(item, ['is_live', 'isLive', 'live', 'living'], '');
    const hasLiveFlag = liveFlag === true || String(liveFlag) === '1';

    const hasRoom = !!pick(item, [
        'room_id', 'roomId', 'roomid',
        'live_room_id', 'liveRoomId',
        'room_url', 'roomUrl'
    ], '');

    const hasPlayUrl = !!firstPlayableUrl(item);

    if (hasLiveFlag || hasPlayUrl || hasRoom) return true;
    if (status.includes('live')) return true;
    if (status.includes('正在')) return true;
    if (status.includes('直播')) return true;
    if (status === '1' || status === '2') return true;

    return false;
}

function filterLiveItems(items = [], league = '', type = '', isHot = false) {
    const leagueText = safeText(league).toLowerCase();
    const typeText = safeText(type);

    return items.filter(item => {
        if (!item || typeof item !== 'object') return false;
        if (!isLiveItem(item)) return false;

        const title = liveTitleText(item);
        const titleLower = title.toLowerCase();
        const itemLeague = getLeagueText(item).toLowerCase();
        const itemType = getSportTypeText(item);

        if (leagueText) {
            if (!itemLeague.includes(leagueText) && !titleLower.includes(leagueText)) {
                return false;
            }
        }

        if (isHot) {
            const hotValue = pick(item, ['is_hot', 'isHot', 'hot', 'recommend', 'is_recommend'], '');
            const hotOk = hotValue === true || String(hotValue) === '1' || title.includes('热门');
            if (!hotOk) return false;
        }

        if (typeText === '1') {
            const ok = itemType === '1' ||
                itemType.includes('足球') ||
                title.includes('足球') ||
                title.includes('英超') ||
                title.includes('西甲') ||
                title.includes('意甲') ||
                title.includes('德甲') ||
                title.includes('法甲') ||
                title.includes('欧冠') ||
                title.includes('中超') ||
                title.includes('中乙');
            if (!ok) return false;
        }

        if (typeText === '2') {
            const ok = itemType === '2' ||
                itemType.includes('篮球') ||
                title.includes('篮球') ||
                title.includes('NBA') ||
                title.includes('CBA') ||
                title.includes('WNBA');
            if (!ok) return false;
        }

        if (typeText === '3') {
            const ok = itemType === '3' || itemType.includes('网球') || title.includes('网球');
            if (!ok) return false;
        }

        if (typeText === '4') {
            const ok = itemType === '4' || itemType.includes('台球') || title.includes('台球');
            if (!ok) return false;
        }

        return true;
    });
}

// ========== 直播接口 ==========

async function fetchLiveByApi(page = 1, size = 30, league = '', type = '', isHot = false) {
    const date = todayString();

    const urls = [
        `${host}/api/v1/live`,
        `${host}/api/v1/lives`,
        `${host}/api/v1/live/list`,
        `${host}/api/v1/lives/list`,
        `${host}/api/v1/live/matches`,
        `${host}/api/v1/matches/live`,
        `${host}/api/v1/rooms`,
        `${host}/api/v1/room/list`,
        `${host}/api/v1/schedule`,
        `${host}/api/v1/schedules`,
        `${host}/api/v1/schedule/today`,
        `${host}/api/v1/matches`
    ];

    const paramList = [
        { page, size, limit: size, league, type, date },
        { page, pageSize: size, league, type, date },
        { page, per_page: size, league, type, date },
        { page, size, league, type, status: 'live' },
        { page, size, league, type, live: 1 },
        { page, size, league, type, is_live: 1 }
    ];

    for (const url of urls) {
        for (const params of paramList) {
            const cleanParams = {};
            Object.keys(params).forEach(key => {
                if (params[key] !== undefined && params[key] !== null && params[key] !== '') {
                    cleanParams[key] = params[key];
                }
            });

            const data = await requestJsonSafe(url, cleanParams, {
                Referer: host + '/pc/live'
            });

            const arr = getDataArray(data);
            if (!arr.length) continue;

            const filtered = filterLiveItems(arr, league, type, isHot);
            if (filtered.length) return filtered.slice(0, size);
        }
    }

    return [];
}

function parseLiveCardsFromHtml(html = '') {
    const text = safeText(html);
    if (!text || text === '加载中...') return [];

    const list = [];
    const roomReg = /\/pc\/room\/(\d+)/g;
    let m;

    while ((m = roomReg.exec(text)) !== null) {
        const roomId = m[1];
        const start = Math.max(0, m.index - 800);
        const end = Math.min(text.length, m.index + 800);
        const block = text.slice(start, end);

        const titleMatch = block.match(/([\u4e00-\u9fa5A-Za-z0-9\s]+?\s+vs\s+[\u4e00-\u9fa5A-Za-z0-9\s]+)/i);
        const title = titleMatch ? titleMatch[1].replace(/\s+/g, ' ').trim() : `直播房间 ${roomId}`;

        const imgMatch = block.match(/https?:\/\/[^"'<>]+?\.(?:jpg|jpeg|png|webp)/i);
        const pic = imgMatch ? imgMatch[0] : '';

        list.push({
            id: roomId,
            room_id: roomId,
            room_url: `${host}/pc/room/${roomId}`,
            title: title,
            cover: pic,
            status_text: 'LIVE',
            is_live: 1
        });
    }

    return list;
}

async function fetchLiveByPage(page = 1, size = 30, league = '', type = '', isHot = false) {
    const html = await requestTextSafe(`${host}/pc/live`, {}, {
        Referer: host + '/pc/live',
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    });

    const arr = parseLiveCardsFromHtml(html);
    return filterLiveItems(arr, league, type, isHot).slice(0, size);
}

async function fetchLiveMatches(page = 1, size = 30, league = '', type = '', isHot = false) {
    let list = await fetchLiveByApi(page, size, league, type, isHot);

    if (!list.length) {
        list = await fetchLiveByPage(page, size, league, type, isHot);
    }

    return list;
}

async function fetchLiveDetail(roomOrMatchId) {
    const id = safeText(roomOrMatchId);
    if (!id) return null;

    const urls = [
        `${host}/api/v1/room/${encodeURIComponent(id)}`,
        `${host}/api/v1/rooms/${encodeURIComponent(id)}`,
        `${host}/api/v1/live/${encodeURIComponent(id)}`,
        `${host}/api/v1/lives/${encodeURIComponent(id)}`,
        `${host}/api/v1/match/${encodeURIComponent(id)}/live`,
        `${host}/api/v1/match/${encodeURIComponent(id)}/streams`,
        `${host}/api/v1/matches/${encodeURIComponent(id)}`,
        `${host}/api/v1/match/${encodeURIComponent(id)}`
    ];

    for (const url of urls) {
        const data = await requestJsonSafe(url, {}, {
            Referer: `${host}/pc/room/${encodeURIComponent(id)}`
        });

        if (!data) continue;
        if (isOk(data)) return data.data;
        if (typeof data === 'object') return data;
    }

    return null;
}

// ========== 录像接口 ==========

async function fetchRecordings(page = 1, size = 30, league = '', type = '') {
    const params = { page, size };

    if (league) {
        params.league = league;
    } else if (type && type !== 'all' && type !== 'nba') {
        params.type = type;
    }

    return await requestJsonSafe(`${host}/api/v1/recordings`, params, {
        Referer: host + '/pc/replay'
    });
}

async function fetchMatchRecordings(matchId) {
    return await requestJsonSafe(`${host}/api/v1/match/${encodeURIComponent(matchId)}/recordings`, {}, {
        Referer: host + '/pc/replay'
    });
}

// ========== 播放源提取 ==========

function addPlayable(arr, name, url) {
    const value = cleanPlayUrl(url);
    if (!value) return;
    const line = `${cleanName(name)}$${value}`;
    if (arr.indexOf(line) >= 0) return;
    arr.push(line);
}

function collectPlayableLinks(node, prefix = '线路', arr = [], depth = 0) {
    if (!node || depth > 7) return arr;

    if (typeof node === 'string') {
        if (isMediaUrl(node)) {
            addPlayable(arr, prefix, node);
        }
        return arr;
    }

    if (Array.isArray(node)) {
        node.forEach((item, idx) => {
            collectPlayableLinks(item, `${prefix}${idx + 1}`, arr, depth + 1);
        });
        return arr;
    }

    if (typeof node !== 'object') return arr;

    const name = cleanName(pick(node, [
        'name', 'title', 'line', 'line_name', 'lineName',
        'source_name', 'sourceName', 'quality', 'label'
    ], prefix));

    const directKeys = [
        'play_url', 'playUrl',
        'video_url', 'videoUrl',
        'stream_url', 'streamUrl',
        'live_url', 'liveUrl',
        'm3u8', 'flv', 'hls',
        'url', 'src', 'link',
        'hd', 'sd', 'uhd',
        'source', 'stream'
    ];

    directKeys.forEach(key => {
        const value = node[key];
        if (typeof value === 'string' && isMediaUrl(value)) {
            addPlayable(arr, name, value);
        }
    });

    Object.keys(node).forEach(key => {
        if ([
            'cover', 'cover_image', 'coverImage',
            'logo', 'home_team_logo', 'away_team_logo',
            'homeLogo', 'awayLogo', 'avatar'
        ].includes(key)) {
            return;
        }
        collectPlayableLinks(node[key], name, arr, depth + 1);
    });

    return arr;
}

function firstPlayableUrl(item) {
    const arr = collectPlayableLinks(item, '线路', [], 0);
    if (!arr.length) return '';
    const parts = arr[0].split('$');
    return parts.length > 1 ? parts.slice(1).join('$') : '';
}

function buildLivePlayLine(liveItem = {}, detailData = null) {
    const arr = [];

    collectPlayableLinks(liveItem, '线路', arr);
    collectPlayableLinks(detailData, '线路', arr);

    if (!arr.length) {
        const roomId = safeText(pick(liveItem, [
            '_live_room_id',
            'room_id', 'roomId', 'roomid',
            'live_room_id', 'liveRoomId',
            'id', 'match_id', 'matchId'
        ], ''));

        const pageUrl = safeText(pick(liveItem, [
            '_live_page_url',
            'room_url', 'roomUrl',
            'page_url', 'pageUrl',
            'link'
        ], ''));

        const finalPage = pageUrl || (roomId ? `${host}/pc/room/${encodeURIComponent(roomId)}` : `${host}/pc/live`);
        addPlayable(arr, '打开直播间', fixUrl(finalPage));
    }

    return arr.join('#');
}

function buildEpisodeLine(items = [], prefix = '录像') {
    const arr = [];
    if (!Array.isArray(items)) return '';

    items.forEach((rec, idx) => {
        const url = cleanPlayUrl(pick(rec, [
            'video_url', 'videoUrl',
            'url',
            'play_url', 'playUrl'
        ], ''));

        if (!url) return;

        const name = cleanName(pick(rec, ['title', 'name'], `${prefix}${idx + 1}`));
        arr.push(`${name}$${url}`);
    });

    return arr.join('#');
}

// ========== 列表解析 ==========

function parseLiveList(items = []) {
    if (!Array.isArray(items)) return [];

    return items.map(item => {
        const titleRaw = safeText(pick(item, ['title', 'name', 'match_name', 'matchName'], ''));
        const league = safeText(getLeagueText(item), '直播');

        const home = safeText(pick(item, [
            'home_team', 'homeTeam',
            'home_name', 'homeName',
            'team1', 'home'
        ], ''));

        const away = safeText(pick(item, [
            'away_team', 'awayTeam',
            'away_name', 'awayName',
            'team2', 'away'
        ], ''));

        const title = titleRaw || joinTitle(home, away, league);

        const time = safeText(pick(item, [
            'start_time', 'startTime',
            'match_time', 'matchTime',
            'time'
        ], '正在直播'));

        const roomId = safeText(pick(item, [
            'room_id', 'roomId', 'roomid',
            'live_room_id', 'liveRoomId',
            'id', 'match_id', 'matchId'
        ], ''));

        const status = safeText(pick(item, [
            'status_text', 'statusText',
            'status', 'match_status', 'matchStatus',
            'state'
        ], 'LIVE'));

        let pic = pick(item, [
            'cover_image', 'coverImage',
            'cover', 'thumb', 'thumbnail',
            'home_team_logo', 'homeLogo',
            'away_team_logo', 'awayLogo',
            'logo', 'pic'
        ], '');

        pic = fixUrl(pic);

        const liveItem = Object.assign({}, item, {
            _live_title: title,
            _live_league: league,
            _live_time: time,
            _live_room_id: roomId,
            _live_page_url: roomId ? `${host}/pc/room/${encodeURIComponent(roomId)}` : fixUrl(pick(item, ['room_url', 'roomUrl', 'link'], ''))
        });

        return {
            vod_id: encodeLiveId(liveItem),
            vod_name: title,
            vod_pic: pic,
            vod_remarks: `🔴 ${status || 'LIVE'} | ${time}`
        };
    }).filter(v => v.vod_id && v.vod_name);
}

function parseVideoList(items = [], showScore = true) {
    if (!Array.isArray(items)) return [];

    return items.map(item => {
        const home = safeText(pick(item, [
            'home_team', 'homeTeam',
            'home_name', 'homeName',
            'team1', 'home'
        ], '主队'));

        const away = safeText(pick(item, [
            'away_team', 'awayTeam',
            'away_name', 'awayName',
            'team2', 'away'
        ], '客队'));

        const league = safeText(pick(item, [
            'league_name', 'leagueName',
            'league',
            'competition_name', 'competitionName'
        ], '赛事'));

        const title = joinTitle(home, away, league);

        const homeScore = safeNumber(pick(item, ['home_score', 'homeScore', 'score_home'], '-'));
        const awayScore = safeNumber(pick(item, ['away_score', 'awayScore', 'score_away'], '-'));
        const score = `${homeScore} - ${awayScore}`;

        const time = safeText(pick(item, [
            'start_time', 'startTime',
            'match_time', 'matchTime',
            'time'
        ], ''));

        const count = safeNumber(pick(item, [
            'recording_count', 'recordingCount',
            'replay_count', 'video_count'
        ], '0'));

        let pic = pick(item, [
            'cover_image', 'coverImage',
            'cover',
            'home_team_logo', 'homeLogo',
            'away_team_logo', 'awayLogo',
            'logo', 'pic'
        ], '');

        pic = fixUrl(pic);

        if (pic.includes('default_cover')) {
            pic = fixUrl(pick(item, [
                'home_team_logo', 'homeLogo',
                'away_team_logo', 'awayLogo',
                'logo'
            ], ''));
        }

        return {
            vod_id: String(pick(item, ['match_id', 'matchId', 'id'], '')),
            vod_name: title,
            vod_pic: pic,
            vod_remarks: showScore ? `${score} | ${time} | ${count}个录像` : time
        };
    }).filter(v => v.vod_id && v.vod_name);
}

// ========== 壳子接口 ==========

async function init(cfg) {
    return JSON.stringify({});
}

async function home(filter) {
    try {
        return JSON.stringify({
            class: classes,
            filters: filters
        });
    } catch (e) {
        return JSON.stringify({ class: [] });
    }
}

async function homeVod() {
    try {
        const liveItems = await fetchLiveMatches(1, 30, '', '', false);
        const liveList = parseLiveList(liveItems);

        const data = await fetchRecordings(1, 20);
        const replayList = isOk(data) ? parseVideoList(getDataArray(data)) : [];

        return JSON.stringify({
            list: uniqueByVodId([].concat(liveList, replayList))
        });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function category(tid, pg, filter, extend = {}) {
    try {
        const page = parseInt(pg) || 1;
        const size = 30;
        let league = '';
        let type = normalizeTypeValue(tid);
        const isHot = String(tid || '') === 'live_hot';

        if (extend && extend.league) {
            league = extend.league;
        } else if (String(tid || '') === 'live_nba' || String(tid || '') === 'nba') {
            league = 'NBA';
        }

        if (String(tid || '').startsWith('live')) {
            const liveItems = await fetchLiveMatches(page, size, league, type, isHot);
            const list = parseLiveList(liveItems);
            const pagecount = list.length >= size ? page + 1 : page;

            return JSON.stringify({
                page: page,
                pagecount: pagecount,
                limit: size,
                total: list.length,
                list: list
            });
        }

        const data = await fetchRecordings(page, size, league, type);
        const list = isOk(data) ? parseVideoList(getDataArray(data)) : [];
        const pagecount = list.length >= size ? page + 1 : page;

        return JSON.stringify({
            page: page,
            pagecount: pagecount,
            limit: size,
            total: list.length,
            list: list
        });
    } catch (e) {
        return JSON.stringify({
            page: parseInt(pg) || 1,
            pagecount: 0,
            limit: 0,
            total: 0,
            list: []
        });
    }
}

async function detail(id) {
    try {
        const rawId = String(id || '').trim();
        if (!rawId) return JSON.stringify({ list: [] });

        const liveItem = decodeLiveId(rawId);

        if (liveItem) {
            const roomId = safeText(pick(liveItem, [
                '_live_room_id',
                'room_id', 'roomId', 'roomid',
                'live_room_id', 'liveRoomId',
                'id', 'match_id', 'matchId'
            ], ''));

            const detailData = roomId ? await fetchLiveDetail(roomId) : null;

            const title = safeText(pick(liveItem, [
                '_live_title',
                'title', 'name', 'match_name', 'matchName'
            ], '正在直播'));

            const league = safeText(pick(liveItem, [
                '_live_league',
                'league_name', 'leagueName',
                'league',
                'competition_name', 'competitionName'
            ], '直播'));

            const time = safeText(pick(liveItem, [
                '_live_time',
                'start_time', 'startTime',
                'match_time', 'matchTime',
                'time'
            ], '正在直播'));

            const pic = fixUrl(pick(liveItem, [
                'cover_image', 'coverImage',
                'cover', 'thumb', 'thumbnail',
                'home_team_logo', 'homeLogo',
                'away_team_logo', 'awayLogo',
                'logo', 'pic'
            ], ''));

            const playLine = buildLivePlayLine(liveItem, detailData);

            const vodInfo = {
                vod_id: rawId,
                vod_name: title,
                vod_pic: pic,
                vod_remarks: '正在直播',
                vod_content: `${league} ${title}，比赛时间：${time}`,
                vod_play_from: playLine ? '正在直播' : '',
                vod_play_url: playLine,
                type_name: league
            };

            return JSON.stringify({ list: [vodInfo] });
        }

        const matchId = rawId;
        const data = await fetchMatchRecordings(matchId);
        if (!isOk(data)) return JSON.stringify({ list: [] });

        const root = data.data || {};
        const match = root.match || {};
        const replays = root.replays || [];
        const highlights = root.highlights || [];

        const home = safeText(pick(match, [
            'home_team', 'homeTeam',
            'home_name', 'homeName',
            'team1', 'home'
        ], '主队'));

        const away = safeText(pick(match, [
            'away_team', 'awayTeam',
            'away_name', 'awayName',
            'team2', 'away'
        ], '客队'));

        const league = safeText(pick(match, [
            'league_name', 'leagueName',
            'league',
            'competition_name', 'competitionName'
        ], '赛事'));

        const title = joinTitle(home, away, league);

        const score = `${safeNumber(pick(match, ['home_score', 'homeScore', 'score_home'], '-'))} - ${safeNumber(pick(match, ['away_score', 'awayScore', 'score_away'], '-'))}`;

        const time = safeText(pick(match, [
            'start_time', 'startTime',
            'match_time', 'matchTime',
            'time'
        ], ''));

        const round = safeText(pick(match, ['match_round', 'matchRound', 'round'], ''));

        const playFrom = [];
        const playUrls = [];

        const replayLine = buildEpisodeLine(replays, '录像');
        if (replayLine) {
            playFrom.push('全场录像');
            playUrls.push(replayLine);
        }

        const highlightLine = buildEpisodeLine(highlights, '集锦');
        if (highlightLine) {
            playFrom.push('比赛集锦');
            playUrls.push(highlightLine);
        }

        const pic = fixUrl(pick(match, [
            'cover_image', 'coverImage',
            'cover',
            'home_team_logo', 'homeLogo',
            'away_team_logo', 'awayLogo',
            'logo', 'pic'
        ], ''));

        const vodInfo = {
            vod_id: matchId,
            vod_name: title,
            vod_pic: pic,
            vod_remarks: score,
            vod_content: `${league} ${round} ${home} vs ${away}，比分 ${score}，比赛时间：${time}`,
            vod_play_from: playFrom.join('$$$'),
            vod_play_url: playUrls.join('$$$'),
            type_name: league
        };

        return JSON.stringify({ list: [vodInfo] });
    } catch (e) {
        return JSON.stringify({ list: [] });
    }
}

async function search(wd, quick, pg = 1) {
    try {
        const keyword = safeText(wd).toLowerCase();
        if (!keyword) {
            return JSON.stringify({
                page: 1,
                pagecount: 0,
                list: []
            });
        }

        const liveItems = await fetchLiveMatches(1, 100);
        const filteredLive = liveItems.filter(item => {
            return liveTitleText(item).toLowerCase().includes(keyword);
        });
        const liveList = parseLiveList(filteredLive);

        const data = await fetchRecordings(1, 100);
        let replayList = [];

        if (isOk(data)) {
            const arr = getDataArray(data);
            const filteredReplay = arr.filter(item => {
                const title = [
                    pick(item, ['title', 'name', 'match_name', 'matchName'], ''),
                    pick(item, ['home_team', 'homeTeam', 'home_name', 'homeName'], ''),
                    pick(item, ['away_team', 'awayTeam', 'away_name', 'awayName'], ''),
                    pick(item, ['league_name', 'leagueName', 'league'], '')
                ].join(' ').toLowerCase();

                return title.includes(keyword);
            });

            replayList = parseVideoList(filteredReplay);
        }

        const list = uniqueByVodId([].concat(liveList, replayList));

        return JSON.stringify({
            page: parseInt(pg) || 1,
            pagecount: 1,
            limit: list.length,
            total: list.length,
            list: list
        });
    } catch (e) {
        return JSON.stringify({
            page: parseInt(pg) || 1,
            pagecount: 0,
            list: []
        });
    }
}

async function play(flag, id, flags) {
    try {
        const url = cleanPlayUrl(id);
        const needParse = isLivePageUrl(url) && !isMediaUrl(url);

        return JSON.stringify({
            parse: needParse ? 1 : 0,
            url: url,
            header: {
                'User-Agent': headers['User-Agent'],
                'Referer': isLivePageUrl(url) ? host + '/pc/live' : host,
                'Origin': host
            }
        });
    } catch (e) {
        return JSON.stringify({
            parse: 0,
            url: id || ''
        });
    }
}

export default {
    init: init,
    home: home,
    homeVod: homeVod,
    category: category,
    detail: detail,
    search: search,
    play: play
};