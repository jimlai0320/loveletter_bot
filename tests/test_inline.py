import asyncio
import time
from collections import defaultdict
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from telegram import InlineQueryResultCachedPhoto
from engine import Game,Player
from storage import Store
from inline_ui import InlineUI
import bot

@pytest.fixture
def env(tmp_path):
    store=Store(str(tmp_path/'test.db'))
    g=Game(-100,1,room_title='測試宮廷')
    g.players=[Player(1,'Jim',hand=[2,9]),Player(2,'Amy',hand=[5]),Player(3,'Tom',hand=[8])]
    g.deck=[0,1,3,4,6]
    g.stage='playing'
    state=NS(STORE=store,GAMES={-100:g},LOCKS=defaultdict(asyncio.Lock),publish=AsyncMock(),group_keys=lambda g:None,log=NS(warning=lambda *a:None))
    ui=InlineUI(state)
    store.set_meta(ui.cache_key,{str(v):f'photo_{v}' for v in range(10)})
    fake=NS(send_photo=AsyncMock(),edit_message_text=AsyncMock(),send_message=AsyncMock())
    ctx=NS(bot=fake,application=NS(bot=fake),user_data={})
    return ui,state,g,ctx

def test_gallery_preview_secret_but_outgoing_neutral(env):
    ui,_,g,_=env
    results=ui.gallery(g,1)
    assert all(isinstance(x,InlineQueryResultCachedPhoto) for x in results)
    assert [x.photo_file_id for x in results]==['photo_2','photo_9']
    for x in results:
        assert '公主' not in x.input_message_content.message_text
        assert '祭司' not in x.input_message_content.message_text
        assert len(x.id.encode())<=64
        assert x.reply_markup.inline_keyboard[0][0].callback_data.startswith('ix:')

def test_no_other_player_hands(env):
    ui,_,g,_=env
    assert ui.gallery(g,99)[0].title=='你未加入這個牌桌'
    waiting=ui.gallery(g,2)
    assert [x.photo_file_id for x in waiting]==['photo_5']
    assert waiting[0].reply_markup is None

def test_personal_zero_cache(env):
    ui,_,g,ctx=env
    q=NS(query=g.gid,from_user=NS(id=1),answer=AsyncMock())
    asyncio.run(ui.query(NS(inline_query=q),ctx))
    assert q.answer.call_args.kwargs=={'cache_time':0,'is_personal':True}

def test_feedback_then_fallback_is_idempotent(env):
    ui,state,g,ctx=env
    token=ui.gallery(g,1)[0].id
    async def run():
        await ui.chosen(NS(chosen_inline_result=NS(result_id=token,from_user=NS(id=1),inline_message_id='inlineA')),ctx)
        revision=g.rev
        q=NS(data='ix:'+token,from_user=NS(id=1),inline_message_id='inlineA',answer=AsyncMock())
        await ui.callback(NS(callback_query=q),ctx)
        assert g.rev==revision and g.phase=='target'
        assert ctx.bot.send_photo.await_count==1
        assert ctx.bot.send_photo.call_args.args[0]==g.chat_id
        assert ctx.bot.send_photo.call_args.kwargs['photo']=='photo_2'
        assert state.STORE.choice(token)['done']==1
    asyncio.run(run())

def test_fallback_before_feedback_idempotent(env):
    ui,_,g,ctx=env
    token=ui.gallery(g,1)[0].id
    async def run():
        q=NS(data='ix:'+token,from_user=NS(id=1),inline_message_id='inlineA',answer=AsyncMock())
        await ui.callback(NS(callback_query=q),ctx)
        await ui.chosen(NS(chosen_inline_result=NS(result_id=token,from_user=NS(id=1),inline_message_id='inlineA')),ctx)
        assert ctx.bot.send_photo.await_count==1
    asyncio.run(run())

def test_wrong_user_cannot_execute_or_edit(env):
    ui,_,g,ctx=env
    token=ui.gallery(g,1)[0].id
    q=NS(data='ix:'+token,from_user=NS(id=2),inline_message_id='inlineA',answer=AsyncMock())
    asyncio.run(ui.callback(NS(callback_query=q),ctx))
    assert g.rev==0 and g.current.hand==[2,9]
    assert q.answer.call_args.kwargs['show_alert']
    ctx.bot.edit_message_text.assert_not_awaited()

