/*
@header({
  searchable: 0,
  filterable: 1,
  quickSearch: 0,
  title: '蜘蛛直播[体]',
  author: 'OpenClaw',
  lang: 'cat'
})
*/

let host = 'https://zzzbvip429.com';
let apiHost = 'https://uwnyqabbrnve9xkwrhb01.k8v4dh4.app';
let businessApi = apiHost + '/business';
const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';

function makeHeaders(extra = {}) {
  return {
    'User-Agent': ua,
    'Referer': host + '/',
    'Origin': host,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/json;charset=UTF-8',
    'DeviceInfo': 'web,openclaw',
    ...extra
  };
}

function safeJson(text) {
  try { return JSON.parse(text || '{}'); } catch (e) { return {}; }
}

function firstArray(obj, keys) {
  for (const k of keys) {
    const v = obj && obj[k];
    if (Array.isArray(v)) return v;
  }
  return [];
}

function uniqByHouse(items) {
  const seen = new Set();
  const out = [];
  (items || []).forEach(it => {
    const id = String(it.houseId || it.appNumber || '').trim();
    if (!id || seen.has(id)) return;
    seen.add(id);
    out.push(it);
  });
  return out;
}

function picOf(it) {
  return it.houseImage || it.loadingCover || it.userImage || it.cover || '';
}

function titleOf(it) {
  return it.houseName || it.houseNameEn || it.houseNameTw || it.nickName || ('直播间 ' + (it.houseId || ''));
}

function remarkOf(it) {
  const nick = it.nickName ? `主播:${it.nickName}` : '';
  const watch = it.visitHistory ? `热度:${it.visitHistory}` : '';
  return [nick, watch].filter(Boolean).join(' ') || (Number(it.liveStatus) === 2 ? '直播中' : '直播');
}

function normalizePlayUrl(url) {
  url = String(url || '').trim();
  if (!url) return '';
  if (url.startsWith('webrtc://')) return '';
  return url;
}

async function refreshApiHost() {
  try {
    const r = await req(host + '/config.json', { headers: makeHeaders({ 'Cache-Control': 'no-cache' }) });
    const cfg = safeJson(r.content);
    if (cfg && cfg['api-endpoint']) {
      apiHost = String(cfg['api-endpoint']).replace(/\/$/, '');
      businessApi = apiHost + '/business';
    }
  } catch (e) {}
}

async function init(cfg) {
  if (cfg.ext && cfg.ext.startsWith('http')) host = cfg.ext.trim().replace(/\/$/, '');
  await refreshApiHost();
}

async function home(filter) {
  return JSON.stringify({
    class: [
      { type_id: 'live', type_name: '全部直播' },
      { type_id: 'hot', type_name: '热门直播' },
      { type_id: 'anchor', type_name: '主播直播' },
      { type_id: 'match', type_name: '赛事列表' }
    ],
    filters: {}
  });
}

async function homeVod() {
  return await category('live', 1, null, {});
}

async function fetchLiveIndex() {
  await refreshApiHost();
  const r = await req(apiHost + '/api/c5/business/livehouse/index', { headers: makeHeaders() });
  return safeJson(r.content);
}

async function fetchAnchorList(pg) {
  await refreshApiHost();
  const r = await req(businessApi + '/anchor/list?page=' + pg + '&size=20', { headers: makeHeaders() });
  return safeJson(r.content);
}

function liveItemsToVod(items) {
  return uniqByHouse(items).map(it => ({
    vod_id: String(it.houseId || it.appNumber || ''),
    vod_name: titleOf(it),
    vod_pic: picOf(it),
    vod_remarks: remarkOf(it)
  })).filter(it => it.vod_id && it.vod_name);
}

