"""Deterministic Chinese card and public-table rendering."""
from functools import lru_cache
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
from engine import NAMES, RULES, COUNTS, card

ROOT = Path(__file__).resolve().parent
BG = '#24171e'
PANEL = '#36232c'
GOLD = '#c9a66c'
CREAM = '#f4e8d1'
MUTED = '#bea99b'

@lru_cache(maxsize=32)
def font(size):
    return ImageFont.truetype(str(ROOT / 'assets/fonts/NotoSansTC-Regular.otf'), size)

def text(d, xy, s, size=24, fill=CREAM):
    d.text(xy, str(s), font=font(size), fill=fill)

def wrap(d, s, width, size):
    lines, line = [], ''
    for c in s:
        if d.textlength(line+c, font=font(size)) > width:
            if c in '，。；：！？、）】' and len(line)>1:
                lines.append(line[:-1])
                line = line[-1]
            else:
                lines.append(line)
                line = ''
        line += c
    if line:
        lines.append(line)
    return lines

def fit_name(d, s, width, size=28):
    while d.textlength(s, font=font(size)) > width and len(s) > 1:
        s = s[:-2] + '…'
    return s

@lru_cache(maxsize=10)
def physical_template(v):
    with Image.open(ROOT / 'assets/physical_cards.png') as im:
        w, h = im.size
        x, y = v % 5, v // 5
        return im.crop((round(x*w/5), round(y*h/2), round((x+1)*w/5), round((y+1)*h/2))).convert('RGB')

@lru_cache(maxsize=10)
def portrait(v):
    im=physical_template(v)
    w,h=im.size
    return im.crop((round(w*.09),round(h*.14),round(w*.92),round(h*.72)))

@lru_cache(maxsize=20)
def card_font(size):
    return ImageFont.truetype(str(ROOT/'assets/fonts/NotoSerifTC-Regular.otf'),size)

@lru_cache(maxsize=10)
def card_image(v):
    im=physical_template(v).resize((500,700),Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(im)
    d.text((87,70),str(v),font=card_font(100),fill='#fff2ca',anchor='mm',stroke_width=1)
    d.text((302,51),NAMES[v],font=card_font(50),fill='#31261b',anchor='mm',stroke_width=1)
    size=27
    while True:
        lines=[];line=''
        for c in RULES[v]:
            if d.textlength(line+c,font=card_font(size))>410:
                if c in '，。；：！？、）】' and len(line)>1:
                    lines.append(line[:-1]);line=line[-1]
                else:lines.append(line);line=''
            line+=c
        if line:lines.append(line)
        if len(lines)<=3 or size==20:break
        size-=1
    top=548+(104-len(lines)*(size+8))//2
    for i,line in enumerate(lines):
        d.text((250,top+i*(size+8)),line,font=card_font(size),fill='#493623',anchor='mt')
    # Deck quantity is secondary, on the left frame below the rank seal.
    for i in range(COUNTS[v]):
        y=167+i*15
        d.ellipse((22,y,29,y+7),fill='#a74839',outline='#f9e3a5')
    return im.resize((420,588),Image.Resampling.LANCZOS)

def canvas(w, h, title, subtitle):
    im = Image.new('RGB', (w,h), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((14,14,w-15,h-15), outline=GOLD, width=2)
    text(d, (34,25), title, 42)
    text(d, (36,91), subtitle, 21, GOLD)
    d.line((34,131,w-34,131), fill=GOLD, width=1)
    return im, d

def hand_image(g, index):
    p = g.players[index]
    values = p.hand
    if g.stage == 'playing' and g.turn == index and g.phase == 'order':
        values = g.pending['return']
    n = max(1, len(values))
    w = 900 if n <= 2 else 1320
    im, d = canvas(w, 830, '情書  /  你的密函', f'第 {g.round_no} 局  ·  {p.name[:18]}  ·  好感 {p.score} / {g.goal}')
    for i, v in enumerate(values):
        x = (w - n*420 - (n-1)*12)//2 + i*432
        im.paste(card_image(v), (x,163))
        text(d, (x+12,769), f'選項 {i+1}  ·  {card(v)}', 25, GOLD)
    if not values:
        text(d, (85,370), '本局已出局，下一局再接再厲。', 32)
    return im

def board_image(g):
    im, d = canvas(900, 1210, '情 書', 'LOVE LETTER  /  宮廷密函  /  六人版')
    im.paste(ImageOps.fit(portrait(9), (170,106), centering=(0.5,0)), (694,24))
    d.rectangle((694,24,864,130),outline=GOLD,width=1)
    labels = {'lobby':'等待入席', 'playing':f'第 {g.round_no} 局', 'round_end':'本局揭曉', 'match_end':'最終加冕'}
    text(d, (38,151), labels[g.stage], 32)
    sub = f'{len(g.players)} / 6 位玩家' if g.stage == 'lobby' else f'牌庫 {len(g.deck):02d} 張  ·  目標 {g.goal} 枚好感'
    text(d, (38,202), sub, 24, GOLD)
    for i in range(6):
        x, y = 34+(i%2)*426, 259+(i//2)*200
        active = g.stage == 'playing' and i == g.turn
        d.rounded_rectangle((x,y,x+406,y+181), radius=18, fill=PANEL, outline=GOLD if active else '#61454b', width=3 if active else 1)
        if i >= len(g.players):
            text(d, (x+28,y+37), f'{i+1:02d}  等待入席', 28, MUTED)
            continue
        p = g.players[i]
        text(d, (x+20,y+15), fit_name(d, f'{i+1:02d}  {p.name}', 355), 28)
        state = '電腦' if p.ai else '玩家'
        if g.stage != 'lobby':
            state = '已出局' if not p.alive else '保護中' if p.protected else '正在行動' if active else '等待中'
        text(d, (x+20,y+61), f'{state}   /   好感 {p.score}', 22, GOLD)
        if g.stage in ('round_end', 'match_end') and p.alive:
            text(d, (x+20,y+99), '持牌：'+card(p.hand[0]), 23)
        elif g.stage == 'lobby':
            text(d, (x+20,y+107), '密函已備妥，靜候開局', 21, MUTED)
        else:
            if p.discards:
                v = p.discards[-1]
                im.paste(ImageOps.fit(portrait(v),(63,88)),(x+325,y+79))
                d.rectangle((x+324,y+78,x+389,y+168),outline=GOLD,width=1)
                d.rectangle((x+325,y+140,x+388,y+167),fill=BG)
                text(d,(x+348,y+137),v,21,GOLD)
            for k, line in enumerate(wrap(d, '棄牌：'+(' · '.join(str(v) for v in p.discards) or '尚無'), 296, 22)[:2]):
                text(d, (x+20,y+99+k*30), line, 22, MUTED)
    text(d, (38,873), '宮廷紀事', 26, GOLD)
    logs = g.log[-3:] or ['加入座位後，由房主開始遊戲。', '可加入電腦，補滿六人立即試玩。']
    y = 921
    for s in logs:
        for line in wrap(d, s, 818, 23)[:2]:
            text(d, (40,y), line, 23)
            y += 33
        y += 7
    text(d, (38,1150), '群組選圖出牌  ·  只有本人看得到選牌內容', 21, MUTED)
    return im

def photo(im):
    buf = BytesIO()
    im.save(buf, format='JPEG', quality=90)
    buf.seek(0)
    buf.name = 'loveletter.jpg'
    return buf

def reference_image():
    im = Image.new('RGB', (2160,1250), BG)
    for v in range(10):
        im.paste(card_image(v), (12+(v%5)*432,24+(v//5)*614))
    return im
