"""Telegram adapter; run exactly one process per BOT_TOKEN."""
import asyncio
import logging
import os
import threading
import time
import sys
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from dotenv import load_dotenv
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup, InputMediaPhoto, BotCommand, Update
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, AIORateLimiter, InlineQueryHandler, ChosenInlineResultHandler
from engine import Game, NAMES, RULES, card
from render import board_image, hand_image, photo, reference_image
from storage import Store
from inline_ui import InlineUI

load_dotenv(Path(__file__).with_name('.env'))
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
log = logging.getLogger('loveletter')
GAMES = {}
LOCKS = defaultdict(asyncio.Lock)
STORE = None
USERNAME = ''
TURN_SECONDS = max(15, int(os.getenv('TURN_SECONDS', '60')))
INLINE = InlineUI(sys.modules[__name__])

def code(g, action, value=''):
    return f'll:{g.chat_id}:{g.gid}:{g.rev}:{action}:{value}'

def link(g=None):
    return f'https://t.me/{USERNAME}?start=' + (f'join_{g.chat_id}_{g.gid}' if g else 'hand')

def group_keys(g):
    if g.stage == 'lobby':
        rows = [[Button('💌 加入遊戲', callback_data=code(g,'join'))],
                [Button('▶ 開始遊戲', callback_data=code(g,'begin')), Button('＋電腦補滿', callback_data=code(g,'fill'))],
                [Button('離開座位', callback_data=code(g,'leave')), Button('取消遊戲', callback_data=code(g,'cancel'))]]
        if not INLINE.ready():
            rows.insert(0,[Button('首次使用：準備卡圖',url=f'https://t.me/{USERNAME}?start=setup')])
    elif g.stage == 'playing':
        labels={'play':'💌 選牌出牌','target':'查看我的手牌','guess':'查看我的手牌','keep':'💌 大臣：選擇保留','order':'💌 大臣：排列牌庫底'}
        rows = [[Button(labels[g.phase],switch_inline_query_current_chat=f'{g.gid} {g.rev}')]]
        if g.phase=='target':
            buttons=[Button(('自己' if ti==g.turn else g.players[ti].name),callback_data=code(g,'target',ti)) for ti in g.targets(g.pending['card'])]
            rows.extend(buttons[i:i+2] for i in range(0,len(buttons),2))
        if g.phase=='guess':
            buttons=[Button(card(v),callback_data=code(g,'guess',v)) for v in range(10) if v!=1]
            rows.extend(buttons[i:i+3] for i in range(0,len(buttons),3))
        rows += [[Button('我的手牌／秘密情報',callback_data=code(g,'notes'))],
                 [Button('查看公開棄牌',callback_data=code(g,'discards')),Button('取消遊戲',callback_data=code(g,'cancel'))]]
    elif g.stage == 'round_end':
        rows = [[Button('▶ 下一局',callback_data=code(g,'begin')), Button('取消遊戲',callback_data=code(g,'cancel'))]]
    else:
        rows = [[Button('🏆 重新開桌',callback_data=code(g,'rematch'))]]
    rows.append([Button('角色與玩法',callback_data=code(g,'rules'))])
    return Markup(rows)

def private_keys(g, i):
    p = g.players[i]
    if g.stage != 'playing' or i != g.turn:
        return Markup([[Button('重新整理手牌',callback_data=code(g,'refresh'))]])
    rows = []
    if g.phase == 'play':
        for n in g.legal_cards():
            rows.append([Button(f'打出 {n+1}｜{card(p.hand[n])}',callback_data=code(g,'play',n))])
    elif g.phase == 'target':
        for ti in g.targets(g.pending['card']):
            rows.append([Button(('自己' if ti == i else g.players[ti].name), callback_data=code(g,'target',ti))])
    elif g.phase == 'guess':
        buttons = [Button(card(v),callback_data=code(g,'guess',v)) for v in range(10) if v != 1]
        rows = [buttons[n:n+3] for n in range(0,len(buttons),3)]
    elif g.phase == 'keep':
        rows = [[Button(f'保留 {n+1}｜{card(v)}',callback_data=code(g,'keep',n))] for n,v in enumerate(p.hand)]
    elif g.phase == 'order':
        a,b = g.pending['return']
        rows = [[Button(f'較先抽到 {card(a)} → 再 {card(b)}',callback_data=code(g,'order',0))],
                [Button(f'較先抽到 {card(b)} → 再 {card(a)}',callback_data=code(g,'order',1))]]
    return Markup(rows)

