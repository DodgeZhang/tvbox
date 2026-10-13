/*
@header({
  searchable: 0,
  filterable: 0,
  quickSearch: 0,
  title: '919体育[体]',
  author: 'OpenClaw',
  lang: 'cat'
})
*/

const API_BASE = 'https://01cs01.fusk39cd.com/api/web/live_lists';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const headers = {
  'User-Agent': UA,
  'Accept': 'application/json, text/plain, */*',
  'Referer': 'https://01cs01.fusk39cd.com/'
};
const PAGE_SIZE = 20;

function safeString(v) {
  if (v === null || v === undefined || v === 'null') return '';
  return String(v);
}

function safeJson(text, def) {
  if (text && typeof text === 'object') return text;
  try { return JSON.parse(text || '{}'); } catch (e) { return def || {}; }
}

async function fetchJson(url) {
  if (typeof Java !== 'undefined' && Java && Java.req) {
    const r = Java.req(url, { headers });
    return safeJson((r && (r.body || r.content)) || '{}', {});
  }
  const r2 = await req(url, { headers });
  return safeJson((r2 && (r2.content || r2.body)) || '{}', {});
}

function getClasses() {
  return [
    { type_id: '1', type_name: '全部' },
    { type_id: '2', type_name: '足球' },
    { type_id: '3', type_name: '篮球' }
  ];
}

async function init(cfg) {}

async function home(filter) {
  return JSON.stringify({ class: getClasses(), filters: {} });
}

async function homeVod() {
  return await category('1', 1, false, {});
}

async function category(tid, pg, filter, extend) {
  const page = Math.max(parseInt(pg || '1', 10) || 1, 1);
  const typeId = safeString(tid || '1') || '1';
  const list = [];

  try {
    const url = API_BASE + '/' + encodeURIComponent(typeId);
    const json = await fetchJson(url);
    const rows = json && json.code === 200 && json.data && Array.isArray(json.data.data) ? json.data.data : [];

    for (let i = 0; i < rows.length; i++) {
      const item = rows[i];
      if (!item.tournament_id) continue;
      const type = safeString(item.type || typeId);
      const tournamentId = safeString(item.tournament_id);
      const memberId = safeString(item.member_id);
      const homeTeam = safeString(item.home_team_zh);
      const awayTeam = safeString(item.away_team_zh);
      const name = [homeTeam, awayTeam].filter(Boolean).join(' VS ') || safeString(item.league_name_zh) || tournamentId;

      list.push({
        vod_id: type + '|' + tournamentId + '|' + memberId,
        vod_name: name,
        vod_pic: safeString(item.cover),
        vod_remarks: safeString(item.league_name_zh) || safeString(item.match_time) || safeString(item.status)
      });
    }
  } catch (e) {
    return JSON.stringify({ code: 1, page, pagecount: 1, limit: PAGE_SIZE, total: 0, list: [] });
  }

  return JSON.stringify({
    code: 1,
    msg: '数据列表',
    page,
    pagecount: list.length >= PAGE_SIZE ? page + 1 : page,
    limit: PAGE_SIZE,
    total: list.length,
    list
  });
}

async function detail(id) {
  const idList = Array.isArray(id) ? id : String(id || '').split(',').filter(Boolean);
  const list = [];

  for (let n = 0; n < idList.length; n++) {
    const vid = safeString(idList[n]).trim();
    const parts = vid.split('|');
    if (parts.length !== 3) continue;
    const type = parts[0];
    const tournamentId = parts[1];
    const memberId = parts[2];

    try {
      const url = API_BASE + '/' + encodeURIComponent(type) + '/detail/' + encodeURIComponent(tournamentId) + '?member_id=' + encodeURIComponent(memberId);
      const json = await fetchJson(url);
      if (!json || json.code !== 200) continue;

      const detailObj = json.data && json.data.detail ? json.data.detail : {};
      const moreArr = json.data && Array.isArray(json.data.more) ? json.data.more : [];
      const homeTeam = safeString(detailObj.home_team_zh);
      const awayTeam = safeString(detailObj.away_team_zh);
      const vodName = [homeTeam, awayTeam].filter(Boolean).join(' VS ') || safeString(detailObj.league_name_zh) || vid;

      const playFromList = [];
      const playUrlList = [];
      for (let i = 0; i < moreArr.length; i++) {
        const source = moreArr[i];
        const username = safeString(source.username) || ('线路' + (i + 1));
        const urls = [];
        const flv = safeString(source.screen_url);
        const m3u8 = safeString(source.screen_url_m3u8);
        if (flv) urls.push('线路一$' + flv);
        if (m3u8) urls.push('线路二$' + m3u8);
        if (!urls.length) continue;
        playFromList.push(username.replace(/\$|#/g, ''));
        playUrlList.push(urls.join('#'));
      }

      list.push({
        vod_id: vid,
        vod_name: vodName,
        vod_pic: safeString(detailObj.cover),
        type_name: safeString(detailObj.league_name_zh),
        vod_remarks: safeString(detailObj.match_time) || safeString(detailObj.status),
        vod_content: safeString(detailObj.room_notice) || '体育直播',
        vod_play_from: playFromList.join('$$$') || '919体育',
        vod_play_url: playUrlList.join('$$$') || ('暂无播放$' + vid)
      });
    } catch (e) {}
  }

  return JSON.stringify({ code: 1, msg: '数据列表', page: 1, pagecount: 1, limit: list.length, total: list.length, list });
}

async function search(wd, quick, pg) {
  return JSON.stringify({ code: 1, msg: '数据列表', page: parseInt(pg) || 1, pagecount: 1, limit: 20, total: 0, list: [] });
}

async function play(flag, id, flags) {
  const url = safeString(id).replace(/\*\*\*/g, '#');
  if (!/^https?:\/\//i.test(url)) return JSON.stringify({ parse: 0, jx: 0, url: '', msg: '暂无播放地址' });
  return JSON.stringify({ parse: 0, jx: 0, url, header: headers });
}

async function homeContent(filter) { return safeJson(await home(filter), { class: [], filters: {} }); }
async function homeVideoContent() { return safeJson(await homeVod(), { list: [] }); }
async function categoryContent(tid, pg, filter, extend) { return safeJson(await category(tid, pg, filter, extend || {}), { list: [] }); }
async function detailContent(ids) { return safeJson(await detail(ids), { list: [] }); }
async function searchContent(wd, quick, pg) { return safeJson(await search(wd, quick, pg || 1), { list: [] }); }
async function playerContent(flag, id, flags) { return safeJson(await play(flag, id, flags), { parse: 0, url: id }); }

export function __jsEvalReturn() {
  return {
    init,
    home,
    homeVod,
    category,
    search,
    detail,
    play,
    homeContent,
    homeVideoContent,
    categoryContent,
    detailContent,
    searchContent,
    playerContent
  };
}
