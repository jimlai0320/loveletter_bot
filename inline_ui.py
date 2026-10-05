"""Personal inline galleries. Outgoing selections NEVER contain secret cards.

Telegram doesn't disclose the destination chat in chosen_inline_result. Each
opaque choice therefore applies exclusively to its original, named game room;
the authoritative announcement is sent by the bot to that bound room.
"""
import asyncio
import time
from telegram import (InlineKeyboardButton as B, InlineKeyboardMarkup as K,
                      InlineQueryResultCachedPhoto, InlineQueryResultArticle,
                      InputTextMessageContent, InputMediaPhoto)
from telegram.error import TelegramError
from engine import card
from render import card_image,photo

ASSET_VERSION='physical_v2'

class InlineUI:
    def __init__(self,state):
        self.s=state
        self.setup_lock=asyncio.Lock()
        self.bot_id=0
    @property
    def cache_key(self):
        return f'cards:{self.bot_id}:{ASSET_VERSION}'
    def cards(self):
        return self.s.STORE.get_meta(self.cache_key,{}) if self.s.STORE else {}
    def ready(self):
        return all(str(i) in self.cards() for i in range(10))
    async def setup(self,update,ctx):
        if update.effective_chat.type!='private':
            await update.effective_message.reply_text('請由房主私訊 BOT 執行 /setup，初始化一次圖片。')
            return
        async with self.setup_lock:
            if self.ready() and getattr(ctx,'args',[])!=['refresh']:
                await update.effective_message.reply_text('圖片已準備好。回群組 /newgame，或在現有牌桌按開始。')
                return
            await update.effective_message.reply_text('正在準備十張實體卡風格圖片，只需做一次。遊戲中可留在群組操作。')
            media=[InputMediaPhoto(photo(card_image(v)),caption=card(v)) for v in range(10)]
            messages=await ctx.bot.send_media_group(update.effective_user.id,media=media,disable_notification=True)
            if len(messages)!=10 or any(not m.photo for m in messages):
                raise RuntimeError('Incomplete card upload')
            self.s.STORE.set_meta(self.cache_key,{str(v):m.photo[-1].file_id for v,m in enumerate(messages)})
            await update.effective_message.reply_text('十張圖片已就緒。請確認 BotFather 已設定 /setinline 與 /setinlinefeedback（100%），再回群組開桌。')

    @staticmethod
    def info(title,description=''):
        return InlineQueryResultArticle(id='info',title=title,description=description,
                                       input_message_content=InputTextMessageContent('💌 請回情書牌桌使用最新操作按鈕。'))

    def gallery(self,g,uid):
        p=next((p for p in g.players if p.uid==uid),None)
        if p is None:return [self.info('你未加入這個牌桌')]
        if g.stage!='playing':return [self.info('等待房主開始下一局')]
        if not p.alive:return [self.info('本局已出局，下一局再接再厲')]
        if not self.ready():return [self.info('圖片尚未初始化','請房主私訊 /setup')]
        if uid==g.current.uid and g.phase in ('target','guess'):
            return [self.info('請回群組按鈕選目標／猜角色')]
        active=uid==g.current.uid
        action = g.phase if active else None
        vals=g.pending['return'] if active and g.phase=='order' else p.hand
        legal=g.legal_cards() if active and g.phase=='play' else list(range(len(vals)))
        result=[]
        for i,v in enumerate(vals):
            enabled=active and action in ('play','keep','order') and i in legal
            if action=='keep':title=f'保留｜{card(v)}'
            elif action=='order':title=f'牌庫底較先抽到｜{card(v)}'
            elif enabled:title=f'打出｜{card(v)}'
            else:title=f'僅查看｜{card(v)}'
            caption = f'💌 正在處理「{g.room_title}」的選擇。\n若未自動完成，請本人按下方「送出操作」。' if enabled else '💌 已查看自己的手牌。'
            token=self.s.STORE.ticket(g,uid,action,i) if enabled else None
            markup=K([[B('送出操作',callback_data=f'ix:{token}')]]) if token else None
            # Only the preview contains the role; sending always uses neutral text.
            # This also protects stale selections and Chancellor choices.
            result.append(InlineQueryResultCachedPhoto(
                id=token or f'view_{i}',photo_file_id=self.cards()[str(v)],
                title=title,description='只有你能看見此選牌預覽',
                input_message_content=InputTextMessageContent(caption),reply_markup=markup))
        return result

    async def query(self,update,ctx):
        q=update.inline_query
        parts=q.query.strip().split()
        gid=parts[0] if parts else None
        g=next((x for x in self.s.GAMES.values() if x.gid==gid),None) if gid else self.s.active_for(q.from_user.id)
        if not g:
            results=[self.info('請先到群組加入情書牌桌')]
        else:
            async with self.s.LOCKS[g.chat_id]:
                results=self.gallery(g,q.from_user.id)
        await q.answer(results,cache_time=0,is_personal=True)

    async def finish_message(self,bot,message_id,text):
        if not message_id:return
        try:
            await bot.edit_message_text(inline_message_id=message_id,text=text,reply_markup=K([]))
        except TelegramError:
            pass  # Authoritative board is independent of inline message delivery.

    async def commit(self,ctx,token,uid,inline_message_id=None):
        ticket=self.s.STORE.choice(token)
        if not ticket or ticket['uid']!=uid:
            raise ValueError('這不是你的選牌操作。')
        async with self.s.LOCKS[ticket['chat_id']]:
            ticket=self.s.STORE.choice(token)
            if ticket['done']:
                await self.finish_message(ctx.bot,inline_message_id,'💌 此操作已完成，請查看群組最新牌桌。')
                return
            g=self.s.GAMES.get(ticket['chat_id'])
            if not g or g.gid!=ticket['gid'] or time.time()>ticket['expires']:
                raise ValueError('選牌已過期，請重新開啟選牌。')
            if g.deadline and time.time()>g.deadline:
                raise ValueError('行動時間已到，請等系統代打後查看最新牌桌。')
            played=None
            if ticket['action']=='play' and g.stage=='playing' and ticket['rev']==g.rev and uid==g.current.uid:
                played=g.current.hand[ticket['value']]
            name=g.current.name
            g.act(uid,ticket['action'],ticket['value'],ticket['rev'])
            self.s.STORE.commit_choice(g,token)
            # Only a validated played card becomes public, always in its source room.
            if played is not None:
                try:
                    await ctx.bot.send_photo(g.chat_id,photo=self.cards()[str(played)],
                                             caption=f'{name} 打出 {card(played)}。',
                                             reply_markup=self.s.group_keys(g))
                except TelegramError:
                    self.s.log.warning('Played-card image delivery failed; public log remains available.')
            label='已出牌' if played is not None else '已完成秘密選擇'
            await self.finish_message(ctx.bot,inline_message_id,f'💌 {label}，請查看「{g.room_title}」的最新牌桌。')
            await self.s.publish(ctx.application,g)

    async def chosen(self,update,ctx):
        r=update.chosen_inline_result
        if r.result_id=='info' or r.result_id.startswith('view_'):return
        try:
            await self.commit(ctx,r.result_id,r.from_user.id,r.inline_message_id)
        except ValueError as e:
            await self.finish_message(ctx.bot,r.inline_message_id,'💌 '+str(e))

    async def callback(self,update,ctx):
        q=update.callback_query
        token=q.data.split(':',1)[1]
        ticket=self.s.STORE.choice(token)
        if not ticket or ticket['uid']!=q.from_user.id:
            await q.answer('這不是你的選牌操作。',show_alert=True)
            return
        await q.answer()
        try:
            await self.commit(ctx,token,q.from_user.id,q.inline_message_id)
        except ValueError as e:
            await self.finish_message(ctx.bot,q.inline_message_id,'💌 '+str(e))