def private_caption(g, i):
    p = g.players[i]
    if g.stage in ('round_end','match_end'):
        return '本局已結束，請回群組查看結算。'
    if not p.alive:
        return '你本局已出局。可在群組觀看，下一局會重新加入。'
    if i != g.turn:
        return f'目前輪到 {g.current.name}。你的手牌只會傳送給你。'
    prompt = {'play':'輪到你：選擇一張打出。','target':'請選擇效果目標。','guess':'猜對方手牌（不能猜守衛）。',
              'keep':'大臣：選擇要留下的牌。','order':'大臣：決定牌庫底兩張牌的順序。'}[g.phase]
    return f'{prompt}\n每次行動共 {TURN_SECONDS} 秒，逾時會自動完成。'

async def put_photo(bot, cid, old_id, im, caption, keys):
    if old_id:
        try:
            await bot.edit_message_media(chat_id=cid,message_id=old_id,media=InputMediaPhoto(photo(im),caption=caption),reply_markup=keys)
            return old_id
        except BadRequest as e:
            if 'not modified' in str(e).lower():
                return old_id
            # Only fall back for a removed/too-old message. Other API errors propagate.
            if not any(s in str(e).lower() for s in ('not found','can\'t be edited','cannot be edited')):
                raise
    msg = await bot.send_photo(chat_id=cid,photo=photo(im),caption=caption,reply_markup=keys,protect_content=True)
    return msg.message_id

async def show_private(app, g, i):
    p = g.players[i]
    if p.ai or g.stage == 'lobby':
        return
    im = await asyncio.to_thread(hand_image,g,i)
    old = g.dm_ids.get(str(p.uid))
    g.dm_ids[str(p.uid)] = await put_photo(app.bot,p.uid,old,im,private_caption(g,i),private_keys(g,i))

async def show_board(app, g):
    if g.stage == 'lobby':
        caption = f'💌 情書｜{len(g.players)} / 6 人已入席\n直接在群組加入、選圖出牌；由房主開始。'
    elif g.stage == 'playing':
        prompt={'play':'按「選牌出牌」挑選卡圖。','target':'請本人按下方按鈕指定目標。','guess':'請本人按下方按鈕猜角色。','keep':'按「大臣：選擇保留」私下挑牌。','order':'按「大臣：排列牌庫底」私下排順序。'}[g.phase]
        caption = f'💌 第 {g.round_no} 局｜輪到 {g.current.name}\n{prompt}\n'+'\n'.join(g.log[-3:])
    else:
        caption = '\n'.join(g.log[-5:])
    im = await asyncio.to_thread(board_image,g)
    old_id = g.board_id
    # Send first: a delivery failure must not remove the usable previous board.
    msg = await app.bot.send_photo(
        chat_id=g.chat_id, photo=photo(im), caption=caption[:1000],
        reply_markup=group_keys(g), protect_content=True, disable_notification=True)
    g.board_id = msg.message_id
    STORE.save(g)
    if old_id and old_id != g.board_id:
        try:
            await app.bot.delete_message(chat_id=g.chat_id,message_id=old_id)
        except TelegramError:
            # Older messages may be undeletable; retire their controls instead.
            try:
                await app.bot.edit_message_reply_markup(
                    chat_id=g.chat_id,message_id=old_id,reply_markup=None)
            except TelegramError:
                log.warning('Previous board cleanup failed for chat %s.',g.chat_id)

def arm(g):
    if g.stage == 'playing' and not g.deadline:
        g.deadline = time.time() + (3 if g.current.ai else TURN_SECONDS)

async def publish(app, g, full=True):
    for uid,note in g.private:
        notes=g.secret_notes.setdefault(str(uid),[])
        notes.append(note)
        g.secret_notes[str(uid)]=notes[-12:]
    g.private=[]
    STORE.save(g)
    try:
        await show_board(app,g)
    except TelegramError:
        log.warning('Public board delivery failed for chat %s; /status can recover.',g.chat_id)
    # The fresh board contains the turn prompt and must remain the last game message.
    arm(g)
    STORE.save(g)

def active_for(uid):
    return next((g for g in GAMES.values() if g.stage != 'match_end' and any(p.uid == uid for p in g.players)),None)

