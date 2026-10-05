from collections import Counter
import random
import pytest
from engine import Game, Player, COUNTS
from storage import Store

def setup(hands, deck=None):
    g = Game(-100,1)
    g.players = [Player(i+1,f'P{i+1}',hand=h[:]) for i,h in enumerate(hands)]
    g.stage = 'playing'
    g.deck = deck[:] if deck is not None else [1,2,3,4,5]
    g.reserve = 0
    return g

def play(g,index=0,target=None,guess=None):
    uid = g.current.uid
    g.act(uid,'play',index)
    if target is not None:
        g.act(uid,'target',target)
    if guess is not None:
        g.act(uid,'guess',guess)

def test_counts_and_setup():
    g = Game(-1,1)
    for i in range(6): g.join(i+1,str(i))
    g.new_round()
    assert sum(COUNTS)==21
    assert len(g.deck)==13
    assert len(g.current.hand)==2
    assert g.goal==3

def test_two_player_setup():
    g=Game(-1,1)
    g.join(1,'a'); g.join(2,'b'); g.new_round()
    assert len(g.exposed)==3 and len(g.deck)==14 and g.goal==6

@pytest.mark.parametrize('other',[5,7])
def test_countess_forced(other):
    g=setup([[other,8],[2]])
    before=g.dumps()
    with pytest.raises(ValueError): g.act(1,'play',0)
    assert g.dumps()==before
    play(g,1)
    assert g.players[0].discards==[8]

def test_countess_chancellor_not_forced():
    g=setup([[6,8],[2]],deck=[5,7,1])
    play(g)
    g.act(1,'keep',1)
    assert g.current.hand==[5]
    g.act(1,'order',1)
    assert g.deck==[7,8]

def test_guard_correct_and_protected():
    g=setup([[1,9],[2],[3]])
    g.players[2].protected=True
    play(g)
    with pytest.raises(ValueError):g.act(1,'target',2)
    g.act(1,'target',1)
    with pytest.raises(ValueError):g.act(1,'guess',1)
    g.act(1,'guess',2)
    assert not g.players[1].alive
    assert g.turn==2 and not g.current.protected

def test_priest_private():
    g=setup([[2,8],[9],[4]])
    play(g,target=1)
    assert g.private==[[1,'祭司情報：P2 的手牌是 9 公主。']]
    assert not any('公主' in s for s in g.log)

def test_baron_tie_and_loss():
    g=setup([[3,4],[4],[9]])
    play(g,target=1)
    assert all(p.alive for p in g.players)
    g=setup([[3,4],[8],[9]])
    play(g,target=1)
    assert not g.players[0].alive
    assert len(g.private)==2

def test_handmaid_expires_at_start_only():
    g=setup([[4,9],[0],[1]],deck=[0,0,1,2,3,4])
    play(g)
    assert g.players[0].protected
    play(g)
    assert g.players[0].protected
    play(g,index=0)
    assert g.phase=='target'
    assert 0 not in g.targets(1)
    g.act(3,'target',1); g.act(3,'guess',9)
    assert g.turn==0 and not g.players[0].protected

def test_all_protected_effect_skips():
    g=setup([[1,9],[8],[2]])
    for p in g.players[1:]: p.protected=True
    play(g)
    assert g.turn==1

def test_prince_self_when_all_protected():
    g=setup([[5,9],[8],[2]])
    for p in g.players[1:]: p.protected=True
    play(g)
    assert g.targets(5)==[0]
    g.act(1,'target',0)
    assert not g.players[0].alive

def test_prince_draws_reserve():
    g=setup([[5,7],[2]],deck=[])
    play(g,target=1)
    assert g.players[1].hand==[0]
    assert g.reserve is None and g.stage=='round_end'

def test_prince_princess_no_redraw():
    g=setup([[5,7],[9],[2]])
    play(g,target=1)
    assert not g.players[1].alive and g.players[1].hand==[]
    assert g.players[1].discards==[9]

@pytest.mark.parametrize('deck', [[],[2],[2,3,4]])
def test_chancellor_deck_edges(deck):
    g=setup([[6,9],[5]],deck=deck)
    play(g)
    if deck:
        assert g.phase=='keep'
        g.act(1,'keep',0)
        if g.phase=='order':g.act(1,'order',1)
    assert g.players[0].hand==[9]

def test_king_swaps():
    g=setup([[7,9],[2],[1]])
    play(g,target=1)
    assert g.players[0].hand==[2]
    assert g.players[1].hand[0]==9

def test_princess_play_eliminates():
    g=setup([[9,2],[8]])
    play(g)
    assert g.players[0].discards==[9,2]
    assert g.players[1].score==1

def test_tied_winners_no_discard_tiebreak():
    g=setup([[0,7],[7]],deck=[])
    g.players[1].discards=[8,5]
    play(g)
    assert g.winners==[0,1]
    assert [p.score for p in g.players]==[2,1]

def test_spy_only_survivors():
    g=setup([[1,8],[9],[2]],deck=[])
    g.players[0].discards=[0,0]
    g.players[2].discards=[0]
    play(g,target=2,guess=2)
    assert g.players[0].score==1
    assert g.players[1].score==1

def test_two_spy_survivors_no_bonus():
    g=setup([[0,8],[9]],deck=[])
    g.players[1].discards=[0]
    play(g)
    assert [p.score for p in g.players]==[0,1]

def test_simultaneous_match_winners():
    g=setup([[0,7],[7],[2],[3],[4],[5]],deck=[])
    g.players[0].score=1
    g.players[1].score=2
    play(g)
    assert g.champions==[0,1]
    assert g.stage=='match_end'

def test_unauthorized_stale_and_duplicate():
    g=setup([[2,8],[9]])
    with pytest.raises(ValueError):g.act(2,'play',0)
    g.act(1,'play',0,0)
    with pytest.raises(ValueError):g.act(1,'target',1,0)
    g.act(1,'target',1,g.rev)
    with pytest.raises(ValueError):g.act(1,'target',1,g.rev)

def test_storage_roundtrip_pending(tmp_path):
    g=setup([[6,9],[5]])
    play(g)
    g.act(1,'keep',0)
    store=Store(str(tmp_path/'test.db'))
    store.save(g)
    loaded=store.load()[g.chat_id]
    assert loaded.dumps()==g.dumps()
    loaded.act(1,'order',0)
    store.delete(g.chat_id)
    assert store.load()=={}

def test_1000_complete_matches_conserve_all_cards():
    random.seed(841)
    expected=Counter({v:n for v,n in enumerate(COUNTS)})
    for match in range(1000):
        g=Game(-1,1)
        for i in range(2+match%5):g.join(i+1,str(i),True)
        g.new_round()
        steps=0
        while g.stage!='match_end':
            if g.stage=='round_end':g.new_round()
            action,value=g.auto_action()
            g.act(g.current.uid,action,value)
            total=g.deck+g.exposed+[v for p in g.players for v in p.hand+p.discards]+g.pending.get('return',[])
            if g.reserve is not None:total.append(g.reserve)
            assert Counter(total)==expected
            assert all(p.hand or not p.alive for p in g.players)
            steps+=1
            assert steps<4000
