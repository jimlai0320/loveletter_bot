"""Pure rules engine. No Telegram dependency; deck index 0 is the top."""
from dataclasses import dataclass, field, asdict
import random
import secrets

NAMES = ['間諜', '守衛', '祭司', '男爵', '侍女', '王子', '大臣', '國王', '女伯爵', '公主']
COUNTS = [2, 6, 2, 2, 2, 2, 2, 1, 1, 1]
RULES = [
    '回合結束時，若存活者中只有你棄過間諜，額外獲得一枚好感。',
    '指定其他玩家，猜測其手牌。不能猜守衛；猜中使對方出局。',
    '指定其他玩家，私下查看其手牌。',
    '與其他玩家私下比牌，點數較低者出局；相同則無事發生。',
    '直到你的下次行動開始前，不受其他玩家指定。',
    '指定任一玩家（可選自己）棄牌並重抽；棄掉公主會出局。',
    '再抽最多兩張，保留一張，其餘依你指定的順序放回牌庫底。',
    '與其他玩家交換手牌。',
    '若同時持有王子或國王，必須打出女伯爵。',
    '打出或棄掉公主，立即出局。',
]

def card(v):
    return f'{v} {NAMES[v]}'

@dataclass
class Player:
    uid: int
    name: str
    ai: bool = False
    hand: list = field(default_factory=list)
    discards: list = field(default_factory=list)
    alive: bool = True
    protected: bool = False
    score: int = 0

