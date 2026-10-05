import json
import os
import sqlite3
import time
import secrets
from pathlib import Path
from engine import Game

class Store:
    def __init__(self, path=None):
        path = path or os.getenv('DATA_PATH', 'data/games.sqlite3')
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS games (chat_id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS choices (token TEXT PRIMARY KEY, chat_id INTEGER, gid TEXT, uid INTEGER, rev INTEGER, action TEXT, value INTEGER, expires REAL, done INTEGER DEFAULT 0)')
    def save(self, game):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO games VALUES (?,?)', (game.chat_id, json.dumps(game.dumps(), ensure_ascii=False)))
    def load(self):
        return {cid: Game.loads(json.loads(body)) for cid, body in self.db.execute('SELECT chat_id,body FROM games')}
    def delete(self, cid):
        with self.db:
            self.db.execute('DELETE FROM games WHERE chat_id=?', (cid,))
            self.db.execute('DELETE FROM choices WHERE chat_id=?', (cid,))
    def get_meta(self,key,default=None):
        r=self.db.execute('SELECT body FROM metadata WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else default
    def set_meta(self,key,value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',(key,json.dumps(value)))
    def ticket(self,g,uid,action,value):
        now=time.time()
        with self.db:
            self.db.execute('DELETE FROM choices WHERE expires<?',(now-3600,))
            row=self.db.execute('SELECT token FROM choices WHERE chat_id=? AND gid=? AND uid=? AND rev=? AND action=? AND value=? AND expires>? AND done=0',
                                (g.chat_id,g.gid,uid,g.rev,action,value,now)).fetchone()
            if row:return row[0]
            token=secrets.token_urlsafe(18)
            self.db.execute('INSERT INTO choices VALUES (?,?,?,?,?,?,?,?,0)',(token,g.chat_id,g.gid,uid,g.rev,action,value,now+300))
            return token
    def choice(self,token):
        row=self.db.execute('SELECT chat_id,gid,uid,rev,action,value,expires,done FROM choices WHERE token=?',(token,)).fetchone()
        return dict(zip(('chat_id','gid','uid','rev','action','value','expires','done'),row)) if row else None
    def commit_choice(self,g,token):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO games VALUES (?,?)',(g.chat_id,json.dumps(g.dumps(),ensure_ascii=False)))
            self.db.execute('UPDATE choices SET done=1 WHERE token=?',(token,))
