import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import bot
from engine import Game, Player
from storage import Store

def test_callback_length_and_private_controls():
    g=Game(-1001234567890,1234567890)
    g.players=[Player(1234567890,'a',hand=[1,9]),Player(2,'b',hand=[5])]
    g.stage='playing'
    for markup in (bot.private_keys(g,0),bot.group_keys(g)):
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data:assert len(button.callback_data.encode())<=64
    group_text=' '.join(b.text for row in bot.group_keys(g).inline_keyboard for b in row)
    assert '公主' not in group_text

def test_public_hand_command_never_sends_cards():
    message=SimpleNamespace(reply_text=AsyncMock())
    g=Game(-200,1)
    bot.GAMES[-200]=g
    update=SimpleNamespace(effective_chat=SimpleNamespace(type='supergroup',id=-200),effective_message=message)
    asyncio.run(bot.hand(update,None))
    assert message.reply_text.await_count==1
    assert '個人選牌' in message.reply_text.call_args.args[0]

def test_adapter_full_turn_and_stale_click(tmp_path):
    async def run():
        bot.STORE=Store(str(tmp_path/'ui.db'))
        bot.USERNAME='example_bot'
        g=Game(-100,1)
        g.players=[Player(1,'Jim',hand=[2,9]),Player(2,'Amy',hand=[5])]
        g.deck=[0,1,3,4]
        g.stage='playing'
        bot.GAMES[g.chat_id]=g
        fake=SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=22)),edit_message_media=AsyncMock(),send_message=AsyncMock())
        ctx=SimpleNamespace(bot=fake,application=SimpleNamespace(bot=fake))
        message=SimpleNamespace(reply_text=AsyncMock())
        q=SimpleNamespace(data=bot.code(g,'play',0),answer=AsyncMock(),message=message)
        u=SimpleNamespace(callback_query=q,effective_user=SimpleNamespace(id=1),effective_chat=SimpleNamespace(type='private'),effective_message=message)
        await bot.callback(u,ctx)
        assert g.phase=='target'
        await bot.callback(u,ctx)
        assert g.phase=='target' and message.reply_text.await_count==1
        q.data=bot.code(g,'target',1)
        await bot.callback(u,ctx)
        assert g.turn==1
        assert all(call.args[0]==-100 for call in fake.send_message.call_args_list)
        assert g.secret_notes['1']==['祭司情報：Amy 的手牌是 5 王子。']
        assert not any('5 王子' in call.args[1] for call in fake.send_message.call_args_list)
        assert not g.private
        assert bot.STORE.load()[-100].turn==1
    asyncio.run(run())