function matchItemsToVod(items) {
  return (items || []).map(it => {
    const home = it.homeTeam && it.homeTeam.teamName || '';
    const away = it.awayTeam && it.awayTeam.teamName || '';
    const comp = it.competitionName || (it.competition && it.competition.competitionName) || '';
    const title = [comp, home && away ? `${home} VS ${away}` : ''].filter(Boolean).join(' ');
    const appoints = it.anchorAppointmentVoList || it.reservedAnchors || [];
    const houseId = appoints[0] && (appoints[0].houseId || appoints[0].appNumber);
    return {
      vod_id: houseId ? String(houseId) : ('match$' + (it.matchId || '')),
      vod_name: title || ('赛事 ' + (it.matchId || '')),
      vod_pic: '',
      vod_remarks: houseId ? '可观看' : '暂无主播'
    };
  }).filter(it => it.vod_id && !it.vod_id.endsWith('undefined'));
}

async function category(tid, pg, filter, extend = {}) {
  tid = tid || 'live';
  pg = Number(pg || 1);
  let list = [];
  let pagecount = 1;

  if (tid === 'match') {
    await refreshApiHost();
    const r = await req(apiHost + '/api/c7/business/match/list?pageNum=' + pg + '&pageSize=30', { headers: makeHeaders() });
    const json = safeJson(r.content);
    const data = json.data || {};
    list = matchItemsToVod(data.records || []);
    pagecount = data.pages || data.totalPage || 1;
  } else if (tid === 'anchor') {
    const json = await fetchAnchorList(pg);
    const data = json.data || {};
    list = liveItemsToVod(data.records || []);
    pagecount = data.pages || 1;
  } else {
    const json = await fetchLiveIndex();
    const data = json.data || {};
    let items = [];
    if (tid === 'hot') {
      items = firstArray(data, ['streamingAnchorRanking', 'ongoingLivestreams']);
    } else {
      items = []
        .concat(firstArray(data, ['ongoingLivestreams']))
        .concat(firstArray(data, ['anchorLivestreams']))
        .concat(firstArray(data, ['streamingAnchorRanking']));
    }
    list = liveItemsToVod(items);
  }

  return JSON.stringify({ page: pg, pagecount, limit: 20, total: list.length, list });
}

async function detail(id) {
  if (String(id || '').startsWith('match$')) {
    return JSON.stringify({ list: [] });
  }

  await refreshApiHost();
  const houseId = String(id || '').trim();
  const r = await req(businessApi + '/anchor/detail?houseId=' + encodeURIComponent(houseId), { headers: makeHeaders() });
  const json = safeJson(r.content);
  const it = json.data || {};
  if (!it.houseId && !houseId) return JSON.stringify({ list: [] });

  const urls = [];
  const u1 = normalizePlayUrl(it.playStreamAddress2 || it.playStreamAddress);
  const u2 = normalizePlayUrl(it.playStreamAddress && it.playStreamAddress !== u1 ? it.playStreamAddress : '');
  const u3 = normalizePlayUrl(it.playStreamAddress3);
  if (u1) urls.push('高清线路$' + u1);
  if (u2) urls.push('备用线路$' + u2);
  if (u3) urls.push('WebRTC$' + u3);

  return JSON.stringify({
    list: [{
      vod_id: houseId,
      vod_name: titleOf(it) || ('直播间 ' + houseId),
      vod_pic: picOf(it),
      vod_remarks: Number(it.liveStatus) === 2 ? '直播中' : '直播',
      vod_play_from: '蜘蛛直播',
      vod_play_url: urls.join('#'),
      vod_content: (it.anchorAnnouncement || it.marquee || '蜘蛛直播实时体育直播').replace(/<[^>]+>/g, '')
    }]
  });
}

async function search(wd, quick, pg = 1) {
  return JSON.stringify({ page: pg, list: [] });
}

async function play(flag, id, flags) {
  return JSON.stringify({ parse: 0, url: id, header: makeHeaders() });
}

export function __jsEvalReturn() {
  return { init, home, homeVod, category, search, detail, play };
}