async def start(update,ctx):
    if update.effective_chat.type != 'private':
        await update.effective_message.reply_text('在群組輸入 /newgame 建立情書牌桌。')
        return
    arg = ctx.args[0] if ctx.args else ''
    if arg=='setup':
        await INLINE.setup(update,ctx)
        return
    if arg.startswith('join_'):
        try:
            _,cid,gid = arg.split('_')
            g = GAMES.get(int(cid))
            if not g or g.gid != gid:
                raise ValueError('這個牌桌已關閉，請回群組使用新的加入按鈕。')
            async with LOCKS[g.chat_id]:
                existing = active_for(update.effective_user.id)
                if existing and existing is not g:
                    raise ValueError('你已在另一個牌桌，請先結束或離開該桌。')
                if not any(p.uid == update.effective_user.id for p in g.players):
                    g.join(update.effective_user.id,update.effective_user.full_name)
                await update.message.reply_text('你已入席！手牌會傳送到這裡，請回群組等待開局。')
                await publish(ctx.application,g)
        except ValueError as e:
            await update.message.reply_text(str(e))
        return
    await update.message.reply_text('💌 情書｜群組選圖版\n首次使用請在此輸入 /setup 準備卡圖。\n遊戲時在群組 /newgame，按「選牌出牌」即可。\n/hand 可選用私訊手牌備援。')

async def newgame(update,ctx):
    if update.effective_chat.type not in ('group','supergroup'):
        await update.effective_message.reply_text('請把 BOT 加入群組，再於群組輸入 /newgame。')
        return
    cid = update.effective_chat.id
    async with LOCKS[cid]:
        if cid in GAMES and GAMES[cid].stage != 'match_end':
            await update.message.reply_text('已有牌桌，請用 /status 查看。')
            return
        g = Game(cid,update.effective_user.id)
        g.room_title=(update.effective_chat.title or '情書牌桌')[:40]
        existing=active_for(update.effective_user.id)
        if existing and existing.chat_id!=cid:
            await update.message.reply_text('你已在其他牌桌，請先離席或結束該場。')
            return
        g.join(update.effective_user.id,update.effective_user.full_name)
        GAMES[cid] = g
        await publish(ctx.application,g)

async def hand(update,ctx):
    if update.effective_chat.type != 'private':
        g=GAMES.get(update.effective_chat.id)
        if g:
            await update.effective_message.reply_text('按下方按鈕查看個人選牌介面。',reply_markup=Markup([[Button('查看我的手牌',switch_inline_query_current_chat=f'{g.gid} {g.rev}')],[Button('我的手牌／秘密情報',callback_data=code(g,'notes'))]]))
        else:
            await update.effective_message.reply_text('請先 /newgame 建桌。')
        return
    g = active_for(update.effective_user.id)
    if not g:
        await update.effective_message.reply_text('目前沒有進行中的座位，請回群組加入遊戲。')
        return
    if g.stage == 'lobby':
        await update.effective_message.reply_text('你已入席，等待房主開始。')
        return
    async with LOCKS[g.chat_id]:
        i = next(i for i,p in enumerate(g.players) if p.uid == update.effective_user.id)
        # A fresh message intentionally brings the hand back to the bottom of the DM.
        g.dm_ids.pop(str(update.effective_user.id),None)
        await show_private(ctx.application,g,i)
        STORE.save(g)

async def status(update,ctx):
    g = GAMES.get(update.effective_chat.id)
    if not g:
        await update.effective_message.reply_text('此群組尚未開桌，請用 /newgame。')
        return
    async with LOCKS[g.chat_id]:
        await show_board(ctx.application,g)
        STORE.save(g)

async def rules(update,ctx):
    s = '💌 情書｜21 張牌・2～6 人\n每次抽一張、出一張。僅剩一人或牌庫抽完時結算。牌庫抽完後，最高牌者得 1 枚好感，同分者各得 1 枚。\n目標：2 人 6 枚／3 人 5 枚／4 人 4 枚／5～6 人 3 枚。\n\n'
    s += '\n\n'.join(f'{card(i)}：{RULES[i]}' for i in range(10))
    await update.effective_message.reply_text(s)

