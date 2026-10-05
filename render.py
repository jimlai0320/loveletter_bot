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
    # Compact aspect ratio and large type keep the group thumbnail readable.
    # Detailed action logs remain in the Telegram caption below the picture.
    im = Image.new('RGB', (1000, 820), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((12,12,987,807), outline=GOLD, width=3)
    labels = {'lobby':'等待入席', 'playing':f'第 {g.round_no} 局',
              'round_end':'本局揭曉', 'match_end':'最終加冕'}
    text(d, (32,20), '情書', 52)
    text(d, (170,35), labels[g.stage], 36, GOLD)
    sub = (f'{len(g.players)} / 6 人已入席' if g.stage == 'lobby'
           else f'牌庫 {len(g.deck)} 張  ·  目標 {g.goal} 好感')
    text(d, (34,94), sub, 32)
    im.paste(ImageOps.fit(portrait(9), (154,112), centering=(0.5,0)), (812,30))
    d.rectangle((812,30,966,142),outline=GOLD,width=2)
    for i in range(6):
        x, y = 32+(i%2)*476, 164+(i//2)*200
        active = g.stage == 'playing' and i == g.turn
        d.rounded_rectangle((x,y,x+460,y+188), radius=16, fill=PANEL,
                            outline=GOLD if active else '#73545d', width=4 if active else 2)
        if i >= len(g.players):
            text(d, (x+20,y+54), f'{i+1}  等待入席', 38, MUTED)
            continue
        p = g.players[i]
        text(d, (x+18,y+7), fit_name(d, f'{i+1}  {p.name}', 421, 38), 38)
        state = '電腦' if p.ai else '玩家'
        if g.stage != 'lobby':
            state = '已出局' if not p.alive else '保護中' if p.protected else '行動中' if active else '等待中'
        text(d, (x+18,y+64), f'{state} · 好感 {p.score}', 30, GOLD)
        revealed = (g.stage in ('round_end', 'match_end') and p.alive and p.hand)
        v = p.hand[0] if revealed else p.discards[-1] if p.discards else None
        if g.stage == 'lobby':
            text(d, (x+18,y+117), '已入席，準備開局', 30, MUTED)
        else:
            if revealed:
                detail = '持牌 '+card(p.hand[0])
            else:
                # Full discard history is available through the group button.
                values = ' '.join(str(n) for n in p.discards[-5:])
                detail = '棄牌 '+(('…' if len(p.discards)>5 else '')+values or '尚無')
            for k, line in enumerate(wrap(d, detail, 304, 30)[:2]):
                text(d, (x+18,y+109+k*34), line, 30, MUTED)
            if v is not None:
                im.paste(ImageOps.fit(portrait(v),(108,120)),(x+335,y+61))
                d.rectangle((x+334,y+60,x+444,y+182),outline=GOLD,width=2)
                d.rectangle((x+335,y+137,x+443,y+181),fill=BG)
                d.text((x+389,y+132), str(v), font=font(38), fill=CREAM, anchor='mt')
    text(d, (34,764), '金框：目前回合  ·  完整棄牌請按下方按鈕', 26, GOLD)
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
