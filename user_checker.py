import aiohttp
import logging
import config
from discord.ext import commands

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# КОНФИГ
# ═══════════════════════════════════════════════════════════════════


SERVER_URL: str = ""

CHECK_TOKEN: str = ""

CHECK_GUILD_IDS: list[str] = [
    
]

CHECK_MSG_LIMIT: int = 25


# ═══════════════════════════════════════════════════════════════════
# ПОИСК ЧЕРЕЗ СЕРВЕР
# ═══════════════════════════════════════════════════════════════════

async def search_user(
    target_user_id: str,
    progress_cb=None,
) -> list:
    """
    Отправляет запрос на внешний сервер и возвращает список результатов.

    Каждый элемент списка — словарь с полями:
      guild_id, guild_name, nick, roles, messages

    Аналогичен по структуре старой функции _search_user_in_guilds —
    остальной код recruitment.py остаётся без изменений.

    progress_cb(done, total, name) — опциональный колбэк прогресса
    (вызывается единожды: в начале и в конце).
    """
    total = len(CHECK_GUILD_IDS)

    if progress_cb:
        await progress_cb(0, total, "Запрос к серверу…")

    payload = {
        "token":          CHECK_TOKEN,
        "target_user_id": target_user_id,
        "guild_ids":      CHECK_GUILD_IDS,
        "limit":          CHECK_MSG_LIMIT,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SERVER_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                data = await resp.json()
    except aiohttp.ClientConnectorError as e:
        logger.error("UserChecker: не удалось подключиться к серверу %s: %s", SERVER_URL, e)
        raise RuntimeError(f"Сервер проверки недоступен: {SERVER_URL}") from e
    except Exception as e:
        logger.error("UserChecker: ошибка запроса: %s", e, exc_info=True)
        raise

    if data.get("status") != "ok":
        err = data.get("error") or data.get("detail") or str(data)
        logger.error("UserChecker: сервер вернул ошибку: %s", err)
        raise RuntimeError(f"Сервер вернул ошибку: {err}")

    results: list = data.get("results", [])

    if progress_cb:
        await progress_cb(total, total, "Готово")

    logger.info(
        "UserChecker: проверка %s завершена, серверов в ответе: %d",
        target_user_id, len(results),
    )
    return results


# ═══════════════════════════════════════════════════════════════════
# HTML-ОТЧЁТ
# ═══════════════════════════════════════════════════════════════════

def _generate_check_html(user_id: str, results: list) -> bytes:
    from datetime import timezone, timedelta, datetime
    import html as _h
    import re as _re

    def _discord_fmt(raw: str) -> str:
        s = _h.escape(raw)
        s = s.replace('\n', '<br>')
        s = _re.sub(r'```(?:\w+<br>)?(.*?)```', lambda m: '<div class="code-block">' + m.group(1) + '</div>', s, flags=_re.DOTALL)
        s = _re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', s)
        s = _re.sub(r'\|\|(.+?)\|\|', r'<span class="spoiler">\1</span>', s)
        s = _re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', s)
        s = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
        s = _re.sub(r'\*([^*<]+)\*', r'<em>\1</em>', s)
        s = _re.sub(r'__(.+?)__', r'<u>\1</u>', s)
        s = _re.sub(r'~~(.+?)~~', r'<s>\1</s>', s)
        s = _re.sub(r'(^|<br>)&gt; ?(.+?)(?=<br>|$)', r'\1<div class="blockquote">\2</div>', s)
        s = _re.sub(r'&lt;@!?(\d+)&gt;', r'<span class="mention">@\1</span>', s)
        s = _re.sub(r'&lt;#(\d+)&gt;', r'<span class="mention">#\1</span>', s)
        s = _re.sub(r'&lt;@&amp;(\d+)&gt;', r'<span class="mention role-mention">@role</span>', s)
        return s

    msk_tz = timezone(timedelta(hours=3))

    def _fmt_ts(ts_raw: str) -> str:
        try:
            dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            return dt.astimezone(msk_tz).strftime("%d.%m.%Y %H:%M МСК")
        except Exception:
            return ts_raw

    guild_tabs = []
    for entry in results:
        gname = _h.escape(entry.get("guild_name") or entry.get("guild_id", "Неизвестный"))
        nick  = entry.get("nick")
        roles = entry.get("roles", [])
        ch_map: dict = {}
        for msg in entry.get("messages", []):
            ch = msg.get("channel", "unknown")
            ch_map.setdefault(ch, []).append(msg)
        guild_tabs.append((gname, nick, roles, bool(nick), ch_map))

    server_btn_html  = ""
    server_pane_html = ""

    guild_tabs_with_msgs = [(gi, g) for gi, g in enumerate(guild_tabs) if g[4]]

    actual_idx = 0
    for orig_gi, (gname, nick, roles, found, ch_map) in guild_tabs_with_msgs:
        gi = actual_idx
        active_cls  = "active" if gi == 0 else ""
        has_anything = found or bool(ch_map)
        dot = "&#x1F7E2;" if has_anything else "&#x1F534;"
        server_btn_html += (
            f'<button class="srv-btn {active_cls}" onclick="switchServer({gi})" id="srv-btn-{gi}">'
            f'{dot} {gname}</button>\n'
        )

        nick_display = f"@{_h.escape(nick)}" if nick else '<span style="color:#949ba4;font-style:italic">не найден</span>'
        roles_e  = ", ".join(_h.escape(r) for r in roles) if roles else "Нет ролей"
        total_msgs = sum(len(v) for v in ch_map.values())

        meta_html = (
            '<div class="member-meta">'
            f'<div class="meta-row"><span class="meta-label">Ник</span><span class="meta-val">{nick_display}</span></div>'
            f'<div class="meta-row"><span class="meta-label">Роли</span><span class="meta-val roles-val">{roles_e}</span></div>'
            f'<div class="meta-row"><span class="meta-label">Сообщений</span><span class="meta-val">{total_msgs}</span></div>'
            '</div>'
        )

        if not ch_map:
            ch_section = '<div class="no-msgs">Сообщений не найдено</div>'
        else:
            ch_btn_html  = ""
            ch_pane_html = ""
            author_label = _h.escape(nick) if nick else "Удалённый/бывший участник"
            for ci, (ch_name, msgs) in enumerate(ch_map.items()):
                ca = "active" if ci == 0 else ""
                ch_btn_html += (
                    f'<button class="ch-btn {ca}" onclick="switchCh({gi},{ci})" '
                    f'id="ch-btn-{gi}-{ci}">#{_h.escape(ch_name)} ({len(msgs)})</button>\n'
                )
                msg_rows = ""
                for m in msgs:
                    ts_fmt   = _fmt_ts(m.get("timestamp", ""))
                    text     = _discord_fmt(m.get("content", ""))
                    body     = text if text else '<span class="dc-empty-msg">[вложение]</span>'
                    msg_id   = m.get("message_id", "")
                    ch_id    = m.get("channel_id", "")
                    guild_id = entry.get("guild_id", "")
                    if msg_id and ch_id and guild_id:
                        msg_link = f"https://discord.com/channels/{guild_id}/{ch_id}/{msg_id}"
                        ts_html  = f'<a class="dc-ts" href="{msg_link}" target="_blank" title="Открыть в Discord">{ts_fmt} 🔗</a>'
                    else:
                        ts_html  = f'<span class="dc-ts">{ts_fmt}</span>'
                    msg_rows += (
                        '<div class="dc-message">'
                        '<div class="dc-avatar">&#x1F4AC;</div>'
                        '<div class="dc-body">'
                        f'<div class="dc-header"><span class="dc-author">{author_label}</span>{ts_html}</div>'
                        f'<div class="dc-text">{body}</div>'
                        '</div></div>'
                    )
                disp = "block" if ci == 0 else "none"
                ch_pane_html += (
                    f'<div class="ch-panel" id="ch-panel-{gi}-{ci}" style="display:{disp}">'
                    f'{msg_rows}</div>\n'
                )
            ch_section = f'<div class="ch-tabs-bar">{ch_btn_html}</div><div class="ch-panels">{ch_pane_html}</div>'

        pane_inner = meta_html + ch_section
        disp = "block" if gi == 0 else "none"
        server_pane_html += (
            f'<div class="srv-panel" id="srv-panel-{gi}" style="display:{disp}">'
            f'{pane_inner}</div>\n'
        )
        actual_idx += 1

    CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#313338;color:#dcddde;font-family:'gg sans','Noto Sans',sans-serif;font-size:14px;min-height:100vh;display:flex;flex-direction:column}
.ph{background:#1e1f22;padding:14px 22px;border-bottom:3px solid #F87120;display:flex;align-items:center;gap:10px;flex-shrink:0}
.ph h1{font-size:18px;color:#fff;font-weight:700}
.ph .uid{margin-left:auto;font-size:12px;color:#949ba4;font-family:monospace}
.layout{display:flex;flex:1;overflow:hidden}
.srv-sidebar{width:220px;flex-shrink:0;background:#2b2d31;border-right:1px solid #1e1f22;overflow-y:auto;padding:10px 8px;display:flex;flex-direction:column;gap:3px}
.srv-btn{background:transparent;color:#949ba4;border:none;padding:8px 12px;border-radius:6px;cursor:pointer;font-size:13px;font-family:inherit;text-align:left;width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.srv-btn:hover{background:#35373c;color:#dcddde}
.srv-btn.active{background:#F87120;color:#fff;font-weight:600}
.srv-content{flex:1;overflow-y:auto;padding:18px 24px}
.srv-panel{display:none}
.member-meta{background:#2b2d31;border-radius:8px;padding:14px 18px;margin-bottom:16px;display:flex;flex-direction:column;gap:8px;border-left:3px solid #F87120}
.meta-row{display:flex;gap:12px;align-items:flex-start}
.meta-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#949ba4;min-width:80px;padding-top:1px}
.meta-val{color:#dcddde;font-size:14px;word-break:break-word}
.roles-val{color:#b9bbbe;font-size:13px}
.ch-tabs-bar{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:12px}
.ch-btn{background:#1e1f22;color:#949ba4;border:none;padding:5px 12px;border-radius:5px;cursor:pointer;font-size:12px;font-family:inherit}
.ch-btn:hover{background:#35373c;color:#dcddde}
.ch-btn.active{background:#F87120;color:#fff;font-weight:600}
.dc-message{display:flex;gap:12px;padding:5px 4px;border-radius:4px;margin-bottom:2px}
.dc-message:hover{background:#2e3035}
.dc-avatar{width:38px;height:38px;border-radius:50%;background:#5865f2;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;margin-top:2px}
.dc-body{flex:1;min-width:0}
.dc-header{display:flex;align-items:baseline;gap:8px;margin-bottom:3px;flex-wrap:wrap}
.dc-author{font-weight:700;color:#fff;font-size:14px}
.dc-ts{font-size:11px;color:#949ba4}
a.dc-ts{font-size:11px;color:#949ba4;text-decoration:none}
a.dc-ts:hover{color:#F87120;text-decoration:underline}
.dc-text{color:#dcddde;line-height:1.6;word-wrap:break-word}
.dc-empty-msg{color:#4f545c;font-style:italic}
strong{color:#fff}em{font-style:italic}u{text-decoration:underline}s{text-decoration:line-through;color:#949ba4}
code.inline-code{background:#1e1f22;color:#c9d1d9;font-family:monospace;font-size:13px;padding:1px 5px;border-radius:3px}
.code-block{background:#1e1f22;color:#c9d1d9;font-family:monospace;font-size:13px;padding:10px 14px;border-radius:5px;margin:4px 0;white-space:pre-wrap;word-break:break-all;border-left:3px solid #404249}
.blockquote{border-left:3px solid #4f545c;padding:2px 10px;margin:2px 0;color:#b9bbbe}
.spoiler{background:#202225;color:transparent;border-radius:3px;padding:0 3px;cursor:pointer;transition:color .2s,background .2s}
.spoiler:hover{background:#36393f;color:#dcddde}
.mention{background:rgba(88,101,242,.2);color:#8ab4f8;border-radius:3px;padding:0 3px;font-weight:500}
.role-mention{background:rgba(250,119,32,.15);color:#F87120}
.no-msgs{padding:16px 0;color:#949ba4;font-style:italic}
"""

    JS = """
function switchServer(gi){
  document.querySelectorAll('.srv-panel').forEach(p=>p.style.display='none');
  document.querySelectorAll('.srv-btn').forEach(b=>b.classList.remove('active'));
  var p=document.getElementById('srv-panel-'+gi);
  var b=document.getElementById('srv-btn-'+gi);
  if(p)p.style.display='block';
  if(b)b.classList.add('active');
}
function switchCh(gi,ci){
  var panes=document.querySelectorAll('#srv-panel-'+gi+' .ch-panel');
  var btns=document.querySelectorAll('#srv-panel-'+gi+' .ch-btn');
  panes.forEach(p=>p.style.display='none');
  btns.forEach(b=>b.classList.remove('active'));
  var p=document.getElementById('ch-panel-'+gi+'-'+ci);
  var b=document.getElementById('ch-btn-'+gi+'-'+ci);
  if(p)p.style.display='block';
  if(b)b.classList.add('active');
}
"""

    html = (
        "<!DOCTYPE html><html lang='ru'><head>"
        "<meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
        f"<title>Проверка {user_id}</title>"
        f"<style>{CSS}</style>"
        "</head><body>"
        "<div class='ph'>"
        "<span style='font-size:18px'>&#x1F50D;</span>"
        "<h1>Проверка участника</h1>"
        f"<div class='uid'>ID: {user_id}</div>"
        "</div>"
        "<div class='layout'>"
        f"<div class='srv-sidebar'>{server_btn_html}</div>"
        f"<div class='srv-content'>{server_pane_html}</div>"
        "</div>"
        f"<script>{JS}</script>"
        "</body></html>"
    )
    return html.encode("utf-8")


# ═══════════════════════════════════════════════════════════════════
# COG
# ═══════════════════════════════════════════════════════════════════

class UserCheckerCog(commands.Cog):
    """Регистрирует модуль проверки пользователей. Логика — в search_user()."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("UserCheckerCog загружен. Сервер: %s", SERVER_URL)


async def setup(bot: commands.Bot):
    await bot.add_cog(UserCheckerCog(bot))