async def cancel(update,ctx):
    cid = update.effective_chat.id
    async with LOCKS[cid]:
        g = GAMES.get(cid)
        if not g:
            await update.effective_message.reply_text('沒有進行中的牌桌。')
        elif g.owner != update.effective_user.id:
            await update.effective_message.reply_text('只有房主可以取消牌桌。')
        else:
            GAMES.pop(cid)
            STORE.delete(cid)
            await update.effective_message.reply_text('牌桌已取消。使用 /newgame 可重新開桌。')

async def callback(update,ctx):
    q = update.callback_query
    # Secret alerts are answered once, with text visible only to the clicker.
    if ':notes:' in (q.data or ''):
        try:
            _,cid,gid,rev,action,value=q.data.split(':')
            async with LOCKS[int(cid)]:
                g=GAMES.get(int(cid))
                uid=update.effective_user.id
                if not g or g.gid!=gid:
                    raise ValueError('這個牌桌已結束。')
                p=next((p for p in g.players if p.uid==uid),None)
                if not p:raise ValueError('你沒有加入這個牌桌。')
                if g.stage=='lobby':raise ValueError('尚未發牌。')
                notes=g.secret_notes.get(str(uid),[])
                key=f'notes:{g.gid}:{g.round_no}:{uid}'
                pos=ctx.user_data.get(key,0)%max(1,len(notes))
                note=notes[-1-pos] if notes else '目前沒有額外情報。'
                ctx.user_data[key]=pos+1
                s='手牌：'+('、'.join(card(v) for v in p.hand) or '已出局')
                s+='\n'+note
                if len(notes)>1:s+=f'\n情報 {pos+1}/{len(notes)}，再按一次查看上一筆。'
                await q.answer(s[:200],show_alert=True,cache_time=0)
        except ValueError as e:
            await q.answer(str(e),show_alert=True)
        return
    await q.answer()
    try:
        _, cid, gid, rev, action, value = q.data.split(':')
        cid = int(cid)
        async with LOCKS[cid]:
            g = GAMES.get(cid)
            if not g or g.gid != gid:
                raise ValueError('這個牌桌已結束，請使用最新按鈕。')
            uid = update.effective_user.id
            if update.effective_chat.type in ('group','supergroup') and update.effective_chat.id!=g.chat_id:
                raise ValueError('請回原本的牌桌群組操作。')
            if action in ('fill','begin','cancel','rematch') and uid != g.owner:
                raise ValueError('這個操作需要由房主執行。')
            if action == 'cancel':
                GAMES.pop(cid)
                STORE.delete(cid)
                await ctx.bot.send_message(cid,'牌桌已取消。使用 /newgame 重新開桌。')
                return
            if action == 'rules':
                await rules(update,ctx)
                return
            if action == 'discards':
                s = '\n'.join(f'{p.name}：'+('、'.join(card(v) for v in p.discards) or '尚無') for p in g.players)
                if g.exposed:
                    s += '\n雙人局公開移除：'+ '、'.join(card(v) for v in g.exposed)
                await q.message.reply_text(s or '尚無棄牌。')
                return
            if action == 'refresh':
                if update.effective_chat.type != 'private':
                    raise ValueError('請在私訊查看手牌。')
                i = next((i for i,p in enumerate(g.players) if p.uid == uid),None)
                if i is None:
                    raise ValueError('你不在此桌。')
                await show_private(ctx.application,g,i)
                STORE.save(g)
                return
            if action == 'rematch':
                if g.stage != 'match_end':
                    raise ValueError('此場尚未結束。')
                title=g.room_title
                old_board_id=g.board_id
                g = Game(cid,g.owner,room_title=title)
                g.board_id=old_board_id
                existing=active_for(uid)
                if existing and existing.chat_id!=cid:
                    raise ValueError('你已在其他牌桌。')
                g.join(uid,update.effective_user.full_name)
                GAMES[cid] = g
            elif action == 'join':
                existing=active_for(uid)
                if existing and existing is not g:
                    raise ValueError('你已在其他牌桌，請先離席或結束該場。')
                g.join(uid,update.effective_user.full_name)
            elif action == 'fill':
                if g.stage != 'lobby':
                    raise ValueError('只能在開局前加入電腦。')
                if not any(not p.ai for p in g.players):
                    raise ValueError('請先按「加入遊戲」，至少需要一位真人入席。')
                while len(g.players)<6:
                    i = len(g.players)+1
                    g.join(-i,f'宮廷使者 {i}',True)
            elif action == 'leave':
                if g.stage != 'lobby':
                    raise ValueError('遊戲開始後無法離席；逾時會自動出牌。')
                g.players = [p for p in g.players if p.uid != uid]
                g.rev += 1
            elif action == 'begin':
                if not INLINE.ready():
                    raise ValueError('請房主先按「首次使用：準備卡圖」，私訊執行 /setup。')
                if int(rev) != g.rev:
                    raise ValueError('請使用最新牌桌上的開始按鈕。')
                if not any(not p.ai for p in g.players):
                    raise ValueError('至少需要一位真人入席。')
                g.new_round()
            else:
                if action not in ('target','guess') and update.effective_chat.type != 'private':
                    raise ValueError('請在私訊操作手牌。')
                if g.deadline and time.time()>g.deadline:
                    raise ValueError('行動時間已到，請等待系統代打。')
                before_turn = (g.round_no,g.turn)
                g.act(uid,action,int(value),int(rev))
                full = g.stage != 'playing' or before_turn != (g.round_no,g.turn)
                await publish(ctx.application,g,full=full)
                return
            await publish(ctx.application,g)
    except ValueError as e:
        await q.message.reply_text(str(e))