def test_stale_result_never_posts_secret_photo(env):
    ui,_,g,ctx=env
    token=ui.gallery(g,1)[1].id
    g.act(1,'play',0)
    asyncio.run(ui.chosen(NS(chosen_inline_result=NS(result_id=token,from_user=NS(id=1),inline_message_id='inlineA')),ctx))
    ctx.bot.send_photo.assert_not_awaited()
    assert '舊按鈕' in ctx.bot.edit_message_text.call_args.kwargs['text']

def test_expired_and_old_room_results(env):
    ui,state,g,ctx=env
    token=ui.gallery(g,1)[0].id
    state.STORE.db.execute('UPDATE choices SET expires=0 WHERE token=?',(token,))
    state.STORE.db.commit()
    with pytest.raises(ValueError):asyncio.run(ui.commit(ctx,token,1))
    token=ui.gallery(g,1)[0].id
    state.GAMES[-100]=Game(-100,1)
    with pytest.raises(ValueError):asyncio.run(ui.commit(ctx,token,1))
    ctx.bot.send_photo.assert_not_awaited()

def test_chancellor_never_sends_keep_or_return_cards(env):
    ui,_,g,ctx=env
    g.current.hand=[6,9]
    g.act(1,'play',0)
    choices=ui.gallery(g,1)
    assert len(choices)==3
    assert all('公主' not in x.input_message_content.message_text for x in choices)
    async def run():
        await ui.commit(ctx,choices[0].id,1,'inlineA')
        assert g.phase=='order'
        remaining=ui.gallery(g,1)
        assert len(remaining)==2
        await ui.commit(ctx,remaining[1].id,1,'inlineB')
        assert g.players[0].hand==[9]
        ctx.bot.send_photo.assert_not_awaited()
    asyncio.run(run())

def test_countess_illegal_option_view_only(env):
    ui,_,g,_=env
    g.current.hand=[5,8]
    results=ui.gallery(g,1)
    assert results[0].reply_markup is None
    assert results[1].reply_markup is not None

def test_pending_ticket_survives_restart(env):
    ui,state,g,ctx=env
    token=ui.gallery(g,1)[0].id
    state.STORE.save(g)
    state.GAMES=state.STORE.load()
    asyncio.run(ui.commit(ctx,token,1,'inlineA'))
    assert state.GAMES[-100].phase=='target'

def test_notes_alert_only_for_authorized_user(env):
    _,state,g,ctx=env
    bot.STORE=state.STORE;bot.GAMES={-100:g};bot.LOCKS=defaultdict(asyncio.Lock)
    g.secret_notes={'1':['祭司情報：Amy 的手牌是 5 王子。']}
    async def run():
        for uid in (1,2,999):
            q=NS(data=bot.code(g,'notes'),answer=AsyncMock())
            update=NS(callback_query=q,effective_user=NS(id=uid))
            await bot.callback(update,ctx)
            assert q.answer.call_args.kwargs['show_alert']
            alert=q.answer.call_args.args[0]
            assert ('Amy' in alert)==(uid==1)
        ctx.bot.send_message.assert_not_awaited()
    asyncio.run(run())

def test_group_target_button_checks_turn_and_updates(env):
    _,state,g,ctx=env
    bot.STORE=state.STORE;bot.GAMES={-100:g};bot.LOCKS=defaultdict(asyncio.Lock)
    ctx.bot.send_photo=AsyncMock(return_value=NS(message_id=22))
    ctx.bot.edit_message_media=AsyncMock()
    g.act(1,'play',0)
    message=NS(reply_text=AsyncMock())
    async def run():
        for uid in (2,1):
            q=NS(data=bot.code(g,'target',1),answer=AsyncMock(),message=message)
            u=NS(callback_query=q,effective_user=NS(id=uid),effective_chat=NS(type='supergroup',id=-100),effective_message=message)
            await bot.callback(u,ctx)
            if uid==2:assert g.phase=='target'
        assert g.turn==1
        assert g.secret_notes['1']==['祭司情報：Amy 的手牌是 5 王子。']
    asyncio.run(run())

def test_setup_upload_cache_bound_to_bot_identity(env):
    ui,_,_,ctx=env
    ui.bot_id=123
    assert not ui.ready()
    ctx.bot.send_media_group=AsyncMock(return_value=[NS(photo=[NS(file_id=f'new_{v}')]) for v in range(10)])
    msg=NS(reply_text=AsyncMock())
    u=NS(effective_chat=NS(type='private'),effective_user=NS(id=1),effective_message=msg)
    asyncio.run(ui.setup(u,ctx))
    assert ui.ready()
    ui.bot_id=456
    assert not ui.ready()
