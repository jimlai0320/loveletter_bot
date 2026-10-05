from pathlib import Path
from engine import Game, Player
from render import board_image,hand_image,reference_image,card_image

out=Path('preview')
out.mkdir(exist_ok=True)
g=Game(-100,1)
g.players=[Player(i+1,n,hand=[v],score=s) for i,(n,v,s) in enumerate([
    ('Jim',9,1),('小安',2,0),('阿哲',7,2),('Mia',4,1),('宮廷使者 5',5,0),('宮廷使者 6',8,1)])]
g.stage='playing';g.round_no=2;g.deck=[1]*9
g.players[0].hand=[9,2]
g.players[1].discards=[1,0]
g.players[2].discards=[1]
g.players[3].discards=[4];g.players[3].protected=True
g.players[4].discards=[3,5];g.players[4].alive=False;g.players[4].hand=[]
g.players[4].ai=True;g.players[5].ai=True
g.log=['Mia 打出 4 侍女。','Mia 獲得保護，直到下次行動。','輪到 Jim，請前往私訊選牌。']
board_image(g).save(out/'group_table.png')
hand_image(g,0).save(out/'private_hand.png')
reference_image().save(out/'all_characters.jpg',quality=94)
for v in range(10):card_image(v).save(out/f'card_{v}.png')
print('Generated group table, private hand, and ten rendered character cards.')