async def tick(ctx):
    for cid in list(GAMES):
        if LOCKS[cid].locked():
            continue
        async with LOCKS[cid]:
            g = GAMES.get(cid)
            if not g or g.stage != 'playing':
                continue
            arm(g)
            if time.time() < g.deadline:
                continue
            if not g.current.ai:
                g.say(f'{g.current.name} 逾時，由系統自動完成行動。')
            uid = g.current.uid
            for _ in range(5):
                action,value = g.auto_action()
                g.act(uid,action,value)
                if g.stage != 'playing' or g.current.uid != uid:
                    break
            await publish(ctx.application,g)

async def errors(update,ctx):
    # Do not log Update objects, private cards, request URLs or token-bearing errors.
    log.error('Handler failed (%s). Saved game is available via /status and /hand.',type(ctx.error).__name__)

async def post_init(app):
    global USERNAME
    me=await app.bot.get_me()
    USERNAME=me.username
    INLINE.bot_id=me.id
    await app.bot.set_my_commands([BotCommand('newgame','在群組建立情書牌桌'),BotCommand('hand','開啟個人選牌介面'),BotCommand('setup','首次使用時私訊準備卡圖'),BotCommand('status','重新顯示群組牌桌'),BotCommand('rules','角色與玩法'),BotCommand('cancel','房主取消牌桌')])
    for g in GAMES.values():
        if g.stage == 'playing':
            # Restart gives the active player a fresh decision window.
            g.deadline = 0
            await publish(app,g)
    app.job_queue.run_repeating(tick,interval=2,first=3,job_kwargs={'max_instances':1,'coalesce':True})

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Love Letter bot process is running')
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self,*args):
        pass

def main():
    global STORE,GAMES
    token = os.getenv('BOT_TOKEN','').strip()
    if not token or token == 'PASTE_YOUR_BOT_TOKEN_HERE':
        raise SystemExit('請先把 .env.example 複製為 .env，並填入 BOT_TOKEN。')
    STORE = Store()
    GAMES = STORE.load()
    if os.getenv('PORT'):
        server = HTTPServer(('0.0.0.0',int(os.environ['PORT'])),Health)
        threading.Thread(target=server.serve_forever,daemon=True).start()
    app = (Application.builder().token(token).concurrent_updates(False)
           .rate_limiter(AIORateLimiter(max_retries=2)).post_init(post_init)
           .connect_timeout(20).read_timeout(30).write_timeout(30).build())
    for name,handler in [('start',start),('setup',INLINE.setup),('newgame',newgame),('hand',hand),('status',status),('rules',rules),('cancel',cancel)]:
        app.add_handler(CommandHandler(name,handler))
    app.add_handler(CallbackQueryHandler(callback,pattern=r'^ll:'))
    app.add_handler(CallbackQueryHandler(INLINE.callback,pattern=r'^ix:'))
    app.add_handler(InlineQueryHandler(INLINE.query))
    app.add_handler(ChosenInlineResultHandler(INLINE.chosen))
    app.add_error_handler(errors)
    app.run_polling(allowed_updates=['message','callback_query','inline_query','chosen_inline_result'],drop_pending_updates=True)

if __name__ == '__main__':
    main()