@dataclass
class Game:
    chat_id: int
    owner: int
    gid: str = field(default_factory=lambda: secrets.token_hex(4))
    players: list = field(default_factory=list)
    stage: str = 'lobby'
    phase: str = 'play'
    deck: list = field(default_factory=list)
    reserve: int | None = None
    exposed: list = field(default_factory=list)
    turn: int = 0
    round_no: int = 0
    rev: int = 0
    pending: dict = field(default_factory=dict)
    log: list = field(default_factory=list)
    private: list = field(default_factory=list)
    winners: list = field(default_factory=list)
    champions: list = field(default_factory=list)
    deadline: float = 0
    board_id: int | None = None
    dm_ids: dict = field(default_factory=dict)
    room_title: str = '情書牌桌'
    secret_notes: dict = field(default_factory=dict)
    notified_rev: int = -1
    def dumps(self):
        return asdict(self)
    @classmethod
    def loads(cls, data):
        data = dict(data)
        data['players'] = [Player(**p) for p in data['players']]
        return cls(**data)
    @property
    def current(self):
        return self.players[self.turn]
    @property
    def goal(self):
        return {2: 6, 3: 5, 4: 4, 5: 3, 6: 3}.get(len(self.players), 3)
    def say(self, text):
        self.log.append(text)
        self.log = self.log[-30:]
    def tell(self, i, text):
        if not self.players[i].ai:
            self.private.append([self.players[i].uid, text])
    def join(self, uid, name, ai=False):
        if self.stage != 'lobby':
            raise ValueError('遊戲已開始。')
        if any(p.uid == uid for p in self.players):
            raise ValueError('你已在座位上。')
        if len(self.players) >= 6:
            raise ValueError('已滿 6 人。')
        self.players.append(Player(uid, name[:20], ai))
        self.rev += 1
    def new_round(self):
        if self.stage not in ('lobby', 'round_end'):
            raise ValueError('現在不能開始新局。')
        if not 2 <= len(self.players) <= 6:
            raise ValueError('需要 2～6 人；可加入電腦。')
        self.turn = random.choice(self.winners) if self.winners else random.randrange(len(self.players))
        self.deck = [v for v, n in enumerate(COUNTS) for _ in range(n)]
        random.shuffle(self.deck)
        self.reserve = self.deck.pop(0)
        self.exposed = [self.deck.pop(0) for _ in range(3)] if len(self.players) == 2 else []
        for p in self.players:
            p.hand = [self.deck.pop(0)]
            p.discards = []
            p.alive = True
            p.protected = False
        self.round_no += 1
        self.stage = 'playing'
        self.pending = {}
        self.winners = []
        self.champions = []
        self.log = []
        self.private = []
        self.secret_notes = {}
        self.say(f'第 {self.round_no} 局開始，{self.current.name} 先手。')
        self.begin_turn()
    def begin_turn(self):
        self.current.protected = False
        self.current.hand.append(self.deck.pop(0))
        self.phase = 'play'
        self.pending = {}
        self.rev += 1
        self.deadline = 0
    def legal_cards(self):
        h = self.current.hand
        if 8 in h and (5 in h or 7 in h):
            return [i for i, v in enumerate(h) if v == 8]
        return list(range(len(h)))
    def targets(self, value):
        return [i for i, p in enumerate(self.players) if p.alive
                and (i == self.turn and value == 5 or i != self.turn and not p.protected)]
    def eliminate(self, i):
        p = self.players[i]
        p.discards.extend(p.hand)
        self.say(f'{p.name} 出局，棄牌：' + '、'.join(card(v) for v in p.hand))
        p.hand = []
        p.alive = False
        p.protected = False
    def act(self, uid, action, value, revision=None):
        if self.stage != 'playing' or uid != self.current.uid:
            raise ValueError('還沒輪到你，或本局已結束。')
        if revision is not None and revision != self.rev:
            raise ValueError('這是舊按鈕，請使用最新手牌訊息。')
        expected = {'play': 'play', 'target': 'target', 'guess': 'guess', 'keep': 'keep', 'order': 'order'}
        if expected.get(self.phase) != action:
            raise ValueError('操作階段已改變，請使用最新按鈕。')
        p = self.current
        if action == 'play':
            if value not in self.legal_cards():
                raise ValueError('這張牌現在不能出。持有王子／國王時必須出女伯爵。')
            v = p.hand.pop(value)
            p.discards.append(v)
            self.say(f'{p.name} 打出 {card(v)}。')
            self.pending = {'card': v}
            if v in (1, 2, 3, 5, 7):
                if self.targets(v):
                    self.phase = 'target'
                else:
                    self.say('其他玩家均受保護，效果略過。')
                    self.finish_turn()
            elif v == 4:
                p.protected = True
                self.finish_turn()
            elif v == 6 and self.deck:
                p.hand.extend(self.deck.pop(0) for _ in range(min(2, len(self.deck))))
                self.phase = 'keep'
            elif v == 9:
                self.eliminate(self.turn)
                self.finish_turn()
            else:
                self.finish_turn()
        elif action == 'target':
            v = self.pending['card']
            if value not in self.targets(v):
                raise ValueError('不能指定此玩家。')
            self.pending['target'] = value
            t = self.players[value]
            self.say(f'指定 {t.name}。')
            if v == 1:
                self.phase = 'guess'
            else:
                if v == 2:
                    self.tell(self.turn, f'祭司情報：{t.name} 的手牌是 {card(t.hand[0])}。')
                elif v == 3:
                    a, b = p.hand[0], t.hand[0]
                    self.tell(self.turn, f'男爵比牌：你是 {card(a)}，{t.name} 是 {card(b)}。')
                    self.tell(value, f'男爵比牌：你是 {card(b)}，{p.name} 是 {card(a)}。')
                    if a != b:
                        self.eliminate(self.turn if a < b else value)
                    else:
                        self.say('男爵比牌相同，雙方留下。')
                elif v == 5:
                    old = t.hand.pop()
                    t.discards.append(old)
                    self.say(f'{t.name} 棄掉 {card(old)}。')
                    if old == 9:
                        self.eliminate(value)
                    elif self.deck:
                        t.hand = [self.deck.pop(0)]
                    else:
                        assert self.reserve is not None
                        t.hand = [self.reserve]
                        self.reserve = None
                elif v == 7:
                    p.hand, t.hand = t.hand, p.hand
                    self.tell(self.turn, f'交換後，你的手牌是 {card(p.hand[0])}。')
                    self.tell(value, f'國王交換：你收到 {card(t.hand[0])}。')
                self.finish_turn()
        elif action == 'guess':
            if value not in range(10) or value == 1:
                raise ValueError('不能猜守衛。')
            ti = self.pending['target']
            self.say(f'{p.name} 猜測 {self.players[ti].name} 持有 {card(value)}。')
            if self.players[ti].hand[0] == value:
                self.eliminate(ti)
            else:
                self.say('猜錯，對方安全。')
            self.finish_turn()
        elif action == 'keep':
            if value not in range(len(p.hand)):
                raise ValueError('無效卡牌。')
            keep = p.hand[value]
            others = p.hand[:value] + p.hand[value+1:]
            p.hand = [keep]
            if len(others) == 2:
                self.pending['return'] = others
                self.phase = 'order'
            else:
                self.deck.extend(others)
                self.finish_turn()
        elif action == 'order':
            if value not in (0, 1):
                raise ValueError('無效順序。')
            r = self.pending.pop('return')
            self.deck.extend([r[value], r[1-value]])
            self.finish_turn()
        self.rev += 1
    def finish_turn(self):
        self.pending = {}
        self.phase = 'play'
        alive = [i for i, p in enumerate(self.players) if p.alive]
        if len(alive) == 1 or not self.deck:
            best = max(self.players[i].hand[0] for i in alive)
            self.winners = [i for i in alive if self.players[i].hand[0] == best]
            for i in self.winners:
                self.players[i].score += 1
            self.say('本局勝者：' + '、'.join(self.players[i].name for i in self.winners) + '，各得 1 枚好感。')
            spies = [i for i in alive if 0 in self.players[i].discards]
            if len(spies) == 1:
                self.players[spies[0]].score += 1
                self.say(f'{self.players[spies[0]].name} 獲得間諜額外好感 +1。')
            self.champions = [i for i, p in enumerate(self.players) if p.score >= self.goal]
            self.stage = 'match_end' if self.champions else 'round_end'
            self.deadline = 0
            if self.champions:
                self.say('整場優勝：' + '、'.join(self.players[i].name for i in self.champions))
            return
        self.turn = (self.turn + 1) % len(self.players)
        while not self.current.alive:
            self.turn = (self.turn + 1) % len(self.players)
        self.begin_turn()
    def auto_action(self):
        """Simple non-cheating AI: own hand and public state only."""
        if self.phase == 'play':
            legal = self.legal_cards()
            chosen = min(legal, key=lambda i: self.current.hand[i])
            return 'play', chosen
        if self.phase == 'target':
            ts = self.targets(self.pending['card'])
            others = [i for i in ts if i != self.turn]
            return 'target', random.choice(others or ts)
        if self.phase == 'guess':
            seen = self.exposed + self.current.hand + [v for p in self.players for v in p.discards]
            options = [v for v in range(10) if v != 1]
            weights = [max(0, COUNTS[v] - seen.count(v)) for v in options]
            return 'guess', random.choices(options, weights=weights if sum(weights) else None)[0]
        if self.phase == 'keep':
            return 'keep', max(range(len(self.current.hand)), key=lambda i: self.current.hand[i])
        return 'order', 0
